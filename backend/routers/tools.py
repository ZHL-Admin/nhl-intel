"""Signature-tool endpoints (Phase 5): Lineup Lab line-fit, player fit, matchup previews."""

from typing import List, Optional

from fastapi import APIRouter, HTTPException, Query
from fastapi.concurrency import run_in_threadpool

from models.schemas import (
    LineFitRequest, LineFitProjection, LineSuggestionsResponse,
    TradeFitRequest, TradeFitResult, BestTeamFit,
    TradeEvaluateRequest, TradeEvaluateResponse,
)
from services import tools as tool_svc
from services import trade_engine
from services.cache import cache

router = APIRouter()


# Registered with the literal path /trade-evaluate; tools has no /{id} route, so no shadowing.
@router.post("/trade-evaluate", response_model=TradeEvaluateResponse)
async def post_trade_evaluate(req: TradeEvaluateRequest) -> TradeEvaluateResponse:
    """Evaluate a proposed multi-team trade: per-team talent / surplus / fit / cap decomposition.

    Stateless. A trade is a set of asset movements among N teams (two-team is the common case), with
    optional retention elections. The verdict is a multi-axis decomposition, never a single grade;
    cap compliance is a soft, approximate flag, never a gate."""
    try:
        payload = await run_in_threadpool(trade_engine.evaluate, req.model_dump(), req.season)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return TradeEvaluateResponse(**payload)


@router.post("/line-fit", response_model=LineFitProjection)
@cache(ttl=3600)
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
@cache(ttl=3600)
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
@cache(ttl=3600)
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


@router.get("/trade-fit/best-teams", response_model=List[BestTeamFit])
@cache(ttl=3600)
async def get_best_team_fits(
    player_id: int = Query(...),
    exclude_team: Optional[int] = Query(None),
    season: Optional[str] = Query(None),
) -> List[BestTeamFit]:
    """The teams whose gaps this player fills best, ranked (Phase 5.3)."""
    try:
        payload = await run_in_threadpool(tool_svc.best_team_fits, player_id, season, exclude_team)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return [BestTeamFit(**t) for t in payload]


def _player_name(player_id: int):
    from services.bigquery import bq_service
    rows = bq_service.query(
        f"SELECT ANY_VALUE(first_name||' '||last_name) AS n "
        f"FROM {bq_service.get_full_table_id('stg_rosters')} WHERE player_id = {int(player_id)}")
    return rows[0]["n"] if rows else None
