"""Backfill NHL Edge season aggregates across all tracking-era seasons.

Sweeps a season list, calling the resumable per-season refresh from refresh_edge
for each. Resumable at the (entity, season, game_type, report) grain, so re-running
only fetches what is missing. NHL puck-and-player tracking went league-wide in
2021-22; earlier seasons return little/no Edge data and are skipped automatically
when the API yields nothing.

Usage:
    python -m scripts.backfill_edge                       # default tracking-era seasons
    python -m scripts.backfill_edge --seasons 2023-24 2024-25
    python -m scripts.backfill_edge --game-type 3         # playoffs
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from pathlib import Path

from google.cloud import bigquery

sys.path.insert(0, str(Path(__file__).parent.parent))

from scripts.refresh_edge import refresh_season

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

PROJECT = os.environ["GCP_PROJECT_ID"]

# Tracking era (league-wide puck-and-player tracking from 2021-22).
DEFAULT_SEASONS = ["2021-22", "2022-23", "2023-24", "2024-25", "2025-26"]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seasons", nargs="+", default=DEFAULT_SEASONS)
    ap.add_argument("--game-type", type=int, default=2)
    ap.add_argument("--limit", type=int, help="Cap roster entities per season (sampling)")
    ap.add_argument("--sleep-ms", type=int, default=80)
    args = ap.parse_args()

    client = bigquery.Client(project=PROJECT)
    grand_total = 0
    for season in args.seasons:
        try:
            loaded = refresh_season(client, season, args.game_type, args.limit, args.sleep_ms)
            grand_total += loaded
            logger.info("Season %s done (%d rows loaded).", season, loaded)
        except Exception as e:  # noqa: BLE001
            logger.warning("Season %s failed: %s", season, str(e)[:120])
    logger.info("Edge backfill complete: %d rows loaded across %d seasons.",
                grand_total, len(args.seasons))


if __name__ == "__main__":
    main()
