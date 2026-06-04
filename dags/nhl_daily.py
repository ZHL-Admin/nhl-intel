"""Main Airflow DAG for daily NHL data pipeline."""

import os
from datetime import datetime, timedelta
from airflow import DAG
from airflow.operators.python import PythonOperator
from airflow.operators.bash import BashOperator
import sys
from pathlib import Path

# Add project root to path for imports (done at DAG parse time only)
sys.path.insert(0, str(Path(__file__).parent.parent))


def ingest_nhl_data(**context):
    """Ingest recent NHL games into BigQuery raw tables.

    Looks back up to 30 days from execution date to find games and loads
    schedule, boxscore, and play-by-play data into the nhl_raw dataset.
    """
    # Import heavy packages inside task function to avoid DAG parse timeout
    from ingestion.nhl_api import get_schedule, get_boxscore, get_play_by_play
    from ingestion.loaders import load_json_to_bigquery

    execution_date = context["execution_date"]
    project_id = os.getenv("GCP_PROJECT_ID")
    dataset_raw = os.getenv("GCP_DATASET_RAW", "nhl_raw")

    print(f"Searching for games in the last 30 days from {execution_date.date()}")

    all_game_ids = []
    all_schedules = []
    dates_with_games = []

    # Look back up to 30 days to find games
    for days_back in range(1, 31):
        target_date = (execution_date - timedelta(days=days_back)).date().isoformat()

        try:
            schedule_data = get_schedule(target_date)
            game_week = schedule_data.get("gameWeek", [])

            for day in game_week:
                games = day.get("games", [])
                if games:
                    dates_with_games.append(target_date)
                    all_schedules.append(schedule_data)
                    for game in games:
                        game_id = game.get("id")
                        if game_id:
                            all_game_ids.append(game_id)
                    print(f"Found {len(games)} game(s) on {target_date}")
                    break
        except Exception as e:
            print(f"Error fetching schedule for {target_date}: {e}")
            continue

    print(f"\nTotal games found: {len(all_game_ids)} across {len(dates_with_games)} dates")
    print(f"Game IDs: {all_game_ids}")

    if not all_game_ids:
        print("No games found in the last 30 days")
        return

    # Load all schedule data
    for schedule_data in all_schedules:
        load_json_to_bigquery(
            project_id=project_id,
            dataset_id=dataset_raw,
            table_id="raw_games",
            data=schedule_data,
        )
    print(f"Loaded {len(all_schedules)} schedule records to {dataset_raw}.raw_games")

    # Fetch and load boxscore data for each game
    boxscores = []
    for game_id in all_game_ids:
        print(f"Fetching boxscore for game {game_id}")
        try:
            boxscore = get_boxscore(game_id)
            boxscore["game_id"] = game_id
            boxscores.append(boxscore)
        except Exception as e:
            print(f"Error fetching boxscore for game {game_id}: {e}")
            continue

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
    for game_id in all_game_ids:
        print(f"Fetching play-by-play for game {game_id}")
        try:
            pbp = get_play_by_play(game_id)
            pbp["game_id"] = game_id
            play_by_plays.append(pbp)
        except Exception as e:
            print(f"Error fetching play-by-play for game {game_id}: {e}")
            continue

    if play_by_plays:
        load_json_to_bigquery(
            project_id=project_id,
            dataset_id=dataset_raw,
            table_id="raw_play_by_play",
            data=play_by_plays,
        )
        print(f"Loaded {len(play_by_plays)} play-by-play records to {dataset_raw}.raw_play_by_play")

    print(f"Ingestion complete: {len(all_game_ids)} games across {len(dates_with_games)} dates")


