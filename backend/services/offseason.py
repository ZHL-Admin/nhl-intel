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


def _slot_num(slot: str) -> int:
    """Numeric part of a slot label (F7 -> 7). 0 if unparseable."""
    try:
        return int(slot[1:])
    except (ValueError, TypeError):
        return 0


def _lineup_extras(player_ids: list[int], base_season: str) -> dict:
    """player_id -> {age, gp, g, a, p} for the base season, from the SAME serving tables the team-roster
    endpoint uses (mart_player_game_stats for the counting line, stg_player_bio for age). Last-season
    REALIZED totals only — the engine projects WAR, never a projected counting line, so no G/A/P is ever
    fabricated forward (a projected-points-per-player model would be a separate, out-of-scope build)."""
    if not player_ids:
        return {}
    idlist = ", ".join(str(int(i)) for i in player_ids)
    base_year = int(base_season[:4])
    pgs = bq_service.get_full_table_id("mart_player_game_stats")
    bio = bq_service.get_full_table_id("stg_player_bio")
    out: dict = {}
    # Regular-season counting line (game_id type '02'), aggregated across teams (a mid-season trade's
    # totals still belong to the player), so the lineup shows his real last-season production.
    for r in bq_service.query(
            f"SELECT player_id, COUNT(DISTINCT game_id) AS gp, "
            f"SUM(individual_goals) AS g, SUM(first_assists + second_assists) AS a "
            f"FROM {pgs} WHERE season = '{base_season}' AND player_id IN ({idlist}) "
            f"AND SUBSTR(CAST(game_id AS STRING), 5, 2) = '02' GROUP BY player_id"):
        g = int(r["g"] or 0); a = int(r["a"] or 0)
        out[int(r["player_id"])] = {"gp": int(r["gp"] or 0), "g": g, "a": a, "p": g + a}
    for r in bq_service.query(
            f"SELECT player_id, {base_year} - EXTRACT(YEAR FROM CAST(birth_date AS DATE)) AS age "
            f"FROM {bio} WHERE player_id IN ({idlist}) AND birth_date IS NOT NULL"):
        out.setdefault(int(r["player_id"]), {})["age"] = int(r["age"]) if r.get("age") is not None else None
    return out


def _line_fits(lineup: list[dict]) -> dict:
    """Per-line fit grades for the projected lineup, from the SAME cold-start line-fit path the Roster
    Builder uses (services.tools._line_grade over line_member_features). Now that the offseason lineups
    are DEPLOYMENT-SEEDED (real observed 5v5 units, not value-ranked filler), the top lines are real, so
    the grade is meaningful — the 'arrangement illustrative' caveat is retired. Forward slots group into
    trios by slot number (F1-3 = line 1 ...), defense into pairs (D1-2 = pair 1 ...). Returns
    {'forward': [fit|null x4], 'defense': [fit|null x3]} where fit = {grade, xgf_pct} or null."""
    try:
        from services.tools import _line_grade
    except Exception:  # noqa: BLE001 — grading unavailable -> no grades (never a fabricated one)
        return {"forward": [], "defense": []}
    fwd = {_slot_num(s["slot"]): s for s in lineup if str(s.get("slot", "")).startswith("F")}
    dfn = {_slot_num(s["slot"]): s for s in lineup if str(s.get("slot", "")).startswith("D")}

    def grade(nums: list[int], src: dict):
        ids = [src[n]["player_id"] for n in nums if src.get(n) and src[n].get("player_id")]
        if len(ids) != len(nums):
            return None
        try:
            return _line_grade(ids)
        except Exception:  # noqa: BLE001
            return None

    forward = [grade([3 * k + 1, 3 * k + 2, 3 * k + 3], fwd) for k in range(4)]
    defense = [grade([2 * k + 1, 2 * k + 2], dfn) for k in range(3)]
    return {"forward": forward, "defense": defense}


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
    base_season = str(f.get("transition", "")).split("->")[0]   # e.g. "2025-26->2026-27" -> "2025-26"
    extras = _lineup_extras([int(m["player_id"]) for m in lineup if m.get("player_id")], base_season)
    projected_lineup = []
    for m in lineup:
        e = extras.get(int(m["player_id"])) if m.get("player_id") else None
        projected_lineup.append({
            "slot": m["updated_slot"], "player_id": m.get("player_id"), "name": m.get("name"),
            "position": m.get("position"), "projected_war": m.get("projected_war", 0.0),
            "war_sd": m.get("war_sd", 0.0), "no_track_record": bool(m.get("no_track_record")),
            "replacement": False,
            # Additive context (last-season realized; never a projected counting line — see _lineup_extras).
            "base_war": m.get("base_war"),
            "age": (e or {}).get("age"), "gp": (e or {}).get("gp"),
            "g": (e or {}).get("g"), "a": (e or {}).get("a"), "p": (e or {}).get("p"),
        })

    base_components = {k: f.get(f"base_{k}") for k in
                       ("play_5v5", "finishing", "goaltending", "special_teams")}
    # The ledger shown to the UI excludes the bookkeeping replacement_fill row (no player).
    ledger = [m for m in moves if m.get("move_type") != "replacement_fill"]

    return {
        "forecast": f,
        "base_components": base_components,
        "moves": ledger,
        "projected_lineup": projected_lineup,
        "line_fits": _line_fits(projected_lineup),
        "style_note": f.get("style_note") or None,
        "verdict": expl["verdict"],
        "reasons": expl["reasons"],
        "limitations": expl["limitations"],
    }
