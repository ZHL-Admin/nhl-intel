"""Phase 5 — pre-registered validation, INTERNAL track only (5B removed with the killed track).

Pre-registration (thresholds fixed BEFORE any result is computed; all evaluation inputs frozen to
data/parquet/frozen_eval/ before metrics run):

5A Question: do deployment-system terms predict MOVERS beyond the Atlas rating?
  Cohort   : Atlas movers definition (movers_eval), all 15 pairs 2010-26.
  Target   : mean of dest-season (S+1) and follow-up (S+2) 5v5 on-ice xG share, where the player
             has 400+ PRORATED 5v5 min in both; players with only S+1 use S+1 alone (subgroup).
             Proration = toi_min * 82 / season_scheduled_games.
  Predictors:
    (i)  incumbent = Atlas variant RAPM alone, via a calibration offset a + b*q_S (q = off+def,
         origin-season S rating), refit clean per fold.
    (ii) variant + destination-deployment + type-by-deployment, where DESTINATION REGIME = the
         coach behind the destination bench AT SEASON START (season-start consolidated regime's
         deployment fingerprint), and PREDICTED ROLE = the player's origin-season (S) player-type
         held fixed. sys() coefficients come from Design B, refit clean per fold.
  Metrics  : MAE and Spearman, leave-one-season-pair-out; 1000-resample bootstrap CIs on (ii)-(i).
  Decision : SHIP if (ii) improves MAE over (i) by >=3% AND the CI excludes zero; INVESTIGATE at
             0-3% or CI spanning zero; KILL if no improvement.
  Contrast : same comparison on STAYERS (did not change teams), reported either way.
  Slices   : F/D, player-type, TOI tiers. Influence: jackknife + top-25-residual removal.
  Leakage  : Design B is otherwise fit on all seasons incl. eval pairs -> refit clean per fold
             EXCLUDING the held-out pair's target seasons {S+1, S+2}. RAPM is external/frozen.

5C Noise ceiling: split-half reliability of the target as evaluated; improvement vs its ceiling.
"""
from __future__ import annotations

import json

import numpy as np
import polars as pl

from . import (config, design_b as DB, fingerprints as F, phase2 as P2, player_types as PT,
               portability as PORT, regime_ledger as R, team_season as TS)

FROZEN = config.PARQUET / "frozen_eval"
MIN_PRORATED = 400.0
SEASONS = config.SEASONS_ALL


# ---------------------------------------------------------------- building blocks
def _sched_games():
    g = pl.read_parquet(config.ATLAS_PARQUET / "games.parquet",
                        columns=["season_label", "home_team_id", "away_team_id"])
    long = pl.concat([g.select("season_label", pl.col("home_team_id").alias("t")),
                      g.select("season_label", pl.col("away_team_id").alias("t"))])
    s = long.group_by("season_label", "t").len().group_by("season_label").agg(max_g=pl.col("len").max())
    return dict(zip(s["season_label"].to_list(), s["max_g"].to_list()))


def _target_table():
    """Per (player, season): 5v5 on-ice xG share + prorated 5v5 minutes."""
    sched = _sched_games()
    p5 = pl.read_parquet(config.ATLAS_PARQUET / "player_5v5.parquet").select(
        "player_id", "season_label", "xg_share", "toi_min")
    return p5.with_columns(
        prorated_min=pl.col("toi_min") * 82.0 / pl.col("season_label").replace_strict(sched, return_dtype=pl.Float64))


def _q_table():
    r = pl.read_parquet(config.ATLAS_PARQUET / "rapm_variant.parquet")
    return r.select("player_id", pl.col("season").alias("season_label"), q=pl.col("off_impact") + pl.col("def_impact"))


def _type_table():
    return pl.read_parquet(config.PARQUET / "player_types.parquet").select("player_id", "season_label", "type_id", "pg")


def _primary_team():
    o = pl.read_parquet(config.ATLAS_PARQUET / "player_season_team_onice.parquet")
    return o.sort("toi_s", descending=True).unique(["player_id", "season_label"], keep="first").select(
        "player_id", "season_label", "team_id")


