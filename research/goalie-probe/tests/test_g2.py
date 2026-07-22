"""G2 tests. Artifact-dependent tests skip when behavior parquet is absent."""
from __future__ import annotations
import polars as pl, pytest
from gprobe import behavior as B, stability_g2 as ST2, config


def test_rebound_is_denominator_backed():
    # rebound_control is the ONLY axis flagged denominator-backed, and is listed first
    assert ST2.AXES["rebound_control"][4] is True
    assert list(ST2.AXES)[0] == "rebound_control"
    for ax, spec in ST2.AXES.items():
        if ax != "rebound_control":
            assert spec[4] is False           # tracking axes are goals-only


def _built():
    return B.REB.exists() and B.TRK.exists()


@pytest.mark.skipif(not _built(), reason="G2 artifacts not built")
def test_rebound_denominator_is_saves():
    reb = pl.read_parquet(B.REB)
    # denominator (den) = saves; numerator (rebounds generated) never exceeds it
    assert (reb["num"] <= reb["den"]).all()
    assert reb["den"].sum() > 100_000       # many saves


@pytest.mark.skipif(not _built(), reason="G2 artifacts not built")
def test_stability_deterministic_and_shaped():
    import numpy as np
    a = ST2.run(); b = ST2.run()
    assert a.height == 5 and set(a["axis"]) == set(ST2.AXES)
    # reproducible to numerical precision (fixed seed + deterministic array order); polars' multi-threaded
    # float sums preclude bit-identity, so allclose is the honest bar
    assert np.allclose(a.sort("axis")["split_half_r"], b.sort("axis")["split_half_r"], atol=1e-9)
    assert np.allclose(a.sort("axis")["yoy_p"], b.sort("axis")["yoy_p"], atol=1e-9)
    # PASS logic matches the pre-stated bar
    for r in a.iter_rows(named=True):
        assert r["PASS"] == (r["split_half_r"] >= config.SPLIT_HALF_BAR and r["yoy_p"] < 0.05)
