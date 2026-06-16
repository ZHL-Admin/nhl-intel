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
    from ingestion.nhl_api import (
        get_schedule, get_boxscore, get_play_by_play, get_shift_charts,
        get_game_landing, get_game_right_rail, get_standings_by_date,
        get_partner_odds, get_ppt_replay, derive_season_from_game_id,
    )
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

    # Derive season from first game ID (all games in daily pipeline will be same season)
    season = derive_season_from_game_id(all_game_ids[0])
    print(f"Derived season: {season}")

    # Load all schedule data
    for schedule_data in all_schedules:
        load_json_to_bigquery(
            project_id=project_id,
            dataset_id=dataset_raw,
            table_id="raw_games",
            data=schedule_data,
            season=season,
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
            season=season,
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
            season=season,
        )
        print(f"Loaded {len(play_by_plays)} play-by-play records to {dataset_raw}.raw_play_by_play")

    # Fetch and load shift charts for each game (on-ice attribution backbone)
    shift_charts = []
    for game_id in all_game_ids:
        print(f"Fetching shift charts for game {game_id}")
        try:
            payload = get_shift_charts(game_id)
            shift_charts.append({"id": game_id, "game_id": game_id, "data": payload.get("data", [])})
        except Exception as e:
            print(f"Error fetching shift charts for game {game_id}: {e}")
            continue

    if shift_charts:
        load_json_to_bigquery(
            project_id=project_id,
            dataset_id=dataset_raw,
            table_id="raw_shift_charts",
            data=shift_charts,
            season=season,
        )
        print(f"Loaded {len(shift_charts)} shift charts to {dataset_raw}.raw_shift_charts")

    # ppt-replay goal tracking: enumerate each game's goal eventIds from the freshly
    # ingested pbp and fetch the sprite for each (real per-frame player/puck coords).
    ppt_rows = []
    for pbp in play_by_plays:
        gid = pbp["game_id"]
        goal_event_ids = [
            p.get("eventId") for p in pbp.get("plays", [])
            if p.get("typeDescKey") == "goal" and p.get("eventId") is not None
        ]
        for eid in goal_event_ids:
            try:
                payload = get_ppt_replay(gid, eid)
            except Exception as e:
                print(f"Error fetching ppt-replay for {gid}/{eid}: {e}")
                continue
            if payload:
                ppt_rows.append(payload)
    if ppt_rows:
        load_json_to_bigquery(
            project_id=project_id,
            dataset_id=dataset_raw,
            table_id="raw_ppt_replay",
            data=ppt_rows,
            season=season,
        )
        print(f"Loaded {len(ppt_rows)} goal sprites to {dataset_raw}.raw_ppt_replay")

    # --- Phase 1.3 surfaces (current-season games / execution date) ---

    # Game landing + right-rail context (goal video links, scratches, season series).
    landings, rails = [], []
    for game_id in all_game_ids:
        try:
            landings.append(get_game_landing(game_id))
        except Exception as e:
            print(f"Error fetching landing for game {game_id}: {e}")
        try:
            rr = get_game_right_rail(game_id)
            rr["id"] = game_id          # right-rail payload has no id; inject it
            rr["game_id"] = game_id
            rails.append(rr)
        except Exception as e:
            print(f"Error fetching right-rail for game {game_id}: {e}")
    if landings:
        load_json_to_bigquery(project_id, dataset_raw, "raw_game_landing", landings, season)
        print(f"Loaded {len(landings)} landing records to {dataset_raw}.raw_game_landing")
    if rails:
        load_json_to_bigquery(project_id, dataset_raw, "raw_game_right_rail", rails, season)
        print(f"Loaded {len(rails)} right-rail records to {dataset_raw}.raw_game_right_rail")

    # Standings for each date that had games.
    standings_rows = []
    for target_date in sorted(set(dates_with_games)):
        try:
            standings_rows.extend(get_standings_by_date(target_date).get("standings", []))
        except Exception as e:
            print(f"Error fetching standings for {target_date}: {e}")
    if standings_rows:
        load_json_to_bigquery(project_id, dataset_raw, "raw_standings", standings_rows, season)
        print(f"Loaded {len(standings_rows)} standings rows to {dataset_raw}.raw_standings")

    # Partner odds snapshot (INTERNAL CALIBRATION ONLY — never exposed via API/UI).
    try:
        odds = get_partner_odds("US")
        load_json_to_bigquery(project_id, dataset_raw, "raw_partner_odds", odds, season)
        print(f"Loaded partner-odds snapshot ({len(odds.get('games', []))} games) to {dataset_raw}.raw_partner_odds")
    except Exception as e:
        print(f"Error fetching partner odds: {e}")

    print(f"Ingestion complete: {len(all_game_ids)} games across {len(dates_with_games)} dates")


