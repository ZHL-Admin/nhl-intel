"""Phase 5 addendum — the summer-install question (F12 scope; exploratory, observational with
roster adjustment, labeled as such).

F12 baseline (Phase 2): at the resolution of within-team, one-season MID-SEASON coach changes,
on-ice style behaved like a roster property (placebo), only deployment moved. This addendum asks
the F12 scope question: does style install across a SUMMER (a full offseason + camp) rather than
mid-season? Observational — coach-change summers also turn over more roster, so continuity is
controlled (S2) and the strong test is directional (S4).

Metric families (Phase 2 primitives; PK from the Phase 2 addendum):
  style      : pace, rush/cycle/forecheck/point-shot shares-for, rush/cycle shares-against,
               shot-location-against (inner/outer/point), forecheck pressure/60
  deployment : top-6 forward TOI share, zone-start polarization   (calibration; should clear)
  pk         : PK shot-location-against (inner/outer/point)

Seed 20260711. Report -> reports/phase5-summer-addendum.md.
"""
from __future__ import annotations

import json

import numpy as np
import polars as pl

from . import (config, context as C, fingerprints as F, phase2 as P2, regime_ledger as R)

STYLE = ["pace", "rush_share_for", "cycle_share_for", "forecheck_share_for", "point_shot_share_for",
         "rush_share_against", "cycle_share_against", "loc_inner_against", "loc_outer_against",
         "loc_point_against", "forecheck_pressure_per60"]
DEPLOY = ["top6_fwd_toi_share", "zone_start_polarization"]
PK = ["pk_loc_inner_against", "pk_loc_outer_against", "pk_loc_point_against"]
FAMILIES = {"style": STYLE, "deployment": DEPLOY, "pk": PK}
ALLM = STYLE + DEPLOY + PK
MIN_REGIME_GAMES = 20     # min in-season games for a boundary regime fingerprint
COACH_PRIOR_MIN = 40      # min games for an incoming coach's prior fingerprint
COACH_PRIOR_WINDOW = 3    # seasons back

SEASONS = config.SEASONS_ALL
_SY = {s: 2010 + i for i, s in enumerate(SEASONS)}


# ---------------------------------------------------------------- fingerprints
def _full_fp(prim, deploy, pk, game_ids, team):
    m = P2.metric_vector(prim, deploy, game_ids, team)
    m.update(F.pk_location(pk, game_ids, team))
    return {k: m.get(k) for k in ALLM}


def _load():
    prim = P2._load(F.PRIM_DIR, SEASONS)
    deploy = P2._load(F.DEPLOY_DIR, SEASONS)
    pk = P2._load(F.PK_DIR, SEASONS)
    gc = R.assemble_game_coaches(); tg = R.to_team_games(gc)
    raw = R.build_ledger(tg.filter(pl.col("coach").is_not_null()))
    raw_annot, _ = R.consolidate_ledger(raw, k=4)
    reg = P2.consolidated_regime_games(tg, raw_annot)   # team-game: team_id, season_label, game_id, coach, consolidated_start_game_id
    return prim, deploy, pk, reg


def boundary_and_regime_fps(prim, deploy, pk, reg):
    """Per (team, season): season-START and season-END consolidated-regime fingerprints + the
    start/end coach and in-season game counts. Also per CONSOLIDATED REGIME (across seasons):
    full fingerprint + coach + games + end season, for the incoming-coach prior-fingerprint test."""
    tsb = {}   # (team, season) -> dict
    for (team, season), sub in reg.group_by(["team_id", "season_label"]):
        sub = sub.sort("game_id")
        start_cons = sub["consolidated_start_game_id"][0]
        end_cons = sub["consolidated_start_game_id"][-1]
        sg = sub.filter(pl.col("consolidated_start_game_id") == start_cons)
        eg = sub.filter(pl.col("consolidated_start_game_id") == end_cons)
        tsb[(team, season)] = {
            "start_coach": sg["coach"][0], "end_coach": eg["coach"][-1],
            "start_games": sg["game_id"].unique().to_list(), "end_games": eg["game_id"].unique().to_list(),
            "start_fp": _full_fp(prim, deploy, pk, sg["game_id"].unique().to_list(), team) if sg.height else None,
            "end_fp": _full_fp(prim, deploy, pk, eg["game_id"].unique().to_list(), team) if eg.height else None,
            "n_start": sg["game_id"].n_unique(), "n_end": eg["game_id"].n_unique()}
    # per consolidated regime (across all its games/seasons)
    regimes = []
    for (team, cons), sub in reg.group_by(["team_id", "consolidated_start_game_id"]):
        gids = sub["game_id"].unique().to_list()
        regimes.append({"team_id": team, "coach": sub.sort("game_id")["coach"][0],
                        "end_syear": int(sub["season_label"].replace_strict(_SY, return_dtype=pl.Int64).max()),
                        "start_syear": int(sub["season_label"].replace_strict(_SY, return_dtype=pl.Int64).min()),
                        "n_games": len(gids), "fp": _full_fp(prim, deploy, pk, gids, team)})
    return tsb, regimes


