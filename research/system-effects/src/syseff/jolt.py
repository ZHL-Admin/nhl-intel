"""Jolt addendum — event-time study of the new-coach on-ice result bump (F14).

Pre-registered in reports/registration_jolt.md (thresholds fixed before results). Observational.
Question: is the +0.004 score-close xG-share new-coach bump EFFORT (fades on an event-time curve),
REVERSION (firing at a low ebb → mean regression), or NEITHER?

Design: for each Cohort C change, the team's 5v5 score-close on-ice xG share in event-time bins
around τ=0 (new coach's first game). Compared to a MATCHED-TROUGH PLACEBO — no-change team-seasons
at their own trailing-xG trough — to separate a genuine coaching bump from ordinary post-trough
recovery. All inputs frozen to data/parquet/frozen_eval_jolt/ before metrics. Seed 20260711.
"""
from __future__ import annotations

import json

import numpy as np
import polars as pl

from . import config, context as C, phase2 as P2, regime_ledger as R

FROZEN = config.PARQUET / "frozen_eval_jolt"
SEASONS = config.SEASONS_ALL
_SY = {s: 2010 + i for i, s in enumerate(SEASONS)}
BINS = [("pre_-20_-11", -20, -11), ("pre_-10_-1", -10, -1),
        ("post_+1_+10", 1, 10), ("post_+11_+20", 11, 20), ("post_+21_+40", 21, 40)]
POST_MID = {"post_+1_+10": 5.5, "post_+11_+20": 15.5, "post_+21_+40": 30.5}


# ---------------------------------------------------------------- per-game team score-close xG
def _team_game_close(seasons):
    frames = []
    for s in seasons:
        tg = C.build_team_game_xg(s).group_by("game_id", "team_id").agg(
            xgf_c=pl.col("xgf_close").sum(), xga_c=pl.col("xga_close").sum())
        frames.append(tg.with_columns(season_label=pl.lit(s)))
    return pl.concat(frames)


def _share(games_df):
    f = float(games_df["xgf_c"].sum()); a = float(games_df["xga_c"].sum())
    return f / (f + a) if (f + a) > 0 else None


def _bin_share(tg_team: pl.DataFrame, tau_of: dict):
    """tg_team: team's games (game_id, xgf_c, xga_c). tau_of: game_id -> τ. Returns per-bin share."""
    out = {}
    d = tg_team.with_columns(tau=pl.col("game_id").replace_strict(tau_of, default=None, return_dtype=pl.Int64))
    for name, lo, hi in BINS:
        sub = d.filter((pl.col("tau") >= lo) & (pl.col("tau") <= hi))
        out[name] = {"share": _share(sub), "n": sub.height}
    return out


def _team_season_share(tgc, team, season):
    d = tgc.filter((pl.col("team_id") == team) & (pl.col("season_label") == season))
    return _share(d) if d.height else None


