"""Team-related API endpoints.

Provides endpoints for team details, trends, roster, and vs-opponent stats.
"""
from fastapi import APIRouter, HTTPException, Query
from typing import Optional

from models.schemas import TeamDetail, TeamTrends, TeamTrendPoint, TeamRoster, RosterPlayer, TeamVsOpponent
from services.bigquery import bq_service
from services.cache import cache

router = APIRouter()


@router.get("/{team_id}", response_model=TeamDetail)
@cache(ttl=600)
async def get_team_detail(
    team_id: int,
    season: Optional[int] = Query(None, description="Season (e.g., 20232024)"),
) -> TeamDetail:
    """Get detailed information for a specific team.

    Args:
        team_id: NHL team ID.
        season: Optional season filter.

    Returns:
        Team details including current season stats.

    Raises:
        HTTPException: If team not found.
    """
    # Get current season if not provided
    if not season:
        season_sql = f"""
        SELECT MAX(season) as current_season
        FROM {bq_service.get_full_table_id('mart_team_game_stats')}
        """
        season_result = bq_service.query(season_sql)
        season = season_result[0]['current_season'] if season_result else 20232024

    # Aggregate team stats for the season with rankings
    sql = f"""
    WITH team_stats AS (
        SELECT
            team_id,
            team_abbrev,
            COUNT(DISTINCT game_id) as games_played,
            SUM(CASE WHEN goals_for > goals_against THEN 1 ELSE 0 END) as wins,
            SUM(CASE WHEN goals_for < goals_against THEN 1 ELSE 0 END) as losses,
            0 as otl,
            SUM(CASE WHEN goals_for > goals_against THEN 2 ELSE 0 END) as points,
            AVG(cf_pct) as cf_pct,
            AVG(hdcf_per60) as hdcf_per60,
            AVG(hdca_per60) as hdca_per60,
            AVG(xgf / (toi_5v5_minutes / 60.0)) as xgf_per60,
            AVG(xga / (toi_5v5_minutes / 60.0)) as xga_per60,
            SUM(goals_for) as total_goals_for,
            SUM(goals_against) as total_goals_against,
            AVG(zone_entry_success_rate) as zone_entry_success_rate
        FROM {bq_service.get_full_table_id('mart_team_game_stats')}
        WHERE season = {season}
        GROUP BY team_id, team_abbrev
    ),
    team_ranks AS (
        SELECT
            *,
            RANK() OVER (ORDER BY cf_pct DESC) as cf_pct_rank,
            RANK() OVER (ORDER BY xgf_per60 / (xgf_per60 + xga_per60) DESC) as xgf_pct_rank,
            RANK() OVER (ORDER BY hdcf_per60 DESC) as hdcf_per60_rank,
            RANK() OVER (ORDER BY hdca_per60 ASC) as hdca_per60_rank,
            RANK() OVER (ORDER BY total_goals_for / NULLIF(games_played, 0) DESC) as gf_per_gp_rank,
            RANK() OVER (ORDER BY total_goals_against / NULLIF(games_played, 0) ASC) as ga_per_gp_rank,
            RANK() OVER (ORDER BY zone_entry_success_rate DESC NULLS LAST) as zone_entry_success_rate_rank
        FROM team_stats
    )
    SELECT * FROM team_ranks
    WHERE team_id = {team_id}
    """

    results = bq_service.query(sql)
    if not results:
        raise HTTPException(status_code=404, detail="Team not found")

    row = results[0]
    return TeamDetail(
        team_id=row['team_id'],
        team_name=row['team_abbrev'],  # TODO: Get full team name
        team_abbrev=row['team_abbrev'],
        season=season,
        games_played=row['games_played'],
        wins=row['wins'],
        losses=row['losses'],
        otl=row['otl'],
        points=row['points'],
        cf_pct=row['cf_pct'],
        hdcf_per60=row['hdcf_per60'],
        hdca_per60=row['hdca_per60'],
        xgf_per60=row['xgf_per60'],
        xga_per60=row['xga_per60'],
        total_goals_for=row['total_goals_for'],
        total_goals_against=row['total_goals_against'],
        zone_entry_success_rate=row.get('zone_entry_success_rate'),
        cf_pct_rank=row['cf_pct_rank'],
        xgf_pct_rank=row['xgf_pct_rank'],
        hdcf_per60_rank=row['hdcf_per60_rank'],
        hdca_per60_rank=row['hdca_per60_rank'],
        gf_per_gp_rank=row['gf_per_gp_rank'],
        ga_per_gp_rank=row['ga_per_gp_rank'],
        zone_entry_success_rate_rank=row.get('zone_entry_success_rate_rank')
    )


