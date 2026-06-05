"""Player-related API endpoints.

Provides endpoints for player details, trends, gamelog, shots, and vs-opponent stats.
"""
from fastapi import APIRouter, HTTPException, Query
from typing import Optional, List

from models.schemas import (
    PlayerDetail, PlayerTrends, PlayerTrendPoint, PlayerGamelog, GamelogEntry,
    PlayerShots, ShotLocation, PlayerVsOpponent
)
from services.bigquery import bq_service
from services.cache import cache

router = APIRouter()


@router.get("/{player_id}", response_model=PlayerDetail)
@cache(ttl=600)
async def get_player_detail(
    player_id: int,
    season: Optional[int] = Query(None, description="Season (e.g., 20232024)"),
) -> PlayerDetail:
    """Get detailed information for a specific player.

    Args:
        player_id: NHL player ID.
        season: Optional season filter.

    Returns:
        Player details including current season stats.

    Raises:
        HTTPException: If player not found.
    """
    # Get current season if not provided
    if not season:
        season_sql = f"""
        SELECT MAX(season) as current_season
        FROM {bq_service.get_full_table_id('stg_boxscores')}
        """
        season_result = bq_service.query(season_sql)
        season = season_result[0]['current_season'] if season_result else 20232024

    # Get aggregated player stats
    sql = f"""
    SELECT
        player_id,
        CONCAT(first_name, ' ', last_name) as player_name,
        position_code as position,
        team_id,
        COUNT(DISTINCT game_id) as games_played,
        AVG(toi_5v5) as toi_per_gp,
        AVG(primary_points_per60) as points_per60,
        AVG((individual_goals / toi_5v5) * 60.0) as goals_per60,
        AVG((primary_assists / toi_5v5) * 60.0) as assists_per60,
        AVG(on_ice_xgf_pct) as cf_pct,
        AVG(ixg_per60) as hdcf_per60
    FROM {bq_service.get_full_table_id('mart_player_game_stats')}
    WHERE player_id = {player_id}
    GROUP BY player_id, first_name, last_name, position_code, team_id
    """

    results = bq_service.query(sql)
    if not results:
        raise HTTPException(status_code=404, detail="Player not found")

    row = results[0]

    # Get team abbrev
    team_sql = f"""
    SELECT DISTINCT team_abbrev
    FROM {bq_service.get_full_table_id('mart_team_game_stats')}
    WHERE team_id = {row['team_id']}
    LIMIT 1
    """
    team_result = bq_service.query(team_sql)
    team_abbrev = team_result[0]['team_abbrev'] if team_result else "UNK"

    return PlayerDetail(
        player_id=row['player_id'],
        player_name=row['player_name'],
        position=row['position'],
        team_id=row['team_id'],
        team_abbrev=team_abbrev,
        season=season,
        games_played=row['games_played'],
        toi_per_gp=row['toi_per_gp'],
        points_per60=row['points_per60'],
        goals_per60=row['goals_per60'],
        assists_per60=row['assists_per60'],
        cf_pct=row['cf_pct'],
        hdcf_per60=row['hdcf_per60']
    )


@router.get("/{player_id}/trends", response_model=PlayerTrends)
@cache(ttl=600)
async def get_player_trends(
    player_id: int,
    season: Optional[int] = Query(None, description="Season (e.g., 20232024)"),
) -> PlayerTrends:
    """Get rolling trends for a specific player.

    Args:
        player_id: NHL player ID.
        season: Optional season filter.

    Returns:
        Player trends including 5-game and 10-game rolling averages.

    Raises:
        HTTPException: If player not found.
    """
    # Get current season if not provided
    if not season:
        season_sql = f"""
        SELECT MAX(season) as current_season
        FROM {bq_service.get_full_table_id('stg_boxscores')}
        """
        season_result = bq_service.query(season_sql)
        season = season_result[0]['current_season'] if season_result else 20232024

    # Calculate rolling averages
    sql = f"""
    WITH ordered_games AS (
        SELECT
            game_date,
            primary_points_per60,
            on_ice_xgf_pct as cf_pct,
            ROW_NUMBER() OVER (ORDER BY game_date) as game_num
        FROM {bq_service.get_full_table_id('mart_player_game_stats')}
        WHERE player_id = {player_id}
    )
    SELECT
        game_date,
        AVG(primary_points_per60) OVER (
            ORDER BY game_date
            ROWS BETWEEN 4 PRECEDING AND CURRENT ROW
        ) as points_per60_5gp,
        AVG(cf_pct) OVER (
            ORDER BY game_date
            ROWS BETWEEN 4 PRECEDING AND CURRENT ROW
        ) as cf_pct_5gp,
        game_num
    FROM ordered_games
    WHERE game_num >= 5
    ORDER BY game_date
    LIMIT 50
    """

    results = bq_service.query(sql)
    if not results:
        raise HTTPException(status_code=404, detail="Player not found or insufficient data")

    points_per60_5gp = []
    points_per60_10gp = []  # TODO: Add 10-game rolling
    cf_pct_5gp = []
    cf_pct_10gp = []  # TODO: Add 10-game rolling

    for row in results:
        points_per60_5gp.append(PlayerTrendPoint(
            game_date=row['game_date'],
            value=row['points_per60_5gp']
        ))
        cf_pct_5gp.append(PlayerTrendPoint(
            game_date=row['game_date'],
            value=row['cf_pct_5gp']
        ))

    return PlayerTrends(
        player_id=player_id,
        season=season,
        points_per60_5gp=points_per60_5gp,
        points_per60_10gp=points_per60_10gp,
        cf_pct_5gp=cf_pct_5gp,
        cf_pct_10gp=cf_pct_10gp
    )


