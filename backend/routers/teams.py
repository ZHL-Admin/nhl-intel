"""Team-related API endpoints.

Provides endpoints for team details, trends, roster, and vs-opponent stats.
"""
from fastapi import APIRouter, HTTPException, Query
from typing import Optional, List

from models.schemas import (
    TeamDetail, TeamTrends, TeamTrendPoint, TeamRoster, RosterPlayer,
    TeamVsOpponent, PlayerZoneDeployment, TeamSituational, EdgeTeamProfile,
    TeamIdentity, TeamIdentityWindow, IdentityMetric, StyleMap, StyleMapTeam, StreakCard
)
from services.bigquery import bq_service
from services.cache import cache
from routers.streaks import card_from_row

router = APIRouter()

# Fingerprint metric keys exposed by /teams/{id}/identity, in display order. Labels and
# higher-is-better direction live on the frontend (config/metrics.ts), single-sourced.
IDENTITY_METRIC_KEYS = [
    "rush_share_for", "forecheck_share_for", "cycle_share_for", "point_shot_share_for",
    "rebound_share_for", "rush_share_against", "forecheck_share_against",
    "cycle_share_against", "point_shot_share_against", "rebound_share_against",
    "pace", "shot_quality", "shot_volume_per60", "hits_per60",
    "penalties_taken_per60", "penalties_drawn_per60", "pp_point_shot_share",
    "oz_time_pct", "dz_time_pct", "oz_conversion",
]


def _team_abbrev(team_id: int, season: str) -> Optional[str]:
    rows = bq_service.query(f"""
        SELECT ANY_VALUE(team_abbrev) AS a
        FROM {bq_service.get_full_table_id('mart_team_game_stats')}
        WHERE team_id = {team_id} AND season = '{season}'
    """)
    return rows[0]['a'] if rows and rows[0].get('a') else None


@router.get("/style-map", response_model=StyleMap)
@cache(ttl=3600)
async def get_style_map(
    season: Optional[str] = Query(None, description="Season (default: latest)"),
) -> StyleMap:
    """League style map: 2D PCA coordinates per team + axis annotations (Phase 3.2)."""
    sm = bq_service.get_models_table_id('style_map')
    mart = bq_service.get_full_table_id('mart_team_game_stats')
    if not season:
        srows = bq_service.query(f"SELECT MAX(season) AS s FROM {sm}")
        season = srows[0]['s']
    rows = bq_service.query(f"""
        WITH abbrev AS (
            SELECT team_id, ANY_VALUE(team_abbrev) AS team_abbrev
            FROM {mart} WHERE season = '{season}' GROUP BY team_id
        )
        SELECT s.team_id, a.team_abbrev, s.x, s.y,
               s.x_pos_desc, s.x_neg_desc, s.y_pos_desc, s.y_neg_desc
        FROM {sm} s LEFT JOIN abbrev a USING (team_id)
        WHERE s.season = '{season}'
        ORDER BY s.team_id
    """)
    if not rows:
        raise HTTPException(status_code=404, detail="Style map not found")
    first = rows[0]
    return StyleMap(
        season=season,
        x_pos_desc=first['x_pos_desc'], x_neg_desc=first['x_neg_desc'],
        y_pos_desc=first['y_pos_desc'], y_neg_desc=first['y_neg_desc'],
        teams=[StyleMapTeam(team_id=r['team_id'], team_abbrev=r.get('team_abbrev'),
                            x=r['x'], y=r['y']) for r in rows],
    )


@router.get("/{team_id}/streak", response_model=StreakCard)
@cache(ttl=1800)
async def get_team_streak(
    team_id: int,
    season: Optional[str] = Query(None, description="Season (default: latest)"),
    window: int = Query(10, description="Last-N games window (5, 10, or 20)"),
) -> StreakCard:
    """Streak Doctor card for a team: last-N run decomposed with a verdict (Phase 3.3)."""
    cards = bq_service.get_models_table_id('streak_cards')
    if not season:
        season = bq_service.query(f"SELECT MAX(season) AS s FROM {cards}")[0]['s']
    rows = bq_service.query(f"""
        SELECT * FROM {cards}
        WHERE team_id = {team_id} AND season = '{season}' AND window_games = {window}
    """)
    if not rows:
        raise HTTPException(status_code=404, detail="Streak card not found")
    return card_from_row(rows[0], _team_abbrev(team_id, season))


