"""Stage 4 — goals accounting and assembly of nhl_models.player_phase_value.

Converts rate coefficients to goals/60 via the league constants and V (deny_g60, suppress_g60,
pv_def_g60; escape published as a rate in v1), assembles one row per (player_id, season_window), and
generates artifacts/phase_value/overlap_report.md (component correlations + def_impact overlap + team
reconciliation). Composite sd from the shared bootstrap resamples, not quadrature.

STUB — implemented in Stage 4. See docs/methodology/phase-value.md §6.
"""
from __future__ import annotations


def main() -> None:
    raise NotImplementedError("phase_value Stage 4 — assemble_phase_value not yet implemented")


if __name__ == "__main__":
    main()