@router.get("/{player_id}/gamelog", response_model=PlayerGamelog)
@cache(ttl=600)
async def get_player_gamelog(
    player_id: int,
    season: Optional[int] = Query(None, description="Season (e.g., 20232024)"),
    limit: int = Query(20, description="Number of games to return", ge=1, le=100),
) -> PlayerGamelog:
    """Get game-by-game log for a specific player.

    Args:
        player_id: NHL player ID.
        season: Optional season filter.
        limit: Number of games to return (default 20, max 100).

    Returns:
        Player gamelog with per-game stats.

    Raises:
        HTTPException: If player not found.
    """
    # Get current season if not provided
    if not season:
        season_sql = f"""
        SELECT MAX(season) as current_season
        FROM {bq_service.get_full_table_id('stg_boxscores')}
        """
        season_result = bq_service.query(season_sql)
        season = season_result[0]['current_season'] if season_result else 20232024

    # Get game-by-game stats with opponent info
    sql = f"""
    WITH player_games AS (
        SELECT
            p.game_id,
            p.game_date,
            p.team_id,
            p.toi_5v5 as toi,
            CAST(p.primary_points_per60 * p.toi_5v5 / 60.0 AS INT64) as points,
            0 as goals,
            0 as assists,
            0 as shots,
            0 as cf,
            CAST(p.ixg_per60 * p.toi_5v5 / 60.0 AS INT64) as hdcf
        FROM {bq_service.get_full_table_id('mart_player_game_stats')} p
        WHERE p.player_id = {player_id}
    ),
    game_info AS (
        SELECT
            g.game_id,
            CASE
                WHEN g.home_team_id = pg.team_id THEN g.away_team_id
                ELSE g.home_team_id
            END as opponent_id,
            CASE
                WHEN g.home_team_id = pg.team_id THEN g.away_team_abbrev
                ELSE g.home_team_abbrev
            END as opponent_abbrev
        FROM {bq_service.get_full_table_id('stg_boxscores')} g
        INNER JOIN player_games pg ON g.game_id = pg.game_id
    )
    SELECT
        pg.*,
        gi.opponent_id,
        gi.opponent_abbrev
    FROM player_games pg
    LEFT JOIN game_info gi ON pg.game_id = gi.game_id
    ORDER BY pg.game_date DESC
    LIMIT {limit}
    """

    results = bq_service.query(sql)
    if not results:
        raise HTTPException(status_code=404, detail="Player not found")

    games: List[GamelogEntry] = []
    for row in results:
        games.append(GamelogEntry(
            game_id=row['game_id'],
            game_date=row['game_date'],
            opponent_id=row['opponent_id'],
            opponent_abbrev=row['opponent_abbrev'],
            toi=row['toi'],
            goals=row['goals'],
            assists=row['assists'],
            points=row['points'],
            shots=row['shots'],
            cf=row['cf'],
            hdcf=row['hdcf']
        ))

    return PlayerGamelog(
        player_id=player_id,
        season=season,
        games=games
    )


