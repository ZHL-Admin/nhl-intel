"""
Score win probability + leverage for every game (Phase 2.4).

Writes nhl_models.win_probability: one row per (game_id, elapsed_seconds) on a 10-second
grid with home_wp and leverage. Leverage(t) = WP(one more home goal) - WP(one more away
goal) at the same state — it peaks late in tight games.

Run:
  python -m models_ml.score_winprob                    # full rescore, season by season
  python -m models_ml.score_winprob --since 2026-01-01 # incremental (delete>=since, append)
  python -m models_ml.score_winprob --season 2025-26 --dry-run-write
"""

from __future__ import annotations

import argparse
from pathlib import Path

import joblib
import pandas as pd

from models_ml import bq
from models_ml.winprob_features import (
    add_state_features, build_pull_sql, make_design, shift_score,
)

MODEL_VERSION = "winprob_v1"
ARTIFACT = Path(__file__).parent / "artifacts" / f"{MODEL_VERSION}.joblib"
TABLE = "win_probability"
SCORE_STEP = 10
OUT_COLS = ["game_id", "game_date", "elapsed_seconds", "home_wp", "leverage", "model_version"]

ALL_SEASONS = [
    "2010-11", "2011-12", "2012-13", "2013-14", "2014-15", "2015-16", "2016-17",
    "2017-18", "2018-19", "2019-20", "2020-21", "2021-22", "2022-23", "2023-24",
    "2024-25", "2025-26",
]


def score_frame(model, df: pd.DataFrame) -> pd.DataFrame:
    df = add_state_features(df)
    home_wp = model.predict_proba(make_design(df))[:, 1]
    wp_up = model.predict_proba(make_design(shift_score(df, +1)))[:, 1]
    wp_dn = model.predict_proba(make_design(shift_score(df, -1)))[:, 1]
    out = pd.DataFrame({
        "game_id": df["game_id"].to_numpy(),
        "game_date": df["game_date"].to_numpy(),
        "elapsed_seconds": df["elapsed"].astype("int64").to_numpy(),
        "home_wp": home_wp,
        "leverage": wp_up - wp_dn,
    })
    out["model_version"] = MODEL_VERSION
    return out[OUT_COLS]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--since", default=None)
    ap.add_argument("--season", default=None, help="score a single season")
    ap.add_argument("--dry-run-write", action="store_true")
    args = ap.parse_args()

    model = joblib.load(ARTIFACT)
    client = bq.client()

    if args.since:
        where = f"and c.game_id in (select game_id from `{bq.project()}.nhl_staging.stg_boxscores` where game_date >= '{args.since}')"
        df = bq.query_df(build_pull_sql(bq.project(), where=where, step=SCORE_STEP), client)
        out = score_frame(model, df)
        print(f"scored {len(out):,} rows (since {args.since})")
        if not args.dry_run_write:
            bq.delete_partition_since(TABLE, "game_date", args.since)
            bq.write_df(out, TABLE, write_disposition="WRITE_APPEND", clustering_fields=["game_id"])
            print(f"appended to nhl_models.{TABLE}")
        return

    seasons = [args.season] if args.season else ALL_SEASONS
    wrote_any = False  # truncate on the FIRST season that actually has rows (idempotent)
    for season in seasons:
        df = bq.query_df(build_pull_sql(bq.project(), where=f"and c.season = '{season}'",
                                        step=SCORE_STEP), client)
        if df.empty:
            print(f"{season}: no rows, skipping")
            continue
        out = score_frame(model, df)
        disp = "WRITE_APPEND" if (args.season or wrote_any) else "WRITE_TRUNCATE"
        print(f"{season}: {len(out):,} rows ({disp})")
        if not args.dry_run_write:
            bq.write_df(out, TABLE, write_disposition=disp, clustering_fields=["game_id"])
            wrote_any = True
    print("done")


if __name__ == "__main__":
    main()