# ---------------------------------------------------------------- S1 cohorts + S2 continuity
def _pctx_by_season():
    return {s: pl.read_parquet(C.PCTX_DIR / f"{s.replace('-', '_')}.parquet") for s in SEASONS}


def _rapm():
    r = pl.read_parquet(config.ATLAS_PARQUET / "rapm_variant.parquet")
    return r.select("player_id", pl.col("season").alias("season_label"), q=pl.col("off_impact") + pl.col("def_impact"))


def continuity(team, seasonA, pctx, rapm):
    """Returning share of season-A 5v5 TOI, and RAPM-value (TOI x rating-percentile) share, for
    the players on `team` in A who are still on `team` the next season."""
    B = SEASONS[SEASONS.index(seasonA) + 1]
    a = pctx[seasonA].filter(pl.col("team_id") == team).group_by("player_id").agg(toi=pl.col("toi_5v5_s").sum())
    b_ids = set(pctx[B].filter(pl.col("team_id") == team)["player_id"].to_list())
    if a.height == 0:
        return None
    ra = rapm.filter(pl.col("season_label") == seasonA)
    qpc = ra.with_columns(qpct=pl.col("q").rank() / pl.len()).select("player_id", "qpct")
    a = a.join(qpc, on="player_id", how="left").with_columns(
        qpct=pl.col("qpct").fill_null(0.5), returning=pl.col("player_id").is_in(list(b_ids)))
    a = a.with_columns(value=pl.col("toi") * pl.col("qpct"))
    toi_share = a.filter(pl.col("returning"))["toi"].sum() / a["toi"].sum()
    val_share = a.filter(pl.col("returning"))["value"].sum() / a["value"].sum()
    return float(toi_share), float(val_share)


def transitions(tsb, pctx, rapm):
    """S1+S2: one row per season-boundary team transition A->A+1."""
    rows = []
    for (team, A), d in tsb.items():
        if A == SEASONS[-1]:
            continue
        B = SEASONS[SEASONS.index(A) + 1]
        nxt = tsb.get((team, B))
        if not nxt or d["end_coach"] is None or nxt["start_coach"] is None:
            continue
        if d["end_fp"] is None or nxt["start_fp"] is None:
            continue
        cont = continuity(team, A, pctx, rapm)
        if cont is None:
            continue
        rows.append({"team_id": team, "seasonA": A, "seasonB": B,
                     "prior_coach": d["end_coach"], "new_coach": nxt["start_coach"],
                     "coach_change": int(d["end_coach"] != nxt["start_coach"]),
                     "ret_toi": cont[0], "ret_value": cont[1],
                     "n_end_A": d["n_end"], "n_start_B": nxt["n_start"],
                     "team_prev": d["end_fp"], "team_new": nxt["start_fp"]})
    return rows


# ---------------------------------------------------------------- S3 dose test
def _std_map(rows):
    """Per-metric SD of |Δ| across all transitions (for standardizing pooled family regressions)."""
    sd = {}
    for m in ALLM:
        v = [abs(r["team_new"][m] - r["team_prev"][m]) for r in rows
             if r["team_new"].get(m) is not None and r["team_prev"].get(m) is not None]
        sd[m] = float(np.std(v)) + 1e-12
    return sd


