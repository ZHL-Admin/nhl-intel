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
