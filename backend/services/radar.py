"""Service for the skills radar (Part B): reads nhl_models.player_radar / goalie_radar."""

from __future__ import annotations

import json
from typing import Optional

from services.bigquery import bq_service


# --- Scouting identity line (data-grounded, generated from the radar spokes) ----------------
# A one-line analyst read: lead with the player's defining strength(s) and a percentile, add a
# deployment read, and contrast with his clearest weakness. Every claim carries a real number, so
# it reads like a scouting note rather than a label. No em dashes.
_STRENGTH_NOUN = {
    "finishing": "finishing", "shot_volume": "shot volume", "shot_danger": "shot quality",
    "rush_offense": "rush offense", "cycle_forecheck": "forecheck and cycle game",
    "playmaking": "playmaking", "ev_off_impact": "even-strength impact",
    "pp_value": "power-play value", "burst": "skating", "ev_def_impact": "even-strength defense",
    "pk_role": "penalty-kill role", "def_deployment": "defensive deployment",
    "penalty_diff": "penalty differential", "physicality": "physical game",
}
# Weakness clauses (subject is the player); usage-only spokes are handled as deployment, not weakness.
_WEAKNESS_CLAUSE = {
    "finishing": "finishes below the league rate", "shot_volume": "rarely shoots",
    "shot_danger": "settles for low-danger looks", "rush_offense": "creates little off the rush",
    "cycle_forecheck": "does little below the goal line", "playmaking": "limited as a playmaker",
    "ev_off_impact": "drags even-strength play", "pp_value": "adds little on the power play",
    "burst": "lacks burst", "ev_def_impact": "bleeds chances at even strength",
    "penalty_diff": "takes more penalties than he draws",
    # physicality is a STYLE spoke, not a deficiency, so it is never framed as a weakness (it can
    # still surface as a strength via _STRENGTH_NOUN).
}


def _ord(p: float) -> str:
    n = int(round(p))
    suf = "th" if 10 <= n % 100 <= 20 else {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{suf}"


def _strength_adj(p: float) -> str:
    if p >= 93:
        return "Elite"
    if p >= 85:
        return "Strong"
    if p >= 78:
        return "High-end"
    if p >= 60:
        return "Solid"
    return "Middling"


def _identity_line(spokes: list) -> Optional[str]:
    """Build the data-grounded scouting sentence from the spoke percentiles (0-100)."""
    pct = {s["key"]: s["percentile"] for s in spokes
           if s.get("percentile") is not None and s.get("key") in _STRENGTH_NOUN}
    if not pct:
        return None
    ranked = sorted(pct.items(), key=lambda kv: -kv[1])
    strengths = [(k, p) for k, p in ranked if p >= 80][:2] or [ranked[0]]
    strength_keys = {k for k, _ in strengths}

    # Deployment read from the usage spokes (skip if defensive deployment is already a named strength).
    dep, pk = pct.get("def_deployment"), pct.get("pk_role")
    deploy_tail = None
    if "def_deployment" not in strength_keys and dep is not None and pk is not None:
        if dep >= 75 and pk >= 60:
            deploy_tail = "in heavy defensive minutes"
        elif dep <= 25 and pk <= 33:
            deploy_tail = "on sheltered minutes"

    # Weakness: the clearest low skill spoke (ev defense gets priority, it is the most telling).
    weak = None
    cand = sorted([(k, p) for k, p in pct.items()
                   if k in _WEAKNESS_CLAUSE and k not in strength_keys], key=lambda kv: kv[1])
    if cand and cand[0][1] <= 25:
        weak = cand[0]
    edi = pct.get("ev_def_impact")
    if edi is not None and edi <= 22 and "ev_def_impact" not in strength_keys:
        weak = ("ev_def_impact", edi)

    lead_k, lead_p = strengths[0]
    s = f"{_strength_adj(lead_p)} {_STRENGTH_NOUN[lead_k]} ({_ord(lead_p)})"
    if len(strengths) > 1:
        k2, p2 = strengths[1]
        s += f" and {_STRENGTH_NOUN[k2]} ({_ord(p2)})"
    if deploy_tail:
        s += f" {deploy_tail}"
    if weak:
        s += f", but {_WEAKNESS_CLAUSE[weak[0]]} ({_ord(weak[1])})"
    return s + "."


def _latest(table: str, id_col: str, entity_id: int) -> Optional[str]:
    rows = bq_service.query(
        f"SELECT MAX(season) AS s FROM {bq_service.get_models_table_id(table)} "
        f"WHERE {id_col} = {int(entity_id)}")
    return rows[0]["s"] if rows and rows[0]["s"] else None


def player_radar(player_id: int, season: Optional[str] = None) -> Optional[dict]:
    season = season or _latest("player_radar", "player_id", player_id)
    if not season:
        return None
    rows = bq_service.query(
        f"SELECT * FROM {bq_service.get_models_table_id('player_radar')} "
        f"WHERE player_id = {int(player_id)} AND season = '{season}'")
    if not rows:
        return None
    r = rows[0]
    spokes = json.loads(r["spokes"])
    return {
        "player_id": r["player_id"], "season": r["season"], "pos_group": r.get("pos_group"),
        "spokes": spokes,
        "overall_label": r.get("overall_label"), "offensive_label": r.get("offensive_label"),
        "defensive_label": r.get("defensive_label"), "descriptor": r.get("descriptor"),
        "identity_line": _identity_line(spokes),
        "baseline": r.get("baseline"),
    }


def goalie_radar(goalie_id: int, season: Optional[str] = None) -> Optional[dict]:
    season = season or _latest("goalie_radar", "goalie_id", goalie_id)
    if not season:
        return None
    rows = bq_service.query(
        f"SELECT * FROM {bq_service.get_models_table_id('goalie_radar')} "
        f"WHERE goalie_id = {int(goalie_id)} AND season = '{season}'")
    if not rows:
        return None
    r = rows[0]
    return {"goalie_id": r["goalie_id"], "season": r["season"],
            "games_played": r.get("games_played"), "spokes": json.loads(r["spokes"]),
            "baseline": r.get("baseline")}
