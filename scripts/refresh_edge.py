"""Refresh NHL Edge season aggregates into BigQuery raw tables.

Iterates the season's roster skaters/goalies (from stg_rosters) and all teams that
played (from stg_boxscores), fetches every Edge report per entity, and loads them to
nhl_raw.raw_edge_skaters / raw_edge_goalies / raw_edge_teams. One row per
(entity_id, season_id, game_type, report) with the payload serialized.

Resumable: skips (entity_id, season_id, game_type, report) tuples already present.
Rate-limited: --sleep-ms between requests (stats hosts are sensitive).

Usage:
    python -m scripts.refresh_edge --season 2025-26                 # full refresh
    python -m scripts.refresh_edge --season 2024-25 --limit 15      # small sample
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

from ingestion.nhl_api import (
    get_edge_detail,
    EDGE_SKATER_REPORTS,
    EDGE_GOALIE_REPORTS,
    EDGE_TEAM_REPORTS,
)
from ingestion.loaders import load_json_to_bigquery

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

PROJECT = os.environ["GCP_PROJECT_ID"]
DATASET_RAW = os.environ.get("GCP_DATASET_RAW", "nhl_raw")
DATASET_STAGING = os.environ.get("GCP_DATASET_STAGING", "nhl_staging")


def _season_id(season: str) -> str:
    """'2025-26' -> '20252026'."""
    start = int(season[:4])
    return f"{start}{start + 1}"


def _existing(client: bigquery.Client, table: str) -> set:
    """Set of (entity_id, season_id, game_type, report) already ingested."""
    try:
        sql = f"SELECT DISTINCT entity_id, season_id, game_type, report FROM `{PROJECT}.{DATASET_RAW}.{table}`"
        return {(r.entity_id, r.season_id, r.game_type, r.report) for r in client.query(sql).result()}
    except Exception:
        return set()


def _roster(client: bigquery.Client, season: str, limit: int | None) -> tuple[list[int], list[int]]:
    """Distinct skater and goalie player ids for the season."""
    lim = f"LIMIT {limit}" if limit else ""
    sql = f"""
        SELECT DISTINCT player_id, position_code
        FROM `{PROJECT}.{DATASET_STAGING}.stg_rosters`
        WHERE season = '{season}' AND player_id IS NOT NULL
        ORDER BY player_id {lim}
    """
    skaters, goalies = [], []
    for r in client.query(sql).result():
        (goalies if r.position_code == "G" else skaters).append(int(r.player_id))
    return skaters, goalies


def _teams(client: bigquery.Client, season: str) -> list[int]:
    sql = f"""
        SELECT DISTINCT home_team_id FROM `{PROJECT}.{DATASET_STAGING}.stg_boxscores`
        WHERE season = '{season}' AND home_team_id IS NOT NULL
    """
    return [int(r.home_team_id) for r in client.query(sql).result()]


def _ingest(client, entity, table, ids, reports, season, season_id, game_type, done,
            rows_by_table, sleep_ms, flush_size=500, loaded_counts=None):
    """Fetch+stage Edge reports for a set of entities, flushing to BigQuery every
    flush_size rows so a long backfill is durable/resumable mid-run (skips None 404s)."""
    for eid in ids:
        for report in reports:
            if (eid, season_id, game_type, report) in done:
                continue
            try:
                payload = get_edge_detail(entity, eid, season_id, game_type, report)
            except Exception as e:  # noqa: BLE001
                logger.warning("  %s %s %s failed: %s", entity, eid, report, str(e)[:60])
                continue
            if payload is None:  # 404 — entity has no Edge data for this report
                continue
            rows_by_table[table].append({
                "entity_id": eid, "season_id": season_id,
                "game_type": game_type, "report": report, "data": payload,
            })
            if len(rows_by_table[table]) >= flush_size:
                load_json_to_bigquery(PROJECT, DATASET_RAW, table, rows_by_table[table], season)
                if loaded_counts is not None:
                    loaded_counts[table] = loaded_counts.get(table, 0) + len(rows_by_table[table])
                logger.info("  flushed %d rows to %s", len(rows_by_table[table]), table)
                rows_by_table[table] = []
            time.sleep(sleep_ms / 1000.0)


def refresh_season(client: bigquery.Client, season: str, game_type: int = 2,
                   limit: int | None = None, sleep_ms: int = 100) -> int:
    """Refresh all Edge reports for one season. Returns total rows loaded.

    Resumable: skips (entity, season, game_type, report) tuples already present.
    Reused by backfill_edge.py to sweep multiple seasons.
    """
    season_id = _season_id(season)
    skaters, goalies = _roster(client, season, limit)
    teams = _teams(client, season) if not limit else _teams(client, season)[: max(1, limit // 3)]
    logger.info("Refreshing Edge %s (gt=%d): %d skaters, %d goalies, %d teams",
                season, game_type, len(skaters), len(goalies), len(teams))

    rows_by_table = {"raw_edge_skaters": [], "raw_edge_goalies": [], "raw_edge_teams": []}
    loaded_counts: dict[str, int] = {}
    _ingest(client, "skater", "raw_edge_skaters", skaters, EDGE_SKATER_REPORTS, season, season_id, game_type, _existing(client, "raw_edge_skaters"), rows_by_table, sleep_ms, loaded_counts=loaded_counts)
    _ingest(client, "goalie", "raw_edge_goalies", goalies, EDGE_GOALIE_REPORTS, season, season_id, game_type, _existing(client, "raw_edge_goalies"), rows_by_table, sleep_ms, loaded_counts=loaded_counts)
    _ingest(client, "team", "raw_edge_teams", teams, EDGE_TEAM_REPORTS, season, season_id, game_type, _existing(client, "raw_edge_teams"), rows_by_table, sleep_ms, loaded_counts=loaded_counts)

    # Flush any remaining (< flush_size) rows per table.
    for table, rows in rows_by_table.items():
        if rows:
            load_json_to_bigquery(PROJECT, DATASET_RAW, table, rows, season)
            loaded_counts[table] = loaded_counts.get(table, 0) + len(rows)
    total = sum(loaded_counts.values())
    logger.info("Season %s loaded: %s (total %d)", season, dict(loaded_counts), total)
    return total


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--season", default="2025-26")
    ap.add_argument("--game-type", type=int, default=2)
    ap.add_argument("--limit", type=int, help="Cap roster entities (for sampling)")
    ap.add_argument("--sleep-ms", type=int, default=100)
    args = ap.parse_args()

    client = bigquery.Client(project=PROJECT)
    refresh_season(client, args.season, args.game_type, args.limit, args.sleep_ms)
    logger.info("Edge refresh complete.")


if __name__ == "__main__":
    main()