# ---------------------------------------------------------------- assembly (freeze)
def assemble(write: bool = True):
    tgc = _team_game_close(SEASONS)
    gc = R.assemble_game_coaches(); tg = R.to_team_games(gc)
    changes = P2.cohort_C_changes(tg)
    raw = R.build_ledger(tg.filter(pl.col("coach").is_not_null()))
    raw_annot, _ = R.consolidate_ledger(raw, k=4)
    reg = P2.consolidated_regime_games(tg, raw_annot)

    # ---- real changes: event-time bins + baseline
    real = []
    for c in changes:
        team = c["team_id"]; S = c["season"]
        pre = sorted(set(c["old_games"])); post = sorted(set(c["new_games"]))
        tau = {}
        for i, g in enumerate(pre):        # last pre game = -1
            tau[g] = -(len(pre) - i)
        for i, g in enumerate(post):       # first post game = +1
            tau[g] = i + 1
        tt = tgc.filter((pl.col("team_id") == team) & pl.col("game_id").is_in(list(tau)))
        bins = _bin_share(tt, tau)
        prev_season = SEASONS[SEASONS.index(S) - 1] if SEASONS.index(S) > 0 else None
        base = _team_season_share(tgc, team, prev_season) if prev_season else None
        if base is None:
            base = _team_season_share(tgc, team, S)
        real.append({"team_id": team, "season": S, "baseline": base,
                     **{f"bin__{k}__share": v["share"] for k, v in bins.items()},
                     **{f"bin__{k}__n": v["n"] for k, v in bins.items()}})

    # pre-window range of the real changes (to match placebo troughs)
    pre_levels = [r["bin__pre_-10_-1__share"] for r in real if r["bin__pre_-10_-1__share"] is not None]
    lo_pre, hi_pre = float(np.percentile(pre_levels, 5)), float(np.percentile(pre_levels, 95))

    # ---- matched-trough placebo: one-regime team-seasons at a firing-comparable trough.
    # Two constructions: DEEPEST (as literally registered) and MATCHED-DEPTH (the intended control:
    # sample a pseudo-τ0 whose trailing-10 level matches the real pre-window range WITHOUT taking the
    # season minimum). The deepest version has a regression-to-minimum bias (its pre-level lands below
    # the real pre-level), so the matched-depth version is the valid control; both are reported.
    rng = np.random.default_rng(config.SEED)
    plac_deep, plac_fair = [], []
    for row in P2.one_regime_team_seasons(reg).iter_rows(named=True):
        team = row["team_id"]; S = row["season_label"]
        g = (reg.filter((pl.col("team_id") == team) & (pl.col("season_label") == S))
             .sort("game_id")["game_id"].unique(maintain_order=True).to_list())
        if len(g) < 45:
            continue
        tt = tgc.filter((pl.col("team_id") == team) & pl.col("game_id").is_in(g)).sort("game_id")
        sbg = {r["game_id"]: (r["xgf_c"], r["xga_c"]) for r in tt.to_dicts()}
        trailing = {}
        for j in range(20, len(g) - 10):
            f = sum(sbg.get(x, (0, 0))[0] for x in g[j - 10:j]); a = sum(sbg.get(x, (0, 0))[1] for x in g[j - 10:j])
            trailing[j] = f / (f + a) if (f + a) > 0 else None
        prev_season = SEASONS[SEASONS.index(S) - 1] if SEASONS.index(S) > 0 else None
        base = _team_season_share(tgc, team, prev_season) if prev_season else _team_season_share(tgc, team, S)

        def emit(j):
            tau = {gid: i - j for i, gid in enumerate(g[:j])}
            tau.update({gid: i + 1 for i, gid in enumerate(g[j:])})
            b = _bin_share(tt, tau)
            return {"team_id": team, "season": S, "baseline": base,
                    **{f"bin__{k}__share": v["share"] for k, v in b.items()},
                    **{f"bin__{k}__n": v["n"] for k, v in b.items()}}

        # deepest (registered)
        cand = [(j, t) for j, t in trailing.items() if t is not None]
        if cand:
            jd, td = min(cand, key=lambda x: x[1])
            if lo_pre <= td <= hi_pre:
                plac_deep.append(emit(jd))
        # matched-depth (valid control): sample one index whose trailing level is in range
        inrange = [j for j, t in trailing.items() if t is not None and lo_pre <= t <= hi_pre]
        if inrange:
            plac_fair.append(emit(int(rng.choice(inrange))))

    realdf = pl.DataFrame(real); deepdf = pl.DataFrame(plac_deep); fairdf = pl.DataFrame(plac_fair)
    if write:
        FROZEN.mkdir(parents=True, exist_ok=True)
        realdf.write_parquet(FROZEN / "real_changes_eventtime.parquet")
        deepdf.write_parquet(FROZEN / "placebo_deepest_eventtime.parquet")
        fairdf.write_parquet(FROZEN / "placebo_matched_depth_eventtime.parquet")
        _freeze_target_reliability(tgc, changes)
    return realdf, fairdf, deepdf


def _freeze_target_reliability(tgc, changes):
    """Split-half reliability of the outcome as evaluated: per change, post-window (τ+1..+40) team
    xG share on odd vs even games."""
    gc = R.assemble_game_coaches(); tg = R.to_team_games(gc)
    rows = []
    for c in changes:
        team = c["team_id"]; post = sorted(set(c["new_games"]))[:40]
        tt = tgc.filter((pl.col("team_id") == team) & pl.col("game_id").is_in(post)).sort("game_id")
        gg = tt["game_id"].to_list()
        odd = tt.filter(pl.col("game_id").is_in(gg[0::2])); even = tt.filter(pl.col("game_id").is_in(gg[1::2]))
        rows.append({"team_id": team, "season": c["season"], "xg_odd": _share(odd), "xg_even": _share(even)})
    pl.DataFrame(rows).write_parquet(FROZEN / "target_splithalf.parquet")


# ---------------------------------------------------------------- metrics
def _mean_ci(vals, n_boot=2000, seed=config.SEED):
    v = np.array([x for x in vals if x is not None])
    if len(v) < 3:
        return None
    rng = np.random.default_rng(seed)
    boot = [v[rng.integers(0, len(v), len(v))].mean() for _ in range(n_boot)]
    return {"mean": float(v.mean()), "ci95": [float(np.percentile(boot, 2.5)), float(np.percentile(boot, 97.5))], "n": int(len(v))}


