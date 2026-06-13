"""Ingest the NHL stats-REST glossary into BigQuery (one-time).

Fetches api.nhle.com/stats/rest/en/glossary and loads the term records to
nhl_raw.raw_glossary for Phase 6 concept cards. Run once (re-run with --force to
refresh definitions). Note: the api-web /v1/glossary path is dead (404); the live
glossary is on the stats-REST host.

Usage:
    python -m scripts.ingest_glossary
    python -m scripts.ingest_glossary --force
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from pathlib import Path

from google.cloud import bigquery

sys.path.insert(0, str(Path(__file__).parent.parent))

from ingestion.nhl_api import get_glossary
from ingestion.loaders import load_json_to_bigquery

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

PROJECT = os.environ["GCP_PROJECT_ID"]
DATASET_RAW = os.environ.get("GCP_DATASET_RAW", "nhl_raw")


def _already_present(client: bigquery.Client) -> bool:
    try:
        sql = f"SELECT COUNT(*) AS n FROM `{PROJECT}.{DATASET_RAW}.raw_glossary`"
        return next(iter(client.query(sql).result())).n > 0
    except Exception:
        return False


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()

    client = bigquery.Client(project=PROJECT)
    if not args.force and _already_present(client):
        logger.info("Glossary already present; use --force to refresh.")
        return

    records = get_glossary().get("data", [])
    logger.info("Fetched %d glossary terms; loading...", len(records))
    if records:
        load_json_to_bigquery(PROJECT, DATASET_RAW, "raw_glossary", records)
        logger.info("Loaded %d rows to raw_glossary", len(records))


if __name__ == "__main__":
    main()
