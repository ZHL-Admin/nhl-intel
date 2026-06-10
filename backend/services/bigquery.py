"""BigQuery client and query utilities.

Provides singleton BigQuery client and helper methods for querying mart tables.
"""
import os
from pathlib import Path
from typing import List, Dict, Any, Optional
from google.cloud import bigquery


class BigQueryService:
    """Singleton service for BigQuery operations.

    Manages connection to BigQuery and provides query utilities for mart tables.
    """

    _instance: Optional['BigQueryService'] = None
    _client: Optional[bigquery.Client] = None

    def __new__(cls) -> 'BigQueryService':
        """Ensure only one instance of BigQueryService exists."""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self) -> None:
        """Initialize BigQuery client if not already initialized."""
        if self._client is None:
            self.project_id = os.getenv("GCP_PROJECT_ID")
            # Configure datasets for different model layers
            self.dataset_staging = os.getenv("GCP_DATASET_STAGING", "nhl_staging")
            self.dataset_mart = os.getenv("GCP_DATASET_MART", "nhl_mart")

            # Handle credentials path - make it absolute if relative
            creds_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
            if creds_path and not Path(creds_path).is_absolute():
                # Assume relative to project root (parent of backend dir)
                root_dir = Path(__file__).parent.parent.parent
                creds_path = str(root_dir / creds_path)
                os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = creds_path

            self._client = bigquery.Client(project=self.project_id)

    @property
    def client(self) -> bigquery.Client:
        """Get BigQuery client instance.

        Returns:
            BigQuery client instance.
        """
        if self._client is None:
            raise RuntimeError("BigQuery client not initialized")
        return self._client

    def query(self, sql: str, params: Optional[List[Any]] = None) -> List[Dict[str, Any]]:
        """Execute a query and return results as list of dicts.

        Args:
            sql: SQL query string.
            params: Optional query parameters for parameterized queries.

        Returns:
            List of dictionaries representing query results.

        Raises:
            Exception: If query execution fails.
        """
        job_config = bigquery.QueryJobConfig()

        if params:
            job_config.query_parameters = params

        query_job = self.client.query(sql, job_config=job_config)
        results = query_job.result()

        return [dict(row) for row in results]

    def get_full_table_id(self, table_name: str) -> str:
        """Get fully qualified table ID, routing to correct dataset by prefix.

        Args:
            table_name: Name of the table (e.g., 'stg_boxscores', 'mart_team_game_stats').

        Returns:
            Fully qualified table ID (project.dataset.table).
        """
        # Route tables to correct dataset based on prefix
        if table_name.startswith('mart_'):
            dataset = self.dataset_mart
        elif table_name.startswith('stg_') or table_name.startswith('int_'):
            dataset = self.dataset_staging
        else:
            # Default to mart for backwards compatibility
            dataset = self.dataset_mart

        return f"{self.project_id}.{dataset}.{table_name}"

    def get_game_shots(self, game_id: int, situation: str = "all") -> List[Dict[str, Any]]:
        """Fetch all shot coordinates for both teams in a game from int_shot_types.

        Args:
            game_id: NHL game identifier.
            situation: Filter by situation - "all", "5v5", or specific situation code.

        Returns:
            List of shot dictionaries with coordinates and metadata.
        """
        situation_filter = ""
        if situation != "all":
            # Map common situation names to codes
            situation_map = {
                "5v5": "1551",
                "pp": "1541",  # Power play (5v4)
                "pk": "1451"   # Penalty kill (4v5)
            }
            situation_code = situation_map.get(situation.lower(), situation)
            situation_filter = f"AND situation_code = '{situation_code}'"

        sql = f"""
        SELECT
            x_coord,
            y_coord,
            type_desc_key as shot_type,
            type_desc_key as event_type,
            situation_code,
            event_owner_team_id as team_id,
            period_number as period,
            time_in_period,
            shooting_player_id as shooter_id,
            scoring_player_id,
            goalie_in_net_id as goalie_id,
            is_goal
        FROM {self.get_full_table_id('int_shot_types')}
        WHERE game_id = {game_id}
            {situation_filter}
        ORDER BY period_number, time_in_period
        """

        return self.query(sql)

    def get_xg_worm(self, game_id: int, situation: str = "all") -> List[Dict[str, Any]]:
        """Fetch cumulative xG differential data points for the xG Worm chart.

        Args:
            game_id: NHL game identifier.
            situation: Filter by situation - "all", "5v5", or specific situation code.

        Returns:
            List of xG worm data points with cumulative differentials and goal markers.
        """
        situation_filter = ""
        if situation != "all":
            situation_map = {
                "5v5": "1551",
                "pp": "1541",
                "pk": "1451"
            }
            situation_code = situation_map.get(situation.lower(), situation)
            situation_filter = f"AND situation_code = '{situation_code}'"

        sql = f"""
        WITH shot_xg AS (
            SELECT
                game_seconds,
                event_team_id,
                is_goal,
                xg
            FROM {self.get_full_table_id('int_shot_types')}
            WHERE game_id = {game_id}
                {situation_filter}
        ),
        game_info AS (
            SELECT
                game_id,
                home_team_id,
                away_team_id,
                home_team_abbrev,
                away_team_abbrev
            FROM {self.get_full_table_id('stg_boxscores')}
            WHERE game_id = {game_id}
        ),
        cumulative_xg AS (
            SELECT
                s.game_seconds,
                SUM(CASE WHEN s.event_team_id = g.home_team_id THEN s.xg ELSE 0 END)
                    OVER (ORDER BY s.game_seconds) as home_cumulative_xg,
                SUM(CASE WHEN s.event_team_id = g.away_team_id THEN s.xg ELSE 0 END)
                    OVER (ORDER BY s.game_seconds) as away_cumulative_xg,
                s.is_goal,
                s.event_team_id,
                g.home_team_id,
                g.away_team_id,
                g.home_team_abbrev,
                g.away_team_abbrev
            FROM shot_xg s
            CROSS JOIN game_info g
        ),
        goal_markers AS (
            SELECT
                game_seconds,
                event_team_id,
                ROW_NUMBER() OVER (PARTITION BY event_team_id ORDER BY game_seconds) as goal_number
            FROM shot_xg
            WHERE is_goal = TRUE
        )
        SELECT
            c.game_seconds as game_time_seconds,
            c.home_cumulative_xg - c.away_cumulative_xg as cumulative_xg_diff,
            c.home_cumulative_xg as home_xg,
            c.away_cumulative_xg as away_xg,
            CASE WHEN c.is_goal THEN 'goal' ELSE NULL END as event_type,
            CASE WHEN c.is_goal THEN c.event_team_id ELSE NULL END as team_id,
            CASE
                WHEN c.is_goal AND c.event_team_id = c.home_team_id
                    THEN c.home_team_abbrev || ' ' || CAST(g.goal_number AS STRING) || '-' ||
                         CAST((SELECT COUNT(*) FROM goal_markers WHERE event_team_id = c.away_team_id AND game_seconds <= c.game_seconds) AS STRING)
                WHEN c.is_goal AND c.event_team_id = c.away_team_id
                    THEN c.away_team_abbrev || ' ' || CAST((SELECT COUNT(*) FROM goal_markers WHERE event_team_id = c.home_team_id AND game_seconds <= c.game_seconds) AS STRING) || '-' ||
                         CAST(g.goal_number AS STRING)
                ELSE NULL
            END as label
        FROM cumulative_xg c
        LEFT JOIN goal_markers g ON c.game_seconds = g.game_seconds AND c.event_team_id = g.event_team_id
        ORDER BY c.game_seconds
        """

        return self.query(sql)

    def get_team_zone_time(self, team_id: int, season: str, game_id: Optional[int] = None) -> List[Dict[str, Any]]:
        """Fetch zone time percentages from mart_team_zone_time.

        Args:
            team_id: Team identifier.
            season: Season in format "YYYY-YY" (e.g., "2024-25").
            game_id: Optional game ID to filter for single game.

        Returns:
            List of zone time records.
        """
        game_filter = f"AND game_id = {game_id}" if game_id else ""

        sql = f"""
        SELECT
            game_id,
            game_date,
            team_id,
            oz_pct,
            nz_pct,
            dz_pct
        FROM {self.get_full_table_id('mart_team_zone_time')}
        WHERE team_id = {team_id}
            AND season = '{season}'
            {game_filter}
        ORDER BY game_date DESC
        """

        return self.query(sql)

    def get_team_faceoffs(self, team_id: int, season: str, game_id: Optional[int] = None) -> List[Dict[str, Any]]:
        """Fetch faceoff statistics from mart_team_faceoffs.

        Args:
            team_id: Team identifier.
            season: Season in format "YYYY-YY" (e.g., "2024-25").
            game_id: Optional game ID to filter for single game.

        Returns:
            List of faceoff records.
        """
        game_filter = f"AND game_id = {game_id}" if game_id else ""

        sql = f"""
        SELECT
            game_id,
            game_date,
            team_id,
            total_faceoffs,
            faceoffs_won,
            faceoffs_lost,
            faceoff_win_pct,
            oz_faceoffs_won,
            oz_faceoff_win_pct,
            nz_faceoffs_won,
            nz_faceoff_win_pct,
            dz_faceoffs_won,
            dz_faceoff_win_pct
        FROM {self.get_full_table_id('mart_team_faceoffs')}
        WHERE team_id = {team_id}
            AND season = '{season}'
            {game_filter}
        ORDER BY game_date DESC
        """

        return self.query(sql)

    def get_team_situational(self, team_id: int, game_id: int, situation: str = "all") -> List[Dict[str, Any]]:
        """Fetch team stats for a specific game from mart_team_stats_situational.

        Args:
            team_id: Team identifier.
            game_id: Game identifier.
            situation: Filter by situation - "all", "5v5", "pp", or "pk".

        Returns:
            List of situational stat records (usually 1-4 records).
        """
        situation_filter = ""
        if situation != "all":
            situation_filter = f"AND situation = '{situation}'"

        sql = f"""
        SELECT
            game_id,
            team_id,
            situation,
            toi_seconds,
            cf_pct,
            xgf_pct,
            hdcf_pct,
            goals_for,
            goals_against,
            shot_attempts_for,
            shot_attempts_against
        FROM {self.get_full_table_id('mart_team_stats_situational')}
        WHERE team_id = {team_id}
            AND game_id = {game_id}
            {situation_filter}
        ORDER BY
            CASE situation
                WHEN 'all' THEN 1
                WHEN '5v5' THEN 2
                WHEN 'pp' THEN 3
                WHEN 'pk' THEN 4
                ELSE 5
            END
        """

        return self.query(sql)

    def get_player_situational(self, player_id: int, season: str) -> List[Dict[str, Any]]:
        """Fetch player stats by situation from mart_player_situational.

        Args:
            player_id: Player identifier.
            season: Season in format "YYYY-YY" (e.g., "2024-25").

        Returns:
            List of situational stat records (usually 4: all, 5v5, pp, pk).
        """
        sql = f"""
        SELECT
            player_id,
            season,
            situation,
            games_played,
            toi_per_gp,
            points_per60,
            goals_per60,
            ixg_per60,
            cf_pct,
            hdcf_per60
        FROM {self.get_full_table_id('mart_player_situational')}
        WHERE player_id = {player_id}
            AND season = '{season}'
        ORDER BY
            CASE situation
                WHEN 'all' THEN 1
                WHEN '5v5' THEN 2
                WHEN 'pp' THEN 3
                WHEN 'pk' THEN 4
                ELSE 5
            END
        """

        return self.query(sql)

    def get_player_zone_deployment(self, player_id: int, season: str) -> List[Dict[str, Any]]:
        """Fetch zone deployment from mart_player_zone_deployment.

        Args:
            player_id: Player identifier.
            season: Season in format "YYYY-YY" (e.g., "2024-25").

        Returns:
            List with single zone deployment record.
        """
        sql = f"""
        SELECT
            player_id,
            season,
            team_id,
            offensive_zone_starts,
            neutral_zone_starts,
            defensive_zone_starts,
            total_zone_starts,
            ozs_pct,
            nzs_pct,
            dzs_pct
        FROM {self.get_full_table_id('mart_player_zone_deployment')}
        WHERE player_id = {player_id}
            AND season = '{season}'
        """

        return self.query(sql)

    def get_player_shooting_luck(self, player_id: int, season: str) -> List[Dict[str, Any]]:
        """Fetch shooting luck metrics from mart_player_shooting_luck.

        Args:
            player_id: Player identifier.
            season: Season in format "YYYY-YY" (e.g., "2024-25").

        Returns:
            List with single shooting luck record.
        """
        sql = f"""
        SELECT
            player_id,
            season,
            team_id,
            total_shots,
            total_goals,
            total_ixg,
            actual_shooting_pct,
            expected_shooting_pct,
            shooting_luck_delta
        FROM {self.get_full_table_id('mart_player_shooting_luck')}
        WHERE player_id = {player_id}
            AND season = '{season}'
        """

        return self.query(sql)

    def get_player_relative(self, player_id: int, season: str) -> List[Dict[str, Any]]:
        """Fetch relative performance from mart_player_relative.

        Args:
            player_id: Player identifier.
            season: Season in format "YYYY-YY" (e.g., "2024-25").

        Returns:
            List with single relative performance record.
        """
        sql = f"""
        SELECT
            player_id,
            season,
            team_id,
            player_cf_pct,
            team_cf_pct,
            relative_cf_pct,
            player_xgf_pct,
            team_xgf_pct,
            relative_xgf_pct
        FROM {self.get_full_table_id('mart_player_relative')}
        WHERE player_id = {player_id}
            AND season = '{season}'
        """

        return self.query(sql)


# Create singleton instance
bq_service = BigQueryService()
