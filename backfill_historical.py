"""Standalone historical backfill script for NHL data.

This script runs independently of Airflow and can be executed from your local machine.
It's significantly faster than the DAG-based approach due to:
- Async/concurrent API requests with proper rate limiting
- No Airflow overhead (metadata DB, heartbeats, scheduler)
- No VM resource constraints
- Direct BigQuery writes

Usage:
    # Single season
    python backfill_historical.py --season 2025-26

    # Multiple seasons
    python backfill_historical.py --seasons 2024-25 2025-26

    # All seasons (2015-16 through 2025-26)
    python backfill_historical.py --all

    # Drop tables and start fresh
    python backfill_historical.py --all --drop-tables

    # Dry run (enumerate games only)
    python backfill_historical.py --season 2025-26 --dry-run
"""

import asyncio
import argparse
import os
import sys
import time
from datetime import datetime, date as date_cls, timedelta
from pathlib import Path
from typing import List, Dict, Set
import httpx
from google.cloud import bigquery
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
from dotenv import load_dotenv

# Load environment variables from .env
load_dotenv()

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

from ingestion.nhl_api import get_schedule
from ingestion.loaders import load_json_to_bigquery


class BackfillStats:
    """Track backfill progress and statistics."""

    def __init__(self, season: str):
        self.season = season
        self.total_games = 0
        self.existing_games = 0
        self.games_to_fetch = 0
        self.boxscores_fetched = 0
        self.pbp_fetched = 0
        self.shifts_fetched = 0
        self.boxscores_failed = 0
        self.pbp_failed = 0
        self.shifts_failed = 0
        self.start_time = time.time()

    def print_summary(self):
        """Print final statistics."""
        duration = time.time() - self.start_time
        print(f"\n{'='*60}")
        print(f"Backfill Summary - {self.season}")
        print(f"{'='*60}")
        print(f"Total games found:       {self.total_games}")
        print(f"Already in BigQuery:     {self.existing_games}")
        print(f"Games to fetch:          {self.games_to_fetch}")
        print(f"Boxscores fetched:       {self.boxscores_fetched}")
        print(f"Boxscores failed:        {self.boxscores_failed}")
        print(f"Play-by-play fetched:    {self.pbp_fetched}")
        print(f"Play-by-play failed:     {self.pbp_failed}")
        print(f"Shift charts fetched:    {self.shifts_fetched}")
        print(f"Shift charts failed:     {self.shifts_failed}")
        print(f"Duration:                {duration/60:.1f} minutes")
        print(f"{'='*60}\n")


async def enumerate_season_games(season: str, bq_client: bigquery.Client) -> tuple[List[int], List[dict], BackfillStats]:
    """Enumerate all game IDs for a season and collect schedule data.

    Args:
        season: Season string in format "YYYY-YY" (e.g., "2023-24").
        bq_client: BigQuery client for checking existing games.

    Returns:
        Tuple of (game_ids_to_fetch, schedule_responses, stats).
    """
    stats = BackfillStats(season)

    start_year = int(season.split("-")[0])
    api_season_id = int(f"{start_year}{start_year + 1}")

    print(f"\n[{season}] Enumerating games for season {season} (API ID: {api_season_id})")

    all_game_ids = set()
    schedule_responses = []  # Collect all schedule API responses

    # Walk the entire season week-by-week. Each /schedule/{date} call returns a full
    # gameWeek, so stepping 7 days at a time covers every game day with no gaps.
    # Range spans Oct 1 (season start) through Jul 1 to include the full playoffs.
    season_start = date_cls(start_year, 10, 1)
    season_end = date_cls(start_year + 1, 7, 1)

    current = season_start
    while current < season_end:
        target_date = current.isoformat()

        try:
            schedule_data = get_schedule(target_date)
            game_week = schedule_data.get("gameWeek", [])

            # Save schedule response if it has games for this season
            has_season_games = False
            for week_day in game_week:
                games = week_day.get("games", [])
                for game in games:
                    game_id = game.get("id")
                    game_season = game.get("season")

                    if game_id and game_season == api_season_id:
                        all_game_ids.add(game_id)
                        has_season_games = True

            if has_season_games:
                schedule_responses.append(schedule_data)

            await asyncio.sleep(0.1)  # Small delay between requests

        except Exception as e:
            print(f"[{season}] Warning: Could not fetch schedule for {target_date}: {e}")

        current += timedelta(days=7)

    stats.total_games = len(all_game_ids)
    print(f"[{season}] Found {stats.total_games} total games")
    print(f"[{season}] Collected {len(schedule_responses)} schedule responses")

    # Check for existing games in BigQuery
    project_id = os.getenv("GCP_PROJECT_ID")
    dataset_raw = os.getenv("GCP_DATASET_RAW", "nhl_raw")

    query = f"""
        SELECT DISTINCT game_id
        FROM `{project_id}.{dataset_raw}.raw_boxscores`
        WHERE season = '{season}'
    """

    try:
        existing_games = bq_client.query(query).result()
        existing_game_ids = {row.game_id for row in existing_games}
        stats.existing_games = len(existing_game_ids)
        print(f"[{season}] Found {stats.existing_games} games already in BigQuery")

        games_to_fetch = sorted(list(all_game_ids - existing_game_ids))
        stats.games_to_fetch = len(games_to_fetch)
        print(f"[{season}] Will fetch {stats.games_to_fetch} new games")

    except Exception as e:
        print(f"[{season}] Could not check existing games: {e}")
        print(f"[{season}] Will attempt to fetch all games")
        games_to_fetch = sorted(list(all_game_ids))
        stats.games_to_fetch = len(games_to_fetch)

    return games_to_fetch, schedule_responses, stats


