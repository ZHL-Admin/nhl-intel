"""G1 tests. Artifact-dependent tests skip when the spine/save-quality parquet is absent."""
from __future__ import annotations

import polars as pl
import pytest

from gprobe import config, spine as S, savequality as SQ


# ---------------------------------------------------------------- pure config/logic
def test_denominator_and_dropped_buckets():
    # SPINE is SOG + goals (the shots-faced denominator), never goals alone
    assert set(config.SHOT_EVENTS) == {"shot-on-goal", "goal"}
    # rush / one-timer are NOT in the kept bucket thresholds (dropped, not fabricated)
    assert "rush" not in config.SHOT_TYPE_MAP and "one_timer" not in config.SHOT_TYPE_MAP


def test_danger_region_bands_partition():
    from gprobe.spine import _danger, _region
    assert _danger(0.02) == "low" and _danger(0.09) == "mid" and _danger(0.30) == "high"
    assert _region(10) == "inner_slot" and _region(30) == "outer_slot" and _region(60) == "point"


def _built():
    return S.SPINE.exists() and SQ.SAVEQ.exists()


@pytest.mark.skipif(not _built(), reason="G1 artifacts not built")
def test_spine_is_shots_faced():
    s = pl.read_parquet(S.SPINE)
    assert (s["saved"] + s["is_goal"] == 1).all()                 # every row is a save or a goal
    g = s.filter(pl.col("goalie_id").is_not_null())
    assert 0.87 < g["saved"].mean() < 0.93                        # sane overall save%


@pytest.mark.skipif(not _built(), reason="G1 artifacts not built")
def test_buckets_computable_on_saves():
    # THE POINT: every kept bucket is defined on SAVES, not just goals
    saves = pl.read_parquet(S.SPINE).filter((pl.col("saved") == 1) & pl.col("goalie_id").is_not_null())
    assert saves["shot_bucket"].null_count() == 0
    assert saves["region"].drop_nulls().len() > 0.99 * saves.height
    assert saves["danger"].drop_nulls().len() > 0.8 * saves.height     # ~90% xG coverage
    assert saves["rebound"].dtype == pl.Boolean


@pytest.mark.skipif(not _built(), reason="G1 artifacts not built")
def test_gsax_league_centered_and_gate():
    q = pl.read_parquet(SQ.SAVEQ).filter(pl.col("scope") == "pooled")
    # league-centered: shot-weighted mean deviation per bucket ~ 0
    for (dim, b), sub in q.filter(pl.col("gsax_dev_raw").is_not_null()).partition_by(
            "dimension", "bucket", as_dict=True, include_key=True).items():
        w = (sub["gsax_dev_raw"] * sub["n_xg"]).sum() / sub["n_xg"].sum()
        assert abs(w) < 0.5, f"{dim}/{b} not centered: {w}"
    # minimum-sample gate is exactly n_shots>=50
    assert (q["claim_ok"] == (q["n_shots"] >= config.MIN_BUCKET_SHOTS)).all()