def run() -> dict:
    real, plac, deep = assemble()   # plac = matched-depth (valid control); deep = deepest (disclosed)

    # (1) event-time curve (real)
    curve = {name: _mean_ci(real[f"bin__{name}__share"].to_list()) for name, _, _ in BINS}
    # (2) trough test: pre-change [-10..-1] minus prior-season baseline
    dev = [(r["bin__pre_-10_-1__share"] - r["baseline"])
           for r in real.to_dicts() if r["bin__pre_-10_-1__share"] is not None and r["baseline"] is not None]
    trough = _mean_ci(dev)
    # (3) REAL recovery alone (post bin minus pre-window) — the clean bump, no placebo needed
    real_recovery = {name: _mean_ci(_recovery(real, name)) for name in POST_MID}
    # (4) excess over the MATCHED-DEPTH placebo (recovery DiD); deepest placebo reported for disclosure
    excess = {name: _diff_ci(_recovery(real, name), _recovery(plac, name)) for name in POST_MID}
    excess_deepest = {name: _diff_ci(_recovery(real, name), _recovery(deep, name)) for name in POST_MID}
    # (5) fade slope on REAL recovery alone (does the bump decay?) — the effort signature
    fade = _fade_real_recovery(real)

    era = _era_split(real, plac)
    influence = _loo_excess(real, plac)
    ceiling = _noise_ceiling()
    decision = _decide(trough, excess, fade)

    out = {"seed": config.SEED, "n_changes": real.height,
           "n_placebo_matched_depth": plac.height, "n_placebo_deepest": deep.height,
           "placebo_pre_level": {"real": round(float(real["bin__pre_-10_-1__share"].mean()), 4),
                                 "matched_depth": round(float(plac["bin__pre_-10_-1__share"].mean()), 4),
                                 "deepest_biased": round(float(deep["bin__pre_-10_-1__share"].mean()), 4)},
           "event_time_curve_real": curve, "trough_vs_baseline": trough,
           "real_recovery_from_trough": real_recovery,
           "excess_over_matched_depth_placebo": excess,
           "excess_over_deepest_placebo_DISCLOSED_biased": excess_deepest,
           "fade_slope_real_recovery": fade,
           "era_split": era, "influence": influence, "noise_ceiling": ceiling,
           "decision": decision}
    (config.REPORTS / "phase5_jolt_analysis.json").write_text(json.dumps(out, indent=2, default=str))
    return out


def _fade_real_recovery(real):
    """Fade of the REAL bump: regress per-change recovery (post bin minus pre-window) on event-time
    midpoint. Effort => significantly negative slope from a positive intercept; reversion => flat."""
    xs, ys = [], []
    for r in real.to_dicts():
        pre = r.get("bin__pre_-10_-1__share")
        for name, mid in POST_MID.items():
            s = r.get(f"bin__{name}__share")
            if s is not None and pre is not None:
                xs.append(mid); ys.append(s - pre)
    xs = np.array(xs); ys = np.array(ys)
    X = np.column_stack([np.ones(len(xs)), xs])
    beta, *_ = np.linalg.lstsq(X, ys, rcond=None)
    resid = ys - X @ beta; dof = max(1, len(ys) - 2)
    se = float(np.sqrt((resid @ resid) / dof * np.linalg.pinv(X.T @ X)[1, 1]))
    return {"slope_per_game": round(float(beta[1]), 6), "intercept": round(float(beta[0]), 5),
            "se": round(se, 6), "t": round(float(beta[1]) / se, 2) if se > 0 else None, "n": int(len(ys))}


def _diff_ci(a, b, n_boot=2000, seed=config.SEED):
    av = np.array([x for x in a if x is not None]); bv = np.array([x for x in b if x is not None])
    if len(av) < 3 or len(bv) < 3:
        return None
    rng = np.random.default_rng(seed)
    boot = [av[rng.integers(0, len(av), len(av))].mean() - bv[rng.integers(0, len(bv), len(bv))].mean()
            for _ in range(n_boot)]
    return {"diff": float(av.mean() - bv.mean()), "ci95": [float(np.percentile(boot, 2.5)), float(np.percentile(boot, 97.5))],
            "n_real": int(len(av)), "n_placebo": int(len(bv))}


def _recovery(df, name):
    """Per-unit recovery = post-bin share minus the pre-window [-10..-1] level."""
    out = []
    for r in df.to_dicts():
        post, pre = r.get(f"bin__{name}__share"), r.get("bin__pre_-10_-1__share")
        out.append(post - pre if post is not None and pre is not None else None)
    return out


