"""
Score every unblocked shot with the in-house xG model and decomposition (Phase 2.2).

Writes nhl_models.shot_xg: one row per scored shot (non-empty-net, non-shootout) with
xg, base_rate, the five probability-space decomposition contributions, and model_version.
Empty-net shots are intentionally absent (they carry no model xG); marts left-join and so
exclude them from xG totals automatically.

Run:
  python -m models_ml.score_xg                 # full rescore (WRITE_TRUNCATE)
  python -m models_ml.score_xg --since 2026-01-01   # incremental (delete>=since, append)
  python -m models_ml.score_xg --sample 50000 --dry-run-write   # smoke (no BQ write)
"""

from __future__ import annotations

import argparse
from pathlib import Path

import lightgbm as lgb
import pandas as pd

from models_ml import bq
from models_ml.xg_decompose import predict_with_decomposition
from models_ml.xg_features import build_features, build_pull_sql

MODEL_VERSION = "xg_v1"
ARTIFACT = Path(__file__).parent / "artifacts" / f"{MODEL_VERSION}.txt"
TABLE = "shot_xg"
OUT_COLS = [
    "game_id", "event_id", "season", "game_date", "team_id",
    "xg", "base_rate",
    "xg_contrib_location", "xg_contrib_shot_type", "xg_contrib_strength",
    "xg_contrib_sequence", "xg_contrib_game_state", "model_version",
]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--since", default=None, help="only (re)score game_date >= this (YYYY-MM-DD)")
    ap.add_argument("--sample", type=int, default=None)
    ap.add_argument("--dry-run-write", action="store_true", help="compute but do not write to BQ")
    args = ap.parse_args()

    model = lgb.Booster(model_file=str(ARTIFACT))

    where = f"and iss.game_date >= '{args.since}'" if args.since else ""
    sql = build_pull_sql(bq.project(), where=where)
    if args.sample:
        sql += f"\norder by farm_fingerprint(cast(iss.event_id as string)) limit {args.sample}"

    print("Pulling shots to score...")
    raw = bq.query_df(sql)
    df = build_features(raw)
    print(f"scoring {len(df):,} shots")

    dec = predict_with_decomposition(model, df)
    out = pd.concat([df[["game_id", "event_id", "season", "game_date", "team_id"]].reset_index(drop=True),
                     dec.reset_index(drop=True)], axis=1)
    out["model_version"] = MODEL_VERSION
    out = out[OUT_COLS]

    print(out[["xg", "base_rate", "xg_contrib_location", "xg_contrib_sequence"]].describe().round(4).to_string())

    if args.dry_run_write:
        print("\n--dry-run-write: not writing to BigQuery")
        return

    if args.since:
        bq.delete_partition_since(TABLE, "game_date", args.since)
        bq.write_df(out, TABLE, write_disposition="WRITE_APPEND", clustering_fields=["season", "team_id"])
        print(f"appended {len(out):,} rows to nhl_models.{TABLE} (>= {args.since})")
    else:
        bq.write_df(out, TABLE, write_disposition="WRITE_TRUNCATE", clustering_fields=["season", "team_id"])
        print(f"wrote {len(out):,} rows to nhl_models.{TABLE} (full rescore)")


if __name__ == "__main__":
    main()
