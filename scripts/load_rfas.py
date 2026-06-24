"""Ingest the pending-RFA CSV snapshot into nhl_raw.raw_contracts_rfa.

Pending RFAs (restricted free agents) are a SEPARATE feed from signed contracts (`contracts.csv` ->
raw_contracts): their current deal has expired, so the source has no signed-contract terms for them.
Instead it carries the analyst's PROJECTED next deal (proj_cap / proj_term), the qualifying offer
(qo), and last-season production (gp, toi, points). Crucially the feed has NO TEAM column — an RFA's
team is derived downstream from his latest NHL game (mart_player_contracts' RFA branch).

Raw stays SOURCE-FAITHFUL (dollar strings, "8 yrs", "20:52" kept verbatim); all parsing happens in
stg_contracts_rfa. Idempotent on as_of_date (a re-run replaces the snapshot).

Run (env: set -a && source .env && set +a && export GOOGLE_APPLICATION_CREDENTIALS=...):
    python -m scripts.load_rfas                                  # ./contracts - rfas.csv, today, 2025-26
    python -m scripts.load_rfas --csv "path.csv" --as-of 2026-06-18 --season 2025-26
"""
from __future__ import annotations

import argparse
import os
from datetime import date

import pandas as pd
from google.cloud import bigquery

RAW_DATASET = "nhl_raw"
TABLE = "raw_contracts_rfa"

# CSV header -> BigQuery-safe column. Order preserved; values kept as source strings. NOTE: no TEAM.
COLUMN_MAP = {
    "PLAYERS": "player_name_src",
    "POS": "pos",
    "HAND": "hand",
    "BIRTHPLACE": "birthplace",
    "AGE": "age",
    "PROJ. CAP": "proj_cap",
    "PROJ. TERM": "proj_term",
    "GP": "gp",
    "TOI": "toi",
    "P": "points",
    "P/G": "points_per_game",
    "CAP": "current_cap",
    "QO": "qo",
}

SCHEMA = (
    [bigquery.SchemaField(c, "STRING") for c in COLUMN_MAP.values()]
    + [
        bigquery.SchemaField("as_of_date", "DATE"),
        bigquery.SchemaField("season", "STRING"),
        bigquery.SchemaField("ingested_at", "TIMESTAMP"),
    ]
)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--csv", default="contracts - rfas.csv", help="path to the pending-RFA CSV")
    ap.add_argument("--as-of", default=date.today().isoformat(),
                    help="snapshot date YYYY-MM-DD (default: today)")
    ap.add_argument("--season", default="2025-26", help='season STRING (default "2025-26")')
    ap.add_argument("--dry-run", action="store_true", help="parse + print shape, do not load")
    args = ap.parse_args()

    df = pd.read_csv(args.csv, dtype=str).fillna("")
    missing = [c for c in COLUMN_MAP if c not in df.columns]
    if missing:
        raise SystemExit(f"RFA CSV missing expected columns: {missing}")
    df = df[list(COLUMN_MAP)].rename(columns=COLUMN_MAP)
    df["as_of_date"] = pd.to_datetime(args.as_of).date()
    df["season"] = args.season
    df["ingested_at"] = pd.Timestamp.utcnow()

    print(f"RFAs: {len(df)} rows, as_of={args.as_of}, season={args.season}")
    print(df[["player_name_src", "pos", "proj_cap", "proj_term", "qo"]].head(3).to_string(index=False))
    if args.dry_run:
        return 0

    project = os.environ["GCP_PROJECT_ID"]
    client = bigquery.Client(project=project)
    table_id = f"{project}.{RAW_DATASET}.{TABLE}"

    try:
        client.get_table(table_id)
    except Exception:
        client.create_table(bigquery.Table(table_id, schema=SCHEMA))
        print(f"created {table_id}")

    client.query(f"DELETE FROM `{table_id}` WHERE as_of_date = DATE('{args.as_of}')").result()
    job = client.load_table_from_dataframe(
        df, table_id,
        job_config=bigquery.LoadJobConfig(schema=SCHEMA,
                                          write_disposition=bigquery.WriteDisposition.WRITE_APPEND))
    job.result()
    n = list(client.query(f"SELECT COUNT(*) n FROM `{table_id}`").result())[0].n
    print(f"loaded {len(df)} rows -> {table_id} (table now {n} rows total)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
