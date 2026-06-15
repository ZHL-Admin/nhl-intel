"""Game-related API endpoints.

Provides endpoints for game lists, game details, and game player stats.
"""
import math
from fastapi import APIRouter, HTTPException, Query
from typing import Optional, List
from datetime import date, datetime, timedelta

from models.schemas import (
    GameDate, Game, GameDetail, GamePlayerStats, TeamGameStats, PlayerGameStats,
    GameShots, ShotAttempt, XGWormPoint, GoalDetail, PressurePoint, TeamComparisonStats, GoaltenderStat,
    SpecialTeamsStat, GoalieDangerStat, ShotQualityRow, SkaterImpact, GameContext,
    WinProbSeries, WinProbPoint, WinProbGoalSwing
)
from services.bigquery import bq_service
from services.cache import cache

router = APIRouter()


@router.get("/dates", response_model=List[GameDate])
@cache(ttl=3600)  # 1 hour cache
async def get_game_dates(
    from_date: Optional[date] = Query(None, description="Start date for game date range"),
    to_date: Optional[date] = Query(None, description="End date for game date range"),
) -> List[GameDate]:
    """Get list of dates on which games occurred or are scheduled.

    Returns distinct game dates with game counts for date navigation.
    Default range: 30 days before today through 14 days after today.

    Args:
        from_date: Optional start date. Defaults to 30 days before today.
        to_date: Optional end date. Defaults to 14 days after today.

    Returns:
        List of dates with game counts, sorted in descending order.
    """
    # Set default date range if not provided
    today = datetime.now().date()
    used_default_range = from_date is None and to_date is None
    if from_date is None:
        from_date = today - timedelta(days=30)
    if to_date is None:
        to_date = today + timedelta(days=14)

    games_table = bq_service.get_full_table_id('stg_games')

    # Query for distinct game dates with counts
    sql = f"""
    SELECT
        game_date,
        COUNT(DISTINCT game_id) as game_count
    FROM {games_table}
    WHERE game_date BETWEEN '{from_date}' AND '{to_date}'
    GROUP BY game_date
    ORDER BY game_date ASC
    """

    results = bq_service.query(sql)

    # Fall back to the most recent slate of games when the default window is empty
    # (e.g. during the offseason, or before the current season has been ingested).
    # This keeps the explorer populated instead of showing "no games" near today.
    if not results and used_default_range:
        fallback_sql = f"""
        SELECT
            game_date,
            COUNT(DISTINCT game_id) as game_count
        FROM {games_table}
        WHERE game_date >= (
            SELECT DATE_SUB(MAX(game_date), INTERVAL 45 DAY) FROM {games_table}
        )
        GROUP BY game_date
        ORDER BY game_date ASC
        """
        results = bq_service.query(fallback_sql)

    game_dates = []
    for row in results:
        game_date = GameDate(
            game_date=row['game_date'],
            game_count=row['game_count']
        )
        game_dates.append(game_date)

    return game_dates


