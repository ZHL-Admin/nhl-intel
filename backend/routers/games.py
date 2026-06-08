"""Game-related API endpoints.

Provides endpoints for game lists, game details, and game player stats.
"""
from fastapi import APIRouter, HTTPException, Query
from typing import Optional, List
from datetime import date

from models.schemas import (
    Game, GameDetail, GamePlayerStats, TeamGameStats, PlayerGameStats,
    GameShots, ShotAttempt, XGWormPoint
)
from services.bigquery import bq_service
from services.cache import cache

router = APIRouter()


@router.get("/", response_model=List[Game])
@cache(ttl=300)
async def get_games(
    date: Optional[date] = Query(None, description="Filter games for specific date"),
    start_date: Optional[date] = Query(None, description="Filter games from this date"),
    end_date: Optional[date] = Query(None, description="Filter games until this date"),
    team_id: Optional[int] = Query(None, description="Filter games for specific team"),
    season: Optional[int] = Query(None, description="Filter by season (e.g., 20232024)"),
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
        filters.append(f"g.season = {season}")

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
            zone_entry_success_rate,
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
            ga_p3
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
                zone_entry_success_rate=row.get('zone_entry_success_rate'),
                shot_attempts=row.get('shot_attempts_for'),
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
                ga_p3=row.get('ga_p3')
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
                score=game_row['home_team_score']
            )
            away_stats = TeamGameStats(
                team_id=game_row['away_team_id'],
                team_abbrev=game_row['away_team_abbrev'],
                score=game_row['away_team_score']
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
        p.individual_high_danger_attempts as hdcf,
        p.ixg,
        p.ixg_per60,
        p.hot_cold_flag,
        p.first_assists,
        p.second_assists,
        p.ihdcf,
        p.pim,
        p.rush_attempts
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
            rush_attempts=row.get('rush_attempts')
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
            'team_id': row['event_team_id'],
            'shot_type': row.get('shot_type')  # Always present from int_shot_types
        }

        # Add goal-specific details if this is a goal
        if row.get('is_goal'):
            scorer_id = row.get('shooter_player_id')
            assist1_id = row.get('assist1_player_id')
            assist2_id = row.get('assist2_player_id')
            goalie_id = row.get('goalie_player_id')

            # Calculate period and time from game_seconds
            game_seconds = row.get('game_seconds', 0)
            period = row.get('period', (game_seconds // 1200) + 1)
            seconds_in_period = game_seconds % 1200
            minutes = seconds_in_period // 60
            seconds = seconds_in_period % 60
            time_in_period = f"{minutes:02d}:{seconds:02d}"

            shot_data.update({
                'scorer_id': scorer_id,
                'scorer_name': player_names.get(scorer_id) if scorer_id else None,
                'period': period,
                'time_in_period': time_in_period,
                'assist1_id': assist1_id,
                'assist1_name': player_names.get(assist1_id) if assist1_id else None,
                'assist2_id': assist2_id,
                'assist2_name': player_names.get(assist2_id) if assist2_id else None,
                'goalie_id': goalie_id,
                'goalie_name': player_names.get(goalie_id) if goalie_id else None
            })

        shot = ShotAttempt(**shot_data)

        if row['event_team_id'] == game_row['home_team_id']:
            home_shots.append(shot)
        else:
            away_shots.append(shot)

    return GameShots(
        game_id=game_id,
        home_shots=home_shots,
        away_shots=away_shots
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
