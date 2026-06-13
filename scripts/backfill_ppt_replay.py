"""Backfill ppt-replay goal tracking sprites into BigQuery.

For every goal in scope (all goals of the current and prior season, matching the
landing/right-rail window in Phase 1.3), fetches the two-hop ppt-replay payload
(metadata -> wsr.nhle.com sprite) and loads one row per (game_id, event_id) into
nhl_raw.raw_ppt_replay.

Resumable: skips (game_id, event_id) pairs already present. Throttled: the wsr host
is sensitive, so we sleep >= --sleep-ms (default 1100ms ~= <=1 req/sec) between goals;
tenacity handles 429s with exponential backoff inside get_ppt_replay. Batch-flushes to
BigQuery so a long run is durable mid-stream. Sprites are also cached on disk by
get_ppt_replay, so a re-run after an interruption is cheap.

NOTE: non-goal events expose the same ev{eventId}.json sprite scheme, so scope could
later widen beyond goals; goals are the chosen floor (highest value, bounded volume).

Usage:
    python -m scripts.backfill_ppt_replay --seasons 2024-25 2025-26
    python -m scripts.backfill_ppt_replay --game-id 2025030414     # single game
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

from ingestion.nhl_api import get_ppt_replay
from ingestion.loaders import load_json_to_bigquery

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)
logging.getLogger("httpx").setLevel(logging.WARNING)

PROJECT = os.environ["GCP_PROJECT_ID"]
DATASET_RAW = os.environ.get("GCP_DATASET_RAW", "nhl_raw")
DATASET_STAGING = os.environ.get("GCP_DATASET_STAGING", "nhl_staging")

DEFAULT_SEASONS = ["2024-25", "2025-26"]


def _goals(client: bigquery.Client, seasons: list[str], game_id: int | None) -> list[tuple[int, int, str]]:
    """List (game_id, event_id, season) for every goal in scope."""
    if game_id:
        where = f"game_id = {game_id}"
    else:
        season_list = ", ".join(f"'{s}'" for s in seasons)
        where = f"season IN ({season_list})"
    sql = f"""
        SELECT game_id, event_id, season
        FROM `{PROJECT}.{DATASET_STAGING}.stg_play_by_play`
        WHERE {where} AND type_desc_key = 'goal' AND event_id IS NOT NULL
        ORDER BY game_id, event_id
    """
    return [(int(r.game_id), int(r.event_id), r.season) for r in client.query(sql).result()]


def _existing(client: bigquery.Client) -> set[tuple[int, int]]:
    try:
        sql = f"SELECT DISTINCT game_id, event_id FROM `{PROJECT}.{DATASET_RAW}.raw_ppt_replay`"
        return {(int(r.game_id), int(r.event_id)) for r in client.query(sql).result()}
    except Exception:
        return set()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seasons", nargs="+", default=DEFAULT_SEASONS)
    ap.add_argument("--game-id", type=int, help="Single game (overrides --seasons)")
    ap.add_argument("--sleep-ms", type=int, default=1100, help="Throttle between goals (>=1 req/sec)")
    ap.add_argument("--batch-size", type=int, default=100, help="Flush to BigQuery every N sprites")
    args = ap.parse_args()

    client = bigquery.Client(project=PROJECT)
    goals = _goals(client, args.seasons, args.game_id)
    done = _existing(client)
    todo = [g for g in goals if (g[0], g[1]) not in done]
    logger.info("Goals in scope: %d total, %d already ingested, %d to fetch.",
                len(goals), len(goals) - len(todo), len(todo))

    batch: list[dict] = []
    by_season_loaded: dict[str, int] = {}
    total = 0

    def flush():
        nonlocal batch, total
        if not batch:
            return
        # Load grouped by season so the loader stamps the right season label.
        from collections import defaultdict
        groups: dict[str, list[dict]] = defaultdict(list)
        for row in batch:
            groups[row.pop("_season")].append(row)
        for season, rows in groups.items():
            load_json_to_bigquery(PROJECT, DATASET_RAW, "raw_ppt_replay", rows, season)
            by_season_loaded[season] = by_season_loaded.get(season, 0) + len(rows)
        total += len(batch)
        logger.info("Flushed batch (cumulative loaded: %d)", total)
        batch = []

    for game_id, event_id, season in todo:
        try:
            payload = get_ppt_replay(game_id, event_id)
        except Exception as e:  # noqa: BLE001
            logger.warning("ppt-replay %s/%s failed: %s", game_id, event_id, str(e)[:80])
            payload = None
        if payload:
            payload["_season"] = season
            batch.append(payload)
        if len(batch) >= args.batch_size:
            flush()
        time.sleep(args.sleep_ms / 1000.0)

    flush()
    logger.info("ppt-replay backfill complete: %d sprites loaded.", total)
    for season in sorted(by_season_loaded):
        logger.info("  %s: %d goal sprites", season, by_season_loaded[season])


if __name__ == "__main__":
    main()
