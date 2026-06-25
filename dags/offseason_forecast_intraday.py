"""Intraday refresh for the Offseason Forecast (a second daily run).

The nightly `nhl_daily` DAG already refreshes the live roster and recomputes the forecast once a day
(13:00 UTC). During the offseason, signings and trades land throughout the day, so this small DAG runs
the offseason-only path a SECOND time (21:00 UTC) to keep the ledger fresh, without re-running the
whole nightly pipeline:

    refresh_rosters  ->  dbt (stg_roster_current)  ->  project_roster_forecast --full  ->  export

It is cheap: the value tables (GAR, ratings, aging) are static between seasons, so only the live roster
is re-pulled and the forecast re-diffed. The forecast job self-guards to the offseason (it is a no-op
once the next season's first game is played), so this DAG is harmless to leave scheduled year-round.

NOTE: the export does an in-place `--only` update of the DuckDB serving file (fast). The backend must
reload that file to serve the update (the deployment's reload policy / a restart handles this).
"""

import os
from datetime import datetime, timedelta

from airflow import DAG
from airflow.operators.bash import BashOperator

default_args = {
    "owner": "nhl-intel",
    "retries": 1,
    "retry_delay": timedelta(minutes=5),
    "email_on_failure": True,
    "email_on_retry": False,
}

_env = {
    **os.environ,
    "GCP_PROJECT_ID": os.getenv("GCP_PROJECT_ID"),
    "GCP_DATASET_RAW": os.getenv("GCP_DATASET_RAW", "nhl_raw"),
    "GCP_DATASET_STAGING": os.getenv("GCP_DATASET_STAGING", "nhl_staging"),
    "GCP_DATASET_MART": os.getenv("GCP_DATASET_MART", "nhl_mart"),
    "GCP_DATASET_MODELS": os.getenv("GCP_DATASET_MODELS", "nhl_models"),
}
_dbt = ("cd /opt/airflow/dbt && /home/airflow/.local/bin/dbt run "
        "--profiles-dir /opt/airflow/dbt --log-path /tmp/dbt_logs --target-path /tmp/dbt_target")

with DAG(
    dag_id="offseason_forecast_intraday",
    default_args=default_args,
    description="Second daily refresh of the offseason roster forecast (offseason-only)",
    schedule_interval="0 21 * * *",   # 21:00 UTC — 8h after the nightly nhl_daily run (13:00 UTC)
    start_date=datetime(2024, 1, 1),
    catchup=False,
    tags=["nhl", "offseason", "forecast"],
) as dag:

    # 1. Re-pull every team's live roster (32 small api-web calls) so today's signings/trades land.
    refresh_rosters = BashOperator(
        task_id="refresh_rosters",
        bash_command="cd /opt/airflow && python -m scripts.refresh_rosters",
        env=_env,
    )

    # 2. Rebuild the live-roster staging the forecast diffs against (cheap; just this model + its dep).
    dbt_roster = BashOperator(
        task_id="dbt_roster_current",
        bash_command=f"{_dbt} --select stg_roster_current int_player_current_team",
        env=_env,
    )

    # 3. Recompute the forecast. Self-guards to the offseason (no-op once the next season has started).
    roster_forecast = BashOperator(
        task_id="roster_forecast",
        bash_command="cd /opt/airflow && python -m models_ml.project_roster_forecast --full",
        env=_env,
    )

    # 4. Push just the two forecast tables into the DuckDB serving file (in-place, ~seconds).
    export_forecast = BashOperator(
        task_id="export_forecast",
        bash_command="cd /opt/airflow && python -m scripts.export_to_duckdb --only roster_forecast,roster_moves",
        env=_env,
    )

    refresh_rosters >> dbt_roster >> roster_forecast >> export_forecast
