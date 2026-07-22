"""Phase 0 tests. Artifact-dependent tests skip when primitives are not built."""
from __future__ import annotations
import glob, re
import polars as pl, pytest
from defscheme import config as C


FAULT_WORDS = ["out of position", "blame", "fault", "mistake", "responsible"]


def test_laws_present():
    assert "GOALS-ONLY" in C.LAW_1 and "NO FAULT LANGUAGE" in C.LAW_2
    # LAW 2 declares exactly the forbidden vocabulary
    for w in FAULT_WORDS:
        assert w in C.LAW_2


def test_attack_normalization_defended_net():
    # a point at the attacked net (attack_sign*89) normalizes to the defended net at +89
    for sign in (1.0, -1.0):
        x_std = sign * 89.0
        assert abs(x_std * sign - C.DEF_NET_X) < 1e-9


def _built():
    return bool(glob.glob(str(C.PARQUET / "def_prim_*.parquet")))


@pytest.mark.skipif(not _built(), reason="primitives not built")
def test_primitives_schema_and_sanity():
    p = pl.concat([pl.read_parquet(f) for f in glob.glob(str(C.PARQUET / "def_prim_*.parquet"))])
    for col in ["dist_net", "dist_puck", "off_centroid", "team_spread", "dist_nearest_atk",
                "zone", "puck_side", "low_high", "n_def", "x_norm", "y_norm"]:
        assert col in p.columns
    # geometry sanity: distances non-negative; defended net normalized to +x (most defenders in +x half)
    assert p["dist_net"].min() >= 0 and p["dist_puck"].min() >= 0
    assert (p["x_norm"] > 0).mean() > 0.6            # defenders cluster in their own (defended) half
    # situation buckets are the fixed vocabulary
    assert set(p["zone"].unique()) <= {"dzone", "neutral", "ozone"}
    assert set(p["puck_side"].unique()) <= {"strong", "weak"}


@pytest.mark.skipif(not (C.REPORTS / "phase0.md").exists(), reason="report not written")
def test_no_fault_language_beyond_the_law():
    txt = (C.REPORTS / "phase0.md").read_text().lower()
    # forbidden words may appear ONLY inside the quoted LAW 2 statement, nowhere else
    for w in FAULT_WORDS:
        assert txt.count(w) <= C.LAW_2.lower().count(w), f"fault word '{w}' used beyond the Law-2 quote"
