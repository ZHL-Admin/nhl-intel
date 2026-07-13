"""Moves feed — the dated, global, newest-first roster-transactions source that powers the Home
Ledger (doc 19 §5) and the Offseason Forecast move ledger (doc 10). One source, two consumers.

Contract: verdicts are precomputed server-side, never client-side. Trades read the Trade Builder /
trade-outcome scoreboard (`trade_outcomes.net_war_slot` per team → edge + margin), so the Ledger's
"Edge DET" equals the Trade Builder tilt for the same trade (doc 13 acceptance).

STATUS:
- TRADES are live: assembled from `stg_trades` (date, teams, players) joined to `trade_outcomes`
  for the precomputed edge/margin. Newest first, paginated.
- SIGNINGS / EXTENSIONS are NOT yet served here: `mart_player_contracts` has the terms (aav,
  term_years) but no signing-event date and no served Contract Grader letter grade, so there is no
  honest way to date-order them or fill the verdict. TODO(dag): write a signing-event date + a
  precomputed grade in the nightly DAG, then merge signings into this feed (blank verdict until
  graded). Never grade a signing client-side.

`?fixtures=true` returns clearly-marked synthetic rows (incl. signings) for layout review only.
"""

from datetime import date, timedelta

from fastapi import APIRouter, Query
from fastapi.concurrency import run_in_threadpool

from models.schemas import MovesPage, MoveRow, MovePlayer, ContractTerms, MoveVerdict
from services.bigquery import bq_service
from services.cache import cache

router = APIRouter()

# Below this |Δ net_war_slot| the two sides are effectively even → no edge shown (blank verdict).
_EDGE_EPS = 0.05


def _fixture_rows() -> list[MoveRow]:
    """Review-only fixtures (trades + signings). Not served unless ?fixtures=true is passed."""
    today = date.today()
    d = lambda n: today - timedelta(days=n)  # noqa: E731
    return [
        MoveRow(id="fx-1", date=d(1), type="extension", teams=["OTT"],
                players=[MovePlayer(player_id=8482116, name="Tim Stützle", pos="C")],
                terms=ContractTerms(years=8, aav=8_350_000), verdict=MoveVerdict(grade="A-")),
        MoveRow(id="fx-2", date=d(1), type="trade", teams=["DET", "BUF"],
                players=[MovePlayer(player_id=8478406, name="JJ Peterka", pos="RW")],
                verdict=MoveVerdict(edge="DET", margin=1.4)),
        MoveRow(id="fx-3", date=d(2), type="signing", teams=["LAK"],
                players=[MovePlayer(player_id=8471685, name="Nikolaj Ehlers", pos="LW")],
                terms=ContractTerms(years=6, aav=7_000_000), verdict=MoveVerdict(grade="B+")),
        MoveRow(id="fx-8", date=d(7), type="signing", teams=["SEA"],
                players=[MovePlayer(player_id=8479580, name="Jake Walman", pos="D")],
                terms=ContractTerms(years=4, aav=5_500_000), verdict=None),
    ]


def _real_trades(limit: int, offset: int) -> MovesPage:
    """Recent trades, newest first, with the precomputed trade-outcome edge/margin verdict."""
    stg = bq_service.get_full_table_id("stg_trades")
    outcomes = bq_service.get_models_table_id("trade_outcomes")

    # Scope to the current offseason (the latest season present) so the Home ledger's rows and its
    # "All {n} moves this offseason" count reflect this summer, not all-time trade history.
    season_filter = f"trade_date IS NOT NULL AND season = (SELECT MAX(season) FROM {stg})"

    total = bq_service.query(
        f"SELECT COUNT(DISTINCT trade_id) AS n FROM {stg} WHERE {season_filter}"
    )[0]["n"]

    trades = bq_service.query(f"""
        WITH involved AS (
            SELECT trade_id, acquiring_team AS team, trade_date FROM {stg} WHERE {season_filter}
            UNION ALL
            SELECT trade_id, giving_team AS team, trade_date FROM {stg} WHERE {season_filter}
        ),
        tr AS (
            SELECT trade_id, MAX(trade_date) AS trade_date, LIST(DISTINCT team) AS teams
            FROM involved GROUP BY trade_id
        ),
        v AS (
            SELECT trade_id, ARG_MAX(team, net_war_slot) AS edge_team,
                   (MAX(net_war_slot) - MIN(net_war_slot)) AS margin
            FROM {outcomes} GROUP BY trade_id
        )
        SELECT tr.trade_id, tr.trade_date, tr.teams, v.edge_team, v.margin
        FROM tr LEFT JOIN v USING (trade_id)
        ORDER BY tr.trade_date DESC, tr.trade_id DESC
        LIMIT {int(limit)} OFFSET {int(offset)}
    """)

    ids = [t["trade_id"] for t in trades]
    players_by_trade: dict[str, list[MovePlayer]] = {}
    dest_by_trade: dict[str, str] = {}  # acquiring team of the headline (first) player → the "To" team
    if ids:
        idlist = ", ".join("'" + str(i).replace("'", "''") + "'" for i in ids)
        for r in bq_service.query(f"""
            SELECT trade_id, resolved_player_id, asset, position, acquiring_team
            FROM {stg}
            WHERE resolved_player_id IS NOT NULL AND trade_id IN ({idlist})
        """):
            bucket = players_by_trade.setdefault(r["trade_id"], [])
            if any(p.player_id == r["resolved_player_id"] for p in bucket):
                continue
            bucket.append(MovePlayer(player_id=int(r["resolved_player_id"]),
                                     name=r.get("asset") or "", pos=r.get("position")))
            dest_by_trade.setdefault(r["trade_id"], r.get("acquiring_team"))

    items: list[MoveRow] = []
    for t in trades:
        margin = t.get("margin")
        edge = t.get("edge_team")
        verdict = (MoveVerdict(edge=edge, margin=round(float(margin), 1))
                   if edge and margin is not None and abs(float(margin)) >= _EDGE_EPS else None)
        # Order teams so the headline player's destination is first (the ledger's "To"); the edge
        # winner lives separately in the verdict.
        teams = list(t.get("teams") or [])
        dest = dest_by_trade.get(t["trade_id"])
        if dest and dest in teams:
            teams = [dest] + [x for x in teams if x != dest]
        items.append(MoveRow(
            id=t["trade_id"], date=t["trade_date"], type="trade",
            teams=teams, players=players_by_trade.get(t["trade_id"], []),
            terms=None, verdict=verdict,
        ))
    return MovesPage(items=items, total=int(total))


@router.get("", response_model=MovesPage)
@router.get("/", response_model=MovesPage)
@cache(ttl=1800)
async def list_moves(
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    fixtures: bool = Query(False, description="Review-only: return synthetic fixture rows"),
) -> MovesPage:
    """Global roster moves, newest first, paginated. Trades are live; signings pending the DAG."""
    if fixtures:
        rows = _fixture_rows()
        return MovesPage(items=rows[offset:offset + limit], total=len(rows))
    return await run_in_threadpool(_real_trades, limit, offset)
