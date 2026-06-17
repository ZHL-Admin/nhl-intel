"""
Trade/free-agency fit explanation templates (Phase 5.3, blueprint 6.4).

Deterministic, data-driven reasons for how well a player addresses a team's needs. No LLM. The
scorer (models_ml/score_team_fit.py) passes the player's archetype mix + composite components and
the team's archetype/component gaps; this builds 2-3 sentences that each reference a number in the
payload (consistency rule). Reused by the Phase 6 insight engine.
"""

from __future__ import annotations

COMPONENT_PHRASE = {
    "ev_offense": "even-strength offense", "ev_defense": "even-strength defense",
    "pp": "power-play offense", "pk": "penalty killing", "finishing": "finishing",
}

# a team "needs" an archetype when its mix trails the top teams by at least this (mix-share units)
ARCH_NEED_THRESHOLD = 0.01


def reasons(*, player_primary_arch: str | None, player_arch_weight: float,
            team_arch_needs: dict[str, float], player_top_component: str,
            player_top_component_value: float, team_component_needs: dict[str, float]) -> list[str]:
    out: list[str] = []

    # 1) archetype fit: does the player's primary role fill a gap?
    if player_primary_arch:
        gap = team_arch_needs.get(player_primary_arch, 0.0)
        if gap >= ARCH_NEED_THRESHOLD:
            out.append(f"He profiles as a {player_primary_arch} "
                       f"({player_arch_weight * 100:.0f}% of his mix), a role they lack relative "
                       f"to the top teams.")
        else:
            out.append(f"They already have {player_primary_arch} depth, so he does not add a "
                       f"missing role.")

    # 2) component fit: does the player's strongest value address a component gap?
    comp_phrase = COMPONENT_PHRASE.get(player_top_component, player_top_component)
    if team_component_needs.get(player_top_component, 0.0) > 0:
        out.append(f"His {comp_phrase} ({player_top_component_value:+.1f} goals) addresses their "
                   f"{comp_phrase} gap.")

    # 3) the biggest unaddressed need
    if team_component_needs:
        biggest = max(team_component_needs, key=team_component_needs.get)
        if team_component_needs[biggest] > 0 and biggest != player_top_component:
            out.append(f"He does not address their largest need, "
                       f"{COMPONENT_PHRASE.get(biggest, biggest)} "
                       f"({team_component_needs[biggest]:+.1f} goals behind the top teams).")

    return out[:3]
