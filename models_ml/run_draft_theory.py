"""The "85% theory" test + steal/bust inputs (Handoff 5, Phase B).

Compares each evaluable drafted player's realized 7-year value against the empirical expectation for
their slot (nhl_models.pick_value_curve), then summarizes how often a pick "busts" relative to its slot.
The slogan ("~85% of picks bust") is intentionally NOT oversold: we report below-slot-MEAN, below-slot-
MEDIAN, and never-NHL together, pooled AND by pick range, because the right-skew means a majority below
the MEAN is expected by construction.

Outputs:
  nhl_models.draft_value_player  — one row per evaluable pick (realized vs expected, value_above_slot,
                                   flags) backing the steal/bust board and the player-page line.
  nhl_models.draft_value_summary — pooled + by-range shares (the real numbers behind the theory).

A consistency check recomputes the summary shares from draft_value_player and asserts they match the
stored summary (the site's consistency-checker discipline) before writing.

Run:
    python -m models_ml.run_draft_theory --dry-run
    python -m models_ml.run_draft_theory
"""
from __future__ import annotations

import argparse

import numpy as np
import pandas as pd

from models_ml import bq, config

D = config.DRAFT_VALUE


def _bucket(overall: int, rnd: int) -> str:
    if overall <= 10:
        return "1-10"
    if overall <= 31:
        return "11-31"
    if rnd == 2:
        return "R2"
    return "R3-7"


def build_player() -> pd.DataFrame:
    P = bq.project()
    picks = bq.query_df(f"""
        select pick_key, draft_year, round, overall_pick, draft_team_abbrev, full_name, pos_group,
               resolved_player_id, made_nhl, realized_value, realized_pwar, realized_pwar_sd,
               games_played_window, career_gp, became_regular
        from `{P}.nhl_staging.int_draft_player_value`
        where is_evaluable and not is_censored
    """)
    curve = bq.query_df(f"""
        select overall_pick, ev_mean_smooth as expected_mean, ev_median_smooth as expected_median
        from `{P}.nhl_models.pick_value_curve`
    """)
    for c in ("realized_value", "realized_pwar", "realized_pwar_sd"):
        picks[c] = pd.to_numeric(picks[c], errors="coerce")
    df = picks.merge(curve, on="overall_pick", how="left")
    df["expected_mean"] = pd.to_numeric(df["expected_mean"], errors="coerce").fillna(0.0)
    df["expected_median"] = pd.to_numeric(df["expected_median"], errors="coerce").fillna(0.0)
    df["value_above_slot"] = df["realized_value"] - df["expected_mean"]
    df["below_mean"] = df["realized_value"] < df["expected_mean"]
    df["below_median"] = df["realized_value"] < df["expected_median"]
    df["never_nhl"] = ~df["made_nhl"].astype(bool)
    df["pick_range"] = [_bucket(int(o), int(r)) for o, r in zip(df.overall_pick, df["round"])]
    df["model_version"] = D["THEORY_VERSION"]
    return df


def summarize(player: pd.DataFrame) -> pd.DataFrame:
    def _agg(g: pd.DataFrame) -> dict:
        n = len(g)
        return {
            "picks": n,
            "share_below_mean": float(g["below_mean"].mean()),
            "share_below_median": float(g["below_median"].mean()),
            "share_never_nhl": float(g["never_nhl"].mean()),
            "share_became_regular": float(g["became_regular"].astype(bool).mean()),
            "mean_realized": float(g["realized_value"].mean()),
            "median_realized": float(g["realized_value"].median()),
        }
    rows = []
    order = {"1-10": 0, "11-31": 1, "R2": 2, "R3-7": 3, "POOLED": 4}
    for rng, g in player.groupby("pick_range"):
        rows.append({"pick_range": rng, **_agg(g)})
    rows.append({"pick_range": "POOLED", **_agg(player)})
    out = pd.DataFrame(rows).sort_values("pick_range", key=lambda s: s.map(order)).reset_index(drop=True)
    out["model_version"] = D["THEORY_VERSION"]
    return out


def consistency_check(player: pd.DataFrame, summary: pd.DataFrame) -> bool:
    """Recompute pooled shares from the player table; assert they match the stored summary."""
    pooled = summary[summary.pick_range == "POOLED"].iloc[0]
    recomputed = {
        "share_below_mean": float(player["below_mean"].mean()),
        "share_below_median": float(player["below_median"].mean()),
        "share_never_nhl": float(player["never_nhl"].mean()),
    }
    ok = all(abs(recomputed[k] - float(pooled[k])) < 1e-9 for k in recomputed)
    print(f"  consistency check (summary vs player): {'PASS' if ok else 'FAIL'}")
    return ok


def _report(player: pd.DataFrame, summary: pd.DataFrame) -> None:
    print(f"\ndraft_value: {len(player)} evaluable picks (classes "
          f"{D['EVAL_CLASS_MIN']}-{D['EVAL_CLASS_MAX']}, {D['EVAL_WINDOW_YEARS']}yr window)")
    print("\n  THE THEORY TEST — share below slot mean / below slot median / never-NHL, by range:")
    print("  range    picks  below_mean  below_median  never_nhl  regular  mean_val")
    for _, r in summary.iterrows():
        print(f"  {r.pick_range:7s}  {int(r.picks):>4}   {100*r.share_below_mean:5.0f}%      "
              f"{100*r.share_below_median:5.0f}%       {100*r.share_never_nhl:5.0f}%   "
              f"{100*r.share_became_regular:4.0f}%   {r.mean_realized:5.2f}")
    pooled = summary[summary.pick_range == "POOLED"].iloc[0]
    print(f"\n  Headline (pooled, evaluable): {100*pooled.share_below_mean:.0f}% of picks return below "
          f"their slot's MEAN, {100*pooled.share_below_median:.0f}% below the MEDIAN, "
          f"{100*pooled.share_never_nhl:.0f}% never play an NHL game.")
    print("\n  Top STEALS (value above slot):")
    for _, r in player.sort_values("value_above_slot", ascending=False).head(6).iterrows():
        print(f"    #{int(r.overall_pick):>3} {r.draft_year} {r.full_name:22s} "
              f"realized={r.realized_value:5.1f} vs slot={r.expected_mean:4.1f}  (+{r.value_above_slot:4.1f})")
    print("\n  Top BUSTS (value below slot; early picks that returned little):")
    busts = player[player.overall_pick <= 31].sort_values("value_above_slot").head(6)
    for _, r in busts.iterrows():
        print(f"    #{int(r.overall_pick):>3} {r.draft_year} {r.full_name:22s} "
              f"realized={r.realized_value:5.1f} vs slot={r.expected_mean:4.1f}  ({r.value_above_slot:5.1f})")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    player = build_player()
    summary = summarize(player)
    _report(player, summary)
    ok = consistency_check(player, summary)
    if not ok:
        raise SystemExit("consistency check failed — not writing")

    if args.dry_run:
        print("\n[dry-run] not written")
        return
    bq.write_df(player, "draft_value_player", write_disposition="WRITE_TRUNCATE",
                clustering_fields=["pick_range", "draft_year"])
    bq.write_df(summary, "draft_value_summary", write_disposition="WRITE_TRUNCATE")
    print(f"\nWrote {len(player)} -> draft_value_player, {len(summary)} -> draft_value_summary.")


if __name__ == "__main__":
    main()
