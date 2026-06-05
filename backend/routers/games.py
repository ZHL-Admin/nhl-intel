"""Game-related API endpoints.

Provides endpoints for game lists, game details, and game player stats.
"""
from fastapi import APIRouter, HTTPException, Query
from typing import Optional, List
from datetime import date

from models.schemas import Game, GameDetail, GamePlayerStats, TeamGameStats, PlayerGameStats
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
    where_clauses = []
    if date:
        where_clauses.append(f"game_date = '{date}'")
    elif start_date:
        where_clauses.append(f"game_date >= '{start_date}'")
    if end_date:
        where_clauses.append(f"game_date <= '{end_date}'")
    if team_id:
        where_clauses.append(f"(home_team_id = {team_id} OR away_team_id = {team_id})")
    if season:
        where_clauses.append(f"season = {season}")

    where_sql = f"WHERE {' AND '.join(where_clauses)}" if where_clauses else ""

    sql = f"""
    WITH deduplicated AS (
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
            ROW_NUMBER() OVER (
                PARTITION BY game_id
                ORDER BY
                    CASE
                        WHEN game_state IN ('OFF', 'FINAL') THEN 1
                        WHEN game_state = 'LIVE' THEN 2
                        ELSE 3
                    END,
                    ingestion_date DESC
            ) as rn
        FROM {bq_service.get_full_table_id('stg_boxscores')}
        {where_sql}
    )
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
        game_state
    FROM deduplicated
    WHERE rn = 1
    ORDER BY game_date DESC, game_id DESC
    LIMIT 100
    """

    results = bq_service.query(sql)

    games = []
    for row in results:
        # Determine if game is preview (not finished)
        is_preview = row['game_state'] not in ['OFF', 'FINAL']

        games.append(Game(
            game_id=row['game_id'],
            game_date=row['game_date'],
            season=row['season'],
            home_team_id=row['home_team_id'],
            home_team_abbrev=row['home_team_abbrev'],
            away_team_id=row['away_team_id'],
            away_team_abbrev=row['away_team_abbrev'],
            home_score=row['home_team_score'] if not is_preview else None,
            away_score=row['away_team_score'] if not is_preview else None,
            is_preview=is_preview
        ))

    return games


@router.get("/{game_id}", response_model=GameDetail)
@cache(ttl=300)
async def get_game_detail(game_id: int) -> GameDetail:
    """Get detailed information for a specific game.

    Args:
        game_id: NHL game ID.

    Returns:
        Detailed game information including team stats.

    Raises:
        HTTPException: If game not found.
    """
    # Get basic game info
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
        game_state
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
            shot_attempts_for
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
                shot_attempts=row.get('shot_attempts_for')
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
        is_preview=is_preview
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
        p.primary_assists as assists,
        (p.individual_goals + p.primary_assists) as points,
        p.individual_shot_attempts as shots,
        p.individual_shot_attempts as cf,
        p.individual_high_danger_attempts as hdcf,
        p.ixg,
        p.ixg_per60,
        p.hot_cold_flag
    FROM {bq_service.get_full_table_id('mart_player_game_stats')} p
    WHERE p.game_id = {game_id}
    ORDER BY (p.individual_goals + p.primary_assists) DESC, p.ixg_per60 DESC
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
            toi=row['toi'],
            goals=row['goals'],
            assists=row['assists'],
            points=row['points'],
            shots=row['shots'],
            cf=row['cf'],
            hdcf=row['hdcf'],
            ixg=row.get('ixg'),
            ixg_per60=row.get('ixg_per60'),
            hot_cold_flag=row.get('hot_cold_flag')
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