@router.get("/{team_id}/identity", response_model=TeamIdentity)
@cache(ttl=3600)
async def get_team_identity(
    team_id: int,
    season: Optional[str] = Query(None, description="Season (default: latest)"),
) -> TeamIdentity:
    """Team identity fingerprint: per-window metrics with league percentiles (Phase 3.2)."""
    table = bq_service.get_full_table_id('mart_team_identity')
    if not season:
        srows = bq_service.query(f"SELECT MAX(season) AS s FROM {table}")
        season = srows[0]['s']
    rows = bq_service.query(f"""
        SELECT * FROM {table}
        WHERE team_id = {team_id} AND season = '{season}'
    """)
    if not rows:
        raise HTTPException(status_code=404, detail="Team identity not found")
    size_rows = bq_service.query(f"""
        SELECT COUNT(DISTINCT team_id) AS n FROM {table}
        WHERE season = '{season}' AND window_kind = 'season'
    """)
    league_size = size_rows[0]['n'] if size_rows else 32
    windows = []
    for r in rows:
        metrics = [IdentityMetric(key=k, value=r.get(k), percentile=r.get(f"{k}_pctile"))
                   for k in IDENTITY_METRIC_KEYS]
        windows.append(TeamIdentityWindow(window=r['window_kind'], games=r['games'],
                                          metrics=metrics))
    windows.sort(key=lambda w: 0 if w.window == 'season' else 1)
    return TeamIdentity(team_id=team_id, team_abbrev=_team_abbrev(team_id, season),
                        season=season, league_size=league_size, windows=windows)


def _season_str_to_id(season: Optional[str]) -> Optional[int]:
    """Convert a 'YYYY-YY' season string to the Edge YYYYYYYY id (e.g. 2024-25 -> 20242025)."""
    if not season:
        return None
    try:
        start = int(season[:4])
        return start * 10000 + (start + 1)
    except (ValueError, IndexError):
        return None