def _season_start_regime_deploy():
    """Per (team, season): deployment fingerprint (top6, zone-pol) of the SEASON-START
    consolidated regime (the coach behind the bench at game 1)."""
    deploy = P2._load(F.DEPLOY_DIR, SEASONS)
    gc = R.assemble_game_coaches(); tg = R.to_team_games(gc)
    raw = R.build_ledger(tg.filter(pl.col("coach").is_not_null()))
    raw_annot, _ = R.consolidate_ledger(raw, k=4)
    reg = P2.consolidated_regime_games(tg, raw_annot)  # per team-game: consolidated_start_game_id, season_label
    rows = []
    for (season, team), sub in reg.group_by(["season_label", "team_id"]):
        sub = sub.sort("game_id")
        start_cons = sub["consolidated_start_game_id"][0]
        gids = sub.filter(pl.col("consolidated_start_game_id") == start_cons)["game_id"].unique().to_list()
        d = F.deployment_over(deploy, gids, team)
        rows.append({"season_label": season, "team_id": team,
                     "top6_fwd_toi_share": d.get("top6_fwd_toi_share"),
                     "zone_start_polarization": d.get("zone_start_polarization"),
                     "n_start_regime_games": len(gids)})
    return pl.DataFrame(rows)


# ---------------------------------------------------------------- assembly + freeze
def _next_season(s):
    i = SEASONS.index(s)
    return SEASONS[i + 1] if i + 1 < len(SEASONS) else None


def assemble(write: bool = True):
    tgt = _target_table(); q = _q_table(); typ = _type_table()
    prim = _primary_team(); startdep = _season_start_regime_deploy()
    mv = pl.read_parquet(config.ATLAS_PARQUET / "movers_eval.parquet").select("player_id", "pair").unique()

    def build_for(pairs_df, is_mover):
        out = []
        for r in pairs_df.iter_rows(named=True):
            pid = r["player_id"]; S = r["origin_season"]; D = r["dest_season"]; F2 = _next_season(D)
            td = tgt.filter((pl.col("player_id") == pid) & (pl.col("season_label") == D))
            if td.height == 0 or td["prorated_min"][0] < MIN_PRORATED:
                continue
            xg_d = td["xg_share"][0]
            tf = tgt.filter((pl.col("player_id") == pid) & (pl.col("season_label") == F2)) if F2 else None
            if tf is not None and tf.height and tf["prorated_min"][0] >= MIN_PRORATED:
                target = (xg_d + tf["xg_share"][0]) / 2.0; subgroup = "both"
            else:
                target = xg_d; subgroup = "s1_only"
            qs = q.filter((pl.col("player_id") == pid) & (pl.col("season_label") == S))
            ts = typ.filter((pl.col("player_id") == pid) & (pl.col("season_label") == S))
            dt = prim.filter((pl.col("player_id") == pid) & (pl.col("season_label") == D))
            if qs.height == 0 or ts.height == 0 or dt.height == 0:
                continue
            dteam = dt["team_id"][0]
            dep = startdep.filter((pl.col("team_id") == dteam) & (pl.col("season_label") == D))
            if dep.height == 0 or dep["top6_fwd_toi_share"][0] is None or dep["zone_start_polarization"][0] is None:
                continue
            out.append({"player_id": pid, "origin_season": S, "dest_season": D, "followup_season": F2,
                        "target": target, "subgroup": subgroup, "is_mover": is_mover,
                        "q_S": qs["q"][0], "type_S": ts["type_id"][0], "pos": ts["pg"][0], "dest_team": dteam,
                        "dest_top6": dep["top6_fwd_toi_share"][0], "dest_zonepol": dep["zone_start_polarization"][0],
                        "toi_min_dest": td["toi_min"][0]})
        return pl.DataFrame(out)

    movers = build_for(mv.with_columns(
        origin_season=pl.col("pair").str.split("->").list.first(),
        dest_season=pl.col("pair").str.split("->").list.last()), is_mover=True)

    # stayers: same primary team in S and D, present both, NOT a mover for that pair
    mover_keys = set(zip(movers["player_id"].to_list(), movers["dest_season"].to_list()))
    stay_rows = []
    for D in SEASONS[1:]:
        S = SEASONS[SEASONS.index(D) - 1]
        ps = prim.filter(pl.col("season_label") == S).select("player_id", pl.col("team_id").alias("team_S"))
        pd = prim.filter(pl.col("season_label") == D).select("player_id", pl.col("team_id").alias("team_D"))
        j = ps.join(pd, on="player_id", how="inner").filter(pl.col("team_S") == pl.col("team_D"))
        for pid in j["player_id"].to_list():
            if (pid, D) in mover_keys:
                continue
            stay_rows.append({"player_id": pid, "origin_season": S, "dest_season": D})
    stayers = build_for(pl.DataFrame(stay_rows), is_mover=False) if stay_rows else pl.DataFrame()

    if write:
        FROZEN.mkdir(parents=True, exist_ok=True)
        movers.write_parquet(FROZEN / "movers_eval_frame.parquet")
        stayers.write_parquet(FROZEN / "stayers_eval_frame.parquet")
        startdep.write_parquet(FROZEN / "season_start_regime_deploy.parquet")
        # freeze the target split-half inputs (odd/even games within target seasons) for 5C
        _freeze_target_splithalf(movers)
    return movers, stayers


