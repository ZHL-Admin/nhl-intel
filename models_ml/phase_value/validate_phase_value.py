"""Stage 5 — pre-registered validation; generates docs/phase-value/validation-report.md.

Computes the pre-registered reliability tiers (A/B/C on year-over-year r), split-half reliability, the
team out-of-sample test, smell tests, the discrimination check, and the sanctioned sensitivity grid —
each against criteria fixed in the spec BEFORE results are known. Writes the earned tiers into
player_phase_value and the methodology doc. Nothing in Stages 1-4 is re-tuned in response to results
except through the declared sensitivity grid.

STUB — implemented in Stage 5. See docs/methodology/phase-value.md §7.
"""
from __future__ import annotations


def main() -> None:
    raise NotImplementedError("phase_value Stage 5 — validate_phase_value not yet implemented")


if __name__ == "__main__":
    main()