def refresh_weekly_aux(**context):
    """Weekly-cadence aux ingestion: NHL Edge + season faceoff splits + glossary.

    Edge season aggregates and season-level faceoff splits change slowly, so this
    runs only on Mondays (execution_date.weekday() == 0). The glossary is refreshed
    opportunistically in the same task (idempotent: only loaded if not already present).
    """
    execution_date = context["execution_date"]
    if execution_date.weekday() != 0:
        print(f"Not Monday ({execution_date.date()}, weekday={execution_date.weekday()}); skipping weekly aux refresh.")
        return

    from ingestion.nhl_api import get_skater_faceoffs, get_glossary, derive_season_from_game_id
    from ingestion.loaders import load_json_to_bigquery
    from google.cloud import bigquery

    project_id = os.getenv("GCP_PROJECT_ID")
    dataset_raw = os.getenv("GCP_DATASET_RAW", "nhl_raw")

    # Derive the current season string/id from the execution date (Oct rollover).
    year = execution_date.year
    season = f"{year}-{str(year + 1)[2:]}" if execution_date.month >= 10 else f"{year - 1}-{str(year)[2:]}"
    season_id = season[:4] + str(int(season[:4]) + 1)

    # NHL Edge season aggregates (current season, resumable per-entity).
    try:
        from scripts.refresh_edge import refresh_season
        client = bigquery.Client(project=project_id)
        loaded = refresh_season(client, season, game_type=2)
        print(f"Edge refresh loaded {loaded} rows for {season}")
    except Exception as e:
        print(f"Error refreshing Edge: {e}")

    # Faceoff splits (regular season). Always refresh the current season (it grows).
    try:
        records = get_skater_faceoffs(season_id, game_type=2)
        for r in records:
            r["game_type"] = 2
        if records:
            load_json_to_bigquery(project_id, dataset_raw, "raw_statsrest_faceoffs", records, season)
            print(f"Loaded {len(records)} faceoff records for {season_id}")
    except Exception as e:
        print(f"Error refreshing faceoffs: {e}")

    # Glossary (only if empty).
    try:
        client = bigquery.Client(project=project_id)
        n = next(iter(client.query(
            f"SELECT COUNT(*) AS n FROM `{project_id}.{dataset_raw}.raw_glossary`"
        ).result())).n
    except Exception:
        n = 0
    if n == 0:
        try:
            terms = get_glossary().get("data", [])
            if terms:
                load_json_to_bigquery(project_id, dataset_raw, "raw_glossary", terms)
                print(f"Loaded {len(terms)} glossary terms")
        except Exception as e:
            print(f"Error refreshing glossary: {e}")
    else:
        print(f"Glossary already present ({n} terms); skipping.")


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
        print(f"No data available for {report_date}, generating no-games report")
        summary = f"No NHL games were played on {report_date}."
        report_data = []
    else:
        # Generate LLM summary only if we have data
        summary = generate_summary(report_data)
        print(f"Generated summary: {summary[:100]}...")

    # Render HTML (works with empty data)
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
    schedule_interval="0 13 * * *",  # Daily at 08:00 ET / 13:00 UTC
    start_date=datetime(2024, 1, 1),
    catchup=False,
    tags=["nhl", "ingestion", "dbt"],
) as dag:
    ingest_task = PythonOperator(
        task_id="ingest_nhl_data",
        python_callable=ingest_nhl_data,
        provide_context=True,
    )

    weekly_aux_task = PythonOperator(
        task_id="refresh_weekly_aux",
        python_callable=refresh_weekly_aux,
        provide_context=True,
    )

    _dbt_env = {
        **os.environ,
        "GCP_PROJECT_ID": os.getenv("GCP_PROJECT_ID"),
        "GCP_DATASET_RAW": os.getenv("GCP_DATASET_RAW", "nhl_raw"),
        "GCP_DATASET_STAGING": os.getenv("GCP_DATASET_STAGING", "nhl_staging"),
        "GCP_DATASET_MART": os.getenv("GCP_DATASET_MART", "nhl_mart"),
        "GCP_DATASET_MODELS": os.getenv("GCP_DATASET_MODELS", "nhl_models"),
    }
    _dbt = ("cd /opt/airflow/dbt && /home/airflow/.local/bin/dbt run "
            "--profiles-dir /opt/airflow/dbt --log-path /tmp/dbt_logs "
            "--target-path /tmp/dbt_target")

    # The in-house xG model (nhl_models.shot_xg) is scored BETWEEN staging/sequence and the
    # shot-attempt intermediates + marts that join it. So dbt runs in two passes around it.
    run_dbt_pre_xg = BashOperator(
        task_id="run_dbt_pre_xg",
        bash_command=f"{_dbt} --exclude path:models/mart int_shot_attempts int_shot_attempts_all int_shot_types int_event_leverage",
        env=_dbt_env,
    )

    # Incremental rescore of recent games (idempotent: deletes >= --since then appends).
    score_xg = BashOperator(
        task_id="score_xg",
        bash_command="cd /opt/airflow && python -m models_ml.score_xg --since {{ macros.ds_add(ds, -3) }}",
        env=_dbt_env,
    )

    run_dbt_marts = BashOperator(
        task_id="run_dbt_marts",
        bash_command=f"{_dbt} --select path:models/mart int_shot_attempts int_shot_attempts_all int_shot_types",
        env=_dbt_env,
    )

    # Power ratings (Phase 3.1) consume the freshly built marts (score-adjusted xGF%,
    # GSAx). They must run BEFORE score_winprob, which now reads team_ratings for its
    # pregame prior. The mart's own opponent adjustment reads the prior run's ratings
    # (a documented fixpoint), so ratings recompute here from the updated marts.
    compute_ratings = BashOperator(
        task_id="compute_ratings",
        bash_command="cd /opt/airflow && python -m models_ml.compute_ratings",
        env=_dbt_env,
    )

    # Deserved standings (Monte Carlo) depend only on the marts / score-adjusted xG.
    simulate_deserved = BashOperator(
        task_id="simulate_deserved",
        bash_command="cd /opt/airflow && python -m models_ml.simulate_deserved",
        env=_dbt_env,
    )

    # League style map (Phase 3.2): PCA of mart_team_identity (built in run_dbt_marts).
    # Cheap (32-team PCA), so run daily to keep it fresh rather than the plan's weekly cadence.
    compute_style_map = BashOperator(
        task_id="compute_style_map",
        bash_command="cd /opt/airflow && python -m models_ml.compute_style_map",
        env=_dbt_env,
    )

    # Streak Doctor cards (Phase 3.3): need marts + goalie GSAx + team_ratings (opponent
    # strength), so run after compute_ratings.
    streak_doctor = BashOperator(
        task_id="streak_doctor",
        bash_command="cd /opt/airflow && python -m models_ml.streak_doctor",
        env=_dbt_env,
    )

    # Isolated-impact RAPM (Phase 4.1): expensive (~1-2h with bootstrap), so refit weekly on
    # Mondays. Needs shot_xg (score_xg) + segments; independent of the team marts.
    train_rapm = BashOperator(
        task_id="train_rapm",
        bash_command=(
            "{% if macros.datetime.strptime(ds, '%Y-%m-%d').weekday() == 0 %}"
            "cd /opt/airflow && python -m models_ml.train_rapm"
            "{% else %}echo 'RAPM: weekly cadence, not Monday — skipping'{% endif %}"
        ),
        env=_dbt_env,
    )

    # --- Phase 4.3 reconciliation (weekly, Monday-gated except the cheap leverage build) ---
    _mon = "{% if macros.datetime.strptime(ds, '%Y-%m-%d').weekday() == 0 %}{}{% else %}echo 'weekly cadence, not Monday — skipping'{% endif %}"

    # int_event_leverage needs win_probability (scored above), so build it after score_winprob.
    build_event_leverage = BashOperator(
        task_id="build_event_leverage",
        bash_command=f"{_dbt} --select int_event_leverage",
        env=_dbt_env,
    )
    compute_clutch = BashOperator(
        task_id="compute_clutch",
        bash_command=_mon.format("cd /opt/airflow && python -m models_ml.compute_clutch"),
        env=_dbt_env,
    )
    compute_consistency = BashOperator(
        task_id="compute_consistency",
        bash_command=_mon.format("cd /opt/airflow && python -m models_ml.compute_consistency"),
        env=_dbt_env,
    )
    compute_coach_trust = BashOperator(
        task_id="compute_coach_trust",
        bash_command=_mon.format("cd /opt/airflow && python -m models_ml.compute_coach_trust"),
        env=_dbt_env,
    )
    compute_divergence = BashOperator(
        task_id="compute_divergence",
        bash_command=_mon.format("cd /opt/airflow && python -m models_ml.compute_divergence"),
        env=_dbt_env,
    )

    # Composite stack (Phase 4.2): per-player value on a goals scale; needs player_impact.
    compute_composite = BashOperator(
        task_id="compute_composite",
        bash_command=(
            "{% if macros.datetime.strptime(ds, '%Y-%m-%d').weekday() == 0 %}"
            "cd /opt/airflow && python -m models_ml.compute_composite"
            "{% else %}echo 'composite: weekly cadence, not Monday — skipping'{% endif %}"
        ),
        env=_dbt_env,
    )

    # Archetypes (Phase 4.2): loads the committed, canonical GMM (archetypes_v1.joblib) and
    # writes soft memberships — deterministic, no refit. Single-threaded BLAS for safety.
    write_archetypes = BashOperator(
        task_id="write_archetypes",
        bash_command=(
            "{% if macros.datetime.strptime(ds, '%Y-%m-%d').weekday() == 0 %}"
            "cd /opt/airflow && VECLIB_MAXIMUM_THREADS=1 OMP_NUM_THREADS=1 "
            "python -m models_ml.fit_archetypes --write"
            "{% else %}echo 'archetypes: weekly cadence, not Monday — skipping'{% endif %}"
        ),
        env=_dbt_env,
    )

    # Win probability + leverage depend on the marts (pregame rating) and segment context.
    score_winprob = BashOperator(
        task_id="score_winprob",
        bash_command="cd /opt/airflow && python -m models_ml.score_winprob --since {{ macros.ds_add(ds, -3) }}",
        env=_dbt_env,
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

    (
        ingest_task
        >> weekly_aux_task
        >> run_dbt_pre_xg
        >> score_xg
        >> run_dbt_marts
        >> compute_ratings
        >> score_winprob
        >> generate_report
        >> publish_report
    )
    # deserved standings + streak cards branch off ratings; style map off the marts; the
    # report waits on them all
    compute_ratings >> simulate_deserved >> generate_report
    compute_ratings >> streak_doctor >> generate_report
    run_dbt_marts >> compute_style_map >> generate_report
    # Phase 4 player models (weekly, Monday-gated inside each task): RAPM -> composite +
    # archetypes. RAPM needs shot_xg + segments + marts; composite/archetypes need RAPM.
    run_dbt_marts >> train_rapm >> compute_composite >> generate_report
    train_rapm >> write_archetypes >> generate_report
    # Phase 4.3 reconciliation: clutch (needs leverage), consistency + coach trust (marts),
    # divergence (needs composite + coach trust).
    score_winprob >> build_event_leverage >> compute_clutch >> generate_report
    run_dbt_marts >> compute_consistency >> generate_report
    run_dbt_marts >> compute_coach_trust
    [compute_composite, compute_coach_trust] >> compute_divergence >> generate_report
