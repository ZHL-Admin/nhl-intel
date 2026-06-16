"""
Physical-aging overlay + burst-decline early-warning VALIDATION (Phase 4.4, blueprint 12.2).

Stores tracking-era skating burst rate and top speed by season, and — only if it survives a
validation gate — an early-warning flag for players whose burst is declining ahead of their
production.

Validation (the same discipline as the clutch permutation test): does a player's year-over-year
burst-rate change predict his NEXT-season points/82 change? If they are positively correlated
(burst falling tends to precede production falling) at a meaningful, significant level, the flag
is shipped; otherwise the overlay ships WITHOUT the flag and the negative result is published.

Output: nhl_models.player_physical (player_id, season, burst_rate, max_speed, burst_change_1yr,
early_warning) — early_warning is all-false if validation fails. The validation stat is printed
and written into docs/methodology/trajectories.md.

Run:  python -m models_ml.compute_physical [--dry-run]
"""

from __future__ import annotations

import argparse

import numpy as np
import pandas as pd
from scipy import stats

from models_ml import bq

EDGE_SEASONS = ["2021-22", "2022-23", "2023-24", "2024-25", "2025-26"]
MIN_GAMES = 20
VALIDATE_MIN_R = 0.10        # ship the flag only if corr >= this and p < 0.05
BURST_DROP_PCTILE = 20       # "sharp" burst decline = bottom-20% of 1yr changes


def pull() -> pd.DataFrame:
    p = bq.project()
    edge = bq.query_df(f"""
        select player_id, season_id, bursts_22_plus_per60 as burst_rate,
               max_skating_speed_mph as max_speed
        from `{p}.nhl_mart.mart_edge_player_profile`
        where game_type = 2 and toi_minutes > 0
    """)
    edge["season"] = (edge["season_id"].astype(str).str[:4] + "-"
                      + edge["season_id"].astype(str).str[6:8])
    prod = bq.query_df(f"""
        select player_id, season,
               sum(individual_goals + first_assists + second_assists) / count(*) * 82 as points82
        from `{p}.nhl_mart.mart_player_game_stats`
        where substr(cast(game_id as string), 5, 2) in ('02', '03')
        group by 1, 2 having count(*) >= {MIN_GAMES}
    """)
    df = edge.merge(prod, on=["player_id", "season"], how="inner")
    for c in ["burst_rate", "max_speed", "points82"]:
        df[c] = pd.to_numeric(df[c]).astype("float64")
    df["season_start"] = df["season"].str[:4].astype(int)
    return df.sort_values(["player_id", "season_start"])


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    df = pull()
    g = df.groupby("player_id")
    df["burst_prev"] = g["burst_rate"].shift(1)
    df["prev_start"] = g["season_start"].shift(1)
    df["points_next"] = g["points82"].shift(-1)
    df["next_start"] = g["season_start"].shift(-1)
    df["burst_change_1yr"] = np.where(df["season_start"] - df["prev_start"] == 1,
                                      df["burst_rate"] - df["burst_prev"], np.nan)
    df["prod_change_next"] = np.where(df["next_start"] - df["season_start"] == 1,
                                      df["points_next"] - df["points82"], np.nan)

    # VALIDATION: does burst change predict next-season production change?
    v = df.dropna(subset=["burst_change_1yr", "prod_change_next"])
    r, pval = stats.pearsonr(v["burst_change_1yr"], v["prod_change_next"]) if len(v) > 30 else (0.0, 1.0)
    validated = (r >= VALIDATE_MIN_R) and (pval < 0.05)
    print(f"Burst-decline validation: corr(burst_change_t, prod_change_t+1) = {r:.3f} "
          f"(p={pval:.3f}, n={len(v)}) -> flag {'SHIPPED' if validated else 'WITHHELD'}")

    df["early_warning"] = False
    if validated:
        thr = np.nanpercentile(df["burst_change_1yr"], BURST_DROP_PCTILE)
        # sharp burst drop while production has NOT yet dropped this year
        df["early_warning"] = ((df["burst_change_1yr"] <= thr)
                               & (df["points82"] - g["points82"].shift(1) >= 0)).fillna(False)
        print(f"  flagged {int(df['early_warning'].sum())} player-seasons")

    out = df[["player_id", "season", "burst_rate", "max_speed", "burst_change_1yr",
              "early_warning"]].copy()
    out["validation_r"] = round(float(r), 4)
    if args.dry_run:
        print(f"\n[dry-run] {len(out)} rows not written")
        return
    out["player_id"] = out["player_id"].astype("int64")
    out["model_version"] = "physical_v1"
    bq.write_df(out, "player_physical", write_disposition="WRITE_TRUNCATE",
                clustering_fields=["player_id"])
    print(f"\nWrote {len(out)} rows to nhl_models.player_physical (validated={validated}).")


if __name__ == "__main__":
    main()
