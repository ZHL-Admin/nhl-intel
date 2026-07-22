"""Stage 3 — stint-level directional design dataset for the phase-value fits.

Starts from the exact RAPM stint universe (int_segment_context + int_shift_segments), emits two
directional rows per stint, and adds the PV exposures/targets by intersecting stints with spells and
episodes: outside_exposure_sec, inzone_sec, episode_starts_nonfo, episode_starts_rush, xg_inzone,
favorable_ends. Consumed by train_phase_value.py.

STUB — implemented in Stage 3. See docs/methodology/phase-value.md §5.
"""
from __future__ import annotations


def main() -> None:
    raise NotImplementedError("phase_value Stage 3 — build_design not yet implemented")


if __name__ == "__main__":
    main()
