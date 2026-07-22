"""Phase 1 tests. Artifact-dependent tests skip when signatures are not built."""
from __future__ import annotations
import polars as pl, pytest
from defscheme import config as C, scheme_norm as SN

FAULT_WORDS = ["out of position", "blame", "fault", "mistake", "responsible"]


def _built():
    return SN.SIGNATURES.exists() and SN.COUNTS.exists()


@pytest.mark.skipif(not _built(), reason="signatures not built")
def test_signature_deviation_and_gate():
    sig = pl.read_parquet(SN.SIGNATURES)
    # deviation + z-score columns exist; deviations are league-centered (~0 mean per situation)
    for f in SN.FEATURES:
        assert f"dev_{f}" in sig.columns and f"z_{f}" in sig.columns
    dz = sig.filter(pl.col("grid") == "coarse").group_by("situation").agg(m=pl.col("dev_depth").mean())
    assert dz["m"].abs().max() < 1.0                       # league-centered
    # min-sample gate is exactly n_goals>=15
    assert (sig["cell_ok"] == (sig["n_goals"] >= SN.MIN_CELL_GOALS)).all()


@pytest.mark.skipif(not _built(), reason="signatures not built")
def test_situation_grid_and_counts():
    counts = pl.read_parquet(SN.COUNTS)
    assert set(counts.filter(pl.col("grid") == "coarse")["situation"].unique()) == {"dzone_high", "dzone_low", "neutral", "ozone"}
    assert counts.filter(pl.col("grid") == "fine")["situation"].n_unique() == 6
    # exhibition teams excluded from the norm universe
    assert not set(counts["defending_team_id"].unique()) & set(SN.EXHIBITION_TEAMS)


@pytest.mark.skipif(not (C.REPORTS / "phase1.md").exists(), reason="report not written")
def test_no_fault_language_phase1():
    txt = (C.REPORTS / "phase1.md").read_text().lower()
    for w in FAULT_WORDS:
        assert txt.count(w) <= C.LAW_2.lower().count(w), f"fault word '{w}' used beyond the Law-2 quote"
