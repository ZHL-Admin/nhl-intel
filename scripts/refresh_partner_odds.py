"""Snapshot partner sportsbook odds into BigQuery (INTERNAL CALIBRATION ONLY).

Fetches /v1/partner-game/{country}/now and appends one snapshot row to
nhl_raw.raw_partner_odds. Per blueprint 13.2 this data is for internal
win-probability calibration only; it is never exposed via API or UI.

In the offseason the games[] array is empty; the snapshot row is still appended so
the cadence is exercised, but stg_partner_odds will yield no rows until games return.

Usage:
    python -m scripts.refresh_partner_odds --country US
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from ingestion.nhl_api import get_partner_odds
from ingestion.loaders import load_json_to_bigquery

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

PROJECT = os.environ["GCP_PROJECT_ID"]
DATASET_RAW = os.environ.get("GCP_DATASET_RAW", "nhl_raw")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--country", default="US")
    args = ap.parse_args()

    payload = get_partner_odds(args.country)
    n_games = len(payload.get("games", []))
    logger.info("Partner odds snapshot: date=%s games=%d",
                payload.get("currentOddsDate"), n_games)
    load_json_to_bigquery(PROJECT, DATASET_RAW, "raw_partner_odds", payload)
    logger.info("Appended 1 snapshot to raw_partner_odds (%d games)", n_games)


if __name__ == "__main__":
    main()