@router.get("/", response_model=List[Game])
@cache(ttl=300)
async def get_games(
    date: Optional[date] = Query(None, description="Filter games for specific date"),
    start_date: Optional[date] = Query(None, description="Filter games from this date"),
    end_date: Optional[date] = Query(None, description="Filter games until this date"),
    team_id: Optional[int] = Query(None, description="Filter games for specific team"),
    season: Optional[str] = Query(None, description="Filter by season (e.g., 2023-24)"),
) -> List[Game]:
    """Get list of games with optional filters.

    Args:
        date: Optional specific date filter.
        start_date: Optional start date filter.
        end_date: Optional end date filter.
        team_id: Optional team ID filter.
        season: Optional season filter.

    Returns:
        List of games matching the filters.
    """
    # Build query with optional filters
    filters = []

    if date:
        filters.append(f"g.game_date = '{date}'")
    elif start_date and end_date:
        filters.append(f"g.game_date BETWEEN '{start_date}' AND '{end_date}'")
    elif start_date:
        filters.append(f"g.game_date >= '{start_date}'")
    elif end_date:
        filters.append(f"g.game_date <= '{end_date}'")

    if team_id:
        filters.append(f"(g.home_team_id = {team_id} OR g.away_team_id = {team_id})")

    if season:
        filters.append(f"g.season = '{season}'")

    where_clause = f"WHERE {' AND '.join(filters)}" if filters else ""

    # Query
    sql = f"""
    SELECT DISTINCT
        g.game_id,
        g.game_date,
        g.season,
        g.home_team_id,
        g.home_team_abbrev,
        g.away_team_id,
        g.away_team_abbrev,
        b.home_team_score,
        b.away_team_score,
        b.game_state,
        CASE
            WHEN b.game_state NOT IN ('OFF', 'FINAL') THEN TRUE
            ELSE FALSE
        END as is_preview
    FROM {bq_service.get_full_table_id('stg_games')} g
    LEFT JOIN {bq_service.get_full_table_id('stg_boxscores')} b
        ON g.game_id = b.game_id
    {where_clause}
    ORDER BY g.game_date DESC, g.game_id DESC
    """

    results = bq_service.query(sql)

    games = []
    for row in results:
        game = Game(
            game_id=row['game_id'],
            game_date=row['game_date'],
            season=row['season'],
            home_team_id=row['home_team_id'],
            home_team_abbrev=row['home_team_abbrev'],
            away_team_id=row['away_team_id'],
            away_team_abbrev=row['away_team_abbrev'],
            home_score=row.get('home_team_score'),
            away_score=row.get('away_team_score'),
            is_preview=row.get('is_preview', True)
        )
        games.append(game)

    return games


