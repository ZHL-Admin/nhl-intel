"""Def-breakdown probe tests. Artifact-dependent tests skip when shares are not built."""
from __future__ import annotations
import polars as pl, pytest
from defbreak import config as C, signals as S, events as E


def test_framing_and_banned_words_defined():
    assert "descriptive" in C.FRAMING.lower() and "culprit rate" in C.FRAMING.lower()
    for w in ["blame", "fault", "out of position", "mistake", "bad defense"]:
        assert w in C.BANNED_WORDS


@pytest.mark.skipif(not S.SHARES.exists(), reason="shares not built")
def test_shares_sum_to_one_and_five_defenders():
    d = pl.read_parquet(S.SHARES)
    g = d.group_by("game_id", "event_id").agg(s=pl.col("breakdown_share").sum(), n=pl.len())
    assert (g["n"] == 5).all()                       # five defenders per goal
    assert (g["s"] - 1.0).abs().max() < 1e-6         # one unit of breakdown per goal
    assert d["breakdown_share"].min() >= -1e-9 and d["breakdown_share"].max() <= 1.0 + 1e-9   # proper shares
    assert (d["hard_culprit"] == (d["breakdown_share"] >= C.HARD_CULPRIT)).all()


@pytest.mark.skipif(not (C.REPORTS / "probe.md").exists(), reason="report not written")
def test_no_banned_words_beyond_framing():
    txt = (C.REPORTS / "probe.md").read_text().lower()
    for w in C.BANNED_WORDS:
        assert txt.count(w) <= C.FRAMING.lower().count(w), f"banned word '{w}' used beyond the framing quote"