def _freeze_target_splithalf(movers):
    """For 5C: per mover, the dest-season on-ice xG share computed on ODD vs EVEN games
    (from the onice primitive), so the target's split-half reliability can be evaluated."""
    from . import context as C
    rows = []
    for D, sub in movers.group_by("dest_season"):
        D = D[0] if isinstance(D, tuple) else D
        onice = pl.read_parquet(C.ONICE_DIR / f"{D.replace('-', '_')}.parquet")
        gids = sorted(onice["game_id"].unique().to_list())
        odd = set(gids[0::2]); even = set(gids[1::2])
        for pid in sub["player_id"].to_list():
            po = onice.filter((pl.col("player_id") == pid) & pl.col("game_id").is_in(list(odd)))
            pe = onice.filter((pl.col("player_id") == pid) & pl.col("game_id").is_in(list(even)))
            def sh(df):
                if df.height == 0:
                    return None
                s = df.sum(); f, a = float(s["xgf"][0]), float(s["xga"][0])
                return f / (f + a) if (f + a) > 0 else None
            rows.append({"player_id": pid, "dest_season": D, "xg_odd": sh(po), "xg_even": sh(pe)})
    pl.DataFrame(rows).write_parquet(FROZEN / "target_splithalf.parquet")


# ---------------------------------------------------------------- models (nested, refit clean per fold)
from sklearn.linear_model import Ridge  # noqa: E402

# Design: the INCUMBENT is Atlas RAPM calibrated to the ACTUAL task (target ~ q_S); (ii) is the
# nested model target ~ q_S + sys, where sys is the Design B deployment-system contribution
# (deployment + type x deployment) for the destination regime. The task coefficients (a,b,c) are
# fit on TRAIN movers; the held-out fold's sys is recomputed from a Design B refit EXCLUDING the
# held-out target seasons {S+1, S+2} (leakage-clean); the task model then predicts held-out.


def _syscoefs(d_all, exclude_seasons):
    d = d_all.filter(~pl.col("season_label").is_in(list(exclude_seasons)))
    q = d["q"].to_numpy(); y = d["xg_share"].to_numpy()
    A = np.column_stack([np.ones(len(q)), q]); off, *_ = np.linalg.lstsq(A, y, rcond=None)
    resid = y - A @ off
    X, cols = DB._design_matrix(d)
    m = Ridge(alpha=PORT.ALPHA).fit(X, resid)
    coef = dict(zip(cols, m.coef_))
    dep = d.select(TS.DEPLOY_AXES).to_numpy().astype(float)
    return coef, dep.mean(0), dep.std(0) + 1e-9


def _sys_feature(frame, coef, dep_mean, dep_std):
    out = np.zeros(frame.height)
    for i, r in enumerate(frame.iter_rows(named=True)):
        dep_z = (np.array([r["dest_top6"], r["dest_zonepol"]]) - dep_mean) / dep_std
        out[i] = PORT._sys_contrib(coef, r["type_S"], dep_z)
    return out


def _mae(p, t): return float(np.mean(np.abs(p - t)))
def _spearman(p, t):
    pr = np.argsort(np.argsort(p)); tr = np.argsort(np.argsort(t))
    pr = pr - pr.mean(); tr = tr - tr.mean()
    return float((pr * tr).sum() / np.sqrt((pr ** 2).sum() * (tr ** 2).sum()))