@router.get("/{game_id}", response_model=GameDetail)
@cache(ttl=300)
async def get_game_detail(game_id: int) -> GameDetail:
    """Get detailed information for a specific game.

    Args:
        game_id: NHL game ID.

    Returns:
        Game detail including team statistics.

    Raises:
        HTTPException: If game not found.
    """
    # Check if game exists
    game_sql = f"""
    SELECT
        game_id,
        game_date,
        season,
        home_team_id,
        home_team_abbrev,
        away_team_id,
        away_team_abbrev,
        home_team_score,
        away_team_score,
        home_team_sog,
        away_team_sog,
        game_state,
        venue_name
    FROM {bq_service.get_full_table_id('stg_boxscores')}
    WHERE game_id = {game_id}
    """

    game_results = bq_service.query(game_sql)
    if not game_results:
        raise HTTPException(status_code=404, detail="Game not found")

    game_row = game_results[0]
    is_preview = game_row['game_state'] not in ['OFF', 'FINAL']

    # If not preview, get team stats from mart
    if not is_preview:
        stats_sql = f"""
        SELECT
            team_id,
            team_abbrev,
            home_away,
            goals_for,
            cf_pct,
            xgf_pct,
            hdcf_per60,
            hdca_per60,
            xgf,
            xga,
            zone_entry_proxy_success_rate,
            shot_attempts_for,
            cf_p1,
            cf_p2,
            cf_p3,
            ca_p1,
            ca_p2,
            ca_p3,
            cf_pct_p1,
            cf_pct_p2,
            cf_pct_p3,
            xgf_p1,
            xgf_p2,
            xgf_p3,
            xga_p1,
            xga_p2,
            xga_p3,
            gf_p1,
            gf_p2,
            gf_p3,
            ga_p1,
            ga_p2,
            ga_p3,
            rebound_share_for,
            rush_share_for,
            forecheck_share_for,
            cycle_share_for,
            point_shot_share_for,
            other_share_for,
            cross_ice_share_for,
            rebound_share_against,
            rush_share_against,
            forecheck_share_against,
            cycle_share_against,
            point_shot_share_against,
            other_share_against,
            cross_ice_share_against,
            hits,
            giveaways,
            takeaways,
            hits_adj,
            giveaways_adj,
            takeaways_adj,
            cf_pct_score_adj,
            xgf_pct_score_adj,
            cf_pct_opp_adj,
            xgf_pct_opp_adj
        FROM {bq_service.get_full_table_id('mart_team_game_stats')}
        WHERE game_id = {game_id}
        """

        stats_results = bq_service.query(stats_sql)

        # Organize by home/away
        home_stats = None
        away_stats = None
        for row in stats_results:
            team_stats = TeamGameStats(
                team_id=row['team_id'],
                team_abbrev=row['team_abbrev'],
                score=row['goals_for'],
                cf_pct=row['cf_pct'],
                hdcf_per60=row['hdcf_per60'],
                hdca_per60=row['hdca_per60'],
                xgf=row.get('xgf'),
                xga=row.get('xga'),
                zone_entry_proxy_success_rate=row.get('zone_entry_proxy_success_rate'),
                shot_attempts=row.get('shot_attempts_for'),
                shots_on_goal=game_row['home_team_sog'] if row['home_away'] == 'home' else game_row['away_team_sog'],
                cf_p1=row.get('cf_p1'),
                cf_p2=row.get('cf_p2'),
                cf_p3=row.get('cf_p3'),
                ca_p1=row.get('ca_p1'),
                ca_p2=row.get('ca_p2'),
                ca_p3=row.get('ca_p3'),
                cf_pct_p1=row.get('cf_pct_p1'),
                cf_pct_p2=row.get('cf_pct_p2'),
                cf_pct_p3=row.get('cf_pct_p3'),
                xgf_p1=row.get('xgf_p1'),
                xgf_p2=row.get('xgf_p2'),
                xgf_p3=row.get('xgf_p3'),
                xga_p1=row.get('xga_p1'),
                xga_p2=row.get('xga_p2'),
                xga_p3=row.get('xga_p3'),
                gf_p1=row.get('gf_p1'),
                gf_p2=row.get('gf_p2'),
                gf_p3=row.get('gf_p3'),
                ga_p1=row.get('ga_p1'),
                ga_p2=row.get('ga_p2'),
                ga_p3=row.get('ga_p3'),
                rebound_share_for=row.get('rebound_share_for'),
                rush_share_for=row.get('rush_share_for'),
                forecheck_share_for=row.get('forecheck_share_for'),
                cycle_share_for=row.get('cycle_share_for'),
                point_shot_share_for=row.get('point_shot_share_for'),
                other_share_for=row.get('other_share_for'),
                cross_ice_share_for=row.get('cross_ice_share_for'),
                rebound_share_against=row.get('rebound_share_against'),
                rush_share_against=row.get('rush_share_against'),
                forecheck_share_against=row.get('forecheck_share_against'),
                cycle_share_against=row.get('cycle_share_against'),
                point_shot_share_against=row.get('point_shot_share_against'),
                other_share_against=row.get('other_share_against'),
                cross_ice_share_against=row.get('cross_ice_share_against'),
                hits=row.get('hits'),
                giveaways=row.get('giveaways'),
                takeaways=row.get('takeaways'),
                hits_adj=row.get('hits_adj'),
                giveaways_adj=row.get('giveaways_adj'),
                takeaways_adj=row.get('takeaways_adj'),
                cf_pct_score_adj=row.get('cf_pct_score_adj'),
                xgf_pct_score_adj=row.get('xgf_pct_score_adj'),
                cf_pct_opp_adj=row.get('cf_pct_opp_adj'),
                xgf_pct_opp_adj=row.get('xgf_pct_opp_adj')
            )
            if row['home_away'] == 'home':
                home_stats = team_stats
            else:
                away_stats = team_stats

        if not home_stats or not away_stats:
            # Fallback if mart data not available
            home_stats = TeamGameStats(
                team_id=game_row['home_team_id'],
                team_abbrev=game_row['home_team_abbrev'],
                score=game_row['home_team_score'],
                shots_on_goal=game_row.get('home_team_sog')
            )
            away_stats = TeamGameStats(
                team_id=game_row['away_team_id'],
                team_abbrev=game_row['away_team_abbrev'],
                score=game_row['away_team_score'],
                shots_on_goal=game_row.get('away_team_sog')
            )
    else:
        # Preview game - no stats
        home_stats = TeamGameStats(
            team_id=game_row['home_team_id'],
            team_abbrev=game_row['home_team_abbrev']
        )
        away_stats = TeamGameStats(
            team_id=game_row['away_team_id'],
            team_abbrev=game_row['away_team_abbrev']
        )

    return GameDetail(
        game_id=game_row['game_id'],
        game_date=game_row['game_date'],
        season=game_row['season'],
        home_team=home_stats,
        away_team=away_stats,
        is_preview=is_preview,
        venue_name=game_row.get('venue_name')
    )


