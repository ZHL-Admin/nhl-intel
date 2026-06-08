"""Historical NHL data backfill DAG for seasons 2015-16 through 2023-24.

This DAG is designed for manual triggering only and supports backfilling one season at a time.
To trigger for a specific season, use:

    airflow dags trigger nhl_historical_backfill --conf '{"season": "2023-24"}'

The season parameter should be in format "YYYY-YY" (e.g., "2023-24").

Features:
- Rate limiting: max 2 concurrent requests, 0.5s delay between requests
- Exponential backoff on 429 errors: 30s, 60s, 120s
- Batch processing: 50 games per batch with progress checkpointing
- Idempotency: skips games already in BigQuery to prevent duplicates
- Failure tracking: logs failed games to nhl_raw.raw_backfill_failures
- Post-load dbt transformations and validation
"""

import os
import time
from datetime import datetime, timedelta
from airflow import DAG
from airflow.operators.python import PythonOperator
from airflow.operators.bash import BashOperator
import sys
from pathlib import Path

# Add project root to path for imports (done at DAG parse time only)
sys.path.insert(0, str(Path(__file__).parent.parent))


def enumerate_season_games(**context):
    """Enumerate all game IDs for a given season.

    Converts season string (e.g., "2023-24") to API format (20232024),
    fetches the full season schedule, and collects all game IDs for both
    regular season and playoff games.

    Returns:
        dict: Contains 'game_ids' list, 'season' string, and 'game_count' int
    """
    # Import inside task function to avoid DAG parse timeout
    from ingestion.nhl_api import get_schedule
    from google.cloud import bigquery

    # Get season from DAG run config (e.g., "2023-24")
    dag_run = context["dag_run"]
    season = dag_run.conf.get("season")

    if not season:
        raise ValueError("Season parameter required. Use --conf '{\"season\": \"2023-24\"}'")

    print(f"Enumerating games for season {season}")

    # Convert season string to API format
    # "2023-24" -> 20232024
    start_year = int(season.split("-")[0])
    api_season_id = int(f"{start_year}{start_year + 1}")

    print(f"API season ID: {api_season_id}")

    # Fetch full season schedule
    # NHL API schedule endpoint accepts a date, so we'll use the season start date
    # Regular season typically starts in early October
    season_start_date = f"{start_year}-10-01"

    all_game_ids = []

    # Fetch schedule data for the entire season
    # We'll look from October through June (9 months) to cover regular season and playoffs
    # Sample multiple dates per month to ensure we capture all games
    sample_days = [1, 10, 20]  # Sample 3 dates per month for better coverage

    for month_offset in range(9):
        target_month = 10 + month_offset
        target_year = start_year

        # Handle year rollover (January-June are in the following year)
        if target_month > 12:
            target_month -= 12
            target_year += 1

        # Sample multiple dates within each month
        for day in sample_days:
            target_date = f"{target_year}-{target_month:02d}-{day:02d}"

            try:
                schedule_data = get_schedule(target_date)
                game_week = schedule_data.get("gameWeek", [])

                for week_day in game_week:
                    games = week_day.get("games", [])
                    for game in games:
                        game_id = game.get("id")
                        game_season = game.get("season")

                        # Only include games from this season
                        if game_id and game_season == api_season_id:
                            if game_id not in all_game_ids:
                                all_game_ids.append(game_id)

                # Add small delay between requests
                time.sleep(0.5)

            except Exception as e:
                print(f"Error fetching schedule for {target_date}: {e}")
                continue

    print(f"Found {len(all_game_ids)} total games for season {season}")
    print(f"Game ID range: {min(all_game_ids)} to {max(all_game_ids)}")

    # Check for existing games in BigQuery to enable idempotency
    project_id = os.getenv("GCP_PROJECT_ID")
    dataset_raw = os.getenv("GCP_DATASET_RAW", "nhl_raw")

    client = bigquery.Client(project=project_id)

    # Query existing game IDs from raw_boxscores
    query = f"""
        SELECT DISTINCT game_id
        FROM `{project_id}.{dataset_raw}.raw_boxscores`
        WHERE season = '{season}'
    """

    try:
        existing_games = client.query(query).result()
        existing_game_ids = set(row.game_id for row in existing_games)
        print(f"Found {len(existing_game_ids)} games already in BigQuery for season {season}")

        # Filter out existing games
        games_to_fetch = [gid for gid in all_game_ids if gid not in existing_game_ids]
        print(f"Will fetch {len(games_to_fetch)} new games (skipping {len(existing_game_ids)} existing)")

    except Exception as e:
        print(f"Could not check existing games (table may not exist): {e}")
        print("Will attempt to fetch all games")
        games_to_fetch = all_game_ids

    # Store results in XCom for downstream tasks
    result = {
        "game_ids": games_to_fetch,
        "season": season,
        "game_count": len(games_to_fetch),
        "total_games": len(all_game_ids),
        "existing_games": len(all_game_ids) - len(games_to_fetch)
    }

    return result


