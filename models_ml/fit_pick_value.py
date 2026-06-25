"""Empirical pick-value curve (Handoff 5, Phase B) — the data-derived replacement for the
hand-calibrated slot_war power-law in config.FUTURES.

Per overall pick (1..config.DRAFT_VALUE['MAX_OVERALL']) over the evaluable draft classes, summarize the
realized 7-year-window pWAR of the players actually taken there (int_draft_player_value, never-NHL=0):
mean, median, p10/p25/p75/p90, share-never-NHL, share-became-regular, sample size. The per-pick sample
is small (~9 classes), so the mean and median are loess-smoothed across pick number (Schuckers'
approach), and the smoothed mean is forced monotone non-increasing (a later pick is never worth more in
expectation). One row per overall pick -> nhl_models.pick_value_curve.

This is the WINDOWED empirical curve (the honest measured quantity). compute_futures_value applies a
career-extrapolation factor on top of it for the trade engine (decision 2.5); that factor is derived
here from the aging curves and stored on the curve, not hardcoded.

Run:
    python -m models_ml.fit_pick_value --dry-run
    python -m models_ml.fit_pick_value                 # writes nhl_models.pick_value_curve
"""
from __future__ import annotations

import argparse

import numpy as np
import pandas as pd
from statsmodels.nonparametric.smoothers_lowess import lowess

from models_ml import bq, config

D = config.DRAFT_VALUE


def pull() -> pd.DataFrame:
    P = bq.project()
    return bq.query_df(f"""
        select overall_pick, realized_value, made_nhl, became_regular
        from `{P}.nhl_staging.int_draft_player_value`
        where is_evaluable and not is_censored
    """)


def per_pick(df: pd.DataFrame) -> pd.DataFrame:
    g = df.groupby("overall_pick")
    out = g["realized_value"].agg(
        ev_mean="mean", ev_median="median",
        p10=lambda x: x.quantile(0.10), p25=lambda x: x.quantile(0.25),
        p75=lambda x: x.quantile(0.75), p90=lambda x: x.quantile(0.90),
        n="size",
    )
    out["share_never_nhl"] = g.apply(lambda x: float((~x["made_nhl"]).mean()))
    out["share_regular"] = g.apply(lambda x: float(x["became_regular"].mean()))
    return out.reset_index().sort_values("overall_pick").reset_index(drop=True)


def _smooth_monotone(x: np.ndarray, y: np.ndarray, frac: float) -> tuple[np.ndarray, np.ndarray]:
    """Loess in LOG space (the curve spans ~2 orders of magnitude — 11 WAR at #1 to ~0 at #200 — so
    linear loess crushes the steep top-pick premium; log-space preserves the multiplicative decay).
    Then enforce non-increasing via a running min so a later pick is never worth more in expectation."""
    ylog = np.log1p(np.clip(y, 0.0, None))      # value floored at 0 already, but guard
    sm_log = lowess(ylog, x, frac=frac, return_sorted=False)
    sm = np.expm1(sm_log)
    sm = np.clip(sm, 0.0, None)
    mono = np.minimum.accumulate(sm)
    return sm, mono


def _career_extrap_factor() -> float:
    """Windowed (7yr) -> whole-career scale, from the aging curves' post-window value tail.

    The trade engine's slot curve is whole-career WAR; ours is measured over a 7yr window. We scale
    by (career value / first-W-years value) implied by the aging curves. Falls back to a documented
    constant if aging_curves is unavailable. Stored on the curve; never hardcoded in two places.
    """
    P = bq.project()
    try:
        ac = bq.query_df(f"""
            select age, curve_value
            from `{P}.nhl_models.aging_curves`
            where curve_value is not null
        """)
        ac["age"] = pd.to_numeric(ac["age"], errors="coerce")
        ac["v"] = pd.to_numeric(ac["curve_value"], errors="coerce")
        ac = ac.dropna().groupby("age")["v"].mean().sort_index()
        # a drafted player's window roughly spans ages 19..25 (draft+0..+6); career ~19..38.
        win = ac[(ac.index >= 19) & (ac.index <= 25)].sum()
        career = ac[(ac.index >= 19) & (ac.index <= 38)].sum()
        if win > 0 and career > win:
            return float(career / win)
    except Exception as e:  # noqa: BLE001
        print(f"  aging_curves unavailable ({str(e)[:60]}); using fallback extrap factor")
    return 1.6  # documented fallback: career ~1.6x the first-7-years value


def _report(curve: pd.DataFrame, extrap: float) -> None:
    print(f"\npick_value_curve: {len(curve)} overall picks, "
          f"monotone non-increasing on the smoothed mean (enforced).")
    print(f"  career-extrapolation factor (windowed->career): {extrap:.2f}x  (for the trade-engine drop-in)")
    mono = curve["ev_mean_smooth"].values
    print(f"  monotone check: max increase between adjacent picks = {np.max(np.diff(mono)):.4f} (<=0 required)")
    print("\n  overall  n  ev_mean  ev_median  smooth_mean  never_nhl%  regular%")
    for ov in [1, 5, 10, 15, 31, 40, 62, 100, 150, 200]:
        r = curve[curve.overall_pick == ov]
        if len(r):
            r = r.iloc[0]
            print(f"  {int(r.overall_pick):>5}  {int(r.n):>2}  {r.ev_mean:6.2f}   {r.ev_median:6.2f}   "
                  f"{r.ev_mean_smooth:6.2f}      {100*r.share_never_nhl:4.0f}     {100*r.share_regular:4.0f}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--frac", type=float, default=D["LOESS_FRAC"], help="loess span (READY-gate knob)")
    args = ap.parse_args()

    raw = pull()
    curve = per_pick(raw)
    # restrict to the curve domain and ensure every overall 1..MAX is present where sampled
    curve = curve[curve.overall_pick <= D["MAX_OVERALL"]].copy()

    x = curve["overall_pick"].values.astype(float)
    sm_mean, mono_mean = _smooth_monotone(x, curve["ev_mean"].values, args.frac)
    sm_med, _ = _smooth_monotone(x, curve["ev_median"].values, args.frac)
    curve["ev_mean_smooth"] = mono_mean
    curve["ev_median_smooth"] = np.clip(sm_med, 0.0, None)
    # Smoothed p10/p90 band bounds (loess, NOT forced monotone — a band may legitimately widen/narrow
    # across slots; the raw per-slot quantiles are jagged on ~9 samples). p90_smooth >= p10_smooth >= 0.
    sm_p10, _ = _smooth_monotone(x, curve["p10"].values, args.frac)
    sm_p90, _ = _smooth_monotone(x, curve["p90"].values, args.frac)
    curve["p10_smooth"] = np.clip(sm_p10, 0.0, None)
    curve["p90_smooth"] = np.maximum(np.clip(sm_p90, 0.0, None), curve["p10_smooth"])
    curve["model_version"] = D["CURVE_VERSION"]

    extrap = _career_extrap_factor()
    curve["career_extrap_factor"] = extrap
    _report(curve, extrap)

    if args.dry_run:
        print("\n[dry-run] not written")
        return
    bq.write_df(curve, "pick_value_curve", write_disposition="WRITE_TRUNCATE",
                clustering_fields=["overall_pick"])
    print(f"\nWrote {len(curve)} rows to nhl_models.pick_value_curve.")


if __name__ == "__main__":
    main()
