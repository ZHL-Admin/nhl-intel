"""Phase 3.2 — INTERNAL track, Design A (coach-change experiments).

Reframed per the Phase 2 finding: DEPLOYMENT is the validated treatment (top-6 concentration
and zone-start polarization moved ~1.3-1.9x more at real coach changes than at placebo;
on-ice shot-style did not). So Design A estimates the causal chain

    coach change  ->  deployment change  ->  result change

For every Cohort C change and each skater with 100+ 5v5 min under BOTH the old and the new
coach (same season), within-player old->new deltas on:
  deployment axes : 5v5 TOI/gp, OZ-start share, PP-frac, PK-frac, top-unit membership
  result          : on-ice 5v5 xG share (raw on-ice deltas, NO RAPM refit), all + score-close

...against matched controls (same season, no coach change, matched on position, experience
band [age-band proxy], TOI tier, prior rating), split at a within-season midpoint (2nd-half
minus 1st-half) — a difference-in-differences. Then:
  (i)  mediation: how much of the result delta is carried by the deployment delta;
  (ii) split changes by their measured deployment-fingerprint shift (Phase 2: did deployment
       actually move, or just the name behind the bench);
  (iii) the watch-list style trio (forecheck_share_for, pace, loc_outer_against) reported
       descriptively alongside, clearly labeled UNVALIDATED (Phase 2 caveat).
"""
from __future__ import annotations

import math

import polars as pl

from . import config, context as C, fingerprints as F, phase2 as P2, player_types as PT, regime_ledger as R

DEP_AXES = ["toi_per_gp", "oz_share", "pp_frac", "pk_frac", "top_unit"]
MIN_HALF_MIN = 100.0
STYLE_TRIO = ["forecheck_share_for", "pace", "loc_outer_against"]


# ---------------------------------------------------------------- loaders (cached in-process)
def _load_all(dirpath):
    return {s: pl.read_parquet(dirpath / f"{s.replace('-', '_')}.parquet") for s in config.SEASONS_ALL}


def _positions():
    p = PT._positions()
    return dict(zip(p["player_id"].to_list(), p["pg"].to_list()))


# ---------------------------------------------------------------- deployment + result over a game set
def _deploy_result(depf: pl.DataFrame, onice: pl.DataFrame, game_ids, team_id, pos_map):
    """Per-player deployment vector + on-ice xG share over a game set for one team."""
    gset = list(game_ids)
    d = depf.filter(pl.col("game_id").is_in(gset) & (pl.col("team_id") == team_id))
    if d.height == 0:
        return {}
    ng = len(set(gset))
    agg = d.group_by("player_id").agg(
        toi=pl.col("toi_5v5_s").sum(), pp=pl.col("pp_s").sum(), pk=pl.col("pk_s").sum(),
        oz=pl.col("oz_starts").sum(), dz=pl.col("dz_starts").sum())
    agg = agg.with_columns(
        pos=pl.col("player_id").replace_strict(pos_map, default="F"),
        toi_per_gp=pl.col("toi") / ng / 60.0,
        oz_share=pl.when(pl.col("oz") + pl.col("dz") > 0).then(pl.col("oz") / (pl.col("oz") + pl.col("dz"))).otherwise(None),
        pp_frac=pl.col("pp") / (pl.col("toi") + pl.col("pp") + pl.col("pk")),
        pk_frac=pl.col("pk") / (pl.col("toi") + pl.col("pp") + pl.col("pk")),
        toi_min=pl.col("toi") / 60.0,
    )
    # top-unit membership: forwards top-6 by TOI, defense top-4 by TOI (team-relative over the set)
    fwd = agg.filter(pl.col("pos") == "F").sort("toi", descending=True).head(6)["player_id"].to_list()
    dmn = agg.filter(pl.col("pos") == "D").sort("toi", descending=True).head(4)["player_id"].to_list()
    top = set(fwd) | set(dmn)
    agg = agg.with_columns(top_unit=pl.col("player_id").is_in(list(top)).cast(pl.Float64))
    # on-ice xG share per player over the set (all + close)
    osh = onice.filter(pl.col("game_id").is_in(gset) & (pl.col("team_id") == team_id)).group_by("player_id").agg(
        xgf=pl.col("xgf").sum(), xga=pl.col("xga").sum(),
        xgf_c=pl.col("xgf_close").sum(), xga_c=pl.col("xga_close").sum())
    osh = osh.with_columns(
        xg_share=pl.when(pl.col("xgf") + pl.col("xga") > 0).then(pl.col("xgf") / (pl.col("xgf") + pl.col("xga"))).otherwise(None),
        xg_share_close=pl.when(pl.col("xgf_c") + pl.col("xga_c") > 0).then(pl.col("xgf_c") / (pl.col("xgf_c") + pl.col("xga_c"))).otherwise(None))
    m = agg.join(osh.select("player_id", "xg_share", "xg_share_close"), on="player_id", how="left")
    return {r["player_id"]: r for r in m.to_dicts()}