@router.get("/{team_id}/trends", response_model=TeamTrends)
@cache(ttl=600)
async def get_team_trends(
    team_id: int,
    season: Optional[int] = Query(None, description="Season (e.g., 20232024)"),
) -> TeamTrends:
    """Get rolling trends for a specific team.

    Args:
        team_id: NHL team ID.
        season: Optional season filter.

    Returns:
        Team trends including 5-game and 10-game rolling averages.

    Raises:
        HTTPException: If team not found.
    """
    # Get current season if not provided
    if not season:
        season_sql = f"""
        SELECT MAX(season) as current_season
        FROM {bq_service.get_full_table_id('mart_team_rolling')}
        """
        season_result = bq_service.query(season_sql)
        season = season_result[0]['current_season'] if season_result else 20232024

    # Get rolling trends
    sql = f"""
    SELECT
        game_date,
        rolling_cf_pct_5gp,
        rolling_xgf_pct_5gp,
        rolling_hdcf_per60_5gp
    FROM {bq_service.get_full_table_id('mart_team_rolling')}
    WHERE team_id = {team_id}
      AND season = {season}
      AND has_full_5game_sample = true
    ORDER BY game_date
    LIMIT 50
    """

    results = bq_service.query(sql)
    if not results:
        raise HTTPException(status_code=404, detail="Team not found or insufficient data")

    # Build trend point arrays
    cf_pct_5gp = []
    cf_pct_10gp = []  # TODO: Add 10-game rolling when available in mart
    xgf_pct_5gp = []
    xgf_pct_10gp = []  # TODO: Add 10-game rolling when available in mart
    hdcf_per60_5gp = []
    hdcf_per60_10gp = []  # TODO: Add 10-game rolling when available in mart

    for row in results:
        cf_pct_5gp.append(TeamTrendPoint(
            game_date=row['game_date'],
            value=row['rolling_cf_pct_5gp']
        ))
        xgf_pct_5gp.append(TeamTrendPoint(
            game_date=row['game_date'],
            value=row['rolling_xgf_pct_5gp']
        ))
        hdcf_per60_5gp.append(TeamTrendPoint(
            game_date=row['game_date'],
            value=row['rolling_hdcf_per60_5gp']
        ))

    return TeamTrends(
        team_id=team_id,
        season=season,
        cf_pct_5gp=cf_pct_5gp,
        cf_pct_10gp=cf_pct_10gp,
        xgf_pct_5gp=xgf_pct_5gp,
        xgf_pct_10gp=xgf_pct_10gp,
        hdcf_per60_5gp=hdcf_per60_5gp,
        hdcf_per60_10gp=hdcf_per60_10gp
    )