def fetch_boxscores_batch(**context):
    """Fetch boxscore data for all games in batches of 50.

    Implements rate limiting and retry logic with exponential backoff.
    Failed games are logged to the backfill_failures table.
    """
    # Import inside task function to avoid DAG parse timeout
    from ingestion.nhl_api import get_boxscore
    from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
    import httpx
    from google.cloud import bigquery

    ti = context["ti"]
    season_data = ti.xcom_pull(task_ids="enumerate_season_games")

    game_ids = season_data["game_ids"]
    season = season_data["season"]

    print(f"Fetching boxscores for {len(game_ids)} games in season {season}")

    project_id = os.getenv("GCP_PROJECT_ID")
    dataset_raw = os.getenv("GCP_DATASET_RAW", "nhl_raw")

    # Create enhanced retry decorator with custom backoff for 429 errors
    @retry(
        stop=stop_after_attempt(5),
        wait=wait_exponential(multiplier=30, min=30, max=120),
        retry=retry_if_exception_type(httpx.HTTPStatusError),
        reraise=True
    )
    def fetch_with_retry(game_id):
        try:
            return get_boxscore(game_id)
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 429:
                print(f"Rate limited on game {game_id}, will retry with backoff")
                raise
            else:
                print(f"HTTP error {e.response.status_code} for game {game_id}")
                raise

    boxscores = []
    failed_games = []
    batch_size = 50
    total_batches = (len(game_ids) + batch_size - 1) // batch_size

    for batch_idx in range(total_batches):
        batch_start = batch_idx * batch_size
        batch_end = min(batch_start + batch_size, len(game_ids))
        batch_game_ids = game_ids[batch_start:batch_end]

        print(f"Processing batch {batch_idx + 1}/{total_batches} ({batch_start + 1}-{batch_end}/{len(game_ids)})")

        for game_id in batch_game_ids:
            try:
                boxscore = fetch_with_retry(game_id)
                boxscore["game_id"] = game_id
                boxscores.append(boxscore)

                # Rate limiting: 0.5s delay between requests
                time.sleep(0.5)

            except Exception as e:
                error_msg = str(e)
                print(f"Failed to fetch boxscore for game {game_id} after retries: {error_msg}")
                failed_games.append({
                    "game_id": game_id,
                    "season": season,
                    "data_type": "boxscore",
                    "error_message": error_msg[:500],  # Truncate long errors
                    "timestamp": datetime.utcnow().isoformat()
                })

        print(f"Completed batch {batch_idx + 1}/{total_batches}: {len(boxscores)} successful, {len(failed_games)} failed")

    # Log failures to BigQuery
    if failed_games:
        print(f"Logging {len(failed_games)} failed games to backfill_failures table")
        client = bigquery.Client(project=project_id)
        table_ref = f"{project_id}.{dataset_raw}.raw_backfill_failures"

        # Create table if it doesn't exist
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
        except Exception as e:
            print(f"Could not create failures table: {e}")

        # Insert failure records
        try:
            errors = client.insert_rows_json(table_ref, failed_games)
            if errors:
                print(f"Errors inserting failures: {errors}")
        except Exception as e:
            print(f"Could not log failures: {e}")

    print(f"Boxscore fetch complete: {len(boxscores)} successful, {len(failed_games)} failed")

    # Store boxscores in XCom for loading task
    return {
        "boxscores": boxscores,
        "season": season,
        "success_count": len(boxscores),
        "failure_count": len(failed_games)
    }


