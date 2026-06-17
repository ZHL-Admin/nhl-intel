"""Signature-tool endpoints (Phase 5): Lineup Lab line-fit, trade fit, matchup previews."""

from typing import Optional

from fastapi import APIRouter, HTTPException
from fastapi.concurrency import run_in_threadpool

from models.schemas import (
    LineFitRequest, LineFitProjection, LineSuggestionsResponse,
    TradeFitRequest, TradeFitResult,
)
from services import tools as tool_svc
from services.cache import cache

router = APIRouter()


@router.post("/line-fit", response_model=LineFitProjection)
async def post_line_fit(req: LineFitRequest) -> LineFitProjection:
    """Project a hypothetical line (2 D, 3 F, or a 5-skater unit) from member profiles."""
    ids = req.player_ids
    if len(set(ids)) != len(ids):
        raise HTTPException(status_code=400, detail="duplicate players in the line")
    try:
        payload = await run_in_threadpool(tool_svc.score_line, ids, req.season)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return LineFitProjection(**payload)


@router.post("/line-fit/suggestions", response_model=LineSuggestionsResponse)
async def post_line_suggestions(req: LineFitRequest) -> LineSuggestionsResponse:
    """Per-slot 'better fit' candidates: same-caliber players ranked by projected xGF% gain."""
    ids = req.player_ids
    if len(set(ids)) != len(ids):
        raise HTTPException(status_code=400, detail="duplicate players in the line")
    try:
        payload = await run_in_threadpool(tool_svc.line_fit_suggestions, ids, req.season)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return LineSuggestionsResponse(**payload)


@router.post("/trade-fit", response_model=TradeFitResult)
async def post_trade_fit(req: TradeFitRequest) -> TradeFitResult:
    """Score how well a player addresses a team's archetype + component gaps (Phase 5.3)."""
    try:
        payload = await run_in_threadpool(
            tool_svc.trade_fit, req.player_id, req.team_id, req.season)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    name = await run_in_threadpool(_player_name, req.player_id)
    payload["player_name"] = name
    return TradeFitResult(**payload)


def _player_name(player_id: int):
    from services.bigquery import bq_service
    rows = bq_service.query(
        f"SELECT ANY_VALUE(first_name||' '||last_name) AS n "
        f"FROM {bq_service.get_full_table_id('stg_rosters')} WHERE player_id = {int(player_id)}")
    return rows[0]["n"] if rows else None
