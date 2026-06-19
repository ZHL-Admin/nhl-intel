"""Ingest the player-contract CSV snapshot into nhl_raw.raw_contracts.

The contract data is a DATED SNAPSHOT (currently a scraped CSV; the schema is structured so the
source can later swap to an API with no change): every row is stamped with an `as_of_date` (the
snapshot date) and a `season` (STRING, e.g. "2025-26"). Raw stays SOURCE-FAITHFUL — the dollar
strings ("$17,000,000"), "8 yrs", "Yes/No" etc. are kept verbatim; all parsing happens in
stg_contracts. Columns are only renamed to BigQuery-safe snake_case.

Idempotent on (as_of_date, player, team): re-running the same snapshot deletes that snapshot's rows
first, then re-appends, so a re-run never duplicates and a corrected file cleanly replaces it.

Run (env: set -a && source .env && set +a && export GOOGLE_APPLICATION_CREDENTIALS=...):
    python -m scripts.load_contracts                         # ./contracts.csv, today, 2025-26
    python -m scripts.load_contracts --csv path.csv --as-of 2026-06-18 --season 2025-26
"""
from __future__ import annotations

import argparse
import os
from datetime import date

import pandas as pd
from google.cloud import bigquery

RAW_DATASET = "nhl_raw"
TABLE = "raw_contracts"

# CSV header -> BigQuery-safe column. Order preserved; values kept as source strings.
COLUMN_MAP = {
    "PLAYERS": "player_name_src",
    "TEAM": "team",
    "POS": "pos",
    "AGE": "age",
    "CAP HIT": "cap_hit",
    "TOTAL": "total",
    "AAV": "aav",
    "TERM": "term",
    "SIGN. STATUS": "sign_status",
    "SIGN. AGE": "sign_age",
    "EXPIRY": "expiry_status",
    "CONTRACT START": "contract_start",
    "EXPIRY YEAR": "expiry_year",
    "WAIVERS EXEMPT": "waivers_exempt",
    "SIGNED BY": "signed_by",
    "BASE SALARY": "base_salary",
    "SIGNING BONUS": "signing_bonus",
    "PERF BONUS": "perf_bonus",
    "TYPE": "contract_type",
}

# raw is source-faithful: every contract field is a STRING; only the stamps are typed.
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
    ap.add_argument("--csv", default="contracts.csv", help="path to the contract CSV")
    ap.add_argument("--as-of", default=date.today().isoformat(),
                    help="snapshot date YYYY-MM-DD (default: today)")
    ap.add_argument("--season", default="2025-26", help='season STRING (default "2025-26")')
    ap.add_argument("--dry-run", action="store_true", help="parse + print shape, do not load")
    args = ap.parse_args()

    df = pd.read_csv(args.csv, dtype=str).fillna("")
    missing = [c for c in COLUMN_MAP if c not in df.columns]
    if missing:
        raise SystemExit(f"CSV missing expected columns: {missing}")
    df = df[list(COLUMN_MAP)].rename(columns=COLUMN_MAP)
    df["as_of_date"] = pd.to_datetime(args.as_of).date()
    df["season"] = args.season
    df["ingested_at"] = pd.Timestamp.utcnow()

    print(f"contracts: {len(df)} rows, as_of={args.as_of}, season={args.season}")
    print(df[["player_name_src", "team", "pos", "cap_hit", "term"]].head(3).to_string(index=False))
    if args.dry_run:
        return 0

    project = os.environ["GCP_PROJECT_ID"]
    client = bigquery.Client(project=project)
    table_id = f"{project}.{RAW_DATASET}.{TABLE}"

    # Create the table with the explicit schema if it doesn't exist yet.
    try:
        client.get_table(table_id)
    except Exception:
        client.create_table(bigquery.Table(table_id, schema=SCHEMA))
        print(f"created {table_id}")

    # Idempotent: drop this snapshot's rows, then append (a re-run replaces the snapshot).
    client.query(
        f"DELETE FROM `{table_id}` WHERE as_of_date = DATE('{args.as_of}')"
    ).result()

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
