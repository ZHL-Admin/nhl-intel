"""Refresh live team rosters into the BigQuery raw table nhl_raw.raw_rosters.

Iterates the 32 current franchises and fetches each team's CURRENT active roster from
api-web (resolved as max(/roster-season) -> /roster/{TEAM}/{season8}; see
scripts/ROSTER_FINDINGS.md for why we don't use the /current 307). One row per
(team_abbrev, ingestion_date): the {forwards, defensemen, goalies} arrays are stored
serialized, plus scalar team_abbrev + season8. The "season" column is the human form of
the RESOLVED season, so offseason runs label rows with the new season the moment NHL
publishes it.

This is a MEMBERSHIP feed: it fixes a player's team LABEL before he dresses for a game.
It does NOT update performance — a just-traded player keeps old-team impact/value until
he plays. Transformation/dedup happens in dbt (stg_roster_current keeps the newest
ingestion per player); this script only lands raw snapshots.

Resumable: re-running the same day skips teams already ingested for today's
ingestion_date. Polite: sequential fetch with --sleep-ms between teams (well under the
api-web concurrency budget; 32 tiny calls).

Usage:
    python -m scripts.refresh_rosters                      # all 32 teams, current roster
    python -m scripts.refresh_rosters --limit 3            # small sample
    python -m scripts.refresh_rosters --season 2024-25     # team-list source season
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

from ingestion.nhl_api import api8_to_season, get_roster
from ingestion.loaders import load_json_to_bigquery

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

PROJECT = os.environ["GCP_PROJECT_ID"]
DATASET_RAW = os.environ.get("GCP_DATASET_RAW", "nhl_raw")
DATASET_MART = os.environ.get("GCP_DATASET_MART", "nhl_mart")

TABLE = "raw_rosters"


def _team_abbrevs(client: bigquery.Client, season: str, limit: int | None) -> list[str]:
    """The current franchises — teams that actually played in the given season."""
    lim = f"LIMIT {limit}" if limit else ""
    sql = f"""
        SELECT DISTINCT team_abbrev
        FROM `{PROJECT}.{DATASET_MART}.mart_team_game_stats`
        WHERE season = '{season}' AND team_abbrev IS NOT NULL
        ORDER BY team_abbrev {lim}
    """
    return [r.team_abbrev for r in client.query(sql).result() if r.team_abbrev]


def _done_today(client: bigquery.Client) -> set[str]:
    """Team abbrevs already ingested for today's ingestion_date (for resume)."""
    try:
        sql = (f"SELECT DISTINCT team_abbrev FROM `{PROJECT}.{DATASET_RAW}.{TABLE}` "
               f"WHERE ingestion_date = CURRENT_DATE()")
        return {r.team_abbrev for r in client.query(sql).result()}
    except Exception:
        return set()


def _flush(client: bigquery.Client, rows: list[dict]) -> int:
    """Load accumulated team rows, grouped by their RESOLVED season so each row's
    season column matches the roster it carries (offseason teams may resolve to a newer
    season than others). Returns rows loaded."""
    if not rows:
        return 0
    by_season: dict[str, list[dict]] = {}
    for row in rows:
        by_season.setdefault(api8_to_season(row["season8"]), []).append(row)
    for season, group in by_season.items():
        load_json_to_bigquery(PROJECT, DATASET_RAW, TABLE, group, season)
        logger.info("  flushed %d team rosters (season %s)", len(group), season)
    return len(rows)


def refresh_rosters(client: bigquery.Client, season: str = "2025-26",
                    limit: int | None = None, sleep_ms: int = 100,
                    flush_size: int = 16) -> int:
    """Fetch every current team's roster and load to raw_rosters. Returns rows loaded.

    Reusable from the DAG. `season` only selects which season's team list to iterate
    (the roster fetched per team is its current/latest published season).
    """
    teams = _team_abbrevs(client, season, limit)
    done = _done_today(client)
    logger.info("Refreshing rosters: %d teams (%d already done today)", len(teams), len(done))

    rows: list[dict] = []
    loaded = 0
    for team in teams:
        if team in done:
            continue
        try:
            payload = get_roster(team)
        except Exception as e:  # noqa: BLE001
            logger.warning("  roster %s failed: %s", team, str(e)[:80])
            continue
        rows.append(payload)
        if len(rows) >= flush_size:
            loaded += _flush(client, rows)
            rows = []
        time.sleep(sleep_ms / 1000.0)

    loaded += _flush(client, rows)  # remaining
    logger.info("Roster refresh loaded %d team rosters.", loaded)
    return loaded


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--season", default="2025-26", help="Season whose team list to iterate")
    ap.add_argument("--limit", type=int, help="Cap teams (for sampling)")
    ap.add_argument("--sleep-ms", type=int, default=100)
    args = ap.parse_args()

    client = bigquery.Client(project=PROJECT)
    refresh_rosters(client, args.season, args.limit, args.sleep_ms)
    logger.info("Roster refresh complete.")


if __name__ == "__main__":
    main()
