"""
Tradeable-asset search (Trade tool P7). Reads the unified mart_tradeable_assets layer — every
player, prospect, and draft pick as one row in one WAR + dollar currency — so the (future) trade
builder can search across all asset types behind one picker. Read-only: it only returns assets that
exist in the layer; nothing here invents an asset or a value.
"""
from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, Query
from fastapi.concurrency import run_in_threadpool

from models.schemas import TradeableAsset
from services.bigquery import bq_service
from services.cache import cache

router = APIRouter()

_COLS = (
    "asset_id, asset_type, player_id, label, org_team, pos_or_slot, "
    "value_war, value_war_low, value_war_high, value_dollars, cost_dollars, "
    "surplus_dollars, surplus_low, surplus_high, confidence, note"
)


def _row(r: dict) -> TradeableAsset:
    return TradeableAsset(
        asset_id=r["asset_id"], asset_type=r["asset_type"],
        player_id=int(r["player_id"]) if r.get("player_id") is not None else None,
        label=r["label"], org_team=r.get("org_team"), pos_or_slot=r.get("pos_or_slot"),
        value_war=r.get("value_war"), value_war_low=r.get("value_war_low"),
        value_war_high=r.get("value_war_high"), value_dollars=r.get("value_dollars"),
        cost_dollars=r.get("cost_dollars"), surplus_dollars=r.get("surplus_dollars"),
        surplus_low=r.get("surplus_low"), surplus_high=r.get("surplus_high"),
        confidence=r.get("confidence"), note=r.get("note"),
    )


def _search_sync(q: str, asset_type: Optional[str], org: Optional[str], limit: int) -> List[TradeableAsset]:
    assets = bq_service.get_full_table_id("mart_tradeable_assets")
    where = []
    if q:
        safe = q.replace("'", "''").lower()
        where.append(f"label_lower LIKE '%{safe}%'")
    if asset_type in ("player", "prospect", "pick"):
        where.append(f"asset_type = '{asset_type}'")
    if org:
        where.append(f"org_team = '{org.replace(chr(39), '')}'")
    clause = ("WHERE " + " AND ".join(where)) if where else ""
    # most valuable surplus first; a search with no query just returns the top assets of the filter
    rows = bq_service.query(
        f"SELECT {_COLS} FROM {assets} {clause} "
        f"ORDER BY surplus_dollars DESC NULLS LAST LIMIT {int(limit)}")
    return [_row(r) for r in rows]


@router.get("/search", response_model=List[TradeableAsset])
@cache(ttl=600)
async def search_assets(
    q: str = Query("", description="name substring (blank = top assets of the filter)"),
    type: Optional[str] = Query(None, description="player | prospect | pick"),
    org: Optional[str] = Query(None, description="team abbreviation filter"),
    limit: int = Query(25, ge=1, le=100),
) -> List[TradeableAsset]:
    """Search the unified tradeable-asset layer across players, prospects, and picks."""
    return await run_in_threadpool(_search_sync, q, type, org, limit)
