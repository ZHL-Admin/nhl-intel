"""Stage 2 tests. Artifact-dependent tests skip when descriptors/signatures parquet absent."""
from __future__ import annotations
import polars as pl, pytest
from gtrack import stage2_descriptors as D, stage2_signatures as SG, stage2_reliability as R, config


def test_pattern_classes_and_universe():
    assert set(D.COLUMN_UNIVERSE.values()) <= {"all", "tracked"}
    # carrier-dependent fields are tracked-only per the amendment
    assert D.COLUMN_UNIVERSE["pass_pattern"] == "tracked"
    assert D.COLUMN_UNIVERSE["pass_count"] == "all"


def _built():
    return D.DESCRIPTORS.exists() and SG.SIGNATURES.exists()


@pytest.mark.skipif(not _built(), reason="stage 2 artifacts not built")
def test_descriptors_universe_flags():
    d = pl.read_parquet(D.DESCRIPTORS)
    assert d.height == config.EXPECTED_GOALS
    # carrier-dependent fields are null on non-tracked clips (the amendment)
    nt = d.filter(~pl.col("tracked"))
    assert nt["pass_pattern"].null_count() == nt.height
    assert nt["primary_carrier_id"].null_count() == nt.height
    # pass_count (all clips) is populated everywhere
    assert d["pass_count"].null_count() == 0


@pytest.mark.skipif(not _built(), reason="stage 2 artifacts not built")
def test_signature_universes_separate_and_gated():
    s = pl.read_parquet(SG.SIGNATURES)
    # the two involvement universes are kept separate (never merged)
    assert set(s["involvement"].unique()) == {"pbp", "carrier"}
    # shares are in [0,1] and gate is exactly n_involved>=15
    for f in SG.FIELDS:
        assert s[f].drop_nulls().min() >= 0 and s[f].drop_nulls().max() <= 1
    assert (s["gate_ok"] == (s["n_involved"] >= SG.MIN_INVOLVED)).all()


@pytest.mark.skipif(not _built(), reason="stage 2 artifacts not built")
def test_reliability_shape():
    r = R.run()
    assert r["n_fields"] == 7
    assert r["GATE_PASS"] == (r["n_pass"] > 7 / 2)