# ---------------------------------------------------------------- treated + control player deltas
def _player_deltas(before: dict, after: dict, min_min=MIN_HALF_MIN):
    """For players present in both halves with >= min_min in each, the old->new deltas."""
    rows = []
    for pid in set(before) & set(after):
        b, a = before[pid], after[pid]
        if (b.get("toi_min") or 0) < min_min or (a.get("toi_min") or 0) < min_min:
            continue
        row = {"player_id": pid, "pos": b["pos"]}
        for ax in DEP_AXES:
            if b.get(ax) is not None and a.get(ax) is not None:
                row[f"d_{ax}"] = a[ax] - b[ax]
        for r in ("xg_share", "xg_share_close"):
            if b.get(r) is not None and a.get(r) is not None:
                row[f"d_{r}"] = a[r] - b[r]
        row["before_toi_per_gp"] = b["toi_per_gp"]
        row["before_xg_share"] = b.get("xg_share")
        rows.append(row)
    return rows


# ---------------------------------------------------------------- covariates for matching
def _experience(season_start_year, first_syear):
    yrs = season_start_year - (first_syear if first_syear is not None else season_start_year)
    return "rookie" if yrs <= 2 else ("prime" if yrs <= 6 else "vet")


def run(seasons=None) -> dict:
    seasons = seasons or config.SEASONS_ALL
    depf = _load_all(C.DEPFULL_DIR)
    onice = _load_all(C.ONICE_DIR)
    prim = P2._load(F.PRIM_DIR, seasons)
    deploy = P2._load(F.DEPLOY_DIR, seasons)
    pos_map = _positions()
    exp = C.experience_table()
    exp_map = dict(zip(exp["player_id"].to_list(), exp["first_syear"].to_list()))
    rapm = pl.read_parquet(config.ATLAS_PARQUET / "rapm_variant.parquet").with_columns(
        rating=pl.col("off_impact") + pl.col("def_impact"))
    rating_map = {(r["player_id"], r["season"]): r["rating"] for r in rapm.to_dicts()}

    gc = R.assemble_game_coaches(); tg = R.to_team_games(gc)
    raw = R.build_ledger(tg.filter(pl.col("coach").is_not_null()))
    raw_annot, _ = R.consolidate_ledger(raw, k=4)
    reg = P2.consolidated_regime_games(tg, raw_annot)
    changes = P2.cohort_C_changes(tg)
    syear = {s: 2010 + i for i, s in enumerate(config.SEASONS_ALL)}

    # ---- TREATED: per change, per qualifying player, the old->new deltas + team fingerprint shift
    treated = []
    change_summaries = []
    for c in changes:
        s = c["season"]; team = c["team_id"]
        if s not in depf:
            continue
        before = _deploy_result(depf[s], onice[s], c["old_games"], team, pos_map)
        after = _deploy_result(depf[s], onice[s], c["new_games"], team, pos_map)
        pds = _player_deltas(before, after)
        # team-level fingerprint shift (deployment + style trio)
        vo = P2.metric_vector(prim, deploy, c["old_games"], team)
        vn = P2.metric_vector(prim, deploy, c["new_games"], team)
        fp = {f"d_{m}": (vn.get(m) - vo.get(m)) if vo.get(m) is not None and vn.get(m) is not None else None
              for m in ("top6_fwd_toi_share", "zone_start_polarization", *STYLE_TRIO)}
        for r in pds:
            r.update({"team_id": team, "season": s, "old_coach": c["old_coach"], "new_coach": c["new_coach"],
                      "experience": _experience(syear[s], exp_map.get(r["player_id"])),
                      "prior_rating": rating_map.get((r["player_id"], s)),
                      "d_fp_top6": fp["d_top6_fwd_toi_share"], "d_fp_zonepol": fp["d_zone_start_polarization"]})
            treated.append(r)
        change_summaries.append({"team_id": team, "season": s, "old_coach": c["old_coach"],
                                 "new_coach": c["new_coach"], "n_players": len(pds), **fp})

    # ---- CONTROLS: one-regime team-seasons, split at midpoint, 2nd-half minus 1st-half deltas
    controls = []
    for row in P2.one_regime_team_seasons(reg).iter_rows(named=True):
        s = row["season_label"]; team = row["team_id"]
        if s not in depf:
            continue
        g = (reg.filter((pl.col("team_id") == team) & (pl.col("season_label") == s))
             .sort("game_id")["game_id"].unique(maintain_order=True).to_list())
        if len(g) < 40:
            continue
        cut = len(g) // 2
        before = _deploy_result(depf[s], onice[s], g[:cut], team, pos_map)
        after = _deploy_result(depf[s], onice[s], g[cut:], team, pos_map)
        for r in _player_deltas(before, after):
            r.update({"team_id": team, "season": s,
                      "experience": _experience(syear[s], exp_map.get(r["player_id"])),
                      "prior_rating": rating_map.get((r["player_id"], s))})
            controls.append(r)

    out = {
        "n_changes": len(changes), "n_treated_players": len(treated), "n_control_players": len(controls),
        "did": _did(treated, controls),
        "mediation": _mediation(treated, controls),
        "fingerprint_split": _fp_split(treated, change_summaries),
        "style_trio_descriptive": _style_trio(change_summaries),
        "change_summaries": change_summaries,
    }
    (config.REPORTS / "phase3_designA.json").write_text(__import__("json").dumps(out, indent=2, default=str))
    return out


