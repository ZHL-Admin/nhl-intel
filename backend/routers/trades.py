"""Trade-outcome retrospective endpoints (Handoff 5, Phase D).

Reads nhl_models.trade_outcomes (one row per trade+team, value-based net WAR with bands + JSON asset
ledgers) via bq_service (DuckDB serving). A RETROSPECTIVE on realized outcomes — never a grade of the
decision at the time. One-segment routes are declared before the parameterized /{trade_id} route.
"""

from typing import List, Optional

from fastapi import APIRouter, HTTPException, Query
from fastapi.concurrency import run_in_threadpool

from models.schemas import TradeBoardItem, ArchetypeAgg, ThesisSummary
from services.cache import cache
from services import trade_board

router = APIRouter()


# ------------------------------------------------------------------- entity-first board (Handoff 6)
@router.get("/board", response_model=List[TradeBoardItem])
@cache(ttl=3600)
async def board(
    sort: str = Query("lopsided", pattern="^(lopsided|recent|closest)$"),
    archetype: Optional[str] = Query(None),
    season_from: Optional[str] = Query(None),
    season_to: Optional[str] = Query(None),
    limit: int = Query(40, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> List[TradeBoardItem]:
    """One object per trade (both sides, GM-attributed, margin/verdict/archetype). The trade-centric
    board the entity surfaces drill into. Shows everything — settled and still-maturing (sorted last)."""
    items = await run_in_threadpool(
        trade_board.board, sort, archetype, season_from, season_to, limit, offset)
    return [TradeBoardItem(**t) for t in items]


@router.get("/thesis-summary", response_model=ThesisSummary)
@cache(ttl=3600)
async def thesis_summary() -> ThesisSummary:
    """Headline figures for the Overview hero band (trades graded, decisive/even share, the
    biggest fleece, and the player-for-picks split)."""
    return ThesisSummary(**await run_in_threadpool(trade_board.thesis_summary))


@router.get("/board/{trade_id}", response_model=TradeBoardItem)
@cache(ttl=3600)
async def board_item(trade_id: str) -> TradeBoardItem:
    """A single trade in the board shape — the balance-bar leaf reached by search or deep link."""
    t = await run_in_threadpool(trade_board.get_trade, trade_id)
    if not t:
        raise HTTPException(404, f"unknown trade_id {trade_id}")
    return TradeBoardItem(**t)


@router.get("/archetypes", response_model=List[ArchetypeAgg])
@cache(ttl=3600)
async def archetypes(
    season_from: Optional[str] = Query(None),
    season_to: Optional[str] = Query(None),
) -> List[ArchetypeAgg]:
    """Per-archetype aggregate + exemplars for the Patterns explorer. Only data-taggable archetypes."""
    rows = await run_in_threadpool(trade_board.archetypes, season_from, season_to)
    return [ArchetypeAgg(**r) for r in rows]
