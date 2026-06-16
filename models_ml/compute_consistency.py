"""
Consistency profile (Phase 4.3, blueprint 4.4).

Per player-season, summarise the distribution of single-game game scores
(mart_player_game_score): mean, sd, IQR, the share of "good games" (game score above the
league 60th percentile that window) and "no-shows" (below the 25th), and a consistency index
= the percentile rank of mean/sd within position (a high floor relative to volatility).

Output: nhl_models.player_consistency (player_id, season_window, games, mean_gs, sd_gs, iqr_gs,
good_game_share, no_show_share, consistency_index).

Run:  python -m models_ml.compute_consistency [--dry-run]
"""

from __future__ import annotations

import argparse

import numpy as np
import pandas as pd

from models_ml import bq

SINGLE_SEASONS = ["2021-22", "2022-23", "2023-24", "2024-25", "2025-26"]
WINDOW = ["2023-24", "2024-25", "2025-26"]
WINDOW_LABEL = "2023-24_2025-26"
MIN_GAMES = 20
GOOD_PCTILE = 60
NOSHOW_PCTILE = 25


def pull(seasons: list[str]) -> pd.DataFrame:
    df = bq.query_df(f"""
        select player_id, season, position_code, game_score
        from `{bq.project()}.nhl_mart.mart_player_game_score`
        where substr(cast(game_id as string), 5, 2) in ('02', '03')
          and season in ({", ".join(f"'{s}'" for s in seasons)})
    """)
    df["game_score"] = pd.to_numeric(df["game_score"]).astype("float64")
    df["pos_group"] = np.where(df["position_code"] == "D", "D", "F")
    return df


def compute(df: pd.DataFrame, label: str) -> pd.DataFrame:
    good_thr = np.percentile(df["game_score"], GOOD_PCTILE)
    noshow_thr = np.percentile(df["game_score"], NOSHOW_PCTILE)
    rows = []
    for (pid, pos), g in df.groupby(["player_id", "pos_group"]):
        gs = g["game_score"].to_numpy()
        if len(gs) < MIN_GAMES:
            continue
        sd = gs.std(ddof=1)
        rows.append({
            "player_id": int(pid), "season_window": label, "pos_group": pos,
            "games": len(gs), "mean_gs": float(gs.mean()), "sd_gs": float(sd),
            "iqr_gs": float(np.percentile(gs, 75) - np.percentile(gs, 25)),
            "good_game_share": float((gs > good_thr).mean()),
            "no_show_share": float((gs < noshow_thr).mean()),
            "mean_over_sd": float(gs.mean() / sd) if sd > 0 else 0.0,
        })
    out = pd.DataFrame(rows)
    # consistency index = percentile rank of mean/sd within position
    out["consistency_index"] = out.groupby("pos_group")["mean_over_sd"].rank(pct=True)
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    frames = [compute(pull([s]), s) for s in SINGLE_SEASONS]
    frames.append(compute(pull(WINDOW), WINDOW_LABEL))
    out = pd.concat(frames, ignore_index=True)

    w = out[out["season_window"] == WINDOW_LABEL]
    names = _names(w["player_id"].tolist())
    print("Most consistent forwards (window, >=100 GP):")
    top = w[(w.pos_group == "F") & (w.games >= 100)].sort_values("consistency_index", ascending=False)
    for _, r in top.head(6).iterrows():
        print(f"  {names.get(r['player_id'], r['player_id']):22s} idx {r['consistency_index']:.2f} "
              f"(mean {r['mean_gs']:.2f}, sd {r['sd_gs']:.2f}, good {r['good_game_share']:.0%})")

    if args.dry_run:
        print(f"\n[dry-run] {len(out):,} rows not written")
        return
    out = out.drop(columns=["mean_over_sd"])
    out["player_id"] = out["player_id"].astype("int64")
    out["model_version"] = "consistency_v1"
    bq.write_df(out, "player_consistency", write_disposition="WRITE_TRUNCATE",
                clustering_fields=["season_window", "player_id"])
    print(f"\nWrote {len(out):,} rows to nhl_models.player_consistency.")


def _names(ids):
    ids = [int(i) for i in ids]
    if not ids:
        return {}
    df = bq.query_df(f"""select player_id, any_value(first_name||' '||last_name) as name
                         from `{bq.project()}.nhl_staging.stg_rosters`
                         where player_id in ({", ".join(str(i) for i in ids)}) group by 1""")
    return dict(zip(df["player_id"], df["name"]))


if __name__ == "__main__":
    main()
