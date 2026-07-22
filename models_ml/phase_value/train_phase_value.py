"""Stage 3 — the three phase-value fits (deny / suppress / escape) + the rush sub-fit.

Reuses the RAPM estimation stack identically (two-sided player-indicator design, the same controls,
sparse Ridge, the imported train_rapm.ALPHAS grid, game-grouped 80/20 alpha CV, per-side centering,
defense sign-flip at publication, game-resample bootstrap) with new dense targets/exposures from
build_design.py. Windows mirror RAPM (3-season 1.0/0.6/0.3 headline + single seasons 2021-22 on).

STUB — implemented in Stage 3. See docs/methodology/phase-value.md §5 and DECISIONS PV-D003 (ALPHAS reuse).
"""
from __future__ import annotations


def main() -> None:
    raise NotImplementedError("phase_value Stage 3 — train_phase_value not yet implemented")


if __name__ == "__main__":
    main()
