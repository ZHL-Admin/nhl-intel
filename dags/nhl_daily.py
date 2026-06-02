"""Main Airflow DAG for daily NHL data pipeline."""

import os
from datetime import datetime, timedelta
from airflow import DAG
from airflow.operators.python import PythonOperator
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from ingestion.nhl_api import get_schedule, get_boxscore, get_play_by_play
from ingestion.loaders import load_json_to_bigquery


def ingest_nhl_data(**context):
    """Ingest yesterday's NHL games into BigQuery raw tables.

    Fetches schedule, boxscore, and play-by-play data for all games
    from the previous day and loads them into the nhl_raw dataset.
    """
    execution_date = context["execution_date"]
    target_date = (execution_date - timedelta(days=1)).date().isoformat()

    project_id = os.getenv("GCP_PROJECT_ID")
    dataset_raw = os.getenv("GCP_DATASET_RAW", "nhl_raw")

    print(f"Ingesting NHL data for {target_date}")

    # Fetch schedule to get game IDs
    schedule_data = get_schedule(target_date)
    game_ids = []

    for day in schedule_data.get("gameWeek", []):
        for game in day.get("games", []):
            game_id = game.get("id")
            if game_id:
                game_ids.append(game_id)

    print(f"Found {len(game_ids)} games: {game_ids}")

    if not game_ids:
        print("No games to ingest for this date")
        return

    # Load raw schedule data
    load_json_to_bigquery(
        project_id=project_id,
        dataset_id=dataset_raw,
        table_id="raw_games",
        data=schedule_data,
    )
    print(f"Loaded schedule data to {dataset_raw}.raw_games")

    # Fetch and load boxscore data for each game
    boxscores = []
    for game_id in game_ids:
        print(f"Fetching boxscore for game {game_id}")
        boxscore = get_boxscore(game_id)
        boxscore["game_id"] = game_id
        boxscores.append(boxscore)

    if boxscores:
        load_json_to_bigquery(
            project_id=project_id,
            dataset_id=dataset_raw,
            table_id="raw_boxscores",
            data=boxscores,
        )
        print(f"Loaded {len(boxscores)} boxscores to {dataset_raw}.raw_boxscores")

    # Fetch and load play-by-play data for each game
    play_by_plays = []
    for game_id in game_ids:
        print(f"Fetching play-by-play for game {game_id}")
        pbp = get_play_by_play(game_id)
        pbp["game_id"] = game_id
        play_by_plays.append(pbp)

    if play_by_plays:
        load_json_to_bigquery(
            project_id=project_id,
            dataset_id=dataset_raw,
            table_id="raw_play_by_play",
            data=play_by_plays,
        )
        print(f"Loaded {len(play_by_plays)} play-by-play records to {dataset_raw}.raw_play_by_play")

    print(f"Ingestion complete for {target_date}")


default_args = {
    "owner": "nhl-intel",
    "retries": 2,
    "retry_delay": timedelta(minutes=5),
    "email_on_failure": True,
    "email_on_retry": False,
}

with DAG(
    dag_id="nhl_daily",
    default_args=default_args,
    description="Daily NHL data ingestion pipeline",
    schedule_interval=None,  # Manual trigger for Phase 1
    start_date=datetime(2024, 1, 1),
    catchup=False,
    tags=["nhl", "ingestion"],
) as dag:
    ingest_task = PythonOperator(
        task_id="ingest_nhl_data",
        python_callable=ingest_nhl_data,
        provide_context=True,
    )