def loso_predict(frame, d_all):
    """Leave-one-season-pair-out nested prediction. INCUMBENT target~q_S vs (ii) target~q_S+sys;
    held-out sys is refit-clean (Design B excluding the fold's target seasons)."""
    N = frame.height
    q = frame["q_S"].to_numpy(); t = frame["target"].to_numpy()
    dest = frame["dest_season"].to_numpy()
    # sys feature from the FULL Design B (used only to fit the task coefficients on train folds)
    sys_full = _sys_feature(frame, *_syscoefs(d_all, set()))
    pi = np.full(N, np.nan); pii = np.full(N, np.nan)
    for D in frame["dest_season"].unique().to_list():
        excl = {D, _next_season(D)} - {None}
        test = dest == D; train = ~test
        # incumbent: target ~ q  (fit on train)
        Ai = np.column_stack([np.ones(train.sum()), q[train]])
        bi, *_ = np.linalg.lstsq(Ai, t[train], rcond=None)
        # full: target ~ q + sys_full  (fit on train)
        Af = np.column_stack([np.ones(train.sum()), q[train], sys_full[train]])
        bf, *_ = np.linalg.lstsq(Af, t[train], rcond=None)
        # held-out sys recomputed leakage-clean
        sub = frame.filter(pl.col("dest_season") == D)
        sys_clean = _sys_feature(sub, *_syscoefs(d_all, excl))
        pi[test] = bi[0] + bi[1] * q[test]
        pii[test] = bf[0] + bf[1] * q[test] + bf[2] * sys_clean
    return pi, pii


def _decision(imp_pct, ci_lo_diff):
    # ci_lo_diff = lower bound of (MAE_i - MAE_ii) bootstrap (improvement in MAE units)
    if imp_pct >= 3.0 and ci_lo_diff > 0:
        return "SHIP"
    if imp_pct <= 0.0:
        return "KILL"
    return "INVESTIGATE"


def _boot_ci(pi, pii, t, n=1000, seed=config.SEED):
    rng = np.random.default_rng(seed)
    diffs = []; imps = []
    N = len(t)
    for _ in range(n):
        s = rng.integers(0, N, N)
        mi = _mae(pi[s], t[s]); mii = _mae(pii[s], t[s])
        diffs.append(mi - mii); imps.append(100 * (mi - mii) / mi)
    return (float(np.percentile(diffs, 2.5)), float(np.percentile(diffs, 97.5)),
            float(np.percentile(imps, 2.5)), float(np.percentile(imps, 97.5)))


def evaluate(frame, d_all, label):
    t = frame["target"].to_numpy()
    pi, pii = loso_predict(frame, d_all)
    mae_i, mae_ii = _mae(pi, t), _mae(pii, t)
    imp_pct = 100 * (mae_i - mae_ii) / mae_i
    dlo, dhi, ilo, ihi = _boot_ci(pi, pii, t)
    res = {"label": label, "n": frame.height,
           "mae_incumbent": round(mae_i, 5), "mae_with_deployment": round(mae_ii, 5),
           "mae_improvement_pct": round(imp_pct, 3),
           "mae_diff_ci95": [round(dlo, 6), round(dhi, 6)],
           "improvement_pct_ci95": [round(ilo, 3), round(ihi, 3)],
           "spearman_incumbent": round(_spearman(pi, t), 4),
           "spearman_with_deployment": round(_spearman(pii, t), 4),
           "decision": _decision(imp_pct, dlo)}
    return res, pi, pii


# ---------------------------------------------------------------- slices, influence, ceiling
def slices(frame, pi, pii):
    t = frame["target"].to_numpy()
    out = {}
    def block(mask, name):
        if mask.sum() < 20:
            return
        ti, pii_, pi_ = t[mask], pii[mask], pi[mask]
        mi, mii = _mae(pi_, ti), _mae(pii_, ti)
        out[name] = {"n": int(mask.sum()), "mae_i": round(mi, 5), "mae_ii": round(mii, 5),
                     "improvement_pct": round(100 * (mi - mii) / mi, 2)}
    pos = frame["pos"].to_numpy()
    for p in ("F", "D"):
        block(pos == p, f"pos={p}")
    typ = frame["type_S"].to_numpy()
    for ty in sorted(set(typ)):
        block(typ == ty, f"type={ty}")
    toi = frame["toi_min_dest"].to_numpy()
    qs = np.quantile(toi, [0.33, 0.66])
    block(toi <= qs[0], "toi=low"); block((toi > qs[0]) & (toi <= qs[1]), "toi=mid"); block(toi > qs[1], "toi=high")
    for sg in ("both", "s1_only"):
        block((frame["subgroup"] == sg).to_numpy(), f"subgroup={sg}")
    return out


