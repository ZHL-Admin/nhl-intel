"""Draft Value endpoints (Handoff 5): empirical pick-value curve, the theory-test summary, the
steal/bust board, and a per-player draft block.

All values are in the same WAR units as the rest of the value stack, and are realized 7-year-window
pWAR — an explicit wide-band estimate for pre-2021 seasons (labeled as such in the payload and UI).
One-segment routes are declared before the parameterized /player/{id} route.
"""

from typing import List, Optional

from fastapi import APIRouter, Query
from fastapi.concurrency import run_in_threadpool

from models.schemas import (
    PickValueCurveRow, DraftTheorySummaryRow, DraftBoardRow, DraftPlayerBlock,
)
from services.bigquery import bq_service
from services.cache import cache

router = APIRouter()


@router.get("/pick-value-curve", response_model=List[PickValueCurveRow])
@cache(ttl=86400)
async def pick_value_curve() -> List[PickValueCurveRow]:
    """The empirical value of each overall pick (smoothed mean/median + p10-p90 band), 1..N."""
    curve = bq_service.get_models_table_id("pick_value_curve")
    sql = f"""
        SELECT overall_pick, n, ev_mean, ev_median, ev_mean_smooth, ev_median_smooth,
               p10, p25, p75, p90, p10_smooth, p90_smooth, share_never_nhl, share_regular
        FROM {curve} ORDER BY overall_pick
    """
    rows = await run_in_threadpool(bq_service.query, sql)
    return [PickValueCurveRow(**{k: r.get(k) for k in PickValueCurveRow.model_fields}) for r in rows]


@router.get("/theory-summary", response_model=List[DraftTheorySummaryRow])
@cache(ttl=86400)
async def theory_summary() -> List[DraftTheorySummaryRow]:
    """The "85% theory" shares — below slot mean / median / never-NHL — pooled and by pick range."""
    summ = bq_service.get_models_table_id("draft_value_summary")
    order = "CASE pick_range WHEN '1-10' THEN 0 WHEN '11-31' THEN 1 WHEN 'R2' THEN 2 " \
            "WHEN 'R3-7' THEN 3 ELSE 4 END"
    sql = f"""
        SELECT pick_range, picks, share_below_mean, share_below_median, share_never_nhl,
               share_became_regular, mean_realized, median_realized
        FROM {summ} ORDER BY {order}
    """
    rows = await run_in_threadpool(bq_service.query, sql)
    return [DraftTheorySummaryRow(**{k: r.get(k) for k in DraftTheorySummaryRow.model_fields})
            for r in rows]


@router.get("/board", response_model=List[DraftBoardRow])
@cache(ttl=86400)
async def board(
    type: str = Query("steals", pattern="^(steals|busts)$"),
    pos: Optional[str] = Query(None, description="Filter by F/D/G"),
    limit: int = Query(25, ge=1, le=100),
) -> List[DraftBoardRow]:
    """Steal/bust board: evaluable picks ranked by value above (steals) or below (busts) slot."""
    player = bq_service.get_models_table_id("draft_value_player")
    direction = "DESC" if type == "steals" else "ASC"
    where = "WHERE 1=1"
    if pos in ("F", "D", "G"):
        where += f" AND pos_group = '{pos}'"
    sql = f"""
        SELECT overall_pick, draft_year, full_name, pos_group, draft_team_abbrev,
               resolved_player_id, realized_value, expected_mean, value_above_slot,
               became_regular, made_nhl
        FROM {player}
        {where}
        ORDER BY value_above_slot {direction}
        LIMIT {limit}
    """
    rows = await run_in_threadpool(bq_service.query, sql)
    return [DraftBoardRow(**{k: r.get(k) for k in DraftBoardRow.model_fields}) for r in rows]


@router.get("/player/{player_id}", response_model=Optional[DraftPlayerBlock])
@cache(ttl=86400)
async def player_draft(player_id: int) -> Optional[DraftPlayerBlock]:
    """A player's draft line: where taken, expected vs realized, percentile within range, censoring.

    Reads int_draft_player_value (covers censored 2019+ players too) joined to the empirical curve.
    Returns null for undrafted players (no resolved pick)."""
    idpv = bq_service.get_full_table_id("int_draft_player_value")
    curve = bq_service.get_models_table_id("pick_value_curve")
    sql = f"""
        WITH me AS (
            SELECT * FROM {idpv} WHERE resolved_player_id = {int(player_id)} LIMIT 1
        ),
        -- percentile of realized_value among evaluable picks in the same pick range
        ranked AS (
            SELECT v.realized_value,
                   PERCENT_RANK() OVER (ORDER BY v.realized_value) AS pr
            FROM {idpv} v
            JOIN me ON v.is_evaluable
                   AND (CASE WHEN v.overall_pick<=10 THEN '1-10'
                             WHEN v.overall_pick<=31 THEN '11-31'
                             WHEN v.round=2 THEN 'R2' ELSE 'R3-7' END) =
                       (CASE WHEN me.overall_pick<=10 THEN '1-10'
                             WHEN me.overall_pick<=31 THEN '11-31'
                             WHEN me.round=2 THEN 'R2' ELSE 'R3-7' END)
        )
        SELECT me.overall_pick, me.draft_year, me.round, me.draft_team_abbrev,
               me.realized_pwar, me.realized_value, me.became_regular, me.is_censored,
               c.ev_mean_smooth AS expected_mean,
               me.realized_value - c.ev_mean_smooth AS value_above_slot,
               (SELECT MAX(pr) FROM ranked r WHERE r.realized_value <= me.realized_value) AS pct_within_range
        FROM me
        LEFT JOIN {curve} c ON c.overall_pick = me.overall_pick
    """
    rows = await run_in_threadpool(bq_service.query, sql)
    if not rows:
        return None
    r = rows[0]
    return DraftPlayerBlock(
        overall_pick=r["overall_pick"], draft_year=r["draft_year"], round=r["round"],
        draft_team_abbrev=r.get("draft_team_abbrev"),
        realized_pwar=float(r.get("realized_pwar") or 0.0),
        realized_value=float(r.get("realized_value") or 0.0),
        expected_mean=float(r.get("expected_mean") or 0.0),
        value_above_slot=float(r.get("value_above_slot") or 0.0),
        pct_within_range=float(r.get("pct_within_range") or 0.0),
        became_regular=bool(r.get("became_regular")),
        is_censored=bool(r.get("is_censored")),
    )
