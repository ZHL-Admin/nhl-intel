"""Service for the offseason roster-forecast tool.

Reads nhl_models.roster_forecast + roster_moves through the serving layer (bq_service routes to the
DuckDB serving file or BigQuery) and assembles the league board + per-team decomposition. The
verdict + reasons come from insight_engine.templates.roster_forecast (deterministic, every sentence
references a payload number). Reads only; writes nothing.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from services.bigquery import bq_service


def _abbrev_map() -> dict:
    rows = bq_service.query(
        f"SELECT DISTINCT team_id, team_abbrev FROM "
        f"{bq_service.get_full_table_id('mart_team_game_stats')} WHERE team_abbrev IS NOT NULL")
    return {int(r["team_id"]): r["team_abbrev"] for r in rows}


def _slot_key(slot: str) -> tuple:
    order = {"F": 0, "D": 1, "G": 2}
    if not slot:
        return (9, 99)
    return (order.get(slot[0], 9), int(slot[1:] or 0))


def offseason_board(season: Optional[str] = None) -> list[dict]:
    """Every team's projected rating, delta, rank and band — the league board (depth 1)."""
    fc = bq_service.get_models_table_id("roster_forecast")
    rows = bq_service.query(f"SELECT * FROM {fc} ORDER BY projected_rank")
    abbr = _abbrev_map()
    out = []
    for r in rows:
        d = dict(r)
        d["team_abbrev"] = abbr.get(int(r["team_id"]))
        out.append(d)
    return out


def offseason_team(team_id: int, season: Optional[str] = None) -> dict:
    """One team's full decomposition: forecast + components, move ledger, projected lineup, verdict."""
    fc = bq_service.get_models_table_id("roster_forecast")
    mv = bq_service.get_models_table_id("roster_moves")
    frows = bq_service.query(f"SELECT * FROM {fc} WHERE team_id = {int(team_id)} LIMIT 1")
    if not frows:
        raise ValueError(f"no roster forecast for team {team_id}")
    f = dict(frows[0])
    f["team_abbrev"] = _abbrev_map().get(int(team_id))

    moves = [dict(m) for m in bq_service.query(f"SELECT * FROM {mv} WHERE team_id = {int(team_id)}")]

    from insight_engine.templates import roster_forecast as tmpl
    expl = tmpl.explain(f, moves)

    # Projected lineup = the move rows that hold an updated slot (the filled lineup), slot-ordered.
    lineup = sorted([m for m in moves if m.get("updated_slot")],
                    key=lambda m: _slot_key(m["updated_slot"]))
    projected_lineup = [{
        "slot": m["updated_slot"], "player_id": m.get("player_id"), "name": m.get("name"),
        "position": m.get("position"), "projected_war": m.get("projected_war", 0.0),
        "war_sd": m.get("war_sd", 0.0), "no_track_record": bool(m.get("no_track_record")),
        "replacement": False,
    } for m in lineup]

    base_components = {k: f.get(f"base_{k}") for k in
                       ("play_5v5", "finishing", "goaltending", "special_teams")}
    # The ledger shown to the UI excludes the bookkeeping replacement_fill row (no player).
    ledger = [m for m in moves if m.get("move_type") != "replacement_fill"]

    return {
        "forecast": f,
        "base_components": base_components,
        "moves": ledger,
        "projected_lineup": projected_lineup,
        "style_note": f.get("style_note") or None,
        "verdict": expl["verdict"],
        "reasons": expl["reasons"],
        "limitations": expl["limitations"],
    }