@router.get("/{game_id}/players", response_model=GamePlayerStats)
@cache(ttl=300)
async def get_game_players(game_id: int) -> GamePlayerStats:
    """Get player statistics for a specific game.

    Args:
        game_id: NHL game ID.

    Returns:
        Player statistics for both teams in the game.

    Raises:
        HTTPException: If game not found.
    """
    # Check if game exists and is not preview
    game_sql = f"""
    SELECT game_id, game_state, home_team_id, away_team_id
    FROM {bq_service.get_full_table_id('stg_boxscores')}
    WHERE game_id = {game_id}
    """

    game_results = bq_service.query(game_sql)
    if not game_results:
        raise HTTPException(status_code=404, detail="Game not found")

    game_row = game_results[0]
    is_preview = game_row['game_state'] not in ['OFF', 'FINAL']

    if is_preview:
        # Return empty player lists for preview games
        return GamePlayerStats(
            game_id=game_id,
            home_players=[],
            away_players=[]
        )

    # Get player stats from mart
    player_sql = f"""
    SELECT
        p.player_id,
        CONCAT(p.first_name, ' ', p.last_name) as player_name,
        p.position_code as position,
        p.team_id,
        p.toi_5v5 as toi,
        p.individual_goals as goals,
        (p.first_assists + p.second_assists) as assists,
        (p.individual_goals + p.first_assists + p.second_assists) as points,
        p.individual_shot_attempts as shots,
        p.individual_shot_attempts as cf,
        p.ihdcf as hdcf,
        p.ixg,
        p.ixg_per60,
        p.hot_cold_flag,
        p.first_assists,
        p.second_assists,
        p.ihdcf,
        p.pim,
        p.rush_attempts,
        p.seq_rebound_attempts,
        p.seq_rush_attempts,
        p.seq_forecheck_attempts,
        p.seq_cycle_attempts,
        p.seq_point_shot_attempts,
        p.seq_other_attempts,
        p.seq_cross_ice_attempts,
        p.hits,
        p.giveaways,
        p.takeaways,
        p.hits_adj,
        p.giveaways_adj,
        p.takeaways_adj
    FROM {bq_service.get_full_table_id('mart_player_game_stats')} p
    WHERE p.game_id = {game_id}
    ORDER BY (p.individual_goals + p.first_assists + p.second_assists) DESC, p.ixg_per60 DESC
    """

    player_results = bq_service.query(player_sql)

    home_players = []
    away_players = []

    for row in player_results:
        player_stat = PlayerGameStats(
            player_id=row['player_id'],
            player_name=row['player_name'],
            position=row['position'],
            team_id=row['team_id'],
            toi=row.get('toi'),
            goals=row.get('goals'),
            assists=row.get('assists'),
            points=row.get('points'),
            shots=row.get('shots'),
            cf=row.get('cf'),
            hdcf=row.get('hdcf'),
            ixg=row.get('ixg'),
            ixg_per60=row.get('ixg_per60'),
            hot_cold_flag=row.get('hot_cold_flag'),
            first_assists=row.get('first_assists'),
            second_assists=row.get('second_assists'),
            ihdcf=row.get('ihdcf'),
            pim=row.get('pim'),
            rush_attempts=row.get('rush_attempts'),
            seq_rebound_attempts=row.get('seq_rebound_attempts'),
            seq_rush_attempts=row.get('seq_rush_attempts'),
            seq_forecheck_attempts=row.get('seq_forecheck_attempts'),
            seq_cycle_attempts=row.get('seq_cycle_attempts'),
            seq_point_shot_attempts=row.get('seq_point_shot_attempts'),
            seq_other_attempts=row.get('seq_other_attempts'),
            seq_cross_ice_attempts=row.get('seq_cross_ice_attempts'),
            hits=row.get('hits'),
            giveaways=row.get('giveaways'),
            takeaways=row.get('takeaways'),
            hits_adj=row.get('hits_adj'),
            giveaways_adj=row.get('giveaways_adj'),
            takeaways_adj=row.get('takeaways_adj')
        )

        if row['team_id'] == game_row['home_team_id']:
            home_players.append(player_stat)
        else:
            away_players.append(player_stat)

    return GamePlayerStats(
        game_id=game_id,
        home_players=home_players,
        away_players=away_players
    )


