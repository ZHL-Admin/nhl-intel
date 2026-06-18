"""
Archetype explainer endpoints (Learn): the discovered v2 clusters as a browsable gallery + a
player style-map. Reads nhl_models.archetype_gallery / player_style_map (built by
models_ml.compute_archetype_explainer). Archetypes are DISCOVERED, not designable — nothing here
lets a caller invent one; the style-map only returns real players.
"""
from __future__ import annotations

import json
from typing import List, Optional

from fastapi import APIRouter, HTTPException, Query
from fastapi.concurrency import run_in_threadpool

from models.schemas import (
    ArchetypeCard, ArchetypeTrait, ArchetypeExemplar, RadarSpoke,
    StyleMap, StyleMapPoint, StyleMapRegion,
)
from services.bigquery import bq_service
from services.cache import cache

router = APIRouter()


def _cards_sync(pos: Optional[str]) -> List[ArchetypeCard]:
    g = bq_service.get_models_table_id("archetype_gallery")
    where = f"WHERE pos_group = '{pos}'" if pos in ("F", "D") else ""
    # most valuable archetypes first (mean member composite value), within each position
    rows = bq_service.query(f"SELECT * FROM {g} {where} ORDER BY pos_group, mean_value DESC")
    cards = []
    for r in rows:
        cards.append(ArchetypeCard(
            key=r["key"], name=r["name"], pos_group=r["pos_group"],
            family=r.get("family"), descriptor=r.get("descriptor"),
            member_count=int(r["member_count"]),
            universal_traits=[ArchetypeTrait(**t) for t in json.loads(r["universal_traits"])],
            distinctive_traits=[ArchetypeTrait(**t) for t in json.loads(r["distinctive_traits"])],
            centroid_radar=[RadarSpoke(**s) for s in json.loads(r["centroid_radar"])],
            exemplars=[ArchetypeExemplar(**e) for e in json.loads(r["exemplars"])],
        ))
    return cards


@router.get("", response_model=List[ArchetypeCard])
@cache(ttl=3600)
async def get_archetypes(pos: Optional[str] = Query(None, description="F | D (default: both)")) -> List[ArchetypeCard]:
    """The discovered archetypes (12 F + 11 D): centroid radar, measured traits, real exemplars."""
    return await run_in_threadpool(_cards_sync, pos)


def _style_map_sync(pos: str) -> StyleMap:
    sm = bq_service.get_models_table_id("player_style_map")
    rosters = bq_service.get_full_table_id("stg_rosters")
    teams = bq_service.get_full_table_id("mart_team_game_stats")
    # one point per player (latest season), joined to name + current team
    rows = bq_service.query(f"""
        WITH latest AS (
            SELECT *, ROW_NUMBER() OVER (PARTITION BY player_id ORDER BY season DESC) AS rn
            FROM {sm} WHERE pos_group = '{pos}'
        ),
        nm AS (
            SELECT player_id, ANY_VALUE(first_name || ' ' || last_name) AS name,
                   ARRAY_AGG(team_id ORDER BY game_id DESC LIMIT 1)[OFFSET(0)] AS team_id
            FROM {rosters}
            WHERE SUBSTR(CAST(game_id AS STRING), 5, 2) IN ('01', '02', '03')
            GROUP BY player_id
        ),
        tm AS (SELECT team_id, ANY_VALUE(team_abbrev) AS abbrev FROM {teams} GROUP BY team_id)
        SELECT l.player_id, l.season, l.x, l.y, l.archetype, l.membership, l.is_boundary,
               nm.name, tm.abbrev AS team_abbrev
        FROM latest l LEFT JOIN nm ON l.player_id = nm.player_id
        LEFT JOIN tm ON nm.team_id = tm.team_id
        WHERE l.rn = 1
    """)
    points, agg = [], {}
    for r in rows:
        points.append(StyleMapPoint(
            player_id=r["player_id"], name=r.get("name"), team_abbrev=r.get("team_abbrev"),
            season=r["season"], x=r["x"], y=r["y"], archetype=r["archetype"],
            membership=r["membership"], is_boundary=bool(r["is_boundary"])))
        a = agg.setdefault(r["archetype"], {"sx": 0.0, "sy": 0.0, "n": 0})
        a["sx"] += r["x"]; a["sy"] += r["y"]; a["n"] += 1
    regions = [StyleMapRegion(archetype=k, x=v["sx"] / v["n"], y=v["sy"] / v["n"], member_count=v["n"])
               for k, v in agg.items()]
    return StyleMap(pos_group=pos, points=points, regions=regions)


@router.get("/style-map", response_model=StyleMap)
@cache(ttl=3600)
async def get_style_map(pos: str = Query("F", description="F | D")) -> StyleMap:
    """Player style-map for one position: real player points (latest season) + cluster regions."""
    if pos not in ("F", "D"):
        raise HTTPException(status_code=400, detail="pos must be F or D")
    return await run_in_threadpool(_style_map_sync, pos)
