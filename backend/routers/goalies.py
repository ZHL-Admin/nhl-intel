"""Goalie endpoints on the in-house GSAx layer (Phase 2.5)."""

from typing import List, Optional

from fastapi import APIRouter, HTTPException, Query
from fastapi.concurrency import run_in_threadpool

from models.schemas import GoalieSeason, GoalieGameLogRow, GoalieRadar
from services.bigquery import bq_service
from services.cache import cache

router = APIRouter()


@router.get("/{goalie_id}/radar", response_model=GoalieRadar)
@cache(ttl=1800)
async def get_goalie_radar(
    goalie_id: int,
    season: Optional[str] = Query(None, description="Season (default: latest)"),
) -> GoalieRadar:
    """Goalie skills radar: spokes percentiled within goalies (Part B)."""
    from services.radar import goalie_radar as _radar
    payload = await run_in_threadpool(_radar, goalie_id, season)
    if payload is None:
        raise HTTPException(status_code=404, detail="No radar for this goalie")
    return GoalieRadar(**payload)


def _goalie_name(goalie_id: int) -> Optional[str]:
    rows = bq_service.query(f"""
        SELECT first_name || ' ' || last_name AS name
        FROM {bq_service.get_full_table_id('stg_rosters')}
        WHERE player_id = {goalie_id}
        LIMIT 1
    """)
    return rows[0]['name'] if rows else None


@router.get("/{goalie_id}", response_model=GoalieSeason)
@cache(ttl=3600)
async def get_goalie_season(
    goalie_id: int,
    season: Optional[str] = Query(None, description="Season (e.g. 2024-25); defaults to latest"),
) -> GoalieSeason:
    """Season GSAx line for a goalie, with the NHL Edge second opinion."""
    season_filter = f"AND season = '{season}'" if season else ""
    rows = bq_service.query(f"""
        SELECT * FROM {bq_service.get_full_table_id('mart_goalie_season')}
        WHERE goalie_id = {goalie_id} {season_filter}
        ORDER BY season DESC
        LIMIT 1
    """)
    if not rows:
        raise HTTPException(status_code=404, detail="Goalie season not found")
    r = rows[0]
    return GoalieSeason(goalie_name=_goalie_name(goalie_id), **{k: r.get(k) for k in GoalieSeason.model_fields if k != 'goalie_name'})


@router.get("/{goalie_id}/gamelog", response_model=List[GoalieGameLogRow])
@cache(ttl=600)
async def get_goalie_gamelog(
    goalie_id: int,
    season: Optional[str] = Query(None),
    limit: int = Query(40, ge=1, le=200),
) -> List[GoalieGameLogRow]:
    """Per-game GSAx log for a goalie, most recent first."""
    season_filter = f"AND season = '{season}'" if season else ""
    rows = bq_service.query(f"""
        SELECT game_id, game_date, season, team_id, shots_faced, saves, goals_against,
               save_pct, xga, gsax, high_gsax, high_shots, high_saves
        FROM {bq_service.get_full_table_id('mart_goalie_game_stats')}
        WHERE goalie_id = {goalie_id} {season_filter}
        ORDER BY game_date DESC
        LIMIT {limit}
    """)
    return [GoalieGameLogRow(**{k: r.get(k) for k in GoalieGameLogRow.model_fields}) for r in rows]