def _fade_slope_recovery(real, plac):
    # placebo mean recovery per post bin; real change's excess recovery = its recovery - that mean
    pmean = {name: np.nanmean([x for x in _recovery(plac, name) if x is not None]) for name in POST_MID}
    xs, ys = [], []
    for r in real.to_dicts():
        pre = r.get("bin__pre_-10_-1__share")
        for name, mid in POST_MID.items():
            s = r.get(f"bin__{name}__share")
            if s is not None and pre is not None:
                xs.append(mid); ys.append((s - pre) - pmean[name])
    xs = np.array(xs); ys = np.array(ys)
    X = np.column_stack([np.ones(len(xs)), xs])
    beta, *_ = np.linalg.lstsq(X, ys, rcond=None)
    resid = ys - X @ beta; dof = max(1, len(ys) - 2)
    se = float(np.sqrt((resid @ resid) / dof * np.linalg.pinv(X.T @ X)[1, 1]))
    return {"slope_per_game": round(float(beta[1]), 6), "intercept": round(float(beta[0]), 5),
            "se": round(se, 6), "t": round(float(beta[1]) / se, 2) if se > 0 else None, "n": int(len(ys))}


def _era_split(real, plac):
    out = {}
    for lab, lo, hi in (("2010-17", 2010, 2016), ("2018-26", 2017, 2025)):
        rr = real.filter(pl.col("season").replace_strict(_SY, return_dtype=pl.Int64).is_between(lo, hi))
        pp = plac.filter(pl.col("season").replace_strict(_SY, return_dtype=pl.Int64).is_between(lo, hi))
        out[lab] = {"n_changes": rr.height,
                    "excess_recovery_post_+1_+10": _diff_ci(_recovery(rr, "post_+1_+10"), _recovery(pp, "post_+1_+10"))}
    return out


def _loo_excess(real, plac):
    prec = _recovery(plac, "post_+1_+10")
    rrec = _recovery(real, "post_+1_+10")
    base = _diff_ci(rrec, prec)
    vals = []
    for i in range(len(rrec)):
        sub = [rrec[j] for j in range(len(rrec)) if j != i]
        d = _diff_ci(sub, prec, n_boot=1)
        if d:
            vals.append(d["diff"])
    return {"base_excess": base["diff"] if base else None,
            "loo_min": round(float(np.min(vals)), 5), "loo_max": round(float(np.max(vals)), 5)}


def _noise_ceiling():
    sh = pl.read_parquet(FROZEN / "target_splithalf.parquet").filter(
        pl.col("xg_odd").is_not_null() & pl.col("xg_even").is_not_null())
    r = float(np.corrcoef(sh["xg_odd"].to_numpy(), sh["xg_even"].to_numpy())[0, 1])
    return {"n": sh.height, "post_window_splithalf_r": round(r, 4),
            "spearman_brown": round(2 * r / (1 + r), 4)}


def _decide(trough, excess, fade):
    trough_sig = trough is not None and trough["ci95"][1] < 0     # pre-change significantly below baseline
    e1 = excess["post_+1_+10"]
    excess_sig = e1 is not None and (e1["ci95"][0] > 0 or e1["ci95"][1] < 0)
    excess_pos = e1 is not None and e1["ci95"][0] > 0
    fade_neg = fade["t"] is not None and fade["t"] < -1.96
    if excess_pos and fade_neg:
        v = "EFFORT"
    elif trough_sig and (e1 is not None and e1["ci95"][0] <= 0 <= e1["ci95"][1]):
        v = "REVERSION"
    elif not trough_sig and not excess_sig:
        v = "NEITHER"
    else:
        v = "MIXED"
    return {"trough_significant": bool(trough_sig), "excess_+1_+10_significant": bool(excess_sig),
            "excess_+1_+10_positive": bool(excess_pos), "fade_slope_negative": bool(fade_neg), "verdict": v}


if __name__ == "__main__":
    r = run()
    print("changes:", r["n_changes"], "placebo matched-depth:", r["n_placebo_matched_depth"])
    print("trough vs baseline:", r["trough_vs_baseline"]["mean"], r["trough_vs_baseline"]["ci95"])
    print("excess +1..+10 (vs matched-depth):", r["excess_over_matched_depth_placebo"]["post_+1_+10"])
    print("fade slope (real recovery) t:", r["fade_slope_real_recovery"]["t"])
    print("VERDICT:", r["decision"]["verdict"])
