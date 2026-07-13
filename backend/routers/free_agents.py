"""Free-agent pool — remaining UFAs/RFAs. Powers the Home "Still available" rail (doc 19 §7) and the
Offseason Forecast best-fits section (doc 10 §4). One endpoint, two consumers.

Availability logic (per owner): the contract table documents each player's pending status (UFA/RFA)
and expiry year. This offseason's class = the soonest-expiring cohort (MIN(expiry_year)). A pending
UFA/RFA who is NOT on the updated active roster (`stg_roster_current`) hasn't re-signed → still
available. Ranked by projected value (war_now); Home takes the top N league-wide.

STATUS: projected WAR is served now. A projected AWARD {years, aav} needs the Contract Grader
hypothetical model output (TODO(model)); until then the row shows projected WAR (doc §7 fallback).
Per-team fit grades (Player Fit, for the Forecast consumer) are also pending (TODO(model)).
`?fixtures=true` returns review-only synthetic rows.
"""

from datetime import date

from fastapi import APIRouter, Query
from fastapi.concurrency import run_in_threadpool

from models.schemas import FreeAgentRow, ContractTerms
from services.bigquery import bq_service
from services.cache import cache

router = APIRouter()

_POS = {"L": "LW", "R": "RW", "C": "C", "D": "D", "G": "G"}


def _fixture_rows() -> list[FreeAgentRow]:
    """Review-only fixtures. Not served unless ?fixtures=true is passed."""
    return [
        FreeAgentRow(player_id=8478550, name="Mikko Rantanen", pos="RW", age=28, status="UFA",
                     projected_award=ContractTerms(years=8, aav=11_500_000), projected_war=3.1,
                     fits={"COL": "A", "CAR": "A-"}),
        FreeAgentRow(player_id=8477500, name="Dylan Larkin", pos="C", age=29, status="UFA",
                     projected_award=ContractTerms(years=6, aav=8_100_000), projected_war=2.4,
                     fits={"DET": "A-", "NYR": "B"}),
        FreeAgentRow(player_id=8471214, name="Alex Ovechkin", pos="LW", age=39, status="UFA",
                     projected_award=ContractTerms(years=1, aav=8_000_000), projected_war=1.9, fits={}),
    ]


def _real_free_agents(limit: int) -> list[FreeAgentRow]:
    """Top remaining UFAs/RFAs by WAR: pending FAs not on the updated roster.

    WAR is the SAME number the player page's Value block shows — `player_gar.war` at the latest
    single-season window — so the rail and the profile never disagree. Ranked by that WAR.
    """
    contracts = bq_service.get_full_table_id("mart_player_contracts")
    roster_current = bq_service.get_full_table_id("stg_roster_current")
    rosters = bq_service.get_full_table_id("stg_rosters")
    bio = bq_service.get_full_table_id("stg_player_bio")
    gar_t = bq_service.get_models_table_id("player_gar")
    assess = bq_service.get_models_table_id("player_assessment")

    # The latest single-season window (exclude multi-year blends that contain '_'); this is the
    # season the player board / profile default to, so the WAR matches exactly.
    season = bq_service.query(
        f"SELECT MAX(season_window) AS s FROM {gar_t} WHERE strpos(season_window, '_') = 0"
    )[0]["s"]
    base_year = int(season.split("-")[0]) + 1  # age as of the offseason following the season

    # WAR is the SAME number the Players board ranks + displays by (M3.5): the reliability-shrunk
    # `assessed_war` (± war_sd), falling back to raw `player_gar.war` when a player has no assessment
    # — NOT the raw single-season GAR/WAR. So the rail agrees with the board and the profile rating.
    #
    # Availability = played last season (has an assessment/WAR) but NOT on the updated active roster
    # (`stg_roster_current` = active roster OR under contract). That absence IS "still available", and
    # it catches unsigned veterans whose lapsed contract already dropped out of the contract snapshot.
    # Status is read from the contract table when present, else defaults to UFA (a cleared contract).
    rows = bq_service.query(f"""
        WITH avail AS (
            SELECT p.player_id, p.assessed_war, p.war_sd, g.war AS raw_war
            FROM {assess} p
            LEFT JOIN {gar_t} g ON g.player_id = p.player_id AND g.season_window = '{season}'
            WHERE p.season_window = '{season}'
              AND p.player_id NOT IN (SELECT player_id FROM {roster_current})
        ),
        nm AS (
            SELECT player_id, ARG_MAX(first_name, game_id) AS fn, ARG_MAX(last_name, game_id) AS ln,
                   ARG_MAX(position_code, game_id) AS pos
            FROM {rosters} GROUP BY player_id
        ),
        st AS (
            SELECT player_id,
                   CASE WHEN expiry_status LIKE 'UFA%' THEN 'UFA'
                        WHEN expiry_status LIKE 'RFA%' THEN 'RFA' END AS status
            FROM {contracts}
        )
        SELECT a.player_id, nm.fn || ' ' || nm.ln AS name, COALESCE(nm.pos, b.position) AS pos,
               COALESCE(st.status, 'UFA') AS status,
               {base_year} - EXTRACT(YEAR FROM CAST(b.birth_date AS DATE)) AS age,
               COALESCE(a.assessed_war, a.raw_war) AS war, a.war_sd
        FROM avail a
        LEFT JOIN nm USING(player_id)
        LEFT JOIN {bio} b USING(player_id)
        LEFT JOIN st USING(player_id)
        WHERE nm.fn IS NOT NULL AND COALESCE(a.assessed_war, a.raw_war) IS NOT NULL
        ORDER BY COALESCE(a.assessed_war, a.raw_war) DESC
        LIMIT {int(limit)}
    """)

    out: list[FreeAgentRow] = []
    for r in rows:
        age = r.get("age")
        out.append(FreeAgentRow(
            player_id=int(r["player_id"]),
            name=r.get("name") or "",
            pos=_POS.get(r.get("pos"), r.get("pos")),
            age=int(age) if age is not None else None,
            status=r.get("status"),
            projected_award=None,  # TODO(model): Contract Grader hypothetical award {years, aav}
            projected_war=round(float(r["war"]), 1) if r.get("war") is not None else None,
            war_sd=round(float(r["war_sd"]), 1) if r.get("war_sd") is not None else None,
            fits={},               # TODO(model): Player Fit per-team grades for the Forecast consumer
        ))
    return out


@router.get("", response_model=list[FreeAgentRow])
@router.get("/", response_model=list[FreeAgentRow])
@cache(ttl=1800)
async def list_free_agents(
    limit: int = Query(50, ge=1, le=200),
    fixtures: bool = Query(False, description="Review-only: return synthetic fixture rows"),
) -> list[FreeAgentRow]:
    """Remaining UFAs/RFAs, ranked by projected WAR. Pending FAs not yet on the updated roster."""
    if fixtures:
        return _fixture_rows()[:limit]
    return await run_in_threadpool(_real_free_agents, limit)