@router.get("/{team_id}", response_model=TeamDetail)
@cache(ttl=600)
async def get_team_detail(
    team_id: int,
    season: Optional[str] = Query(None, description="Season (e.g., 2023-24)"),
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
        season = season_result[0]['current_season'] if season_result else "2025-26"

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
            AVG(SAFE_DIVIDE(xgf, toi_5v5_minutes / 60.0)) as xgf_per60,
            AVG(SAFE_DIVIDE(xga, toi_5v5_minutes / 60.0)) as xga_per60,
            SUM(goals_for) as total_goals_for,
            SUM(goals_against) as total_goals_against,
            AVG(zone_entry_proxy_success_rate) as zone_entry_proxy_success_rate
        FROM {bq_service.get_full_table_id('mart_team_game_stats')}
        WHERE season = '{season}'
        GROUP BY team_id, team_abbrev
    ),
    team_ranks AS (
        SELECT
            *,
            RANK() OVER (ORDER BY cf_pct DESC) as cf_pct_rank,
            RANK() OVER (ORDER BY SAFE_DIVIDE(xgf_per60, xgf_per60 + xga_per60) DESC) as xgf_pct_rank,
            RANK() OVER (ORDER BY hdcf_per60 DESC) as hdcf_per60_rank,
            RANK() OVER (ORDER BY hdca_per60 ASC) as hdca_per60_rank,
            RANK() OVER (ORDER BY total_goals_for / NULLIF(games_played, 0) DESC) as gf_per_gp_rank,
            RANK() OVER (ORDER BY total_goals_against / NULLIF(games_played, 0) ASC) as ga_per_gp_rank,
            RANK() OVER (ORDER BY zone_entry_proxy_success_rate DESC NULLS LAST) as zone_entry_proxy_success_rate_rank
        FROM team_stats
    )
    SELECT * FROM team_ranks
    WHERE team_id = {team_id}
    """

    results = bq_service.query(sql)
    if not results:
        raise HTTPException(status_code=404, detail="Team not found")

    row = results[0]

    # Get zone time stats (aggregate across all games)
    zone_time_data = bq_service.get_team_zone_time(team_id, season)
    oz_pct = None
    nz_pct = None
    dz_pct = None
    if zone_time_data:
        # Calculate average percentages across all games
        total_oz = sum(g['oz_pct'] for g in zone_time_data if g.get('oz_pct'))
        total_nz = sum(g['nz_pct'] for g in zone_time_data if g.get('nz_pct'))
        total_dz = sum(g['dz_pct'] for g in zone_time_data if g.get('dz_pct'))
        count = len(zone_time_data)
        if count > 0:
            oz_pct = total_oz / count
            nz_pct = total_nz / count
            dz_pct = total_dz / count

    # Get faceoff stats (aggregate across all games)
    faceoff_data = bq_service.get_team_faceoffs(team_id, season)
    faceoff_win_pct = None
    oz_faceoff_win_pct = None
    nz_faceoff_win_pct = None
    dz_faceoff_win_pct = None
    if faceoff_data:
        # Calculate overall percentages from totals
        total_faceoffs = sum(g['total_faceoffs'] for g in faceoff_data if g.get('total_faceoffs'))
        total_won = sum(g['faceoffs_won'] for g in faceoff_data if g.get('faceoffs_won'))
        if total_faceoffs > 0:
            faceoff_win_pct = (total_won / total_faceoffs) * 100

        # Zone-specific faceoffs
        oz_total = sum(g['oz_faceoffs'] for g in faceoff_data if g.get('oz_faceoffs'))
        oz_won = sum(g['oz_faceoffs_won'] for g in faceoff_data if g.get('oz_faceoffs_won'))
        if oz_total > 0:
            oz_faceoff_win_pct = (oz_won / oz_total) * 100

        nz_total = sum(g['nz_faceoffs'] for g in faceoff_data if g.get('nz_faceoffs'))
        nz_won = sum(g['nz_faceoffs_won'] for g in faceoff_data if g.get('nz_faceoffs_won'))
        if nz_total > 0:
            nz_faceoff_win_pct = (nz_won / nz_total) * 100

        dz_total = sum(g['dz_faceoffs'] for g in faceoff_data if g.get('dz_faceoffs'))
        dz_won = sum(g['dz_faceoffs_won'] for g in faceoff_data if g.get('dz_faceoffs_won'))
        if dz_total > 0:
            dz_faceoff_win_pct = (dz_won / dz_total) * 100

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
        zone_entry_proxy_success_rate=row.get('zone_entry_proxy_success_rate'),
        cf_pct_rank=row['cf_pct_rank'],
        xgf_pct_rank=row['xgf_pct_rank'],
        hdcf_per60_rank=row['hdcf_per60_rank'],
        hdca_per60_rank=row['hdca_per60_rank'],
        gf_per_gp_rank=row['gf_per_gp_rank'],
        ga_per_gp_rank=row['ga_per_gp_rank'],
        zone_entry_proxy_success_rate_rank=row.get('zone_entry_proxy_success_rate_rank'),
        oz_pct=oz_pct,
        nz_pct=nz_pct,
        dz_pct=dz_pct,
        faceoff_win_pct=faceoff_win_pct,
        oz_faceoff_win_pct=oz_faceoff_win_pct,
        nz_faceoff_win_pct=nz_faceoff_win_pct,
        dz_faceoff_win_pct=dz_faceoff_win_pct
    )


@router.get("/{team_id}/edge", response_model=EdgeTeamProfile)
@cache(ttl=86400)
async def get_team_edge(
    team_id: int,
    season: Optional[str] = Query(None, description="Season (e.g., 2024-25); latest if omitted"),
    game_type: int = Query(2, description="2=regular season, 3=playoffs"),
) -> EdgeTeamProfile:
    """NHL Edge team profile: NHL danger-bucket shot shares (season-aggregate)."""
    row = bq_service.get_team_edge(team_id, _season_str_to_id(season), game_type)
    if not row:
        raise HTTPException(status_code=404, detail="No NHL Edge data for this team/season")
    return EdgeTeamProfile(**row)


@router.get("/{team_id}/trends", response_model=TeamTrends)
@cache(ttl=600)
async def get_team_trends(
    team_id: int,
    season: Optional[str] = Query(None, description="Season (e.g., 2023-24)"),
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
        season = season_result[0]['current_season'] if season_result else "2025-26"

    # Get rolling trends
    sql = f"""
    SELECT
        game_date,
        rolling_cf_pct_5gp,
        rolling_xgf_pct_5gp,
        rolling_hdcf_per60_5gp
    FROM {bq_service.get_full_table_id('mart_team_rolling')}
    WHERE team_id = {team_id}
      AND season = '{season}'
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
    season: Optional[str] = Query(None, description="Season (e.g., 2023-24)"),
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
        season = season_result[0]['current_season'] if season_result else "2025-26"

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
    season: Optional[str] = Query(None, description="Season (e.g., 2023-24)"),
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
        season = season_result[0]['current_season'] if season_result else "2025-26"

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
          AND t1.season = '{season}'
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


