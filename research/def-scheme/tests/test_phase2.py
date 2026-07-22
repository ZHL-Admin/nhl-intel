"""Phase 2 tests. Artifact-dependent tests skip when keystone pairs are not built."""
from __future__ import annotations
import polars as pl, pytest
from defscheme import config as C, keystone as K

FAULT_WORDS = ["out of position", "blame", "fault", "mistake", "responsible"]


def test_verdict_logic_is_pre_stated():
    # PASS requires a positive CI-clean gradient AND high-continuity persistence >= 0.40
    def passes(slope, ci_lo, persist_high):
        return slope > 0 and ci_lo > 0 and persist_high >= 0.40
    assert passes(0.5, 0.1, 0.5)
    assert not passes(0.01, -0.56, 0.16)      # the observed keystone result -> FAIL
    assert not passes(0.5, 0.1, 0.30)         # persistence below bar -> FAIL
    assert not passes(0.5, -0.1, 0.5)         # CI spans 0 -> FAIL


@pytest.mark.skipif(not K.PAIRS.exists(), reason="keystone pairs not built")
def test_pairs_structure_and_universe():
    p = pl.read_parquet(K.PAIRS)
    for c in ["roster_continuity", "coach_continuity", "persist_coarse", "persist_fine"]:
        assert c in p.columns
    assert p.height >= 40                       # ~62 consecutive-season pairs
    assert 0.0 <= p["roster_continuity"].drop_nulls().min() and p["roster_continuity"].drop_nulls().max() <= 1.0
    assert not set(p["team_id"].unique()) & set(K.__dict__.get("EXHIBITION", []) or [7801, 7802, 7803, 7804, 7805, 7806])


@pytest.mark.skipif(not (C.REPORTS / "phase2.md").exists(), reason="report not written")
def test_no_fault_language_phase2():
    txt = (C.REPORTS / "phase2.md").read_text().lower()
    for w in FAULT_WORDS:
        assert txt.count(w) <= C.LAW_2.lower().count(w), f"fault word '{w}' used beyond the Law-2 quote"