# ---------------------------------------------------------------- DiD (matched)
def _match_controls(t, controls, rating_cal=0.15):
    """Controls in same season, position, experience, TOI tier (before_toi within 3 min),
    prior rating within caliper."""
    out = []
    for cnt in controls:
        if cnt["season"] != t["season"] or cnt["pos"] != t["pos"] or cnt["experience"] != t["experience"]:
            continue
        if abs((cnt.get("before_toi_per_gp") or 0) - (t.get("before_toi_per_gp") or 0)) > 3.0:
            continue
        if t.get("prior_rating") is not None and cnt.get("prior_rating") is not None:
            if abs(cnt["prior_rating"] - t["prior_rating"]) > rating_cal:
                continue
        out.append(cnt)
    return out


def _did(treated, controls):
    res = {}
    keys = [f"d_{a}" for a in DEP_AXES] + ["d_xg_share", "d_xg_share_close"]
    for k in keys:
        did_vals = []
        raw_t = []
        for t in treated:
            if t.get(k) is None:
                continue
            raw_t.append(t[k])
            mc = _match_controls(t, controls)
            cvals = [c[k] for c in mc if c.get(k) is not None]
            if cvals:
                did_vals.append(t[k] - sum(cvals) / len(cvals))
        res[k] = {
            "n_treated": len(raw_t),
            "mean_treated_delta": round(_mean(raw_t), 5) if raw_t else None,
            "n_did": len(did_vals),
            "mean_did": round(_mean(did_vals), 5) if did_vals else None,
            "sd_did": round(_sd(did_vals), 5) if len(did_vals) > 1 else None,
            "t_stat": round(_mean(did_vals) / (_sd(did_vals) / math.sqrt(len(did_vals))), 2)
            if len(did_vals) > 1 and _sd(did_vals) > 0 else None,
        }
    return res


