"""Query module for pulling report data from BigQuery mart tables."""
import os
from typing import Any, List, Dict
from google.cloud import bigquery


def get_daily_report_data(date: str) -> List[Dict[str, Any]]:
    """Fetch all data from mart_daily_report_feed for a given date.

    Args:
        date: Date string in YYYY-MM-DD format.

    Returns:
        List of dicts containing game data for all teams that played on the date.
        Returns empty list if no games found for the date.
    """
    project_id = os.getenv("GCP_PROJECT_ID", "nhl-intel-498216")
    # mart_* tables are materialized in the mart dataset by dbt
    dataset = os.getenv("GCP_DATASET_MART", "nhl_mart")

    client = bigquery.Client(project=project_id)

    query = f"""
    SELECT
        game_date,
        game_id,
        team_id,
        team_abbrev,
        home_away,
        goals_for,
        goals_against,
        shot_attempts_for,
        shot_attempts_against,
        cf_pct,
        hdcf_per60,
        hdca_per60,
        zone_entry_proxy_success_rate,
        rolling_cf_pct_5gp,
        rolling_hdcf_per60_5gp,
        rolling_hdca_per60_5gp,
        has_full_5game_sample,
        top_player_id,
        top_player_name,
        top_player_position,
        top_player_points_per60,
        top_player_hot_cold
    FROM `{project_id}.{dataset}.mart_daily_report_feed`
    WHERE game_date = '{date}'
    ORDER BY game_id, home_away DESC
    """

    results = []
    for row in client.query(query).result():
        results.append({
            "game_date": row.game_date,
            "game_id": row.game_id,
            "team_id": row.team_id,
            "team_abbrev": row.team_abbrev,
            "home_away": row.home_away,
            "goals_for": row.goals_for,
            "goals_against": row.goals_against,
            "shot_attempts_for": row.shot_attempts_for,
            "shot_attempts_against": row.shot_attempts_against,
            "cf_pct": row.cf_pct,
            "hdcf_per60": row.hdcf_per60,
            "hdca_per60": row.hdca_per60,
            "zone_entry_proxy_success_rate": row.zone_entry_proxy_success_rate,
            "rolling_cf_pct_5gp": row.rolling_cf_pct_5gp,
            "rolling_hdcf_per60_5gp": row.rolling_hdcf_per60_5gp,
            "rolling_hdca_per60_5gp": row.rolling_hdca_per60_5gp,
            "has_full_5game_sample": row.has_full_5game_sample,
            "top_player_id": row.top_player_id,
            "top_player_name": row.top_player_name,
            "top_player_position": row.top_player_position,
            "top_player_points_per60": row.top_player_points_per60,
            "top_player_hot_cold": row.top_player_hot_cold,
        })

    return results
