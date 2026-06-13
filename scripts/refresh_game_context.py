"""Ingest gamecenter landing + right-rail context into BigQuery.

For each final game in a season (from stg_games), fetches /landing and /right-rail
and loads them to nhl_raw.raw_game_landing / raw_game_right_rail. The right-rail
payload has no top-level id, so game_id is injected here (the loader injects it for
landing automatically from the payload's id field).

Scope per blueprint 13.5: current + previous season only (older games don't need
preview context). Resumable: skips game ids already present in both tables.

Usage:
    python -m scripts.refresh_game_context --season 2025-26
    python -m scripts.refresh_game_context --game-id 2025030414   # single game
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

from ingestion.nhl_api import get_game_landing, get_game_right_rail
from ingestion.loaders import load_json_to_bigquery

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

PROJECT = os.environ["GCP_PROJECT_ID"]
DATASET_RAW = os.environ.get("GCP_DATASET_RAW", "nhl_raw")
DATASET_STAGING = os.environ.get("GCP_DATASET_STAGING", "nhl_staging")


def _season_games(client: bigquery.Client, season: str) -> list[int]:
    sql = f"""
        SELECT DISTINCT game_id FROM `{PROJECT}.{DATASET_STAGING}.stg_games`
        WHERE season = '{season}' AND game_state IN ('OFF', 'FINAL')
        ORDER BY game_id
    """
    return [int(r.game_id) for r in client.query(sql).result()]


def _existing(client: bigquery.Client, table: str) -> set[int]:
    try:
        sql = f"SELECT DISTINCT game_id FROM `{PROJECT}.{DATASET_RAW}.{table}`"
        return {int(r.game_id) for r in client.query(sql).result()}
    except Exception:
        return set()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--season", default="2025-26")
    ap.add_argument("--game-id", type=int, help="Single game (overrides --season)")
    ap.add_argument("--sleep-ms", type=int, default=80)
    ap.add_argument("--batch-size", type=int, default=200, help="Flush to BigQuery every N games")
    args = ap.parse_args()
    logging.getLogger("httpx").setLevel(logging.WARNING)

    client = bigquery.Client(project=PROJECT)

    if args.game_id:
        game_ids = [args.game_id]
        season = f"{str(args.game_id)[:4]}-{str(int(str(args.game_id)[:4]) + 1)[2:]}"
    else:
        game_ids = _season_games(client, args.season)
        season = args.season

    have_landing = _existing(client, "raw_game_landing")
    have_rail = _existing(client, "raw_game_right_rail")

    landings, rails = [], []
    total_l, total_r = 0, 0

    def flush():
        nonlocal landings, rails, total_l, total_r
        if landings:
            load_json_to_bigquery(PROJECT, DATASET_RAW, "raw_game_landing", landings, season)
            total_l += len(landings)
        if rails:
            load_json_to_bigquery(PROJECT, DATASET_RAW, "raw_game_right_rail", rails, season)
            total_r += len(rails)
        if landings or rails:
            logger.info("Flushed batch (cumulative: %d landing, %d right-rail)", total_l, total_r)
        landings, rails = [], []

    for gid in game_ids:
        if gid not in have_landing:
            try:
                landings.append(get_game_landing(gid))
            except Exception as e:  # noqa: BLE001
                logger.warning("landing %s failed: %s", gid, str(e)[:80])
        if gid not in have_rail:
            try:
                rr = get_game_right_rail(gid)
                rr["id"] = gid          # right-rail lacks an id; inject it
                rr["game_id"] = gid
                rails.append(rr)
            except Exception as e:  # noqa: BLE001
                logger.warning("right-rail %s failed: %s", gid, str(e)[:80])
        # Flush periodically so a long backfill is durable and resumable mid-run.
        if len(landings) >= args.batch_size or len(rails) >= args.batch_size:
            flush()
        time.sleep(args.sleep_ms / 1000.0)

    flush()
    if total_l or total_r:
        logger.info("Done: loaded %d landing, %d right-rail rows", total_l, total_r)
    else:
        logger.info("Nothing to load (all %d games already present).", len(game_ids))


if __name__ == "__main__":
    main()
