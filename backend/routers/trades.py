"""Trade-outcome retrospective endpoints (Handoff 5, Phase D).

Reads nhl_models.trade_outcomes (one row per trade+team, both valuation lenses with bands + JSON asset
ledgers) via bq_service (DuckDB serving). A RETROSPECTIVE on realized outcomes — never a grade of the
decision at the time. One-segment routes are declared before the parameterized /{trade_id} route.
"""

import json
from typing import List, Optional

from fastapi import APIRouter, HTTPException, Query
from fastapi.concurrency import run_in_threadpool

from models.schemas import (
    TradeOutcomeRow, TradeLedgerEntry, TradeDetail, TradeDetailTeam, TeamTradeLedger,
)
from services.bigquery import bq_service
from services.cache import cache

router = APIRouter()

CAVEAT = ("A retrospective on realized outcomes, not a grade of the decision at the time the trade was "
          "made — the information available then (injuries, development, cap context) was different. "
          "Pick value uses the slot's empirical expectation (headline) or the player it became "
          "(secondary, which conflates the trade with the drafting). Values are wide-band estimates in WAR.")

_ROW_COLS = [
    "trade_id", "season", "trade_date", "team", "team_count",
    "net_war_slot", "net_war_slot_low", "net_war_slot_high",
    "net_war_actual", "net_war_actual_low", "net_war_actual_high",
    "received_count", "sent_count", "has_pick", "has_unresolved",
    "actual_censored", "horizon_incomplete", "confidence",
]


def _row(r: dict) -> TradeOutcomeRow:
    d = {k: r.get(k) for k in _ROW_COLS}
    d["trade_date"] = str(d["trade_date"])
    return TradeOutcomeRow(**d)


def _abbrev_for_team(team_id: int) -> Optional[str]:
    rows = bq_service.query(
        f"SELECT ANY_VALUE(team_abbrev) AS a FROM {bq_service.get_full_table_id('mart_team_game_stats')} "
        f"WHERE team_id = {int(team_id)}")
    return rows[0]["a"] if rows and rows[0].get("a") else None


# ------------------------------------------------------------------------- board (one-segment)
@router.get("/outcomes", response_model=List[TradeOutcomeRow])
@cache(ttl=3600)
async def outcomes(
    lens: str = Query("slot", pattern="^(slot|actual)$"),
    order: str = Query("winners", pattern="^(winners|losers)$"),
    team: Optional[str] = Query(None, description="Filter to a team abbrev"),
    season: Optional[str] = Query(None, description="Filter to a season (YYYY-YY)"),
    include_incomplete: bool = Query(False, description="Include trades whose realized window is unfinished"),
    limit: int = Query(40, ge=1, le=200),
) -> List[TradeOutcomeRow]:
    """The who-won board: (trade, team) rows ranked by net realized WAR under the chosen lens.

    Defaults exclude trades whose realized window is unfinished (recent deals), so the headline board
    is not dominated by deals with no observed outcomes yet."""
    col = "net_war_slot" if lens == "slot" else "net_war_actual"
    direction = "DESC" if order == "winners" else "ASC"
    where = ["1=1"]
    if team:
        where.append(f"team = '{team.replace(chr(39), '')}'")
    if season:
        where.append(f"season = '{season.replace(chr(39), '')}'")
    if not include_incomplete:
        where.append("NOT horizon_incomplete")
    sql = f"""
        SELECT {', '.join(_ROW_COLS)}
        FROM {bq_service.get_models_table_id('trade_outcomes')}
        WHERE {' AND '.join(where)}
        ORDER BY {col} {direction}
        LIMIT {limit}
    """
    rows = await run_in_threadpool(bq_service.query, sql)
    return [_row(r) for r in rows]


# ------------------------------------------------------------------------- team ledger (one-segment)
@router.get("/team/{team_id}/ledger", response_model=TeamTradeLedger)
@cache(ttl=3600)
async def team_ledger(team_id: int) -> TeamTradeLedger:
    """A team's trades, netted, newest first (the team's running trade record in WAR)."""
    abbrev = await run_in_threadpool(_abbrev_for_team, team_id)
    if not abbrev:
        raise HTTPException(404, f"unknown team_id {team_id}")
    sql = f"""
        SELECT {', '.join(_ROW_COLS)}
        FROM {bq_service.get_models_table_id('trade_outcomes')}
        WHERE team = '{abbrev}'
        ORDER BY trade_date DESC
    """
    rows = await run_in_threadpool(bq_service.query, sql)
    trades = [_row(r) for r in rows]
    return TeamTradeLedger(
        team_id=team_id, team_abbrev=abbrev, n_trades=len(trades),
        total_net_slot=round(sum(t.net_war_slot for t in trades), 1),
        total_net_actual=round(sum(t.net_war_actual for t in trades), 1),
        trades=trades, caveat=CAVEAT,
    )


# ------------------------------------------------------------------------- who-won detail
# trade_id is a string key (e.g. "2016-06-29-NJD-EDM"); served under /detail/ so it never collides
# with the one-segment /outcomes and /team routes.
@router.get("/detail/{trade_id}", response_model=TradeDetail)
@cache(ttl=3600)
async def trade_detail_str(trade_id: str) -> TradeDetail:
    """Both/all teams' netted outcomes for one trade, with the full received/sent asset ledgers."""
    tid = trade_id.replace("'", "")
    sql = f"""
        SELECT {', '.join(_ROW_COLS)}, received_ledger, sent_ledger
        FROM {bq_service.get_models_table_id('trade_outcomes')}
        WHERE trade_id = '{tid}'
        ORDER BY net_war_slot DESC
    """
    rows = await run_in_threadpool(bq_service.query, sql)
    if not rows:
        raise HTTPException(404, f"unknown trade_id {trade_id}")

    def _entries(raw) -> List[TradeLedgerEntry]:
        items = json.loads(raw) if raw else []
        return [TradeLedgerEntry(**{k: e.get(k) for k in TradeLedgerEntry.model_fields}) for e in items]

    teams = []
    for r in rows:
        base = _row(r).model_dump()
        teams.append(TradeDetailTeam(**base,
                                     received=_entries(r.get("received_ledger")),
                                     sent=_entries(r.get("sent_ledger"))))
    first = rows[0]
    return TradeDetail(trade_id=tid, season=first["season"], trade_date=str(first["trade_date"]),
                       teams=teams, caveat=CAVEAT)