async def fetch_with_retry(
    url: str,
    game_id: int,
    client: httpx.AsyncClient,
    semaphore: asyncio.Semaphore,
    max_retries: int = 5
) -> dict:
    """Fetch data from URL with retry logic and rate limiting.

    Args:
        url: API endpoint URL.
        game_id: Game ID for error reporting.
        client: httpx async client.
        semaphore: Asyncio semaphore for rate limiting.
        max_retries: Maximum number of retry attempts.

    Returns:
        API response as dict.
    """
    async with semaphore:
        for attempt in range(max_retries):
            try:
                response = await client.get(url, timeout=30.0)
                response.raise_for_status()
                return response.json()

            except httpx.HTTPStatusError as e:
                if e.response.status_code == 429:
                    wait_time = min(30 * (2 ** attempt), 120)  # Exponential backoff, max 2 min
                    print(f"  Rate limited on game {game_id}, waiting {wait_time}s (attempt {attempt+1}/{max_retries})")
                    await asyncio.sleep(wait_time)
                elif e.response.status_code == 404:
                    raise ValueError(f"Game {game_id} not found (404)")
                else:
                    raise

            except Exception as e:
                if attempt < max_retries - 1:
                    wait_time = min(5 * (2 ** attempt), 30)
                    await asyncio.sleep(wait_time)
                else:
                    raise

        raise Exception(f"Max retries exceeded for game {game_id}")


async def fetch_game_data(
    game_ids: List[int],
    season: str,
    stats: BackfillStats,
    tables: List[str],
    max_concurrent: int = 10
) -> tuple[List[dict], List[dict], List[dict], List[dict]]:
    """Fetch the requested surfaces for all games concurrently.

    Args:
        game_ids: List of game IDs to fetch.
        season: Season string.
        stats: BackfillStats object to update.
        tables: Surfaces to fetch (subset of boxscore/pbp/shiftcharts).
        max_concurrent: Maximum concurrent requests against api-web.nhle.com.

    Returns:
        Tuple of (boxscores, play_by_plays, shift_charts, failures).
    """
    semaphore = asyncio.Semaphore(max_concurrent)
    # api.nhle.com (stats REST) is the more sensitive host: cap at 5 per HANDOFF-1.
    shift_semaphore = asyncio.Semaphore(min(5, max_concurrent))
    boxscores = []
    play_by_plays = []
    shift_charts = []
    failures = []

    print(f"[{season}] Fetching {tables} for {len(game_ids)} games (max {max_concurrent} concurrent)")

    async with httpx.AsyncClient() as client:
        tasks = []

        for game_id in game_ids:
            tasks.append(fetch_single_game(
                game_id, season, client, semaphore, stats,
                boxscores, play_by_plays, failures, shift_charts, tables, shift_semaphore,
            ))

        # Show progress
        total = len(tasks)
        for i, task in enumerate(asyncio.as_completed(tasks)):
            await task
            if (i + 1) % 50 == 0 or (i + 1) == total:
                print(f"[{season}] Progress: {i+1}/{total} games processed")

    return boxscores, play_by_plays, shift_charts, failures


