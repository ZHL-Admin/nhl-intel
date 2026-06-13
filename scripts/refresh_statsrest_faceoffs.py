"""Refresh season-level stats-REST faceoff splits into BigQuery.

Fetches every skater's faceoffwins record for a season (paged) and loads them to
nhl_raw.raw_statsrest_faceoffs, injecting game_type into each row so the staging
model can dedupe on (player, season, game_type).

Resumable at the season grain: skips a (season_id, game_type) already present unless
--force is passed (season aggregates are immutable once the season is over; an
in-progress season should be re-pulled with --force).

Usage:
    python -m scripts.refresh_statsrest_faceoffs --season 2024-25
    python -m scripts.refresh_statsrest_faceoffs --season 2025-26 --game-type 3 --force
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from pathlib import Path

from google.cloud import bigquery

sys.path.insert(0, str(Path(__file__).parent.parent))

from ingestion.nhl_api import get_skater_faceoffs
from ingestion.loaders import load_json_to_bigquery

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

PROJECT = os.environ["GCP_PROJECT_ID"]
DATASET_RAW = os.environ.get("GCP_DATASET_RAW", "nhl_raw")


def _season_id(season: str) -> str:
    start = int(season[:4])
    return f"{start}{start + 1}"


def _already_present(client: bigquery.Client, season_id: str, game_type: int) -> bool:
    try:
        sql = f"""
            SELECT COUNT(*) AS n FROM `{PROJECT}.{DATASET_RAW}.raw_statsrest_faceoffs`
            WHERE seasonId = {season_id} AND game_type = {game_type}
        """
        return next(iter(client.query(sql).result())).n > 0
    except Exception:
        return False


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--season", default="2024-25")
    ap.add_argument("--game-type", type=int, default=2)
    ap.add_argument("--force", action="store_true", help="Re-pull even if rows exist")
    args = ap.parse_args()

    client = bigquery.Client(project=PROJECT)
    season_id = _season_id(args.season)

    if not args.force and _already_present(client, season_id, args.game_type):
        logger.info("Faceoffs for %s gt=%d already present; use --force to re-pull.",
                    season_id, args.game_type)
        return

    logger.info("Fetching faceoffwins for %s (gt=%d)...", season_id, args.game_type)
    records = get_skater_faceoffs(season_id, args.game_type)
    for r in records:
        r["game_type"] = args.game_type
    logger.info("Fetched %d player records; loading...", len(records))

    if records:
        load_json_to_bigquery(PROJECT, DATASET_RAW, "raw_statsrest_faceoffs", records, args.season)
        logger.info("Loaded %d rows to raw_statsrest_faceoffs", len(records))
    else:
        logger.warning("No records returned for %s gt=%d", season_id, args.game_type)


if __name__ == "__main__":
    main()
