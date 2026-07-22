"""Stage 1 tests. Artifact-dependent tests skip gracefully when the mechanism/profile parquet is absent."""
from __future__ import annotations

import numpy as np
import polars as pl
import pytest

from gtrack import config, mechanisms as M, profiles as P


# ---------------------------------------------------------------- EB shrinkage (pure)
def test_eb_shrinkage_pulls_toward_league():
    p_l = 0.30
    # a goalie at 0/50 (raw 0%) should be pulled up toward league; k=20 prior
    a, b = P.K * p_l + 0, P.K * (1 - p_l) + 50
    eb = a / (a + b)
    assert 0.0 < eb < p_l                       # shrunk up from 0, below league
    assert abs(eb - (P.K * p_l + 0) / (P.K + 50)) < 1e-9
    # a goalie at 40/50 (80%) pulled down toward league
    a2, b2 = P.K * p_l + 40, P.K * (1 - p_l) + 10
    eb2 = a2 / (a2 + b2)
    assert p_l < eb2 < 0.80


def test_ci_ordering():
    rng = np.random.default_rng(config.SEED)
    lo, hi = P._beta_ci(rng, 5, 15)
    assert 0 <= lo < hi <= 1


# ---------------------------------------------------------------- flag consistency (pure)
def test_mutually_exclusive_flag_logic():
    df = pl.DataFrame({
        "tracked": [True, True], "flight_detected": [True, True],
        "screen_opp": [0, 2], "screen_own": [0, 0], "release_dist": [30.0, 5.0],
        "goalie_lat_speed_rel": [1.0, 8.0], "goalie_depth_change": [0.1, 3.0],
        "rush_flag": [True, False], "entry_type": ["carried", "off_frame_start"],
        "ew_disp_2s": [20.0, 5.0], "second_chance": [False, True], "location": ["glove", "center"],
    })
    scr = pl.col("screen_opp") + pl.col("screen_own")
    out = df.with_columns(
        CLEAN_LOOK=(scr == 0) & (pl.col("release_dist") >= 25) & (pl.col("goalie_lat_speed_rel") < 3),
        SCREENED=scr >= 1,
        RUSH=pl.col("rush_flag"),
        IN_ZONE=(~pl.col("rush_flag")) & (pl.col("entry_type") != "off_frame_start"),
    )
    # CLEAN_LOOK and SCREENED never co-true; RUSH and IN_ZONE never co-true
    assert not (out["CLEAN_LOOK"] & out["SCREENED"]).any()
    assert not (out["RUSH"] & out["IN_ZONE"]).any()


# ---------------------------------------------------------------- artifact-dependent
def _built():
    return M.MECH_FLAGS.exists() and P.PROFILES.exists()


@pytest.mark.skipif(not _built(), reason="stage 1 artifacts not built")
def test_effective_release_semantics():
    m = pl.read_parquet(M.MECH_FLAGS)
    assert m.height == config.EXPECTED_GOALS
    # release_source flags match flight, and TRACKED is the broad universe
    assert (m.filter(pl.col("flight_detected"))["release_source"] == "flight").all()
    assert (m.filter(~pl.col("flight_detected"))["release_source"] == "arrival").all()
    assert 0.85 < m["tracked"].mean() < 0.98          # ~92.5%
    # class-by-class: geometry flags only defined on TRACKED
    assert m.filter(~pl.col("tracked"))["EAST_WEST"].null_count() == m.filter(~pl.col("tracked")).height


@pytest.mark.skipif(not _built(), reason="stage 1 artifacts not built")
def test_profile_gates_applied():
    prof = pl.read_parquet(P.PROFILES)
    # claim_ok is exactly count>=10
    assert (prof["claim_ok"] == (prof["count"] >= P.MECH_CLAIM_GATE)).all()
    # every pooled gated goalie has >=40 GA
    g = prof.filter((pl.col("scope") == "pooled") & pl.col("row_gate_ok"))
    assert g["ga_all"].min() >= P.GA_ROW_GATE
    # EB shares within a mechanism are bounded [0,1]
    assert prof["eb_share"].min() >= 0 and prof["eb_share"].max() <= 1