@router.get("/{team_id}/deployment", response_model=List[PlayerZoneDeployment])
@cache(ttl=21600)  # 6 hours
async def get_team_deployment(
    team_id: int,
    season: Optional[str] = Query(None, description="Season (e.g., '2024-25')"),
) -> List[PlayerZoneDeployment]:
    """Get zone deployment stats for all players on a team.

    Args:
        team_id: NHL team ID.
        season: Optional season filter in format "YYYY-YY".

    Returns:
        List of player zone deployment stats for the team.

    Raises:
        HTTPException: If team not found.
    """
    # Get current season if not provided
    if not season:
        season_sql = f"""
        SELECT MAX(season) as current_season
        FROM {bq_service.get_full_table_id('mart_player_zone_deployment')}
        """
        season_result = bq_service.query(season_sql)
        season = season_result[0]['current_season'] if season_result else "2024-25"

    # Get zone deployment for all players on the team
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
    FROM {bq_service.get_full_table_id('mart_player_zone_deployment')}
    WHERE team_id = {team_id}
        AND season = '{season}'
    ORDER BY total_zone_starts DESC
    """

    results = bq_service.query(sql)
    if not results:
        raise HTTPException(status_code=404, detail="Team not found or no deployment data")

    deployments = []
    for row in results:
        deployment = PlayerZoneDeployment(
            player_id=row['player_id'],
            season=row['season'],
            team_id=row['team_id'],
            oz_starts=row['offensive_zone_starts'],
            nz_starts=row['neutral_zone_starts'],
            dz_starts=row['defensive_zone_starts'],
            total_starts=row['total_zone_starts'],
            ozs_pct=row['ozs_pct'],
            nzs_pct=row['nzs_pct'],
            dzs_pct=row['dzs_pct']
        )
        deployments.append(deployment)

    return deployments


@router.get("/{team_id}/situational", response_model=List[TeamSituational])
@cache(ttl=21600)  # 6 hours
async def get_team_situational(
    team_id: int,
    game_id: int = Query(..., description="Game ID to get situational stats for"),
    situation: str = Query("all", description="Filter by situation: all, 5v5, pp, pk")
) -> List[TeamSituational]:
    """Get situational stats for a team in a specific game.

    Args:
        team_id: NHL team ID.
        game_id: NHL game ID.
        situation: Optional situation filter (all, 5v5, pp, pk).

    Returns:
        List of situational stat records (1-4 records depending on filter).

    Raises:
        HTTPException: If team or game not found.
    """
    # Get situational data using the service layer
    results = bq_service.get_team_situational(team_id, game_id, situation)

    if not results:
        raise HTTPException(status_code=404, detail="Team or game not found")

    situational_stats = []
    for row in results:
        stat = TeamSituational(
            team_id=row['team_id'],
            game_id=row['game_id'],
            situation=row['situation'],
            toi_seconds=row.get('toi_seconds'),
            cf_pct=row.get('cf_pct'),
            xgf_pct=row.get('xgf_pct'),
            hdcf_pct=row.get('hdcf_pct'),
            gf=row.get('goals_for'),
            ga=row.get('goals_against'),
            shots_for=row.get('shot_attempts_for'),
            shots_against=row.get('shot_attempts_against')
        )
        situational_stats.append(stat)

    return situational_stats