async def fetch_single_game(
    game_id: int,
    season: str,
    client: httpx.AsyncClient,
    semaphore: asyncio.Semaphore,
    stats: BackfillStats,
    boxscores: List[dict],
    play_by_plays: List[dict],
    failures: List[dict],
    shift_charts: List[dict],
    tables: List[str],
    shift_semaphore: asyncio.Semaphore,
):
    """Fetch the requested surfaces (boxscore, pbp, shiftcharts) for a single game.

    Args:
        game_id: Game ID to fetch.
        season: Season string.
        client: httpx async client.
        semaphore: Rate limiting semaphore for api-web.nhle.com.
        stats: BackfillStats to update.
        boxscores: List to append successful boxscores.
        play_by_plays: List to append successful play-by-plays.
        failures: List to append failures.
        shift_charts: List to append successful shift-chart rows.
        tables: Surfaces to fetch (subset of boxscore/pbp/shiftcharts).
        shift_semaphore: Separate, smaller semaphore for the stats REST host.
    """
    base_url = "https://api-web.nhle.com/v1/gamecenter"

    # Fetch boxscore
    if "boxscore" in tables:
        try:
            boxscore_url = f"{base_url}/{game_id}/boxscore"
            boxscore = await fetch_with_retry(boxscore_url, game_id, client, semaphore)
            boxscore["game_id"] = game_id
            boxscores.append(boxscore)
            stats.boxscores_fetched += 1
        except Exception as e:
            stats.boxscores_failed += 1
            failures.append({
                "game_id": game_id, "season": season, "data_type": "boxscore",
                "error_message": str(e)[:500], "timestamp": datetime.utcnow().isoformat()
            })

    # Fetch play-by-play
    if "pbp" in tables:
        try:
            pbp_url = f"{base_url}/{game_id}/play-by-play"
            pbp = await fetch_with_retry(pbp_url, game_id, client, semaphore)
            pbp["game_id"] = game_id
            play_by_plays.append(pbp)
            stats.pbp_fetched += 1
        except Exception as e:
            stats.pbp_failed += 1
            failures.append({
                "game_id": game_id, "season": season, "data_type": "play_by_play",
                "error_message": str(e)[:500], "timestamp": datetime.utcnow().isoformat()
            })

    # Fetch shift charts (stats REST host; smaller semaphore per HANDOFF-1)
    if "shiftcharts" in tables:
        try:
            shift_url = f"https://api.nhle.com/stats/rest/en/shiftcharts?cayenneExp=gameId={game_id}"
            payload = await fetch_with_retry(shift_url, game_id, client, shift_semaphore)
            shift_charts.append({"id": game_id, "game_id": game_id, "data": payload.get("data", [])})
            stats.shifts_fetched += 1
        except Exception as e:
            stats.shifts_failed += 1
            failures.append({
                "game_id": game_id, "season": season, "data_type": "shift_charts",
                "error_message": str(e)[:500], "timestamp": datetime.utcnow().isoformat()
            })


def _trim_schedule_response(resp: dict) -> dict:
    """Reduce a schedule API response to the minimal fields stg_games consumes.

    The NHL schedule feed carries many volatile nested fields (e.g. gameWeek.datePromo,
    tvBroadcasts) whose types drift between API versions and break the BigQuery load.
    stg_games only reads game ids and the week date, so we strip everything else. This
    also keeps raw_games matching its existing thin schema.
    """
    trimmed_weeks = []
    for week_day in resp.get("gameWeek", []):
        trimmed_weeks.append({
            "date": week_day.get("date"),
            "games": [
                {"id": game.get("id")}
                for game in week_day.get("games", [])
                if game.get("id") is not None
            ],
        })
    return {"gameWeek": trimmed_weeks}


