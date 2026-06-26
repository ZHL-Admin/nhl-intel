"""Ingest the curated GM-tenures CSV into nhl_raw.raw_gm_tenures (Handoff 6, GM layer).

GM attribution is not in any feed — front-office history is curated, exactly like the contracts CSV.
One row per GM stint (a GM with multiple teams or a return has multiple rows sharing one gm_id). A
DATED SNAPSHOT: raw stays source-faithful (dates kept as strings, parsed in stg_gm_tenures); only the
stamps are typed. Idempotent per as_of_date.

This is the SOURCE OF TRUTH for GM attribution and is flagged as curated everywhere it surfaces — the
GM is the decision-maker of record, not the sole one, and tenure dates are approximate near handovers.

Run (env: set -a && source .env && set +a && export GOOGLE_APPLICATION_CREDENTIALS=...):
    python -m scripts.load_gm_tenures                          # ./gm_tenures.csv, today
    python -m scripts.load_gm_tenures --csv path.csv --as-of 2026-06-25
    python -m scripts.load_gm_tenures --dry-run
"""
from __future__ import annotations

import argparse
import os
from datetime import date

import pandas as pd
from google.cloud import bigquery

RAW_DATASET = "nhl_raw"
TABLE = "raw_gm_tenures"
DEFAULT_CSV = "gm_tenures.csv"

# CSV header -> BigQuery column (already snake_case; kept as source strings).
COLUMNS = ["gm_id", "gm_name", "team_abbrev", "start_date", "end_date", "title", "note"]


def read_gm_csv(path: str) -> pd.DataFrame:
    """Robust read of the curated CSV: `note` (the last column) may contain unquoted commas, so split
    on the first len(COLUMNS)-1 commas and let `note` absorb the remainder. Earlier columns
    (gm_id/name/team/dates/title) never contain commas."""
    rows = []
    with open(path, encoding="utf-8") as f:
        header = f.readline().rstrip("\n").split(",")
        if header[: len(COLUMNS)] != COLUMNS:
            raise SystemExit(f"unexpected CSV header: {header}")
        for line in f:
            line = line.rstrip("\n")
            if not line.strip():
                continue
            parts = line.split(",", len(COLUMNS) - 1)
            parts += [""] * (len(COLUMNS) - len(parts))
            rows.append(parts[: len(COLUMNS)])
    return pd.DataFrame(rows, columns=COLUMNS)

SCHEMA = (
    [bigquery.SchemaField(c, "STRING") for c in COLUMNS]
    + [
        bigquery.SchemaField("as_of_date", "DATE"),
        bigquery.SchemaField("ingested_at", "TIMESTAMP"),
    ]
)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--csv", default=DEFAULT_CSV, help="path to the GM-tenures CSV")
    ap.add_argument("--as-of", default=date.today().isoformat(),
                    help="snapshot date YYYY-MM-DD (default: today)")
    ap.add_argument("--dry-run", action="store_true", help="parse + print shape, do not load")
    args = ap.parse_args()

    df = read_gm_csv(args.csv).fillna("")
    df = df[df["gm_id"].str.strip() != ""]
    df["as_of_date"] = pd.to_datetime(args.as_of).date()
    df["ingested_at"] = pd.Timestamp.utcnow()

    print(f"gm tenures: {len(df)} rows, {df['gm_id'].nunique()} GMs, {df['team_abbrev'].nunique()} teams, "
          f"as_of={args.as_of}")
    print(df[["gm_id", "team_abbrev", "start_date", "end_date", "title"]].head(4).to_string(index=False))
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
    client.load_table_from_dataframe(
        df, table_id,
        job_config=bigquery.LoadJobConfig(schema=SCHEMA,
                                          write_disposition=bigquery.WriteDisposition.WRITE_APPEND),
    ).result()
    n = list(client.query(f"SELECT COUNT(*) n FROM `{table_id}`").result())[0].n
    print(f"loaded {len(df)} rows -> {table_id} (table now {n} rows total)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