def dose_test(rows, phase2_disc):
    sd = _std_map(rows)
    syears = sorted({_SY[r["seasonA"]] for r in rows})
    out = {}
    for fam, metrics in FAMILIES.items():
        # stacked pooled regression: z(|Δ|) ~ coach_change + ret_toi + ret_value + season_FE + metric_FE
        Xrows, y = [], []
        for r in rows:
            for m in metrics:
                a, b = r["team_prev"].get(m), r["team_new"].get(m)
                if a is None or b is None:
                    continue
                z = abs(b - a) / sd[m]
                feat = [1.0, r["coach_change"], r["ret_toi"], r["ret_value"]]
                feat += [1.0 if _SY[r["seasonA"]] == sy else 0.0 for sy in syears[1:]]
                feat += [1.0 if m == mm else 0.0 for mm in metrics[1:]]
                Xrows.append(feat); y.append(z)
        X = np.array(Xrows); y = np.array(y)
        beta, *_ = np.linalg.lstsq(X, y, rcond=None)
        # OLS SE for the coach_change coef (index 1)
        resid = y - X @ beta
        dof = max(1, len(y) - X.shape[1])
        sigma2 = (resid @ resid) / dof
        XtX_inv = np.linalg.pinv(X.T @ X)
        se = float(np.sqrt(sigma2 * XtX_inv[1, 1]))
        cc = float(beta[1])
        # raw comparison: mean standardized |Δ| by cohort, and Phase 2 mid-season standardized dose
        def mean_std_absdelta(subset):
            vals = []
            for r in subset:
                for m in metrics:
                    a, b = r["team_prev"].get(m), r["team_new"].get(m)
                    if a is not None and b is not None:
                        vals.append(abs(b - a) / sd[m])
            return float(np.mean(vals)) if vals else None
        chg = [r for r in rows if r["coach_change"] == 1]
        con = [r for r in rows if r["coach_change"] == 0]
        mid_vals = [phase2_disc[m] / sd[m] for m in metrics if m in phase2_disc]
        mid = float(np.mean(mid_vals)) if mid_vals else None
        out[fam] = {
            "n_obs": len(y), "n_metrics": len(metrics),
            "coach_change_coef_sd_units": round(cc, 4), "se": round(se, 4),
            "ci95": [round(cc - 1.96 * se, 4), round(cc + 1.96 * se, 4)],
            "t": round(cc / se, 2) if se > 0 else None,
            "summer_change_mean_absdelta_sd": round(mean_std_absdelta(chg), 4),
            "summer_continuation_mean_absdelta_sd": round(mean_std_absdelta(con), 4),
            "midseason_dose_sd": round(mid, 4) if mid is not None else None,
        }
    return out


def _phase2_baseline():
    """Combined mid-season median |Δ| per metric: Phase 2 main + PK addendum."""
    main = json.loads((config.REPORTS / "phase2_analysis.json").read_text())["discontinuity"]["per_metric"]
    add = json.loads((config.REPORTS / "phase2_addendum_analysis.json").read_text())["A2_pk_individual"]
    b = {m: v["median_real_abs_shift"] for m, v in main.items() if "median_real_abs_shift" in v}
    b.update({m: v["median_real"] for m, v in add.items()})
    return b


# ---------------------------------------------------------------- S4 directional test
def _incoming_prior_fp(new_coach, prior_team, transition_syear, regimes):
    """Most recent prior consolidated regime of `new_coach` (any team, excluding one that starts
    at/after the transition), 40+ games, ending within COACH_PRIOR_WINDOW seasons before."""
    cands = [g for g in regimes if g["coach"] == new_coach and g["n_games"] >= COACH_PRIOR_MIN
             and g["end_syear"] < transition_syear
             and (transition_syear - g["end_syear"]) <= COACH_PRIOR_WINDOW]
    if not cands:
        return None
    return max(cands, key=lambda g: g["end_syear"])["fp"]


