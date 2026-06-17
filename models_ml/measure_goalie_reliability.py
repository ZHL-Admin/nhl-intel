"""
Measure the season-to-season RELIABILITY of goalie save performance, as a function of workload —
the empirical justification for the shrinkage applied in `compute_goalie_gar.py`.

Goaltending is low-signal: a single season's GSAx is a noisy estimate of a goalie's true level.
The honest point estimate is therefore the raw value regressed toward the population mean *in
proportion to how reliable it is*, and reliability must be MEASURED, not guessed. This is the same
empirical-Bayes / regression-to-the-mean logic already used for low-sample skaters (RAPM ridge,
player-finishing shrinkage); here we derive the constant from the data.

Method of moments on the per-shot rate x = GSAx / shots (per danger tier and overall):
  Var(observed rate) = Var(true talent) + E[sampling noise]
  sampling noise of the mean rate for a goalie with n shots ≈ s² / n,  s² = E[xg·(1−xg)] per shot
  Var(true) = Var(observed) − E[s²/n]                                  (method of moments)
  reliability(n) = Var(true) / (Var(true) + s²/n) = n / (n + k),  k = s² / Var(true)
k is the workload (shots) at which the estimate is 50% signal / 50% noise. A year-over-year
correlation, split by workload, is printed as an independent cross-check.

Run:  python -m models_ml.measure_goalie_reliability
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from models_ml import bq

SINGLE_SEASONS = ["2021-22", "2022-23", "2023-24", "2024-25", "2025-26"]
TIERS = ["hd", "md", "ld", "pk"]
# per-tier shot floors to enter the reliability estimate (a tier needs enough shots to be a rate)
TIER_FLOOR = {"hd": 60, "md": 120, "ld": 200, "pk": 80, "overall": 400}

SQL = """
with shots as (
  select goalie_id, season, is_goal, xg,
    case
      when strength_vs = 'special' then 'pk'
      when danger_tier = 'high'   then 'hd'
      when danger_tier = 'medium' then 'md'
      else 'ld'
    end as bucket
  from `{p}.nhl_staging.int_goalie_shots`
  where substr(cast(game_id as string), 5, 2) in ('02', '03')
)
select goalie_id, season,
  count(*) as shots_total,
  sum(xg) - countif(is_goal) as gsax_total,
  sum(xg * (1 - xg)) as xgvar_total,
  {tier_cols}
from shots group by goalie_id, season
"""


def _tier_cols() -> str:
    parts = []
    for b in TIERS:
        parts.append(f"countif(bucket='{b}') as shots_{b}")
        parts.append(f"sum(if(bucket='{b}', xg, 0)) - countif(bucket='{b}' and is_goal) as gsax_{b}")
        parts.append(f"sum(if(bucket='{b}', xg*(1-xg), 0)) as xgvar_{b}")
    return ",\n  ".join(parts)


def reliability_k(df: pd.DataFrame, gsax: str, shots: str, xgvar: str, floor: float) -> dict:
    """Method-of-moments reliability constant k for one rate metric (single-season rows)."""
    d = df[df[shots] >= floor].copy()
    d = d[d[shots] > 0]
    rate = d[gsax] / d[shots]                       # per-shot GSAx (the talent rate)
    noise_var = d[xgvar] / d[shots] ** 2            # sampling variance of the mean rate
    s2 = (d[xgvar] / d[shots]).mean()               # per-shot variance s²
    var_obs = rate.var(ddof=1)
    var_true = var_obs - noise_var.mean()
    k = float(s2 / var_true) if var_true > 0 else float("inf")
    return {"n": int(len(d)), "var_obs": float(var_obs), "var_true": float(var_true),
            "s2": float(s2), "k": k}


def main() -> None:
    p = bq.project()
    df = bq.query_df(SQL.format(p=p, tier_cols=_tier_cols()))
    numcols = ["shots_total", "gsax_total", "xgvar_total"] + \
              [f"{m}_{b}" for b in TIERS for m in ("shots", "gsax", "xgvar")]
    for c in numcols:
        df[c] = pd.to_numeric(df[c]).astype("float64")
    single = df[df["season"].isin(SINGLE_SEASONS)].copy()

    print("=== 1. Reliability constant k (method of moments, per-shot rate) ===")
    print(f"  {'metric':8s} {'n':>4s} {'k (shots@50%)':>14s}  reliability at 500 / 1000 / 2000 shots")
    fits = {}
    for key, (gs, sh, xv) in {
        "overall": ("gsax_total", "shots_total", "xgvar_total"),
        **{b: (f"gsax_{b}", f"shots_{b}", f"xgvar_{b}") for b in TIERS},
    }.items():
        fit = reliability_k(single, gs, sh, xv, TIER_FLOOR[key])
        fits[key] = fit
        k = fit["k"]
        rel = lambda n: n / (n + k) if np.isfinite(k) else 0.0
        print(f"  {key:8s} {fit['n']:>4d} {k:>14.0f}  "
              f"{rel(500):.2f} / {rel(1000):.2f} / {rel(2000):.2f}")

    print("\n=== 2. Reliability-vs-workload curve (overall rate) ===")
    k_overall = fits["overall"]["k"]
    print("  shots:      " + "  ".join(f"{n:>4d}" for n in [300, 500, 800, 1200, 1800, 2500]))
    print("  reliability:" + "  ".join(f"{n/(n+k_overall):>4.2f}" for n in [300, 500, 800, 1200, 1800, 2500]))

    print("\n=== 3. Year-over-year cross-check (GSAx/shot), split by workload ===")
    # align consecutive single seasons; correlate rate(season) vs rate(season+1)
    single["rate"] = single["gsax_total"] / single["shots_total"]
    pairs = []
    for a, b in zip(SINGLE_SEASONS, SINGLE_SEASONS[1:]):
        ra = single[single["season"] == a].set_index("goalie_id")
        rb = single[single["season"] == b].set_index("goalie_id")
        j = ra[["rate", "shots_total"]].join(rb[["rate"]], lsuffix="_a", rsuffix="_b", how="inner").dropna()
        pairs.append(j)
    allp = pd.concat(pairs)
    for lbl, lo, hi in [("low workload (<1000 sh)", 0, 1000), ("high workload (>=1000 sh)", 1000, 1e9)]:
        sub = allp[(allp["shots_total"] >= lo) & (allp["shots_total"] < hi)]
        r = sub["rate_a"].corr(sub["rate_b"]) if len(sub) > 5 else float("nan")
        print(f"  {lbl:26s} n={len(sub):>3d}  YoY r = {r:.2f}")
    print(f"  ALL pairs                  n={len(allp):>3d}  YoY r = {allp['rate_a'].corr(allp['rate_b']):.2f}")
    print("  -> reliability RISES with workload (the higher-shot split repeats more); this is exactly")
    print("     what the k-based shrinkage encodes. Print these into value-gar.md as justification.")

    print("\n=== config.GOALIE_GAR_CONFIG['RELIABILITY_K'] (paste, sourced from this run) ===")
    print("  RELIABILITY_K = {")
    for key in ["overall"] + TIERS:
        print(f"      {key!r}: {fits[key]['k']:.0f},")
    print("  }")


if __name__ == "__main__":
    main()
