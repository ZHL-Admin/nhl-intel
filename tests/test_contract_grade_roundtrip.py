"""Hermetic round-trip test for the contract-grade valuation curve (no BigQuery/DuckDB required).

The grade pipeline values a player as a cap SHARE (max of intrinsic and caliber-market), then:
  Step 3 — INVERTS that share to an "effective WAR"  (inverse_market_share)
  Step 6 — REPRICES that effective WAR back to a share (market_cap_share), per projected year.
If those two steps use the IDENTICAL log-linear curve, the year-0 reprice must reproduce the input
share exactly. Any non-zero error in the linear regime would be silent drift baked into every grade
(e.g. invert and reprice fitted on different params). This test pins that invariant with synthetic
curve params, so it runs anywhere and fails loudly if the two functions ever diverge.

The market curve has a smooth soft-cap ABOVE the knee (asymptote to the CBA-max share); there the
reprice is intentionally COMPRESSING, not an inverse. That is a documented modeling choice, not drift,
so it is asserted as monotone-compressing rather than exact.
"""
import sys
from pathlib import Path

REPO = Path(__file__).parent.parent
sys.path.insert(0, str(REPO))

import numpy as np                                          # noqa: E402
import pytest                                               # noqa: E402

from models_ml.compute_contract_value import (              # noqa: E402
    market_cap_share, inverse_market_share, value_effective_war)

# Synthetic per-position market curve: log(share) = a + b*WAR + shift, soft-capped above the knee.
# Param values are arbitrary — the round-trip is exact for ANY shared params below the knee.
_A, _B, _SHIFT = -3.2, 0.33, 0.20
_CEIL, _KNEE = 0.187, 0.140
MARKET = {
    "fits": {"F": (_A, _B, _SHIFT), "D": (_A, _B, _SHIFT), "G": (_A, _B, _SHIFT)},
    "ceil": _CEIL, "knee": _KNEE,
    "top_war": {"F": 99.0, "D": 99.0, "G": 99.0},
}
# caliber market with no fits -> caliber_market_share returns None, so value = intrinsic (the floor
# never fires). This isolates the invert<->reprice round trip on the market curve alone.
CM_EMPTY = {"fits": {}, "caps": {}, "caliber_of": lambda *a: 0.5}

TOL = 1e-12


@pytest.mark.parametrize("pg", ["F", "D"])
def test_invert_reprice_is_exact_below_knee(pg):
    """market_cap_share(inverse_market_share(s)) == s for every share below the knee."""
    for s in np.linspace(0.01, _KNEE * 0.98, 12):
        war = inverse_market_share(MARKET, pg, float(s))
        back = market_cap_share(MARKET, pg, war)
        assert abs(back - s) < TOL, f"{pg}: round-trip drift at share={s:.4f} -> {back:.6f}"


@pytest.mark.parametrize("pg", ["F", "D"])
def test_soft_cap_compresses_above_knee(pg):
    """Above the knee the reprice is the intended soft-cap: strictly below the raw share, never above
    the ceiling. (Compression, not an exact inverse — documented, not drift.)"""
    for s in np.linspace(_KNEE * 1.02, _CEIL * 0.99, 6):
        war = inverse_market_share(MARKET, pg, float(s))
        back = market_cap_share(MARKET, pg, war)
        assert back < s + TOL, f"{pg}: soft-cap should compress at share={s:.4f}, got {back:.6f}"
        assert back <= _CEIL + TOL, f"{pg}: reprice {back:.6f} exceeds ceil {_CEIL}"


@pytest.mark.parametrize("pg", ["F", "D"])
def test_value_effective_war_year0_reprices_to_input_value(pg):
    """The shared chain grade_contract uses for term=1: value share -> effective WAR -> year-0 share.
    For any WAR whose intrinsic value sits in the linear regime, repricing the effective WAR must
    reproduce the intrinsic value share exactly (this is the term=1 'graded value == value_share*cap'
    invariant, in cap-share units, cap-independent)."""
    for blended_war in np.linspace(-1.0, 3.0, 13):
        intrinsic = market_cap_share(MARKET, pg, float(blended_war))
        if intrinsic >= _KNEE:                              # stay in the exact (linear) regime
            continue
        eff = value_effective_war(MARKET, CM_EMPTY, pg, float(blended_war), None)
        reprice = market_cap_share(MARKET, pg, eff)
        assert abs(reprice - intrinsic) < TOL, (
            f"{pg}: term-1 round-trip drift at WAR={blended_war:.2f}: "
            f"value_share={intrinsic:.6f} repriced to {reprice:.6f}")


def test_goalies_pass_through_intrinsic_war():
    """Goalies are exempt from the caliber floor: value_effective_war returns the blended WAR itself,
    so repricing it yields the intrinsic share (round-trips by construction)."""
    for blended_war in (-0.5, 0.5, 1.5, 2.5):
        eff = value_effective_war(MARKET, CM_EMPTY, "G", blended_war, None)
        assert eff == blended_war
        if market_cap_share(MARKET, "G", blended_war) < _KNEE:
            assert abs(market_cap_share(MARKET, "G", eff)
                       - market_cap_share(MARKET, "G", blended_war)) < TOL