@router.get("/{player_id}/shots", response_model=PlayerShots)
@cache(ttl=600)
async def get_player_shots(
    player_id: int,
    season: Optional[int] = Query(None, description="Season (e.g., 20232024)"),
) -> PlayerShots:
    """Get shot data for a specific player.

    Args:
        player_id: NHL player ID.
        season: Optional season filter.

    Returns:
        Player shot data including location and danger level breakdowns.

    Raises:
        HTTPException: If player not found.
    """
    # Get current season if not provided
    if not season:
        season_sql = f"""
        SELECT MAX(season) as current_season
        FROM {bq_service.get_full_table_id('stg_boxscores')}
        """
        season_result = bq_service.query(season_sql)
        season = season_result[0]['current_season'] if season_result else 20232024

    # Get shot location data from int_shot_attempts
    sql = f"""
    SELECT
        x_coord,
        y_coord,
        is_goal,
        CASE
            WHEN is_high_danger THEN 'high'
            ELSE 'medium'  -- TODO: Distinguish between low and medium danger
        END as danger_level
    FROM {bq_service.get_full_table_id('int_shot_attempts')}
    WHERE shooting_player_id = {player_id}
    LIMIT 500
    """

    results = bq_service.query(sql)

    # Calculate summary stats
    total_shots = len(results)
    low_danger = 0
    medium_danger = 0
    high_danger = 0

    shot_locations: List[ShotLocation] = []
    for row in results:
        danger = row['danger_level']
        if danger == 'high':
            high_danger += 1
        elif danger == 'medium':
            medium_danger += 1
        else:
            low_danger += 1

        shot_locations.append(ShotLocation(
            x=row['x_coord'] or 0.0,
            y=row['y_coord'] or 0.0,
            is_goal=row['is_goal'],
            danger_level=danger
        ))

    return PlayerShots(
        player_id=player_id,
        season=season,
        total_shots=total_shots,
        low_danger=low_danger,
        medium_danger=medium_danger,
        high_danger=high_danger,
        shot_locations=shot_locations
    )


@router.get("/{player_id}/vs/{opponent_id}", response_model=PlayerVsOpponent)
@cache(ttl=600)
async def get_player_vs_opponent(
    player_id: int,
    opponent_id: int,
    season: Optional[int] = Query(None, description="Season (e.g., 20232024)"),
) -> PlayerVsOpponent:
    """Get player stats vs specific opponent.

    Args:
        player_id: NHL player ID.
        opponent_id: Opponent team ID.
        season: Optional season filter.

    Returns:
        Player stats vs opponent with small_sample flag if < 3 games.

    Raises:
        HTTPException: If player or opponent not found.
    """
    # Get current season if not provided
    if not season:
        season_sql = f"""
        SELECT MAX(season) as current_season
        FROM {bq_service.get_full_table_id('stg_boxscores')}
        """
        season_result = bq_service.query(season_sql)
        season = season_result[0]['current_season'] if season_result else 20232024

    # Find games where player faced this opponent
    sql = f"""
    WITH player_games AS (
        SELECT
            p.game_id,
            p.team_id,
            p.toi_5v5,
            p.primary_points_per60,
            0.5 as cf_pct  -- TODO: Calculate from on-ice data
        FROM {bq_service.get_full_table_id('mart_player_game_stats')} p
        WHERE p.player_id = {player_id}
    ),
    opponent_games AS (
        SELECT DISTINCT g.game_id
        FROM {bq_service.get_full_table_id('stg_boxscores')} g
        WHERE (g.home_team_id = {opponent_id} OR g.away_team_id = {opponent_id})
          AND g.season = {season}
    )
    SELECT
        COUNT(*) as games_played,
        AVG(pg.toi_5v5) as toi_per_gp,
        AVG(pg.primary_points_per60) as points_per60,
        AVG(pg.cf_pct) as cf_pct
    FROM player_games pg
    INNER JOIN opponent_games og ON pg.game_id = og.game_id
    """

    results = bq_service.query(sql)
    if not results or results[0]['games_played'] == 0:
        raise HTTPException(status_code=404, detail="No games found against this opponent")

    row = results[0]
    small_sample = row['games_played'] < 3

    return PlayerVsOpponent(
        player_id=player_id,
        opponent_id=opponent_id,
        season=season,
        games_played=row['games_played'],
        small_sample=small_sample,
        toi_per_gp=row['toi_per_gp'] if not small_sample else None,
        points_per60=row['points_per60'] if not small_sample else None,
        cf_pct=row['cf_pct'] if not small_sample else None
    )