@router.get("/{team_id}/roster", response_model=TeamRoster)
@cache(ttl=600)
async def get_team_roster(
    team_id: int,
    season: Optional[int] = Query(None, description="Season (e.g., 20232024)"),
) -> TeamRoster:
    """Get roster for a specific team.

    Args:
        team_id: NHL team ID.
        season: Optional season filter.

    Returns:
        Team roster with player stats.

    Raises:
        HTTPException: If team not found.
    """
    # Get current season if not provided
    if not season:
        season_sql = f"""
        SELECT MAX(season) as current_season
        FROM {bq_service.get_full_table_id('stg_boxscores')}
        """
        season_result = bq_service.query(season_sql)
        season = season_result[0]['current_season'] if season_result else 20232024

    # Get player stats aggregated by season
    sql = f"""
    SELECT
        player_id,
        CONCAT(first_name, ' ', last_name) as player_name,
        position_code as position,
        COUNT(DISTINCT game_id) as games_played,
        AVG(toi_5v5) as toi_per_gp,
        AVG(primary_points_per60) as points_per60,
        0.5 as cf_pct  -- TODO: Calculate player CF% when on-ice data available
    FROM {bq_service.get_full_table_id('mart_player_game_stats')}
    WHERE team_id = {team_id}
    GROUP BY player_id, first_name, last_name, position_code
    HAVING games_played >= 3
    ORDER BY position_code, points_per60 DESC
    """

    results = bq_service.query(sql)
    if not results:
        raise HTTPException(status_code=404, detail="Team not found")

    forwards = []
    defensemen = []
    goalies = []

    for row in results:
        player = RosterPlayer(
            player_id=row['player_id'],
            player_name=row['player_name'],
            position=row['position'],
            games_played=row['games_played'],
            toi_per_gp=row['toi_per_gp'],
            points_per60=row['points_per60'],
            cf_pct=row['cf_pct']
        )

        if row['position'] in ['C', 'L', 'R']:
            forwards.append(player)
        elif row['position'] == 'D':
            defensemen.append(player)
        elif row['position'] == 'G':
            goalies.append(player)

    return TeamRoster(
        team_id=team_id,
        season=season,
        forwards=forwards,
        defensemen=defensemen,
        goalies=goalies
    )


@router.get("/{team_id}/vs/{opponent_id}", response_model=TeamVsOpponent)
@cache(ttl=600)
async def get_team_vs_opponent(
    team_id: int,
    opponent_id: int,
    season: Optional[int] = Query(None, description="Season (e.g., 20232024)"),
) -> TeamVsOpponent:
    """Get head-to-head stats for team vs specific opponent.

    Args:
        team_id: NHL team ID.
        opponent_id: Opponent team ID.
        season: Optional season filter.

    Returns:
        Head-to-head stats with small_sample flag if < 3 games.

    Raises:
        HTTPException: If team or opponent not found.
    """
    # Get current season if not provided
    if not season:
        season_sql = f"""
        SELECT MAX(season) as current_season
        FROM {bq_service.get_full_table_id('mart_team_game_stats')}
        """
        season_result = bq_service.query(season_sql)
        season = season_result[0]['current_season'] if season_result else 20232024

    # Find games between these two teams
    sql = f"""
    WITH team_games AS (
        SELECT
            t1.game_id,
            t1.game_date,
            t1.team_id,
            t1.goals_for,
            t1.goals_against,
            t1.cf_pct,
            t1.hdcf_per60
        FROM {bq_service.get_full_table_id('mart_team_game_stats')} t1
        INNER JOIN {bq_service.get_full_table_id('mart_team_game_stats')} t2
            ON t1.game_id = t2.game_id
        WHERE t1.team_id = {team_id}
          AND t2.team_id = {opponent_id}
          AND t1.season = {season}
    )
    SELECT
        COUNT(*) as games_played,
        SUM(CASE WHEN goals_for > goals_against THEN 1 ELSE 0 END) as wins,
        SUM(CASE WHEN goals_for < goals_against THEN 1 ELSE 0 END) as losses,
        0 as otl,  -- TODO: Calculate OT losses
        AVG(cf_pct) as cf_pct,
        AVG(hdcf_per60) as hdcf_per60,
        0.0 as xgf_per60  -- TODO: Add xG when available
    FROM team_games
    """

    results = bq_service.query(sql)
    if not results or results[0]['games_played'] == 0:
        raise HTTPException(status_code=404, detail="No games found between these teams")

    row = results[0]
    small_sample = row['games_played'] < 3

    return TeamVsOpponent(
        team_id=team_id,
        opponent_id=opponent_id,
        season=season,
        games_played=row['games_played'],
        small_sample=small_sample,
        wins=row['wins'],
        losses=row['losses'],
        otl=row['otl'],
        cf_pct=row['cf_pct'] if not small_sample else None,
        hdcf_per60=row['hdcf_per60'] if not small_sample else None,
        xgf_per60=row['xgf_per60'] if not small_sample else None
    )