@router.get("/{game_id}/shots", response_model=GameShots)
@cache(ttl=86400)  # 24 hours
async def get_game_shots_endpoint(
    game_id: int,
    situation: str = Query("all", description="Filter by situation: all, 5v5, pp, pk")
) -> GameShots:
    """Get shot attempt coordinates for a specific game from int_shot_types.

    Args:
        game_id: NHL game ID.
        situation: Filter by situation (all, 5v5, pp, pk).

    Returns:
        Shot attempts for both teams with coordinates, outcomes, and shot types.

    Raises:
        HTTPException: If game not found.
    """
    # Check if game exists
    game_sql = f"""
    SELECT game_id, game_state, home_team_id, away_team_id
    FROM {bq_service.get_full_table_id('stg_boxscores')}
    WHERE game_id = {game_id}
    """

    game_results = bq_service.query(game_sql)
    if not game_results:
        raise HTTPException(status_code=404, detail="Game not found")

    game_row = game_results[0]
    is_preview = game_row['game_state'] not in ['OFF', 'FINAL']

    if is_preview:
        # Return empty shot lists for preview games
        return GameShots(
            game_id=game_id,
            home_shots=[],
            away_shots=[]
        )

    # Get shot data using the service layer
    shot_results = bq_service.get_game_shots(game_id, situation)

    # Get player names for this game
    players_sql = f"""
    SELECT DISTINCT
        player_id,
        first_name || ' ' || last_name as player_name
    FROM {bq_service.get_full_table_id('stg_rosters')}
    WHERE game_id = {game_id}
    """
    player_results = bq_service.query(players_sql)
    player_names = {row['player_id']: row['player_name'] for row in player_results}

    home_shots = []
    away_shots = []

    for row in shot_results:
        # Map event_type to outcome format
        outcome_map = {
            'GOAL': 'goal',
            'SHOT': 'shot_on_goal',
            'MISS': 'missed_shot',
            'BLOCK': 'blocked_shot'
        }
        outcome = outcome_map.get(row['event_type'], 'shot_on_goal')

        # Base shot data - shot_type is now always present from int_shot_types
        shot_data = {
            'x': float(row['x_coord']),
            'y': float(row['y_coord']),
            'outcome': outcome,
            'situation': row['situation_code'] or '1551',
            'team_id': row['team_id'],
            'shot_type': row.get('shot_type'),  # Always present from int_shot_types
            # In-house xG + decomposition (Phase 2.2); null for blocked/empty-net shots
            'xg': row.get('xg'),
            'base_rate': row.get('base_rate'),
            'xg_contrib_location': row.get('xg_contrib_location'),
            'xg_contrib_shot_type': row.get('xg_contrib_shot_type'),
            'xg_contrib_strength': row.get('xg_contrib_strength'),
            'xg_contrib_sequence': row.get('xg_contrib_sequence'),
            'xg_contrib_game_state': row.get('xg_contrib_game_state'),
        }

        # Add goal-specific details if this is a goal
        if row.get('is_goal'):
            scorer_id = row.get('scoring_player_id') or row.get('shooter_id')
            goalie_id = row.get('goalie_id')

            shot_data.update({
                'scorer_id': scorer_id,
                'scorer_name': player_names.get(scorer_id) if scorer_id else None,
                'period': row.get('period'),
                'time_in_period': row.get('time_in_period'),
                'goalie_id': goalie_id,
                'goalie_name': player_names.get(goalie_id) if goalie_id else None
            })

        shot = ShotAttempt(**shot_data)

        if row['team_id'] == game_row['home_team_id']:
            home_shots.append(shot)
        else:
            away_shots.append(shot)

    return GameShots(
        game_id=game_id,
        home_shots=home_shots,
        away_shots=away_shots
    )


