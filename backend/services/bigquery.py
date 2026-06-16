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
            self.dataset_models = os.getenv("GCP_DATASET_MODELS", "nhl_models")

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

    def get_models_table_id(self, table_name: str) -> str:
        """Fully qualified ID for a Python model-layer output table (nhl_models)."""
        return f"{self.project_id}.{self.dataset_models}.{table_name}"

    def get_player_edge(self, player_id: int, season_id: Optional[int] = None, game_type: int = 2) -> Optional[Dict[str, Any]]:
        """Fetch a skater's NHL Edge profile for a season (latest if unspecified).

        Args:
            player_id: NHL player id.
            season_id: Season as YYYYYYYY (e.g. 20242025). Latest available if None.
            game_type: 2 = regular season, 3 = playoffs.

        Returns:
            The Edge profile row, or None if no Edge data exists for the player.
        """
        table = self.get_full_table_id('mart_edge_player_profile')
        season_filter = f"AND season_id = {int(season_id)}" if season_id else ""
        sql = f"""
        SELECT * FROM {table}
        WHERE player_id = {int(player_id)} AND game_type = {int(game_type)}
            {season_filter}
        ORDER BY season_id DESC
        LIMIT 1
        """
        rows = self.query(sql)
        return rows[0] if rows else None

    def get_team_edge(self, team_id: int, season_id: Optional[int] = None, game_type: int = 2) -> Optional[Dict[str, Any]]:
        """Fetch a team's NHL Edge profile for a season (latest if unspecified)."""
        table = self.get_full_table_id('mart_edge_team_profile')
        season_filter = f"AND season_id = {int(season_id)}" if season_id else ""
        sql = f"""
        SELECT * FROM {table}
        WHERE team_id = {int(team_id)} AND game_type = {int(game_type)}
            {season_filter}
        ORDER BY season_id DESC
        LIMIT 1
        """
        rows = self.query(sql)
        return rows[0] if rows else None

    def get_game_context(self, game_id: int) -> Optional[Dict[str, Any]]:
        """Fetch GameDetail context: scratches, season series, team stats, goal videos.

        Sources stg_game_context (the parsed landing/right-rail surface) and joins each
        team's last-10 record from stg_standings as-of the game date (last-10 is absent
        from the landing/right-rail payloads). Returns None if the game has no context.

        Args:
            game_id: Game identifier.

        Returns:
            A single context dict with nested arrays, or None if not ingested.
        """
        ctx = self.get_full_table_id('stg_game_context')
        games = self.get_full_table_id('stg_games')
        standings = self.get_full_table_id('stg_standings')

        sql = f"""
        WITH g AS (
            SELECT game_id, game_date, home_team_abbrev, away_team_abbrev
            FROM {games} WHERE game_id = {game_id}
        ),
        -- Latest standings row on or before the game date, per team abbrev.
        l10 AS (
            SELECT
                s.team_abbrev, s.l10_wins, s.l10_losses, s.l10_ot_losses,
                s.league_rank, s.points,
                ROW_NUMBER() OVER (
                    PARTITION BY s.team_abbrev ORDER BY s.standings_date DESC
                ) AS rn
            FROM {standings} s
            JOIN g ON s.standings_date <= g.game_date
                  AND s.team_abbrev IN (g.home_team_abbrev, g.away_team_abbrev)
        )
        SELECT
            c.*,
            g.home_team_abbrev,
            g.away_team_abbrev,
            (SELECT AS STRUCT team_abbrev, l10_wins, l10_losses, l10_ot_losses, league_rank, points
             FROM l10 WHERE team_abbrev = g.home_team_abbrev AND rn = 1) AS home_last10,
            (SELECT AS STRUCT team_abbrev, l10_wins, l10_losses, l10_ot_losses, league_rank, points
             FROM l10 WHERE team_abbrev = g.away_team_abbrev AND rn = 1) AS away_last10
        FROM {ctx} c
        CROSS JOIN g
        WHERE c.game_id = {game_id}
        """
        rows = self.query(sql)
        return rows[0] if rows else None

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
            s.x_coord,
            s.y_coord,
            s.type_desc_key as shot_type,
            s.type_desc_key as event_type,
            s.situation_code,
            s.event_owner_team_id as team_id,
            s.period_number as period,
            s.time_in_period,
            s.shooting_player_id as shooter_id,
            s.scoring_player_id,
            s.goalie_in_net_id as goalie_id,
            s.is_goal,
            mx.xg,
            mx.base_rate,
            mx.xg_contrib_location,
            mx.xg_contrib_shot_type,
            mx.xg_contrib_strength,
            mx.xg_contrib_sequence,
            mx.xg_contrib_game_state
        FROM {self.get_full_table_id('int_shot_types')} s
        LEFT JOIN {self.get_models_table_id('shot_xg')} mx
            ON s.game_id = mx.game_id AND s.event_id = mx.event_id
        WHERE s.game_id = {game_id}
            {situation_filter}
        ORDER BY s.period_number, s.time_in_period
        """

        return self.query(sql)

    def get_winprob(self, game_id: int) -> List[Dict[str, Any]]:
        """Win-probability + leverage series for a game (Phase 2.4)."""
        sql = f"""
        SELECT elapsed_seconds, home_wp, leverage, model_version
        FROM {self.get_models_table_id('win_probability')}
        WHERE game_id = {game_id}
        ORDER BY elapsed_seconds
        """
        return self.query(sql)

    def get_winprob_goal_swings(self, game_id: int) -> List[Dict[str, Any]]:
        """Per-goal win-probability swing: home_wp just after vs just before each goal."""
        sql = f"""
        WITH wp AS (
            SELECT elapsed_seconds, home_wp
            FROM {self.get_models_table_id('win_probability')}
            WHERE game_id = {game_id}
        ),
        goals AS (
            SELECT
                (period_number - 1) * 1200
                  + CAST(SPLIT(time_in_period, ':')[OFFSET(0)] AS INT64) * 60
                  + CAST(SPLIT(time_in_period, ':')[OFFSET(1)] AS INT64) AS elapsed,
                event_owner_team_id AS team_id,
                scoring_player_id
            FROM {self.get_full_table_id('stg_play_by_play')}
            WHERE game_id = {game_id} AND type_desc_key = 'goal' AND time_in_period IS NOT NULL
        )
        SELECT
            g.elapsed AS elapsed_seconds,
            g.team_id,
            g.scoring_player_id,
            (SELECT home_wp FROM wp WHERE wp.elapsed_seconds <= g.elapsed ORDER BY wp.elapsed_seconds DESC LIMIT 1) AS wp_before,
            (SELECT home_wp FROM wp WHERE wp.elapsed_seconds > g.elapsed ORDER BY wp.elapsed_seconds ASC LIMIT 1) AS wp_after
        FROM goals g
        ORDER BY g.elapsed
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
        # mart_player_zone_deployment is per-game; aggregate to a season row.
        sql = f"""
        SELECT
            player_id,
            season,
            ANY_VALUE(team_id) AS team_id,
            AVG(ozs_pct) AS ozs_pct,
            AVG(nzs_pct) AS nzs_pct,
            AVG(dzs_pct) AS dzs_pct
        FROM {self.get_full_table_id('mart_player_zone_deployment')}
        WHERE player_id = {player_id}
            AND season = '{season}'
        GROUP BY player_id, season
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
        # mart_player_shooting_luck is per-game; aggregate over the season (volume-weighted).
        sql = f"""
        SELECT
            player_id,
            season,
            ANY_VALUE(team_id) AS team_id,
            SUM(individual_shot_attempts) AS total_shots,
            SUM(individual_goals) AS total_goals,
            SUM(ixg) AS total_ixg,
            SAFE_DIVIDE(SUM(individual_goals), SUM(individual_shot_attempts)) AS actual_shooting_pct,
            SAFE_DIVIDE(SUM(ixg), SUM(individual_shot_attempts)) AS expected_shooting_pct,
            SAFE_DIVIDE(SUM(individual_goals), SUM(individual_shot_attempts))
                - SAFE_DIVIDE(SUM(ixg), SUM(individual_shot_attempts)) AS shooting_luck_delta
        FROM {self.get_full_table_id('mart_player_shooting_luck')}
        WHERE player_id = {player_id}
            AND season = '{season}'
        GROUP BY player_id, season
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
        # mart_player_relative is per-game and xG-based (no Corsi); aggregate over the season.
        # relative_cf_pct is unavailable in the current mart -> null.
        sql = f"""
        SELECT
            player_id,
            season,
            ANY_VALUE(team_id) AS team_id,
            CAST(NULL AS FLOAT64) AS relative_cf_pct,
            AVG(on_ice_xgf_pct) AS player_xgf_pct,
            AVG(team_avg_on_ice_xgf_pct) AS team_xgf_pct,
            AVG(on_ice_xgf_pct_rel) AS relative_xgf_pct
        FROM {self.get_full_table_id('mart_player_relative')}
        WHERE player_id = {player_id}
            AND season = '{season}'
        GROUP BY player_id, season
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
        """Per-goalie save record split by danger tier, plus total GSAx, from the Phase 2.5
        goalie mart (calibrated xGA over all unblocked shots; standard low/med/high tiers).
        """
        goalie = self.get_full_table_id('mart_goalie_game_stats')
        box = self.get_full_table_id('stg_boxscores')
        rosters = self.get_full_table_id('stg_rosters')
        sql = f"""
        WITH gi AS (
            SELECT home_team_id, away_team_id, home_team_abbrev, away_team_abbrev
            FROM {box} WHERE game_id = {game_id}
        )
        SELECT
            g.goalie_id AS player_id,
            g.high_saves, g.high_shots, g.med_saves, g.med_shots, g.low_saves, g.low_shots,
            ROUND(g.gsax, 2) AS gsax,
            CONCAT(COALESCE(r.first_name, ''), ' ', COALESCE(r.last_name, '')) AS goalie_name,
            CASE WHEN g.team_id = gi.home_team_id THEN gi.home_team_abbrev ELSE gi.away_team_abbrev END AS team_abbrev
        FROM {goalie} g
        CROSS JOIN gi
        LEFT JOIN {rosters} r ON r.game_id = {game_id} AND r.player_id = g.goalie_id
        WHERE g.game_id = {game_id}
        ORDER BY g.shots_faced DESC
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
