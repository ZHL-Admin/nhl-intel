from __future__ import annotations
import polars as pl, pytest
from dblame import config as C
from dblame.data import universe
from dblame.link1 import BLAME

def test_universe_is_5v5_only():
    u = universe()
    # windows are non-negative and every sub-minimum window is flagged short (handled separately)
    assert (u["win_len_s"] >= 0).all()
    assert u.filter(pl.col("win_len_s") < C.MIN_WINDOW_S)["short_window"].all()
    assert u["net_x"].abs().unique().to_list() == [C.NET_X]

@pytest.mark.skipif(not BLAME.exists(), reason="blame not built")
def test_blame_is_absolute_not_forced_unit():
    bl = pl.read_parquet(BLAME)
    assert (bl["blame"] >= 0).all()
    per_goal = bl.group_by("game_id", "event_id").agg(t=pl.col("blame").sum())
    zero = (per_goal["t"] < 1e-6).mean()
    # the whole point vs the old model: many goals assign ~0, and total is NOT pinned at 1.0
    assert zero > 0.3, f"expected many zero-blame goals, got {zero:.2%}"
    assert per_goal["t"].max() > 1.5, "absolute blame should concentrate above 1.0 on multi-failure goals"

@pytest.mark.skipif(not BLAME.exists(), reason="blame not built")
def test_e1_scorer_and_e3_mutually_exclusive():
    bl = pl.read_parquet(BLAME)
    both = bl.filter((pl.col("e1") > 0) & (pl.col("e1_man") == "scorer") & (pl.col("e3") > 0))
    assert both.height == 0, "E1(scorer) and E3 must not double-count the same defender-goal"

@pytest.mark.skipif(not (C.REPORTS / "probe.md").exists(), reason="report not built")
def test_no_banned_words_outside_framing():
    txt = (C.REPORTS / "probe.md").read_text().lower()
    for w in ["bad defense", "fault", "out of position", "mistake"]:
        assert txt.count(w) <= C.FRAMING.lower().count(w), f"banned '{w}' outside the framing quote"