@router.get("/{game_id}/winprob", response_model=WinProbSeries)
@cache(ttl=86400)
async def get_win_probability(game_id: int) -> WinProbSeries:
    """Server-side win-probability + leverage series for a game, plus per-goal WP swings."""
    series_rows = bq_service.get_winprob(game_id)
    if not series_rows:
        # No stored series (preview game or not yet scored)
        return WinProbSeries(game_id=game_id, series=[], goal_swings=[])

    # Player names for goal-swing labels
    names_rows = bq_service.query(f"""
        SELECT DISTINCT player_id, first_name || ' ' || last_name AS name
        FROM {bq_service.get_full_table_id('stg_rosters')}
        WHERE game_id = {game_id}
    """)
    names = {r['player_id']: r['name'] for r in names_rows}

    series = [
        WinProbPoint(
            elapsed_seconds=r['elapsed_seconds'],
            home_wp=r['home_wp'],
            leverage=r['leverage'],
        )
        for r in series_rows
    ]

    goal_swings = []
    for r in bq_service.get_winprob_goal_swings(game_id):
        before = r.get('wp_before')
        after = r.get('wp_after')
        if before is None or after is None:
            continue
        goal_swings.append(WinProbGoalSwing(
            elapsed_seconds=r['elapsed_seconds'],
            team_id=r.get('team_id'),
            scorer_name=names.get(r.get('scoring_player_id')),
            wp_before=before,
            wp_after=after,
            swing=after - before,
        ))

    return WinProbSeries(
        game_id=game_id,
        model_version=series_rows[0].get('model_version'),
        series=series,
        goal_swings=goal_swings,
    )


@router.get("/{game_id}/xgworm", response_model=List[XGWormPoint])
@cache(ttl=86400)  # 24 hours
async def get_xg_worm(
    game_id: int,
    situation: str = Query("all", description="Filter by situation: all, 5v5, pp, pk")
) -> List[XGWormPoint]:
    """Get cumulative xG differential data for xG Worm chart.

    Args:
        game_id: NHL game ID.
        situation: Filter by situation (all, 5v5, pp, pk).

    Returns:
        Time-series data points with cumulative xG differential and goal markers.

    Raises:
        HTTPException: If game not found.
    """
    # Check if game exists
    game_sql = f"""
    SELECT game_id, game_state
    FROM {bq_service.get_full_table_id('stg_boxscores')}
    WHERE game_id = {game_id}
    """

    game_results = bq_service.query(game_sql)
    if not game_results:
        raise HTTPException(status_code=404, detail="Game not found")

    game_row = game_results[0]
    is_preview = game_row['game_state'] not in ['OFF', 'FINAL']

    if is_preview:
        # Return empty list for preview games
        return []

    # Get xG worm data using the service layer
    worm_data = bq_service.get_xg_worm(game_id, situation)

    worm_points = []
    for row in worm_data:
        point = XGWormPoint(
            game_time_seconds=row['game_time_seconds'],
            cumulative_xg_diff=row['cumulative_xg_diff'],
            home_xg=row['home_xg'],
            away_xg=row['away_xg'],
            event_type=row.get('event_type'),
            team_id=row.get('team_id'),
            label=row.get('label')
        )
        worm_points.append(point)

    return worm_points


def _goal_strength(situation_code: Optional[str], scoring_is_home: bool) -> str:
    """Derive a goal's strength (EV/PP/SH/EN) from the situation code.

    situationCode digits are [away_goalie_in, away_skaters, home_skaters, home_goalie_in].
    """
    sc = situation_code or ""
    if len(sc) != 4 or not sc.isdigit():
        return "EV"
    away_g, away_sk, home_sk, home_g = (int(sc[0]), int(sc[1]), int(sc[2]), int(sc[3]))
    if scoring_is_home:
        scoring_sk, opp_sk, opp_goalie_in = home_sk, away_sk, away_g
    else:
        scoring_sk, opp_sk, opp_goalie_in = away_sk, home_sk, home_g

    if opp_goalie_in == 0:
        return "EN"
    if scoring_sk > opp_sk:
        return "PP"
    if scoring_sk < opp_sk:
        return "SH"
    return "EV"


