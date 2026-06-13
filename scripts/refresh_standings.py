"""Ingest league standings-by-date into BigQuery.

Fetches /v1/standings/{date} for each date in a range and loads the 32 team rows
per date to nhl_raw.raw_standings. Used both for the daily DAG (single date) and
for backfilling the current and prior season.

Resumable: skips dates already present unless --force.

Usage:
    python -m scripts.refresh_standings --date 2026-01-15            # single date
    python -m scripts.refresh_standings --start 2025-10-01 --end 2026-04-20
    python -m scripts.refresh_standings --season 2024-25            # full season window
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
import time
from datetime import date, timedelta
from pathlib import Path

from google.cloud import bigquery

sys.path.insert(0, str(Path(__file__).parent.parent))

from ingestion.nhl_api import get_standings_by_date
from ingestion.loaders import load_json_to_bigquery

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

PROJECT = os.environ["GCP_PROJECT_ID"]
DATASET_RAW = os.environ.get("GCP_DATASET_RAW", "nhl_raw")

# Standard NHL season window (regular season + playoffs) for --season backfills.
SEASON_WINDOWS = {"start_month": 10, "start_day": 1, "end_month": 6, "end_day": 30}


def _season_to_dates(season: str) -> tuple[date, date]:
    start_year = int(season[:4])
    return (date(start_year, 10, 1), date(start_year + 1, 6, 30))


def _existing_dates(client: bigquery.Client) -> set[str]:
    try:
        sql = f"SELECT DISTINCT date FROM `{PROJECT}.{DATASET_RAW}.raw_standings`"
        return {r.date for r in client.query(sql).result()}
    except Exception:
        return set()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", help="Single date YYYY-MM-DD")
    ap.add_argument("--start", help="Range start YYYY-MM-DD")
    ap.add_argument("--end", help="Range end YYYY-MM-DD")
    ap.add_argument("--season", help="Season YYYY-YY (expands to Oct 1 .. Jun 30)")
    ap.add_argument("--step-days", type=int, default=1)
    ap.add_argument("--sleep-ms", type=int, default=80)
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()

    if args.date:
        start = end = date.fromisoformat(args.date)
    elif args.season:
        start, end = _season_to_dates(args.season)
    elif args.start and args.end:
        start, end = date.fromisoformat(args.start), date.fromisoformat(args.end)
    else:
        ap.error("provide --date, --season, or --start/--end")

    client = bigquery.Client(project=PROJECT)
    done = set() if args.force else _existing_dates(client)

    rows: list[dict] = []
    d, n_dates = start, 0
    while d <= end:
        ds = d.isoformat()
        if ds not in done:
            try:
                payload = get_standings_by_date(ds)
                teams = payload.get("standings", [])
                rows.extend(teams)
                if teams:
                    n_dates += 1
            except Exception as e:  # noqa: BLE001
                logger.warning("standings %s failed: %s", ds, str(e)[:80])
            time.sleep(args.sleep_ms / 1000.0)
        d += timedelta(days=args.step_days)

    if rows:
        # Season label derived from the range start (NHL season starts in Oct).
        season = f"{start.year}-{str(start.year + 1)[2:]}" if start.month >= 7 \
            else f"{start.year - 1}-{str(start.year)[2:]}"
        load_json_to_bigquery(PROJECT, DATASET_RAW, "raw_standings", rows, season)
        logger.info("Loaded %d standings rows across %d dates", len(rows), n_dates)
    else:
        logger.info("No new standings rows to load.")


if __name__ == "__main__":
    main()