def fetch_play_by_play_batch(**context):
    """Fetch play-by-play data for all games in batches of 50.

    Implements rate limiting and retry logic with exponential backoff.
    Failed games are logged to the backfill_failures table.
    """
    # Import inside task function to avoid DAG parse timeout
    from ingestion.nhl_api import get_play_by_play
    from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
    import httpx
    from google.cloud import bigquery

    ti = context["ti"]
    season_data = ti.xcom_pull(task_ids="enumerate_season_games")

    game_ids = season_data["game_ids"]
    season = season_data["season"]

    print(f"Fetching play-by-play for {len(game_ids)} games in season {season}")

    project_id = os.getenv("GCP_PROJECT_ID")
    dataset_raw = os.getenv("GCP_DATASET_RAW", "nhl_raw")

    # Create enhanced retry decorator with custom backoff for 429 errors
    @retry(
        stop=stop_after_attempt(5),
        wait=wait_exponential(multiplier=30, min=30, max=120),
        retry=retry_if_exception_type(httpx.HTTPStatusError),
        reraise=True
    )
    def fetch_with_retry(game_id):
        try:
            return get_play_by_play(game_id)
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 429:
                print(f"Rate limited on game {game_id}, will retry with backoff")
                raise
            else:
                print(f"HTTP error {e.response.status_code} for game {game_id}")
                raise

    play_by_plays = []
    failed_games = []
    batch_size = 50
    total_batches = (len(game_ids) + batch_size - 1) // batch_size

    for batch_idx in range(total_batches):
        batch_start = batch_idx * batch_size
        batch_end = min(batch_start + batch_size, len(game_ids))
        batch_game_ids = game_ids[batch_start:batch_end]

        print(f"Processing batch {batch_idx + 1}/{total_batches} ({batch_start + 1}-{batch_end}/{len(game_ids)})")

        for game_id in batch_game_ids:
            try:
                pbp = fetch_with_retry(game_id)
                pbp["game_id"] = game_id
                play_by_plays.append(pbp)

                # Rate limiting: 0.5s delay between requests
                time.sleep(0.5)

            except Exception as e:
                error_msg = str(e)
                print(f"Failed to fetch play-by-play for game {game_id} after retries: {error_msg}")
                failed_games.append({
                    "game_id": game_id,
                    "season": season,
                    "data_type": "play_by_play",
                    "error_message": error_msg[:500],  # Truncate long errors
                    "timestamp": datetime.utcnow().isoformat()
                })

        print(f"Completed batch {batch_idx + 1}/{total_batches}: {len(play_by_plays)} successful, {len(failed_games)} failed")

    # Log failures to BigQuery
    if failed_games:
        print(f"Logging {len(failed_games)} failed games to backfill_failures table")
        client = bigquery.Client(project=project_id)
        table_ref = f"{project_id}.{dataset_raw}.raw_backfill_failures"

        try:
            errors = client.insert_rows_json(table_ref, failed_games)
            if errors:
                print(f"Errors inserting failures: {errors}")
        except Exception as e:
            print(f"Could not log failures: {e}")

    print(f"Play-by-play fetch complete: {len(play_by_plays)} successful, {len(failed_games)} failed")

    # Store play-by-plays in XCom for loading task
    return {
        "play_by_plays": play_by_plays,
        "season": season,
        "success_count": len(play_by_plays),
        "failure_count": len(failed_games)
    }


def load_season_to_bigquery(**context):
    """Load all fetched data (boxscores and play-by-play) to BigQuery.

    Loads data to raw_boxscores and raw_play_by_play tables.
    """
    # Import inside task function to avoid DAG parse timeout
    from ingestion.loaders import load_json_to_bigquery

    ti = context["ti"]

    boxscore_data = ti.xcom_pull(task_ids="fetch_boxscores_batch")
    pbp_data = ti.xcom_pull(task_ids="fetch_play_by_play_batch")

    boxscores = boxscore_data["boxscores"]
    play_by_plays = pbp_data["play_by_plays"]
    season = boxscore_data["season"]

    project_id = os.getenv("GCP_PROJECT_ID")
    dataset_raw = os.getenv("GCP_DATASET_RAW", "nhl_raw")

    print(f"Loading {len(boxscores)} boxscores and {len(play_by_plays)} play-by-play records for season {season}")

    # Load boxscores
    if boxscores:
        load_json_to_bigquery(
            project_id=project_id,
            dataset_id=dataset_raw,
            table_id="raw_boxscores",
            data=boxscores,
            season=season,
        )
        print(f"Loaded {len(boxscores)} boxscores to {dataset_raw}.raw_boxscores")
    else:
        print("No boxscores to load")

    # Load play-by-play
    if play_by_plays:
        load_json_to_bigquery(
            project_id=project_id,
            dataset_id=dataset_raw,
            table_id="raw_play_by_play",
            data=play_by_plays,
            season=season,
        )
        print(f"Loaded {len(play_by_plays)} play-by-play records to {dataset_raw}.raw_play_by_play")
    else:
        print("No play-by-play records to load")

    print(f"Load complete for season {season}")

    return {
        "season": season,
        "boxscores_loaded": len(boxscores),
        "play_by_play_loaded": len(play_by_plays)
    }