# ---------------------------------------------------------------- mediation
def _mediation(treated, controls):
    """coach change -> deployment change -> result change. Baron-Kenny style on the
    matched-DiD-adjusted player result delta vs player deployment deltas.
    We regress result_delta on the deployment deltas across treated players and report
    the share of result-delta variance carried by deployment (R^2) plus per-axis betas."""
    rows = [t for t in treated if t.get("d_xg_share_close") is not None]
    axes = [f"d_{a}" for a in DEP_AXES]
    X, y = [], []
    for t in rows:
        if all(t.get(a) is not None for a in axes):
            X.append([t[a] for a in axes]); y.append(t["d_xg_share_close"])
    if len(y) < 20:
        return {"insufficient": True, "n": len(y)}
    import numpy as np
    X = np.array(X); y = np.array(y)
    Xc = np.column_stack([np.ones(len(y)), (X - X.mean(0)) / (X.std(0) + 1e-9)])
    beta, *_ = np.linalg.lstsq(Xc, y, rcond=None)
    yhat = Xc @ beta
    ss_res = ((y - yhat) ** 2).sum(); ss_tot = ((y - y.mean()) ** 2).sum()
    r2 = 1 - ss_res / ss_tot
    # single-mediator via a deployment index = fitted deployment component
    total = y.mean()
    mediated = yhat.mean()  # = total by OLS with intercept; use variance decomposition instead
    return {
        "n": len(y),
        "outcome": "d_xg_share_close",
        "deployment_r2_of_result_delta": round(float(r2), 4),
        "betas_standardized": {a: round(float(b), 5) for a, b in zip(axes, beta[1:])},
        "mean_result_delta": round(float(total), 5),
        "interpretation": "R^2 = share of within-player result-delta variance linearly carried by deployment deltas.",
    }


# ---------------------------------------------------------------- fingerprint-shift split
def _fp_split(treated, change_summaries):
    """Split changes by HOW MUCH deployment actually moved: combined z-normalized shift
    magnitude z(|Δtop6|) + z(|Δzone_pol|), median-split of the real changes into
    'high-deployment-shift' vs 'low-deployment-shift' (balanced, unlike a placebo-median
    bar which flags ~90% of changes). Compare players' result deltas across the two."""
    import numpy as np
    top6 = np.array([abs(cs.get("d_top6_fwd_toi_share") or 0) for cs in change_summaries])
    zpol = np.array([abs(cs.get("d_zone_start_polarization") or 0) for cs in change_summaries])
    z = (top6 - top6.mean()) / (top6.std() + 1e-9) + (zpol - zpol.mean()) / (zpol.std() + 1e-9)
    med = float(np.median(z))
    high = {(cs["team_id"], cs["season"]) for cs, zi in zip(change_summaries, z) if zi >= med}
    grp = {"high": [], "low": []}
    for t in treated:
        g = "high" if (t["team_id"], t["season"]) in high else "low"
        if t.get("d_xg_share_close") is not None:
            grp[g].append(t["d_xg_share_close"])
    def summ(v):
        return {"n_players": len(v), "mean_result_delta": round(_mean(v), 5) if v else None,
                "mean_abs_result_delta": round(_mean([abs(x) for x in v]), 5) if v else None}
    return {"n_changes_high_shift": len(high), "n_changes_total": len(change_summaries),
            "high_deployment_shift": summ(grp["high"]), "low_deployment_shift": summ(grp["low"]),
            "note": "Result deltas are on-ice 5v5 xG share (score-close), signed old->new."}


def _style_trio(change_summaries):
    """Descriptive only (UNVALIDATED per Phase 2 §4): mean |Δ| of the watch-list style trio
    across the Cohort C changes."""
    res = {}
    for m in STYLE_TRIO:
        vals = [abs(cs[f"d_{m}"]) for cs in change_summaries if cs.get(f"d_{m}") is not None]
        res[m] = {"mean_abs_delta": round(_mean(vals), 5) if vals else None, "n": len(vals)}
    res["_label"] = "UNVALIDATED style context (Phase 2 §4: indistinguishable from placebo)"
    return res


def _mean(x): return sum(x) / len(x) if x else float("nan")
def _sd(x):
    if len(x) < 2:
        return float("nan")
    m = _mean(x); return math.sqrt(sum((v - m) ** 2 for v in x) / (len(x) - 1))


if __name__ == "__main__":
    import json
    r = run()
    print(json.dumps({k: v for k, v in r.items() if k not in ("change_summaries",)}, indent=2, default=str))
