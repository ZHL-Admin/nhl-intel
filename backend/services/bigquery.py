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
            self.dataset_raw = os.getenv("GCP_DATASET_RAW", "nhl_raw")

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
        elif table_name.startswith('raw_'):
            dataset = self.dataset_raw
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
        # Default ("all") includes every strength state so power-play and empty-net
        # play and their goals appear; "5v5" restricts to even strength.
        situation_filter = ""
        if situation.lower() == "5v5":
            situation_filter = "AND situation_code = '1551'"

        sql = f"""
        WITH shot_xg AS (
            SELECT
                -- Calculate game_seconds from period and time_in_period
                CASE
                    WHEN period_number = 1 THEN CAST(SPLIT(time_in_period, ':')[OFFSET(0)] AS INT64) * 60 + CAST(SPLIT(time_in_period, ':')[OFFSET(1)] AS INT64)
                    WHEN period_number = 2 THEN 1200 + CAST(SPLIT(time_in_period, ':')[OFFSET(0)] AS INT64) * 60 + CAST(SPLIT(time_in_period, ':')[OFFSET(1)] AS INT64)
                    WHEN period_number = 3 THEN 2400 + CAST(SPLIT(time_in_period, ':')[OFFSET(0)] AS INT64) * 60 + CAST(SPLIT(time_in_period, ':')[OFFSET(1)] AS INT64)
                    WHEN period_number >= 4 THEN 3600 + CAST(SPLIT(time_in_period, ':')[OFFSET(0)] AS INT64) * 60 + CAST(SPLIT(time_in_period, ':')[OFFSET(1)] AS INT64)
                    ELSE 0
                END as game_seconds,
                event_owner_team_id as event_team_id,
                is_goal,
                COALESCE(xg_value, 0) as xg
            FROM {self.get_full_table_id('int_shot_attempts_all')}
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

    def get_goaltending(self, game_id: int) -> List[Dict[str, Any]]:
        """Per-goalie line for a game using the goalie that was in net for each shot.

        Args:
            game_id: NHL game identifier.

        Returns:
            One row per goalie who faced shots, with shots/goals against and name.
        """
        rosters = self.get_full_table_id('stg_rosters')
        sql = f"""
        WITH gi AS (
            SELECT home_team_id, away_team_id, home_team_abbrev, away_team_abbrev
            FROM {self.get_full_table_id('stg_boxscores')}
            WHERE game_id = {game_id}
        ),
        sog AS (
            SELECT
                goalie_in_net_id AS goalie_id,
                COUNTIF(type_desc_key IN ('shot-on-goal', 'goal')) AS shots_against,
                COUNTIF(type_desc_key = 'goal') AS goals_against
            FROM {self.get_full_table_id('stg_play_by_play')}
            WHERE game_id = {game_id}
                AND type_desc_key IN ('shot-on-goal', 'goal')
                AND goalie_in_net_id IS NOT NULL
            GROUP BY goalie_in_net_id
        ),
        xg AS (
            -- Expected goals against, from the xG model, for on-net shots faced
            SELECT
                goalie_in_net_id AS goalie_id,
                SUM(IF(is_on_net, xg_value, 0)) AS xga
            FROM {self.get_full_table_id('int_shot_attempts_all')}
            WHERE game_id = {game_id} AND goalie_in_net_id IS NOT NULL
            GROUP BY goalie_in_net_id
        )
        SELECT
            sog.goalie_id AS player_id,
            sog.shots_against,
            sog.goals_against,
            COALESCE(xg.xga, 0.0) AS xga,
            COALESCE(xg.xga, 0.0) - sog.goals_against AS gsax,
            CONCAT(COALESCE(r.first_name, ''), ' ', COALESCE(r.last_name, '')) AS goalie_name,
            CASE WHEN r.team_id = gi.home_team_id THEN gi.home_team_abbrev ELSE gi.away_team_abbrev END AS team_abbrev,
            r.headshot_url AS headshot
        FROM sog
        LEFT JOIN xg ON xg.goalie_id = sog.goalie_id
        CROSS JOIN gi
        LEFT JOIN {rosters} r ON r.game_id = {game_id} AND r.player_id = sog.goalie_id
        ORDER BY sog.shots_against DESC
        """
        return self.query(sql)

    def get_team_comparison(self, game_id: int) -> Optional[Dict[str, Any]]:
        """Compute box-score team-vs-team counts for a game from play-by-play events.

        Args:
            game_id: NHL game identifier.

        Returns:
            One dict of home_/away_ counts, or None if the game is unknown.
        """
        sql = f"""
        WITH gi AS (
            SELECT home_team_id AS h, away_team_id AS a
            FROM {self.get_full_table_id('stg_boxscores')}
            WHERE game_id = {game_id}
        ),
        ev AS (
            SELECT type_desc_key, event_owner_team_id, situation_code, duration
            FROM {self.get_full_table_id('stg_play_by_play')}
            WHERE game_id = {game_id}
        )
        SELECT
            gi.h AS home_team_id,
            gi.a AS away_team_id,
            COUNTIF(type_desc_key = 'goal' AND event_owner_team_id = gi.h) AS home_goals,
            COUNTIF(type_desc_key = 'goal' AND event_owner_team_id = gi.a) AS away_goals,
            COUNTIF(type_desc_key IN ('shot-on-goal', 'goal') AND event_owner_team_id = gi.h) AS home_sog,
            COUNTIF(type_desc_key IN ('shot-on-goal', 'goal') AND event_owner_team_id = gi.a) AS away_sog,
            COUNTIF(type_desc_key = 'goal' AND event_owner_team_id = gi.h
                AND SAFE_CAST(SUBSTR(situation_code, 3, 1) AS INT64) > SAFE_CAST(SUBSTR(situation_code, 2, 1) AS INT64)) AS home_pp_goals,
            COUNTIF(type_desc_key = 'goal' AND event_owner_team_id = gi.a
                AND SAFE_CAST(SUBSTR(situation_code, 2, 1) AS INT64) > SAFE_CAST(SUBSTR(situation_code, 3, 1) AS INT64)) AS away_pp_goals,
            SUM(IF(type_desc_key = 'penalty' AND event_owner_team_id = gi.h, COALESCE(duration, 0), 0)) AS home_pim,
            SUM(IF(type_desc_key = 'penalty' AND event_owner_team_id = gi.a, COALESCE(duration, 0), 0)) AS away_pim,
            COUNTIF(type_desc_key = 'penalty' AND event_owner_team_id = gi.h) AS home_penalties,
            COUNTIF(type_desc_key = 'penalty' AND event_owner_team_id = gi.a) AS away_penalties,
            COUNTIF(type_desc_key = 'hit' AND event_owner_team_id = gi.h) AS home_hits,
            COUNTIF(type_desc_key = 'hit' AND event_owner_team_id = gi.a) AS away_hits,
            COUNTIF(type_desc_key = 'faceoff' AND event_owner_team_id = gi.h) AS home_faceoff_wins,
            COUNTIF(type_desc_key = 'faceoff' AND event_owner_team_id = gi.a) AS away_faceoff_wins,
            -- A team's blocks = the opponent's shots that were blocked
            COUNTIF(type_desc_key = 'blocked-shot' AND event_owner_team_id = gi.a) AS home_blocks,
            COUNTIF(type_desc_key = 'blocked-shot' AND event_owner_team_id = gi.h) AS away_blocks,
            COUNTIF(type_desc_key = 'giveaway' AND event_owner_team_id = gi.h) AS home_giveaways,
            COUNTIF(type_desc_key = 'giveaway' AND event_owner_team_id = gi.a) AS away_giveaways,
            COUNTIF(type_desc_key = 'takeaway' AND event_owner_team_id = gi.h) AS home_takeaways,
            COUNTIF(type_desc_key = 'takeaway' AND event_owner_team_id = gi.a) AS away_takeaways
        FROM ev CROSS JOIN gi
        GROUP BY gi.h, gi.a
        """
        rows = self.query(sql)
        return rows[0] if rows else None

    def get_pressure_shots(self, game_id: int) -> List[Dict[str, Any]]:
        """Fetch unblocked (Fenwick) shot timestamps for a game, flagged home/away.

        Args:
            game_id: NHL game identifier.

        Returns:
            One row per unblocked shot attempt with game_seconds and is_home.
        """
        sql = f"""
        WITH game_info AS (
            SELECT home_team_id, away_team_id
            FROM {self.get_full_table_id('stg_boxscores')}
            WHERE game_id = {game_id}
        ),
        shots AS (
            SELECT
                CASE
                    WHEN period_number <= 3 THEN (period_number - 1) * 1200
                    ELSE 3600
                END
                + CAST(SPLIT(time_in_period, ':')[OFFSET(0)] AS INT64) * 60
                + CAST(SPLIT(time_in_period, ':')[OFFSET(1)] AS INT64) AS game_seconds,
                event_owner_team_id AS team_id
            FROM {self.get_full_table_id('int_shot_attempts_all')}
            WHERE game_id = {game_id}
                AND is_blocked = FALSE
                AND period_type != 'SO'
        )
        SELECT
            s.game_seconds,
            s.team_id = gi.home_team_id AS is_home
        FROM shots s
        CROSS JOIN game_info gi
        ORDER BY s.game_seconds
        """
        return self.query(sql)

    def get_game_goals(self, game_id: int) -> List[Dict[str, Any]]:
        """Fetch detailed goal information for a game (scorer, assists, strength).

        Args:
            game_id: NHL game identifier.

        Returns:
            One row per goal with scorer/assist names, headshot, situation and timing.
        """
        rosters = self.get_full_table_id('stg_rosters')
        sql = f"""
        WITH goals AS (
            SELECT
                event_id,
                CASE
                    WHEN period_number = 1 THEN CAST(SPLIT(time_in_period, ':')[OFFSET(0)] AS INT64) * 60 + CAST(SPLIT(time_in_period, ':')[OFFSET(1)] AS INT64)
                    WHEN period_number = 2 THEN 1200 + CAST(SPLIT(time_in_period, ':')[OFFSET(0)] AS INT64) * 60 + CAST(SPLIT(time_in_period, ':')[OFFSET(1)] AS INT64)
                    WHEN period_number = 3 THEN 2400 + CAST(SPLIT(time_in_period, ':')[OFFSET(0)] AS INT64) * 60 + CAST(SPLIT(time_in_period, ':')[OFFSET(1)] AS INT64)
                    WHEN period_number >= 4 THEN 3600 + CAST(SPLIT(time_in_period, ':')[OFFSET(0)] AS INT64) * 60 + CAST(SPLIT(time_in_period, ':')[OFFSET(1)] AS INT64)
                    ELSE 0
                END as game_seconds,
                period_number,
                time_in_period,
                situation_code,
                event_owner_team_id,
                scoring_player_id,
                assist1_player_id,
                assist2_player_id
            FROM {self.get_full_table_id('stg_play_by_play')}
            WHERE game_id = {game_id}
                AND type_desc_key = 'goal'
                AND period_type != 'SO'
        ),
        game_info AS (
            SELECT home_team_id, away_team_id, home_team_abbrev, away_team_abbrev
            FROM {self.get_full_table_id('stg_boxscores')}
            WHERE game_id = {game_id}
        )
        SELECT
            g.game_seconds,
            g.period_number,
            g.time_in_period,
            g.situation_code,
            g.event_owner_team_id,
            gi.home_team_id,
            gi.away_team_id,
            gi.home_team_abbrev,
            gi.away_team_abbrev,
            g.scoring_player_id,
            CONCAT(COALESCE(s.first_name, ''), ' ', COALESCE(s.last_name, '')) as scorer_name,
            s.headshot_url as scorer_headshot,
            CONCAT(COALESCE(a1.first_name, ''), ' ', COALESCE(a1.last_name, '')) as assist1_name,
            CONCAT(COALESCE(a2.first_name, ''), ' ', COALESCE(a2.last_name, '')) as assist2_name,
            g.assist1_player_id,
            g.assist2_player_id
        FROM goals g
        CROSS JOIN game_info gi
        LEFT JOIN {rosters} s ON s.game_id = {game_id} AND s.player_id = g.scoring_player_id
        LEFT JOIN {rosters} a1 ON a1.game_id = {game_id} AND a1.player_id = g.assist1_player_id
        LEFT JOIN {rosters} a2 ON a2.game_id = {game_id} AND a2.player_id = g.assist2_player_id
        ORDER BY g.game_seconds
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

    def get_special_teams(self, game_id: int) -> List[Dict[str, Any]]:
        """Per-team power-play and penalty-kill detail for a game.

        PP/PK are derived from the skater counts in situation_code
        (pos 2 = away skaters, pos 3 = home skaters).

        Returns:
            Two rows (home and away) of PP/PK counts and PP xG.
        """
        shots = self.get_full_table_id('int_shot_attempts_all')
        pbp = self.get_full_table_id('stg_play_by_play')
        box = self.get_full_table_id('stg_boxscores')
        sql = f"""
        WITH gi AS (
            SELECT home_team_id AS h, away_team_id AS a, home_team_abbrev AS ha, away_team_abbrev AS aa
            FROM {box} WHERE game_id = {game_id}
        ),
        s AS (
            SELECT
                event_owner_team_id AS team_id,
                is_on_net, is_goal, xg_value,
                SAFE_CAST(SUBSTR(situation_code, 2, 1) AS INT64) AS away_sk,
                SAFE_CAST(SUBSTR(situation_code, 3, 1) AS INT64) AS home_sk
            FROM {shots}
            WHERE game_id = {game_id} AND period_type != 'SO'
        ),
        pen AS (
            SELECT
                COUNTIF(event_owner_team_id = (SELECT h FROM gi)) AS home_pen,
                COUNTIF(event_owner_team_id = (SELECT a FROM gi)) AS away_pen
            FROM {pbp} WHERE game_id = {game_id} AND type_desc_key = 'penalty'
        )
        SELECT side, team_abbrev, is_home, pp_goals, pp_opp, pp_xg, pp_shots, pk_saves, pk_shots FROM (
            SELECT
                'home' AS side, gi.ha AS team_abbrev, TRUE AS is_home,
                COUNTIF(s.is_goal AND s.team_id = gi.h AND s.home_sk > s.away_sk) AS pp_goals,
                (SELECT away_pen FROM pen) AS pp_opp,
                ROUND(SUM(IF(s.team_id = gi.h AND s.home_sk > s.away_sk, s.xg_value, 0)), 2) AS pp_xg,
                COUNTIF(s.is_on_net AND s.team_id = gi.h AND s.home_sk > s.away_sk) AS pp_shots,
                COUNTIF(s.is_on_net AND s.team_id = gi.a AND s.away_sk > s.home_sk)
                    - COUNTIF(s.is_goal AND s.team_id = gi.a AND s.away_sk > s.home_sk) AS pk_saves,
                COUNTIF(s.is_on_net AND s.team_id = gi.a AND s.away_sk > s.home_sk) AS pk_shots
            FROM s CROSS JOIN gi GROUP BY gi.ha
            UNION ALL
            SELECT
                'away' AS side, gi.aa AS team_abbrev, FALSE AS is_home,
                COUNTIF(s.is_goal AND s.team_id = gi.a AND s.away_sk > s.home_sk) AS pp_goals,
                (SELECT home_pen FROM pen) AS pp_opp,
                ROUND(SUM(IF(s.team_id = gi.a AND s.away_sk > s.home_sk, s.xg_value, 0)), 2) AS pp_xg,
                COUNTIF(s.is_on_net AND s.team_id = gi.a AND s.away_sk > s.home_sk) AS pp_shots,
                COUNTIF(s.is_on_net AND s.team_id = gi.h AND s.home_sk > s.away_sk)
                    - COUNTIF(s.is_goal AND s.team_id = gi.h AND s.home_sk > s.away_sk) AS pk_saves,
                COUNTIF(s.is_on_net AND s.team_id = gi.h AND s.home_sk > s.away_sk) AS pk_shots
            FROM s CROSS JOIN gi GROUP BY gi.aa
        )
        ORDER BY is_home
        """
        return self.query(sql)

    def get_goalie_danger(self, game_id: int) -> List[Dict[str, Any]]:
        """Per-goalie save record split by shot-danger band, plus total GSAx.

        Danger bands: high = is_high_danger; medium = xg_value >= 0.04 (non-high);
        low = everything else. GSAx = expected goals against - actual goals against.
        """
        shots = self.get_full_table_id('int_shot_attempts_all')
        box = self.get_full_table_id('stg_boxscores')
        rosters = self.get_full_table_id('stg_rosters')
        sql = f"""
        WITH gi AS (
            SELECT home_team_id, away_team_id, home_team_abbrev, away_team_abbrev
            FROM {box} WHERE game_id = {game_id}
        ),
        s AS (
            SELECT
                goalie_in_net_id AS goalie_id,
                is_on_net, is_goal, xg_value,
                CASE
                    WHEN xg_value >= 0.10 THEN 'high'
                    WHEN xg_value >= 0.045 THEN 'medium'
                    ELSE 'low'
                END AS band
            FROM {shots}
            WHERE game_id = {game_id} AND goalie_in_net_id IS NOT NULL AND period_type != 'SO'
        ),
        agg AS (
            SELECT
                goalie_id,
                COUNTIF(is_on_net AND band = 'high') AS high_shots,
                COUNTIF(is_on_net AND band = 'high') - COUNTIF(is_goal AND band = 'high') AS high_saves,
                COUNTIF(is_on_net AND band = 'medium') AS med_shots,
                COUNTIF(is_on_net AND band = 'medium') - COUNTIF(is_goal AND band = 'medium') AS med_saves,
                COUNTIF(is_on_net AND band = 'low') AS low_shots,
                COUNTIF(is_on_net AND band = 'low') - COUNTIF(is_goal AND band = 'low') AS low_saves,
                SUM(IF(is_on_net, xg_value, 0)) - COUNTIF(is_goal) AS gsax,
                COUNTIF(is_on_net) AS total_shots
            FROM s GROUP BY goalie_id
        )
        SELECT
            agg.goalie_id AS player_id,
            agg.high_saves, agg.high_shots, agg.med_saves, agg.med_shots, agg.low_saves, agg.low_shots,
            ROUND(agg.gsax, 2) AS gsax,
            CONCAT(COALESCE(r.first_name, ''), ' ', COALESCE(r.last_name, '')) AS goalie_name,
            CASE WHEN r.team_id = gi.home_team_id THEN gi.home_team_abbrev ELSE gi.away_team_abbrev END AS team_abbrev
        FROM agg
        CROSS JOIN gi
        LEFT JOIN {rosters} r ON r.game_id = {game_id} AND r.player_id = agg.goalie_id
        ORDER BY agg.total_shots DESC
        """
        return self.query(sql)

    def get_shot_quality(self, game_id: int) -> List[Dict[str, Any]]:
        """Per-team shot attempts and goals by danger band (the shot-quality ladder)."""
        shots = self.get_full_table_id('int_shot_attempts_all')
        box = self.get_full_table_id('stg_boxscores')
        sql = f"""
        WITH gi AS (
            SELECT home_team_id AS h, away_team_id AS a, home_team_abbrev AS ha, away_team_abbrev AS aa
            FROM {box} WHERE game_id = {game_id}
        ),
        s AS (
            SELECT
                event_owner_team_id AS team_id, is_goal,
                CASE
                    WHEN xg_value >= 0.10 THEN 'High danger'
                    WHEN xg_value >= 0.045 THEN 'Medium'
                    ELSE 'Low'
                END AS band
            FROM {shots}
            WHERE game_id = {game_id} AND period_type != 'SO'
        )
        SELECT
            band,
            COUNTIF(s.team_id = gi.h) AS home_attempts,
            COUNTIF(s.team_id = gi.h AND s.is_goal) AS home_goals,
            COUNTIF(s.team_id = gi.a) AS away_attempts,
            COUNTIF(s.team_id = gi.a AND s.is_goal) AS away_goals,
            (SELECT ha FROM gi) AS home_abbrev,
            (SELECT aa FROM gi) AS away_abbrev
        FROM s CROSS JOIN gi
        GROUP BY band
        ORDER BY CASE band WHEN 'High danger' THEN 1 WHEN 'Medium' THEN 2 ELSE 3 END
        """
        return self.query(sql)

    def get_skater_impact(self, game_id: int) -> List[Dict[str, Any]]:
        """Per-skater impact line with real TOI and box-score G/A/P from the raw
        boxscore, joined to individual xG and high-danger chances from the shot model.
        """
        raw = self.get_full_table_id('raw_boxscores')
        shots = self.get_full_table_id('int_shot_attempts_all')
        sql = f"""
        WITH box AS (
            SELECT
                homeTeam.id AS home_id, homeTeam.abbrev AS home_abbrev,
                awayTeam.id AS away_id, awayTeam.abbrev AS away_abbrev,
                playerByGameStats AS p
            FROM {raw} WHERE game_id = {game_id}
        ),
        skaters AS (
            SELECT 'home' AS side, home_abbrev AS team_abbrev, sk.playerId AS player_id,
                sk.name.default AS player_name, sk.position, sk.toi,
                sk.goals, sk.assists, sk.points, sk.sog AS shots
            FROM box, UNNEST(p.homeTeam.forwards) sk
            UNION ALL
            SELECT 'home', home_abbrev, sk.playerId, sk.name.default, sk.position, sk.toi,
                sk.goals, sk.assists, sk.points, sk.sog
            FROM box, UNNEST(p.homeTeam.defense) sk
            UNION ALL
            SELECT 'away', away_abbrev, sk.playerId, sk.name.default, sk.position, sk.toi,
                sk.goals, sk.assists, sk.points, sk.sog
            FROM box, UNNEST(p.awayTeam.forwards) sk
            UNION ALL
            SELECT 'away', away_abbrev, sk.playerId, sk.name.default, sk.position, sk.toi,
                sk.goals, sk.assists, sk.points, sk.sog
            FROM box, UNNEST(p.awayTeam.defense) sk
        ),
        ix AS (
            SELECT
                COALESCE(shooting_player_id, scoring_player_id) AS pid,
                ROUND(SUM(xg_value), 2) AS ixg,
                COUNTIF(is_high_danger) AS ihdcf
            FROM {shots}
            WHERE game_id = {game_id}
                AND COALESCE(shooting_player_id, scoring_player_id) IS NOT NULL
            GROUP BY pid
        )
        SELECT
            sk.player_id, sk.player_name, sk.team_abbrev, sk.position, sk.toi,
            sk.goals, sk.assists, sk.points, sk.shots,
            COALESCE(ix.ixg, 0.0) AS ixg,
            COALESCE(ix.ihdcf, 0) AS ihdcf
        FROM skaters sk
        LEFT JOIN ix ON ix.pid = sk.player_id
        """
        return self.query(sql)


# Create singleton instance
bq_service = BigQueryService()