def directional_test(rows, regimes, seed=config.SEED):
    changes = [r for r in rows if r["coach_change"] == 1]
    eligible = []
    for r in changes:
        fp = _incoming_prior_fp(r["new_coach"], r["team_id"], _SY[r["seasonB"]], regimes)
        if fp is None:
            continue
        eligible.append({**r, "coach_prior": fp})
    # per metric: x = coach_prior - team_prev ; y = team_new - team_prev ; corr across eligible
    rng = np.random.default_rng(seed)
    out = {"n_eligible_transitions": len(eligible),
           "n_eligible_coaches": len({r["new_coach"] for r in eligible})}
    fam_res = {}
    for fam, metrics in FAMILIES.items():
        # PRIMARY (faithful to "per metric ... pooled by family"): one directional correlation
        # PER METRIC (scale-invariant), pooled by averaging across the family; permutation shuffles
        # the coach->prior assignment and re-pools. Also report the pooled-standardized-pairs
        # variant as a robustness check.
        obs, npairs = _family_meancorr(eligible, metrics, list(range(len(eligible))))
        perm = _perm_meancorr(eligible, metrics, rng, obs)
        obs_pool, perm_pool = _pooled_std_variant(eligible, metrics, rng)
        fam_res[fam] = {"n_pairs": npairs, "directional_corr": round(float(obs), 4), "perm_p": round(perm, 4),
                        "robustness_pooled_std": {"directional_corr": round(float(obs_pool[0]), 4),
                                                  "perm_p": round(obs_pool[1], 4)}}
    out["families"] = fam_res
    return out, eligible


def _family_meancorr(eligible, metrics, order):
    """Mean of per-metric directional correlations; each metric's correlation is scale-invariant."""
    corrs, npairs = [], 0
    for m in metrics:
        xs, ys = [], []
        for i, r in enumerate(eligible):
            cp = eligible[order[i]]["coach_prior"].get(m)
            tp, tn = r["team_prev"].get(m), r["team_new"].get(m)
            if cp is None or tp is None or tn is None:
                continue
            xs.append(cp - tp); ys.append(tn - tp)
        c = _corr(np.array(xs), np.array(ys))
        if not np.isnan(c):
            corrs.append(c); npairs += len(xs)
    return (float(np.mean(corrs)) if corrs else float("nan")), npairs


def _perm_meancorr(eligible, metrics, rng, obs, n=2000):
    cnt = 1
    for _ in range(n):
        order = list(rng.permutation(len(eligible)))
        c, _n = _family_meancorr(eligible, metrics, order)
        if not np.isnan(c) and c >= obs:
            cnt += 1
    return cnt / (n + 1)


def _pooled_std_variant(eligible, metrics, rng, n=2000):
    """Robustness: pool per-metric-standardized pairs into one correlation."""
    sdx = {m: (np.std([r["coach_prior"][m] - r["team_prev"][m] for r in eligible
                       if None not in (r["coach_prior"].get(m), r["team_prev"].get(m))]) + 1e-12) for m in metrics}
    sdy = {m: (np.std([r["team_new"][m] - r["team_prev"][m] for r in eligible
                       if None not in (r["team_new"].get(m), r["team_prev"].get(m))]) + 1e-12) for m in metrics}
    def pool(order):
        xs, ys = [], []
        for m in metrics:
            for i, r in enumerate(eligible):
                cp = eligible[order[i]]["coach_prior"].get(m); tp = r["team_prev"].get(m); tn = r["team_new"].get(m)
                if None in (cp, tp, tn):
                    continue
                xs.append((cp - tp) / sdx[m]); ys.append((tn - tp) / sdy[m])
        return _corr(np.array(xs), np.array(ys))
    obs = pool(list(range(len(eligible))))
    cnt = 1
    for _ in range(n):
        if pool(list(rng.permutation(len(eligible)))) >= obs:
            cnt += 1
    return (obs, cnt / (n + 1)), None


def _corr(x, y):
    if len(x) < 3:
        return float("nan")
    x = x - x.mean(); y = y - y.mean()
    d = np.sqrt((x ** 2).sum() * (y ** 2).sum())
    return float((x * y).sum() / d) if d > 0 else float("nan")


def _perm_null(eligible, metrics, sdx, sdy, rng, obs, n=2000):
    cnt = 1
    for _ in range(n):
        order = list(rng.permutation(len(eligible)))
        xs, ys = _pool_std(eligible, metrics, sdx, sdy, order)
        if _corr(np.array(xs), np.array(ys)) >= obs:
            cnt += 1
    return cnt / (n + 1)