@router.get("/{game_id}/goals", response_model=List[GoalDetail])
@cache(ttl=86400)
async def get_game_goals(game_id: int) -> List[GoalDetail]:
    """Get detailed goal info (scorer, assists, strength) for the xG worm tooltip."""
    rows = bq_service.get_game_goals(game_id)

    goals: List[GoalDetail] = []
    for row in rows:
        scoring_is_home = row['event_owner_team_id'] == row['home_team_id']
        team_abbrev = row['home_team_abbrev'] if scoring_is_home else row['away_team_abbrev']

        assists: List[str] = []
        if row.get('assist1_player_id') and (row.get('assist1_name') or '').strip():
            assists.append(row['assist1_name'].strip())
        if row.get('assist2_player_id') and (row.get('assist2_name') or '').strip():
            assists.append(row['assist2_name'].strip())

        scorer_name = (row.get('scorer_name') or '').strip() or None

        goals.append(GoalDetail(
            game_time_seconds=row['game_seconds'],
            period=row['period_number'],
            time_in_period=row['time_in_period'],
            team_id=row['event_owner_team_id'],
            team_abbrev=team_abbrev,
            strength=_goal_strength(row.get('situation_code'), scoring_is_home),
            scorer_id=row.get('scoring_player_id'),
            scorer_name=scorer_name,
            scorer_headshot=row.get('scorer_headshot'),
            assists=assists
        ))

    return goals


# Gaussian smoothing bandwidth (seconds) and sample step for the shot-pressure curve.
_PRESSURE_BANDWIDTH = 120.0
_PRESSURE_STEP = 30
_SQRT_2PI = math.sqrt(2 * math.pi)


def _smoothed_rate(shot_times: List[int], t: int) -> float:
    """Gaussian kernel density of shot timestamps at time t, expressed as shots per 60 min."""
    if not shot_times:
        return 0.0
    density = 0.0
    for ts in shot_times:
        z = (t - ts) / _PRESSURE_BANDWIDTH
        density += math.exp(-0.5 * z * z)
    density /= (_PRESSURE_BANDWIDTH * _SQRT_2PI)  # shots per second
    return density * 3600.0  # shots per 60 minutes


@router.get("/{game_id}/goaltending", response_model=List[GoaltenderStat])
@cache(ttl=86400)
async def get_goaltending(game_id: int) -> List[GoaltenderStat]:
    """Per-goalie line (shots/goals against) from the goalie in net for each shot."""
    rows = bq_service.get_goaltending(game_id)
    out: List[GoaltenderStat] = []
    for r in rows:
        out.append(GoaltenderStat(
            player_id=r['player_id'],
            goalie_name=(r.get('goalie_name') or '').strip() or 'Goalie',
            team_abbrev=r.get('team_abbrev') or '',
            shots_against=int(r.get('shots_against') or 0),
            goals_against=int(r.get('goals_against') or 0),
            gsax=round(float(r.get('gsax') or 0.0), 2),
            headshot=r.get('headshot')
        ))
    return out


@router.get("/{game_id}/teamstats", response_model=TeamComparisonStats)
@cache(ttl=86400)
async def get_team_stats(game_id: int) -> TeamComparisonStats:
    """Box-score team comparison (goals, shots, PP, hits, faceoffs, etc.) from play-by-play."""
    row = bq_service.get_team_comparison(game_id)
    if not row:
        raise HTTPException(status_code=404, detail="Game not found")
    return TeamComparisonStats(**{k: int(v or 0) for k, v in row.items()})


@router.get("/{game_id}/context", response_model=GameContext)
@cache(ttl=86400)
async def get_game_context(game_id: int) -> GameContext:
    """Game context: scratches, season series, team-stat comparisons, last-10 records,
    and per-goal highlight video URLs keyed by event id (landing + right-rail)."""
    row = bq_service.get_game_context(game_id)
    if not row:
        raise HTTPException(status_code=404, detail="Game context not available")
    return GameContext(**row)


@router.get("/{game_id}/pressure", response_model=List[PressurePoint])
@cache(ttl=86400)
async def get_shot_pressure(game_id: int) -> List[PressurePoint]:
    """Smoothed unblocked shots/60 per team over game time (shot pressure chart)."""
    rows = bq_service.get_pressure_shots(game_id)
    if not rows:
        return []

    home_times = [r['game_seconds'] for r in rows if r['is_home']]
    away_times = [r['game_seconds'] for r in rows if not r['is_home']]

    last_shot = max(r['game_seconds'] for r in rows)
    # Round the timeline up to the end of the period in progress (min one full game).
    end = max(3600, math.ceil(last_shot / 1200) * 1200)

    points: List[PressurePoint] = []
    for t in range(0, end + 1, _PRESSURE_STEP):
        points.append(PressurePoint(
            game_time_seconds=t,
            home_rate=round(_smoothed_rate(home_times, t), 2),
            away_rate=round(_smoothed_rate(away_times, t), 2)
        ))

    return points


