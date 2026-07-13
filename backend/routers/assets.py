"""
Tradeable-asset search (Trade tool P7). Reads the unified mart_tradeable_assets layer — every
player, prospect, and draft pick as one row in one WAR + dollar currency — so the (future) trade
builder can search across all asset types behind one picker. Read-only: it only returns assets that
exist in the layer; nothing here invents an asset or a value.
"""
from __future__ import annotations

from typing import List, Optional
from urllib.parse import urlparse

import httpx
from fastapi import APIRouter, HTTPException, Query, Response
from fastapi.concurrency import run_in_threadpool

from models.schemas import TradeableAsset
from services.bigquery import bq_service
from services.cache import cache

router = APIRouter()

# --- NHL image proxy: draw logos/headshots onto an exportable canvas (the share card) ---------------
# assets.nhle.com sends no CORS header, so a crossOrigin canvas load taints and toBlob() fails. We fetch
# the image server-side and re-serve it; the app's permissive CORS middleware then makes it canvas-safe.
# Restricted to the NHL asset host — not an open proxy (no SSRF).
_ALLOWED_IMG_HOSTS = {"assets.nhle.com"}


@router.get("/img")
async def proxy_image(url: str = Query(..., description="assets.nhle.com image URL to proxy for canvas use")):
    if (urlparse(url).hostname or "") not in _ALLOWED_IMG_HOSTS:
        raise HTTPException(status_code=400, detail="host not allowed")
    try:
        async with httpx.AsyncClient(timeout=8.0, follow_redirects=True) as client:
            r = await client.get(url)
    except Exception:  # noqa: BLE001 — upstream unreachable -> the card falls back to a color block
        raise HTTPException(status_code=502, detail="upstream fetch failed")
    if r.status_code != 200:
        raise HTTPException(status_code=r.status_code, detail="upstream error")
    return Response(content=r.content,
                    media_type=r.headers.get("content-type", "application/octet-stream"),
                    headers={"Cache-Control": "public, max-age=86400"})

_COLS = (
    "asset_id, asset_type, player_id, label, org_team, pos_or_slot, "
    "value_war, value_war_low, value_war_high, "
    "value_dollars, value_dollars_low, value_dollars_high, "
    "cap_hit, remaining_years, cost_dollars, "
    "surplus_dollars, surplus_low, surplus_high, confidence, note"
)


def _row(r: dict) -> TradeableAsset:
    return TradeableAsset(**{k: r.get(k) for k in TradeableAsset.model_fields})


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