# ---------------------------------------------------------------- S5 verdict
def verdict(dose, direct):
    style_dir = direct["families"]["style"]
    dir_clears = (style_dir["perm_p"] < 0.05) and (style_dir["directional_corr"] > 0)
    ds = dose["style"]
    dose_clears = ds["summer_change_mean_absdelta_sd"] > ds["summer_continuation_mean_absdelta_sd"] \
        and ds["coach_change_coef_sd_units"] > 0 and ds["ci95"][0] > 0
    if dir_clears and dose_clears:
        v = ("AMEND: F12 amends from 'style is a roster property' to 'style installs need a "
             "summer; mid-season changes only reallocate' — labeled OBSERVATIONAL.")
    elif not dir_clears and not dose_clears:
        v = ("EXTEND: style family fails both tests -> F12 EXTENDS to summers, with the "
             "roster-adjustment caveat stated (continuity confound controlled but observational).")
    else:
        v = ("MIXED: style clears one test but not both -> F12 unchanged; report the split "
             "honestly. (Pre-stated amend requires BOTH; extend requires BOTH fail.)")
    return {"directional_style_clears": dir_clears, "dose_style_clears": dose_clears,
            "deployment_calibration": {"directional": direct["families"]["deployment"],
                                       "dose_coef": dose["deployment"]["coach_change_coef_sd_units"]},
            "verdict": v}


def run() -> dict:
    prim, deploy, pk, reg = _load()
    tsb, regimes = boundary_and_regime_fps(prim, deploy, pk, reg)
    pctx = _pctx_by_season(); rapm = _rapm()
    rows = transitions(tsb, pctx, rapm)
    # apply the boundary-games filter for dose/directional (fingerprint stability)
    stable = [r for r in rows if r["n_end_A"] >= MIN_REGIME_GAMES and r["n_start_B"] >= MIN_REGIME_GAMES]
    dose = dose_test(stable, _phase2_baseline())
    direct, eligible = directional_test(stable, regimes)
    out = {"seed": config.SEED,
           "S1_cohorts": _cohort_counts(rows, stable),
           "S2_continuity": _continuity_summary(rows),
           "S3_dose": dose,
           "S4_directional": direct,
           "S5_verdict": verdict(dose, direct)}
    (config.REPORTS / "phase5_summer_analysis.json").write_text(json.dumps(out, indent=2, default=str))
    return out


def _cohort_counts(rows, stable):
    def cnt(rs):
        return {"total": len(rs), "summer_change": sum(r["coach_change"] for r in rs),
                "summer_continuation": sum(1 - r["coach_change"] for r in rs)}
    by_season = {}
    for r in rows:
        by_season.setdefault(r["seasonB"], [0, 0])
        by_season[r["seasonB"]][r["coach_change"]] += 1
    return {"all_transitions": cnt(rows), "stable_subset_used": cnt(stable),
            "per_dest_season_change_count": {k: v[1] for k, v in sorted(by_season.items())}}


def _continuity_summary(rows):
    out = {}
    for lab, cc in (("summer_change", 1), ("summer_continuation", 0)):
        sub = [r for r in rows if r["coach_change"] == cc]
        for meas in ("ret_toi", "ret_value"):
            v = np.array([r[meas] for r in sub])
            out[f"{lab}__{meas}"] = {"n": len(v), "mean": round(float(v.mean()), 3),
                                     "median": round(float(np.median(v)), 3),
                                     "p25": round(float(np.percentile(v, 25)), 3),
                                     "p75": round(float(np.percentile(v, 75)), 3)}
    return out


if __name__ == "__main__":
    r = run()
    print("cohorts:", r["S1_cohorts"]["all_transitions"], "| stable:", r["S1_cohorts"]["stable_subset_used"])
    print("continuity change ret_toi:", r["S2_continuity"]["summer_change__ret_toi"]["median"],
          "cont:", r["S2_continuity"]["summer_continuation__ret_toi"]["median"])
    for fam in FAMILIES:
        print(f"  dose[{fam}] coef={r['S3_dose'][fam]['coach_change_coef_sd_units']} ci={r['S3_dose'][fam]['ci95']}"
              f" | direct corr={r['S4_directional']['families'][fam]['directional_corr']} p={r['S4_directional']['families'][fam]['perm_p']}")
    print("VERDICT:", r["S5_verdict"]["verdict"])
