"""
Divergence-board explanation templates (Phase 4.3, blueprint 4.4).

Deterministic, data-driven sentences explaining why a player's coach-trust deployment diverges
from his isolated value (composite). No LLM. Reused by the Phase 6 insight engine.

A divergence row carries: the signed divergence (trust z - composite z), the dominant
coach-trust signal, the player's strongest and weakest composite components, and the composite
total. The explanation references numbers present in the row (consistency rule).
"""

from __future__ import annotations

# dominant trust signal -> deployment role phrase
TRUST_ROLE = {
    "pk_share": "a penalty-kill regular",
    "protect_lead_rate": "a lead-protection option late in games",
    "road_home_ratio": "matchup-proof minutes on the road",
}

# composite component key -> readable phrase
COMPONENT_PHRASE = {
    "ev_offense": "even-strength offense",
    "ev_defense": "even-strength defense",
    "pp": "the power play",
    "pk": "penalty killing",
    "finishing": "finishing",
    "penalty_diff": "penalty discipline",
    "goalie_gsax": "goaltending",
}


def tier(z: float) -> str:
    if z >= 1.0:
        return "elite"
    if z >= 0.3:
        return "above average"
    if z <= -1.0:
        return "well below average"
    if z <= -0.3:
        return "below average"
    return "average"


def explain(*, divergence: float, dominant_trust: str, top_component: str,
            bottom_component: str, composite_total: float, composite_z: float) -> str:
    """Return a one-sentence explanation for a divergence-board row."""
    role = TRUST_ROLE.get(dominant_trust, "a trusted deployment role")
    strong = COMPONENT_PHRASE.get(top_component, top_component)
    weak = COMPONENT_PHRASE.get(bottom_component, bottom_component)
    if divergence > 0:
        # coaches trust him more than his isolated value
        return (f"Coaches deploy him as {role}, but his isolated value is {tier(composite_z)} "
                f"({composite_total:+.1f} goals) — the eye test may be crediting usage that his "
                f"{weak} doesn't back up; his clearest strength is {strong}.")
    # numbers exceed the trust the coach shows
    return (f"His {strong} grades {tier(composite_z)} ({composite_total:+.1f} goals), yet he is "
            f"used cautiously rather than as {role} — a player whose value outruns his "
            f"deployment.")


# ── Deployment efficiency board (the Divergence Board rework) ────────────────────────────────
# Each row compares ACTUAL situational usage against the usage the player's situation-appropriate
# VALUE justifies. The sentence names the situation and the value type (consistency rule).
SITUATION_PHRASE = {
    "all": "ice time", "5v5": "5v5 ice time", "pp": "power-play time",
    "pk": "penalty-kill time", "key_moments": "high-leverage ice time",
}


def _ordinal(n: int) -> str:
    s = ["th", "st", "nd", "rd"]
    v = n % 100
    return f"{n}{(s[(v - 20) % 10] if 0 <= (v - 20) % 10 <= 3 else s[0]) if not (10 <= v <= 13) else s[0]}"


def _usage_band(pctile: float) -> str:
    """A plain-language band for a usage percentile (e.g. 'the top 5%', 'the bottom third')."""
    top = 1.0 - pctile
    if top <= 0.10:
        return f"the top {max(1, round(top * 100))}%"
    if pctile >= 0.66:
        return "an upper-rotation share"
    if pctile >= 0.40:
        return "a middle-rotation share"
    if pctile >= 0.20:
        return "a bottom-rotation share"
    return f"the bottom {max(1, round(pctile * 100))}%"


def deployment_explain(*, side: str, situation: str, value_label: str, value_rank: int,
                       n_pool: int, actual_pctile: float, position: str) -> str:
    """One deterministic sentence for a deployment-efficiency row (over/under-used)."""
    where = SITUATION_PHRASE.get(situation, "ice time")
    band = _usage_band(actual_pctile)
    pos_noun = "defensemen" if position == "D" else "forwards"
    if side == "over":
        return (f"Gets {band} of the team's {where}, but his {value_label} ranks "
                f"{_ordinal(value_rank)} of {n_pool} {pos_noun} — deployed beyond what his impact warrants.")
    return (f"His {value_label} ranks {_ordinal(value_rank)} of {n_pool} {pos_noun}, yet he gets only "
            f"{band} of the team's {where} — value the bench leaves unused.")
