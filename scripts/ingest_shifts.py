"""Ingest NHL shift-chart data into BigQuery (nhl_raw.raw_shift_charts).

Resumable: skips game_ids already present in raw_shift_charts. One row per game,
the shift array stored as a serialized JSON string (parsed by stg_shifts).

Usage:
    python -m scripts.ingest_shifts --season 2025-26 --limit 100
    python -m scripts.ingest_shifts --all          # every final game not yet ingested
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
import time
from pathlib import Path

from google.cloud import bigquery

sys.path.insert(0, str(Path(__file__).parent.parent))

from ingestion.nhl_api import get_shift_charts
from ingestion.loaders import load_json_to_bigquery

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

PROJECT = os.environ["GCP_PROJECT_ID"]
DATASET_RAW = os.environ.get("GCP_DATASET_RAW", "nhl_raw")
DATASET_STAGING = os.environ.get("GCP_DATASET_STAGING", "nhl_staging")


def _season_str(game_id: int) -> str:
    s = str(game_id)
    y = int(s[:4])
    return f"{y}-{str(y + 1)[2:]}"


def _games_to_ingest(client: bigquery.Client, season: str | None, limit: int | None) -> list[int]:
    """Final game ids present in staging but missing from raw_shift_charts."""
    season_filter = f"AND b.season = '{season}'" if season else ""
    limit_clause = f"LIMIT {limit}" if limit else ""
    sql = f"""
        SELECT b.game_id
        FROM `{PROJECT}.{DATASET_STAGING}.stg_boxscores` b
        WHERE b.game_id NOT IN (
            SELECT game_id FROM `{PROJECT}.{DATASET_RAW}.raw_shift_charts`
        )
        {season_filter}
        ORDER BY b.game_id DESC
        {limit_clause}
    """
    try:
        return [int(r.game_id) for r in client.query(sql).result()]
    except Exception:
        # raw_shift_charts may not exist yet on the very first run.
        sql_first = f"""
            SELECT b.game_id FROM `{PROJECT}.{DATASET_STAGING}.stg_boxscores` b
            WHERE 1=1 {season_filter} ORDER BY b.game_id DESC {limit_clause}
        """
        return [int(r.game_id) for r in client.query(sql_first).result()]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--season", help="Season 'YYYY-YY', e.g. 2025-26")
    ap.add_argument("--limit", type=int, help="Max games to ingest this run")
    ap.add_argument("--all", action="store_true", help="Ingest every missing final game")
    ap.add_argument("--sleep", type=float, default=0.4, help="Seconds between requests")
    args = ap.parse_args()

    client = bigquery.Client(project=PROJECT)
    game_ids = _games_to_ingest(client, args.season, None if args.all else (args.limit or 50))
    logger.info("Games to ingest: %d", len(game_ids))

    ok = 0
    for i, gid in enumerate(game_ids, 1):
        try:
            payload = get_shift_charts(gid)
            row = {"id": gid, "game_id": gid, "data": payload.get("data", [])}
            load_json_to_bigquery(PROJECT, DATASET_RAW, "raw_shift_charts", row, _season_str(gid))
            ok += 1
            if i % 25 == 0:
                logger.info("  %d/%d ingested", i, len(game_ids))
        except Exception as e:  # noqa: BLE001 - log and continue, resumable
            logger.warning("  game %s failed: %s", gid, e)
        time.sleep(args.sleep)

    logger.info("Done: %d/%d games ingested into raw_shift_charts", ok, len(game_ids))


if __name__ == "__main__":
    main()