def influence(frame, pi, pii):
    t = frame["target"].to_numpy()
    base_i, base_ii = _mae(pi, t), _mae(pii, t)
    base_imp = 100 * (base_i - base_ii) / base_i
    N = len(t)
    # jackknife: leave-one-out improvement%
    jk = []
    for i in range(N):
        m = np.ones(N, bool); m[i] = False
        mi, mii = _mae(pi[m], t[m]), _mae(pii[m], t[m])
        jk.append(100 * (mi - mii) / mi)
    jk = np.array(jk)
    # top-25 (ii) residual removal
    res_ii = np.abs(pii - t)
    keep = np.argsort(res_ii)[:-25]
    mi, mii = _mae(pi[keep], t[keep]), _mae(pii[keep], t[keep])
    return {"base_improvement_pct": round(base_imp, 3),
            "jackknife_improvement_pct": {"min": round(float(jk.min()), 3), "max": round(float(jk.max()), 3),
                                          "sd": round(float(jk.std()), 4)},
            "top25_residual_removed_improvement_pct": round(100 * (mi - mii) / mi, 3),
            "top25_removed_n": int(len(keep))}


def noise_ceiling(frame, pi, pii):
    sh = pl.read_parquet(FROZEN / "target_splithalf.parquet")
    f = frame.join(sh, on=["player_id", "dest_season"], how="left").filter(
        pl.col("xg_odd").is_not_null() & pl.col("xg_even").is_not_null())
    xo, xe = f["xg_odd"].to_numpy(), f["xg_even"].to_numpy()
    r = np.corrcoef(xo, xe)[0, 1]
    r_sb = 2 * r / (1 + r)  # Spearman-Brown to full length
    t = frame["target"].to_numpy()
    def r2(p): return 1 - ((t - p) ** 2).sum() / ((t - t.mean()) ** 2).sum()
    return {"n_splithalf": f.height, "target_splithalf_r": round(float(r), 4),
            "target_reliability_spearman_brown": round(float(r_sb), 4),
            "r2_incumbent": round(float(r2(pi)), 4), "r2_with_deployment": round(float(r2(pii)), 4),
            "note": "reliability is the ceiling on predictable target variance; compare R^2 against it"}


def worst_misses(frame, pii, n=10):
    t = frame["target"].to_numpy(); res = pii - t
    order = np.argsort(-np.abs(res))[:n]
    names = PORT._names(); from .opponent import TEAM_ABBR
    rows = []
    for i in order:
        r = frame.row(int(i), named=True)
        rows.append({"player": names.get(r["player_id"], str(r["player_id"])),
                     "dest": f"{TEAM_ABBR.get(r['dest_team'], r['dest_team'])} {r['dest_season']}",
                     "type_S": r["type_S"], "target": round(r["target"], 3),
                     "pred_ii": round(float(pii[i]), 3), "residual": round(float(res[i]), 3),
                     "subgroup": r["subgroup"]})
    return rows


def run() -> dict:
    movers, stayers = assemble()
    d_all = DB.player_season_table()
    mres, mpi, mpii = evaluate(movers, d_all, "movers")
    sres, spi, spii = evaluate(stayers, d_all, "stayers")
    out = {"seed": config.SEED, "pre_registered": True,
           "movers": mres, "stayers_contrast": sres,
           "slices_movers": slices(movers, mpi, mpii),
           "influence_movers": influence(movers, mpi, mpii),
           "noise_ceiling_movers": noise_ceiling(movers, mpi, mpii),
           "worst_misses_movers": worst_misses(movers, mpii)}
    (config.REPORTS / "phase5_analysis.json").write_text(json.dumps(out, indent=2, default=str))
    return out


if __name__ == "__main__":
    r = run()
    print("MOVERS decision:", r["movers"]["decision"])
    print("  MAE i=%.5f ii=%.5f imp=%.2f%% CI%s" % (
        r["movers"]["mae_incumbent"], r["movers"]["mae_with_deployment"],
        r["movers"]["mae_improvement_pct"], r["movers"]["improvement_pct_ci95"]))
    print("  Spearman i=%.4f ii=%.4f" % (r["movers"]["spearman_incumbent"], r["movers"]["spearman_with_deployment"]))
    print("STAYERS imp=%.2f%%" % r["stayers_contrast"]["mae_improvement_pct"])
    print("ceiling:", r["noise_ceiling_movers"]["target_reliability_spearman_brown"])