@router.get("/{game_id}/specialteams", response_model=List[SpecialTeamsStat])
@cache(ttl=86400)
async def get_special_teams(game_id: int) -> List[SpecialTeamsStat]:
    """Per-team power-play and penalty-kill detail (PP goals/opp/xG/shots, PK saves)."""
    rows = bq_service.get_special_teams(game_id)
    out: List[SpecialTeamsStat] = []
    for r in rows:
        out.append(SpecialTeamsStat(
            team_abbrev=r.get('team_abbrev') or '',
            is_home=bool(r.get('is_home')),
            pp_goals=int(r.get('pp_goals') or 0),
            pp_opp=int(r.get('pp_opp') or 0),
            pp_xg=round(float(r.get('pp_xg') or 0.0), 2),
            pp_shots=int(r.get('pp_shots') or 0),
            pk_saves=int(r.get('pk_saves') or 0),
            pk_shots=int(r.get('pk_shots') or 0),
        ))
    return out


@router.get("/{game_id}/goalie-danger", response_model=List[GoalieDangerStat])
@cache(ttl=86400)
async def get_goalie_danger(game_id: int) -> List[GoalieDangerStat]:
    """Per-goalie save record split by shot-danger band, plus total GSAx."""
    rows = bq_service.get_goalie_danger(game_id)
    out: List[GoalieDangerStat] = []
    for r in rows:
        out.append(GoalieDangerStat(
            player_id=int(r['player_id']),
            goalie_name=(r.get('goalie_name') or '').strip() or 'Goalie',
            team_abbrev=r.get('team_abbrev') or '',
            high_saves=int(r.get('high_saves') or 0),
            high_shots=int(r.get('high_shots') or 0),
            med_saves=int(r.get('med_saves') or 0),
            med_shots=int(r.get('med_shots') or 0),
            low_saves=int(r.get('low_saves') or 0),
            low_shots=int(r.get('low_shots') or 0),
            gsax=round(float(r.get('gsax') or 0.0), 2),
        ))
    return out


@router.get("/{game_id}/shot-quality", response_model=List[ShotQualityRow])
@cache(ttl=86400)
async def get_shot_quality(game_id: int) -> List[ShotQualityRow]:
    """Per-team shot attempts and goals by danger band (shot-quality ladder)."""
    rows = bq_service.get_shot_quality(game_id)
    out: List[ShotQualityRow] = []
    for r in rows:
        out.append(ShotQualityRow(
            band=r.get('band') or '',
            home_abbrev=r.get('home_abbrev') or '',
            away_abbrev=r.get('away_abbrev') or '',
            home_attempts=int(r.get('home_attempts') or 0),
            home_goals=int(r.get('home_goals') or 0),
            away_attempts=int(r.get('away_attempts') or 0),
            away_goals=int(r.get('away_goals') or 0),
        ))
    return out


def _toi_to_seconds(toi: str) -> int:
    """Convert a 'MM:SS' time-on-ice string to total seconds."""
    try:
        m, s = toi.split(':')
        return int(m) * 60 + int(s)
    except (ValueError, AttributeError):
        return 0


@router.get("/{game_id}/skater-impact", response_model=List[SkaterImpact])
@cache(ttl=86400)
async def get_skater_impact(game_id: int) -> List[SkaterImpact]:
    """Per-skater impact line: real TOI + box-score G/A/P joined to individual xG / HDC."""
    rows = bq_service.get_skater_impact(game_id)
    out: List[SkaterImpact] = []
    for r in rows:
        toi = r.get('toi') or '0:00'
        out.append(SkaterImpact(
            player_id=int(r['player_id']),
            player_name=r.get('player_name') or '',
            team_abbrev=r.get('team_abbrev') or '',
            position=r.get('position') or '',
            toi=toi,
            toi_seconds=_toi_to_seconds(toi),
            goals=int(r.get('goals') or 0),
            assists=int(r.get('assists') or 0),
            points=int(r.get('points') or 0),
            shots=int(r.get('shots') or 0),
            ixg=round(float(r.get('ixg') or 0.0), 2),
            ihdcf=int(r.get('ihdcf') or 0),
        ))
    return out