def load_to_bigquery(boxscores: List[dict], play_by_plays: List[dict], schedule_responses: List[dict], failures: List[dict], season: str, shift_charts: List[dict] = None):
    """Load fetched data to BigQuery.

    Args:
        boxscores: List of boxscore dicts.
        play_by_plays: List of play-by-play dicts.
        schedule_responses: List of schedule API response dicts.
        failures: List of failure dicts.
        season: Season string.
        shift_charts: List of shift-chart rows ({id, game_id, data}).
    """
    project_id = os.getenv("GCP_PROJECT_ID")
    dataset_raw = os.getenv("GCP_DATASET_RAW", "nhl_raw")
    shift_charts = shift_charts or []

    print(f"[{season}] Loading to BigQuery: {len(schedule_responses)} schedules, {len(boxscores)} boxscores, {len(play_by_plays)} play-by-plays, {len(shift_charts)} shift charts")

    if schedule_responses:
        trimmed_schedules = [_trim_schedule_response(r) for r in schedule_responses]
        load_json_to_bigquery(
            project_id=project_id,
            dataset_id=dataset_raw,
            table_id="raw_games",
            data=trimmed_schedules,
            season=season,
        )
        print(f"[{season}] ✓ Loaded {len(schedule_responses)} schedule responses")

    if boxscores:
        load_json_to_bigquery(
            project_id=project_id,
            dataset_id=dataset_raw,
            table_id="raw_boxscores",
            data=boxscores,
            season=season,
        )
        print(f"[{season}] ✓ Loaded {len(boxscores)} boxscores")

    if play_by_plays:
        load_json_to_bigquery(
            project_id=project_id,
            dataset_id=dataset_raw,
            table_id="raw_play_by_play",
            data=play_by_plays,
            season=season,
        )
        print(f"[{season}] ✓ Loaded {len(play_by_plays)} play-by-play records")

    if shift_charts:
        load_json_to_bigquery(
            project_id=project_id,
            dataset_id=dataset_raw,
            table_id="raw_shift_charts",
            data=shift_charts,
            season=season,
        )
        print(f"[{season}] ✓ Loaded {len(shift_charts)} shift charts")

    if failures:
        print(f"[{season}] Logging {len(failures)} failures")
        client = bigquery.Client(project=project_id)
        table_ref = f"{project_id}.{dataset_raw}.raw_backfill_failures"

        schema = [
            bigquery.SchemaField("game_id", "INTEGER", mode="REQUIRED"),
            bigquery.SchemaField("season", "STRING", mode="REQUIRED"),
            bigquery.SchemaField("data_type", "STRING", mode="REQUIRED"),
            bigquery.SchemaField("error_message", "STRING", mode="NULLABLE"),
            bigquery.SchemaField("timestamp", "TIMESTAMP", mode="REQUIRED"),
        ]

        try:
            table = bigquery.Table(table_ref, schema=schema)
            client.create_table(table, exists_ok=True)
            client.insert_rows_json(table_ref, failures)
        except Exception as e:
            print(f"[{season}] Warning: Could not log failures: {e}")


def _games_missing_shifts(client: bigquery.Client, season: str) -> List[int]:
    """Season game ids present in raw_boxscores but missing from raw_shift_charts."""
    project = os.getenv("GCP_PROJECT_ID")
    dataset_raw = os.getenv("GCP_DATASET_RAW", "nhl_raw")
    sql = f"""
        SELECT game_id FROM `{project}.{dataset_raw}.raw_boxscores`
        WHERE season = '{season}'
          AND game_id NOT IN (SELECT game_id FROM `{project}.{dataset_raw}.raw_shift_charts`)
        GROUP BY game_id
    """
    try:
        return [int(r.game_id) for r in client.query(sql).result()]
    except Exception:
        # raw_shift_charts does not exist yet on the first shift backfill
        sql2 = f"SELECT DISTINCT game_id FROM `{project}.{dataset_raw}.raw_boxscores` WHERE season = '{season}'"
        return [int(r.game_id) for r in client.query(sql2).result()]


async def backfill_season(season: str, dry_run: bool = False, max_concurrent: int = 10, tables: List[str] = None):
    """Backfill the requested surfaces for a single season.

    Args:
        season: Season string in format "YYYY-YY".
        dry_run: If True, only enumerate games without fetching.
        max_concurrent: Maximum concurrent API requests.
        tables: Surfaces to fetch (subset of boxscore/pbp/shiftcharts). Defaults to
            boxscore + pbp. Pass exactly ["shiftcharts"] for a resumable shift-only
            backfill that targets games missing from raw_shift_charts (no pbp re-pull).
    """
    tables = tables or ["boxscore", "pbp"]
    bq_client = bigquery.Client(project=os.getenv("GCP_PROJECT_ID"))

    # Resumable shift-only path: enumerate from raw_shift_charts gaps, not raw_boxscores.
    if tables == ["shiftcharts"]:
        game_ids = _games_missing_shifts(bq_client, season)
        stats = BackfillStats(season)
        stats.total_games = len(game_ids)
        stats.games_to_fetch = len(game_ids)
        if dry_run:
            print(f"[{season}] Dry run - would fetch shift charts for {len(game_ids)} games")
            return stats
        if not game_ids:
            print(f"[{season}] No shift charts to fetch - all already in BigQuery")
            return stats
        _, _, shift_charts, failures = await fetch_game_data(game_ids, season, stats, tables, max_concurrent)
        load_to_bigquery([], [], [], failures, season, shift_charts=shift_charts)
        stats.print_summary()
        return stats

    # Standard path: enumerate games missing from raw_boxscores, collect schedule data.
    game_ids, schedule_responses, stats = await enumerate_season_games(season, bq_client)

    if dry_run:
        print(f"[{season}] Dry run complete - would fetch {stats.games_to_fetch} games")
        return stats

    if stats.games_to_fetch == 0:
        print(f"[{season}] No games to fetch - all data already in BigQuery")
        if schedule_responses:
            print(f"[{season}] Loading schedule data to raw_games")
            load_to_bigquery([], [], schedule_responses, [], season)
        stats.print_summary()
        return stats

    # Fetch data
    boxscores, play_by_plays, shift_charts, failures = await fetch_game_data(game_ids, season, stats, tables, max_concurrent)

    # Load to BigQuery (including schedule data)
    load_to_bigquery(boxscores, play_by_plays, schedule_responses, failures, season, shift_charts=shift_charts)

    stats.print_summary()
    return stats


