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
    season_from: Optional[str] = Query(None),
    season_to: Optional[str] = Query(None),
) -> List[ValueMapPoint]:
    """One point per entity: value given up vs gained (WAR), net + band, trade record. Nets/records are
    settled-only, with settled_count/maturing_count returned alongside so the UI can state the
    denominator. The map landing."""
    rows = await run_in_threadpool(trade_board.value_map, kind, season_from, season_to)
    return [ValueMapPoint(**r) for r in rows]


@router.get("/{kind}/{entity_id}/dossier", response_model=TraderDossier)
@cache(ttl=3600)
async def dossier(kind: str, entity_id: str) -> TraderDossier:
    """A team or GM's full trade record: verdict header inputs, regime-banded timeline, best/worst, deals.
    Net/record/timeline rollups are settled-only; the deal list shows everything (maturing flagged), with
    settled_count/maturing_count alongside."""
    if kind not in ("team", "gm"):
        raise HTTPException(400, "kind must be team or gm")
    d = await run_in_threadpool(trade_board.dossier, kind, entity_id)
    if not d:
        raise HTTPException(404, f"no trades for {kind} {entity_id}")
    return TraderDossier(**d)
