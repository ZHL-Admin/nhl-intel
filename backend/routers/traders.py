"""Trader (team / GM) entity endpoints (Handoff 6). The GM is a peer entity to the team, both served
through one parameterized dossier. Composes nhl_models.trade_outcomes + stg_gm_tenures via the
trade_board service. One-segment routes before the parameterized dossier route."""

from typing import List, Optional

from fastapi import APIRouter, HTTPException, Query
from fastapi.concurrency import run_in_threadpool

from models.schemas import ValueMapPoint, TraderDossier
from services.cache import cache
from services import trade_board

router = APIRouter()


@router.get("/value-map", response_model=List[ValueMapPoint])
@cache(ttl=3600)
async def value_map(
    kind: str = Query("team", pattern="^(team|gm)$"),
    lens: str = Query("slot", pattern="^(slot|actual)$"),
    season_from: Optional[str] = Query(None),
    season_to: Optional[str] = Query(None),
) -> List[ValueMapPoint]:
    """One point per entity: value given up vs gained (WAR), net + band, trade record. The map landing."""
    rows = await run_in_threadpool(trade_board.value_map, kind, lens, season_from, season_to)
    return [ValueMapPoint(**r) for r in rows]


@router.get("/{kind}/{entity_id}/dossier", response_model=TraderDossier)
@cache(ttl=3600)
async def dossier(kind: str, entity_id: str, lens: str = Query("slot", pattern="^(slot|actual)$")) -> TraderDossier:
    """A team or GM's full trade record: verdict header inputs, regime-banded timeline, best/worst, deals."""
    if kind not in ("team", "gm"):
        raise HTTPException(400, "kind must be team or gm")
    d = await run_in_threadpool(trade_board.dossier, kind, entity_id, lens)
    if not d:
        raise HTTPException(404, f"no trades for {kind} {entity_id}")
    return TraderDossier(**d)