def drop_raw_tables():
    """Drop and recreate raw BigQuery tables to avoid schema conflicts.

    This is useful when running a fresh backfill, as the NHL API schema
    has evolved over time and field types have changed.
    """
    project_id = os.getenv("GCP_PROJECT_ID")
    dataset_raw = os.getenv("GCP_DATASET_RAW", "nhl_raw")

    client = bigquery.Client(project=project_id)

    tables_to_drop = ["raw_games", "raw_boxscores", "raw_play_by_play", "raw_rosters"]

    print(f"\n{'='*60}")
    print(f"Dropping raw tables in {dataset_raw}")
    print(f"{'='*60}")

    for table_name in tables_to_drop:
        table_ref = f"{project_id}.{dataset_raw}.{table_name}"
        try:
            client.delete_table(table_ref)
            print(f"✓ Dropped {table_name}")
        except Exception as e:
            print(f"  Could not drop {table_name}: {e}")

    print(f"{'='*60}\n")


async def main():
    """Main entry point for backfill script."""
    parser = argparse.ArgumentParser(description="Backfill historical NHL data")
    parser.add_argument("--season", help="Single season to backfill (e.g., 2023-24)")
    parser.add_argument("--seasons", nargs="+", help="Multiple seasons to backfill")
    parser.add_argument("--all", action="store_true", help="Backfill all seasons (2015-16 through 2025-26)")
    parser.add_argument("--dry-run", action="store_true", help="Enumerate games only, don't fetch")
    parser.add_argument("--concurrent", type=int, default=10, help="Max concurrent requests (default: 10)")
    parser.add_argument("--drop-tables", action="store_true", help="Drop and recreate raw tables before backfill")
    parser.add_argument(
        "--tables", nargs="+", default=["boxscore", "pbp"],
        choices=["boxscore", "pbp", "shiftcharts"],
        help="Surfaces to fetch. Use '--tables shiftcharts' alone for a resumable "
             "shift-only backfill that does not re-pull pbp (default: boxscore pbp).",
    )
    parser.add_argument("--sleep-ms", type=int, default=100, help="Politeness delay between requests (ms)")

    args = parser.parse_args()

    # Determine which seasons to process
    if args.all:
        seasons = [f"{year}-{str(year+1)[2:]}" for year in range(2015, 2026)]
    elif args.seasons:
        seasons = args.seasons
    elif args.season:
        seasons = [args.season]
    else:
        parser.error("Must specify --season, --seasons, or --all")

    print(f"\n{'='*60}")
    print(f"NHL Historical Backfill")
    print(f"{'='*60}")
    print(f"Seasons: {', '.join(seasons)}")
    print(f"Tables: {', '.join(args.tables)}")
    print(f"Max concurrent requests: {args.concurrent}")
    print(f"Dry run: {args.dry_run}")
    print(f"Drop tables: {args.drop_tables}")
    print(f"{'='*60}\n")

    # Drop tables if requested
    if args.drop_tables and not args.dry_run:
        drop_raw_tables()

    # Process each season
    all_stats = []
    for season in seasons:
        stats = await backfill_season(season, args.dry_run, args.concurrent, tables=args.tables)
        all_stats.append(stats)

    # Print overall summary
    if len(all_stats) > 1:
        print(f"\n{'='*60}")
        print(f"Overall Summary - {len(all_stats)} seasons")
        print(f"{'='*60}")
        total_games = sum(s.total_games for s in all_stats)
        total_fetched = sum(s.boxscores_fetched for s in all_stats)
        total_failed = sum(s.boxscores_failed + s.pbp_failed for s in all_stats)
        total_duration = sum(time.time() - s.start_time for s in all_stats)
        print(f"Total games found:       {total_games}")
        print(f"Total data fetched:      {total_fetched}")
        print(f"Total failures:          {total_failed}")
        print(f"Total duration:          {total_duration/60:.1f} minutes")
        print(f"{'='*60}\n")


if __name__ == "__main__":
    asyncio.run(main())