def generate_daily_report(**context):
    """Generate HTML report from mart data and LLM summary.

    Queries mart_daily_report_feed, generates AI summary, renders HTML template,
    and writes the report to the local output directory.
    """
    # Import heavy packages inside task function to avoid DAG parse timeout
    from reporting.query import get_daily_report_data
    from reporting.llm_summary import generate_summary
    from reporting.render import render_report

    execution_date = context["execution_date"]
    report_date = (execution_date - timedelta(days=1)).date().isoformat()

    print(f"Generating report for {report_date}")

    # Query data
    report_data = get_daily_report_data(report_date)
    print(f"Found {len(report_data)} data points for {report_date}")

    if not report_data:
        print(f"No data available for {report_date}, skipping report generation")
        return None

    # Generate LLM summary
    summary = generate_summary(report_data)
    print(f"Generated summary: {summary[:100]}...")

    # Render HTML
    html = render_report(report_data, summary, report_date)
    print(f"Rendered {len(html)} characters of HTML")

    # Write to local file
    output_dir = Path(__file__).parent.parent / "output"
    output_dir.mkdir(exist_ok=True)
    output_path = output_dir / f"report_{report_date}.html"
    output_path.write_text(html)

    print(f"Report saved to {output_path}")
    return str(output_path)


def publish_report_to_gcs(**context):
    """Upload HTML report to public GCS bucket.

    Reads the report from the local output directory and uploads it to
    the configured GCS bucket for public access.
    """
    # Import heavy packages inside task function to avoid DAG parse timeout
    from google.cloud import storage

    ti = context["ti"]
    report_path_str = ti.xcom_pull(task_ids="generate_report")

    if not report_path_str:
        print("No report path found, skipping publish")
        return

    report_path = Path(report_path_str)
    if not report_path.exists():
        print(f"Report file not found at {report_path}")
        return

    bucket_name = os.getenv("REPORT_OUTPUT_BUCKET", "nhl-intel-reports")
    blob_name = report_path.name

    print(f"Uploading {report_path.name} to gs://{bucket_name}/{blob_name}")

    storage_client = storage.Client()
    bucket = storage_client.bucket(bucket_name)
    blob = bucket.blob(blob_name)

    blob.upload_from_filename(str(report_path))

    # Get public URL (bucket has uniform bucket-level access)
    public_url = f"https://storage.googleapis.com/{bucket_name}/{blob_name}"
    print(f"Report published to: {public_url}")

    return public_url


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
    description="Daily NHL data ingestion and transformation pipeline",
    schedule_interval=None,  # Manual trigger for Phase 1
    start_date=datetime(2024, 1, 1),
    catchup=False,
    tags=["nhl", "ingestion", "dbt"],
) as dag:
    ingest_task = PythonOperator(
        task_id="ingest_nhl_data",
        python_callable=ingest_nhl_data,
        provide_context=True,
    )

    run_dbt_models = BashOperator(
        task_id="run_dbt_models",
        bash_command="cd /opt/airflow/dbt && /home/airflow/.local/bin/dbt run --profiles-dir /opt/airflow/dbt --log-path /tmp/dbt_logs --target-path /tmp/dbt_target && /home/airflow/.local/bin/dbt test --profiles-dir /opt/airflow/dbt --log-path /tmp/dbt_logs --target-path /tmp/dbt_target",
        env={
            **os.environ,
            "GCP_PROJECT_ID": os.getenv("GCP_PROJECT_ID"),
            "GCP_DATASET_RAW": os.getenv("GCP_DATASET_RAW", "nhl_raw"),
            "GCP_DATASET_STAGING": os.getenv("GCP_DATASET_STAGING", "nhl_staging"),
            "GCP_DATASET_MART": os.getenv("GCP_DATASET_MART", "nhl_mart"),
        },
    )

    generate_report = PythonOperator(
        task_id="generate_report",
        python_callable=generate_daily_report,
        provide_context=True,
    )

    publish_report = PythonOperator(
        task_id="publish_report",
        python_callable=publish_report_to_gcs,
        provide_context=True,
    )

    ingest_task >> run_dbt_models >> generate_report >> publish_report