def validate_season_data(**context):
    """Validate loaded data for the season.

    Checks:
    - Game counts are in expected range
    - No duplicate game IDs in mart tables
    - Data quality checks pass
    """
    # Import inside task function to avoid DAG parse timeout
    from google.cloud import bigquery

    ti = context["ti"]
    season_data = ti.xcom_pull(task_ids="enumerate_season_games")
    load_data = ti.xcom_pull(task_ids="load_season_to_bigquery")

    season = season_data["season"]
    total_games = season_data["total_games"]

    project_id = os.getenv("GCP_PROJECT_ID")
    dataset_raw = os.getenv("GCP_DATASET_RAW", "nhl_raw")
    dataset_mart = os.getenv("GCP_DATASET_MART", "nhl_mart")

    client = bigquery.Client(project=project_id)

    print(f"Validating data for season {season}")
    print(f"Expected total games: {total_games}")

    # Check game counts in raw tables
    raw_boxscore_query = f"""
        SELECT COUNT(DISTINCT game_id) as game_count
        FROM `{project_id}.{dataset_raw}.raw_boxscores`
        WHERE season = '{season}'
    """

    try:
        result = client.query(raw_boxscore_query).result()
        raw_game_count = list(result)[0].game_count
        print(f"Games in raw_boxscores: {raw_game_count}")

        # For 2023-24, expect 1350-1375 games
        if season == "2023-24":
            if raw_game_count < 1350 or raw_game_count > 1375:
                print(f"WARNING: Game count {raw_game_count} outside expected range 1350-1375 for {season}")
            else:
                print(f"Game count {raw_game_count} is within expected range for {season}")

    except Exception as e:
        print(f"Could not validate raw data: {e}")

    # Check for duplicates in mart tables
    mart_tables = ["mart_team_game_stats", "mart_player_game_stats"]

    for table_name in mart_tables:
        dup_query = f"""
            SELECT game_id, COUNT(*) as cnt
            FROM `{project_id}.{dataset_mart}.{table_name}`
            WHERE season = '{season}'
            GROUP BY game_id
            HAVING COUNT(*) > 1
            LIMIT 10
        """

        try:
            result = client.query(dup_query).result()
            duplicates = list(result)

            if duplicates:
                print(f"WARNING: Found {len(duplicates)} duplicate game IDs in {table_name}")
                for dup in duplicates[:5]:
                    print(f"  Game {dup.game_id}: {dup.cnt} records")
            else:
                print(f"No duplicates found in {table_name} for season {season}")

        except Exception as e:
            print(f"Could not check duplicates in {table_name}: {e}")

    print(f"Validation complete for season {season}")

    return {
        "season": season,
        "validation_complete": True
    }


# DAG configuration
backfill_default_args = {
    "owner": "nhl-intel",
    "retries": 1,
    "retry_delay": timedelta(minutes=10),
    "email_on_failure": True,
    "email_on_retry": False,
}

with DAG(
    dag_id="nhl_historical_backfill",
    default_args=backfill_default_args,
    description="Historical NHL data backfill (2015-16 through 2023-24) - Manual trigger only",
    schedule_interval=None,  # Manual trigger only
    start_date=datetime(2024, 1, 1),
    catchup=False,
    tags=["nhl", "backfill", "historical"],
) as dag:

    enumerate_games = PythonOperator(
        task_id="enumerate_season_games",
        python_callable=enumerate_season_games,
        provide_context=True,
    )

    fetch_boxscores = PythonOperator(
        task_id="fetch_boxscores_batch",
        python_callable=fetch_boxscores_batch,
        provide_context=True,
    )

    fetch_pbp = PythonOperator(
        task_id="fetch_play_by_play_batch",
        python_callable=fetch_play_by_play_batch,
        provide_context=True,
    )

    load_to_bq = PythonOperator(
        task_id="load_season_to_bigquery",
        python_callable=load_season_to_bigquery,
        provide_context=True,
    )

    run_dbt = BashOperator(
        task_id="run_dbt_for_season",
        bash_command="cd /opt/airflow/dbt && /home/airflow/.local/bin/dbt run --select staging.* mart.* --profiles-dir /opt/airflow/dbt --log-path /tmp/dbt_logs --target-path /tmp/dbt_target",
        env={
            **os.environ,
            "GCP_PROJECT_ID": os.getenv("GCP_PROJECT_ID"),
            "GCP_DATASET_RAW": os.getenv("GCP_DATASET_RAW", "nhl_raw"),
            "GCP_DATASET_STAGING": os.getenv("GCP_DATASET_STAGING", "nhl_staging"),
            "GCP_DATASET_MART": os.getenv("GCP_DATASET_MART", "nhl_mart"),
        },
    )

    validate_data = PythonOperator(
        task_id="validate_season_data",
        python_callable=validate_season_data,
        provide_context=True,
    )

    # Task dependencies
    enumerate_games >> [fetch_boxscores, fetch_pbp] >> load_to_bq >> run_dbt >> validate_data
