"""Stage 2 — the state value function V(state) and league accounting constants.

Reads int_phase_ticks (+ episodes) and writes nhl_models.state_values and
nhl_models.phase_league_constants over the primary scope (PHASE_VALUE_CONFIG['PRIMARY_SCOPE_START']
onward). V(state) = tick-duration-weighted mean net goals in (t, t+H] within the same period.
Hard gate: V(P_OZ_EST) > V(P_NZ) > V(P_OWN_D).

STUB — implemented in Stage 2. See docs/methodology/phase-value.md §4.
"""
from __future__ import annotations


def main() -> None:
    raise NotImplementedError("phase_value Stage 2 — compute_state_values not yet implemented")


if __name__ == "__main__":
    main()
