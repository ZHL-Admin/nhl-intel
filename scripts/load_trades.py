"""Ingest the historical trades CSV snapshot into nhl_raw.raw_trades (Handoff 5, Phase D).

A DATED SNAPSHOT, exactly like load_contracts.py: one row per ASSET moved in a trade (grouped by
trade_id; acquiring_team is the team that RECEIVED that asset). Raw stays SOURCE-FAITHFUL — every
field is kept as a verbatim string ("2016 3rd Round", "Future Considerations", the conditional flag in
notes); all parsing/typing/resolution happens downstream in stg_trades. Columns are only renamed to
BigQuery-safe snake_case and stamped with as_of_date + ingested_at.

Idempotent per as_of_date: re-running the same snapshot deletes that snapshot's rows, then re-appends.

Provenance: a cleaned historical-trades export, 2015-16..2025-26, 1,304 trades. Asset Type is one of
Player / Draft Pick / Other ("Future Considerations"). Draft picks are round-only ("YYYY Nth Round") —
no overall pick, no original owner.

Run (env: set -a && source .env && set +a && export GOOGLE_APPLICATION_CREDENTIALS=...):
    python -m scripts.load_trades                                 # ./Trades 2015-2026.csv, today
    python -m scripts.load_trades --csv path.csv --as-of 2026-06-25
    python -m scripts.load_trades --dry-run
"""
from __future__ import annotations

import argparse
import os
from datetime import date

import pandas as pd
from google.cloud import bigquery

RAW_DATASET = "nhl_raw"
TABLE = "raw_trades"
DEFAULT_CSV = "Trades 2015-2026.csv"

# CSV header -> BigQuery-safe column. Order preserved; values kept as source strings.
COLUMN_MAP = {
    "Season": "season",
    "TradeID": "trade_id",
    "Date": "trade_date",
    "Trade": "trade_label",
    "Acquiring Team": "acquiring_team",
    "Asset Type": "asset_type",
    "Asset": "asset",
    "Position": "position",
    "Notes": "notes",
}

# raw is source-faithful: every trade field is a STRING; only the stamps are typed.
SCHEMA = (
    [bigquery.SchemaField(c, "STRING") for c in COLUMN_MAP.values()]
    + [
        bigquery.SchemaField("as_of_date", "DATE"),
        bigquery.SchemaField("ingested_at", "TIMESTAMP"),
    ]
)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--csv", default=DEFAULT_CSV, help="path to the trades CSV")
    ap.add_argument("--as-of", default=date.today().isoformat(),
                    help="snapshot date YYYY-MM-DD (default: today)")
    ap.add_argument("--dry-run", action="store_true", help="parse + print shape, do not load")
    args = ap.parse_args()

    df = pd.read_csv(args.csv, dtype=str).fillna("")
    missing = [c for c in COLUMN_MAP if c not in df.columns]
    if missing:
        raise SystemExit(f"CSV missing expected columns: {missing}")
    df = df[list(COLUMN_MAP)].rename(columns=COLUMN_MAP)
    # drop fully-blank rows (the source has one stray empty Asset Type row with no asset)
    blank = (df["trade_id"].str.strip() == "")
    if blank.any():
        print(f"dropping {int(blank.sum())} blank row(s)")
        df = df[~blank]
    df["as_of_date"] = pd.to_datetime(args.as_of).date()
    df["ingested_at"] = pd.Timestamp.utcnow()

    n_trades = df["trade_id"].nunique()
    print(f"trades: {len(df)} asset-rows across {n_trades} trades, as_of={args.as_of}")
    print(df["asset_type"].value_counts().to_string())
    print(df[["trade_id", "acquiring_team", "asset_type", "asset", "position"]].head(4).to_string(index=False))
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
                                          write_disposition=bigquery.WriteDisposition.WRITE_APPEND),
    )
    job.result()
    n = list(client.query(f"SELECT COUNT(*) n FROM `{table_id}`").result())[0].n
    print(f"loaded {len(df)} rows -> {table_id} (table now {n} rows total)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
