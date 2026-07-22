"""Stage 0 tests. The reconstruction tests use a synthetic goal (no BigQuery); the corpus/API tests
skip gracefully when the built parquet is not present so `pytest` is green pre-build too."""
from __future__ import annotations

import numpy as np
import polars as pl
import pytest

from gtrack import config, kinematics, reconstruct as R, quality


# ---------------------------------------------------------------- laws & config
def test_laws_and_seed():
    assert config.SEED == 20260714
    assert "GOALS-ONLY" in config.LAW_1 and "FUSION" in config.LAW_2
    from gtrack import api
    assert "LAW 1" in api.goal.__doc__ and "LAW 2" in api.goal.__doc__
    assert "GOALS-ONLY" in api.__doc__ and "FUSION" in api.__doc__


# ---------------------------------------------------------------- kinematics
def test_smoothing_and_fallback():
    x = np.linspace(0, 10, 30) + np.array([0.5 * (-1) ** i for i in range(30)])  # sawtooth noise
    sm, meth = kinematics.smooth(x)
    assert meth == "savgol7"
    assert np.std(np.diff(sm)) < np.std(np.diff(x))          # smoother
    short, meth2 = kinematics.smooth(np.arange(5.0))
    assert meth2 == "roll5"
    tiny, meth3 = kinematics.smooth(np.arange(3.0))
    assert meth3 == "raw"


def test_speed_units():
    # 1 ft/frame at 10 Hz = 10 ft/s
    x = np.arange(20.0); y = np.zeros(20)
    sp, _ = kinematics.speed_series(x, y)
    assert abs(np.median(sp) - 10.0) < 0.5


# ---------------------------------------------------------------- synthetic goal
def _synthetic_goal():
    """A entry-carries over the blue line, passes to B, B shoots into the net."""
    rows = []
    A, B, DEF, GH, GA = 1, 2, 3, 90, 91   # players; GH/GA goalies
    team_atk, team_def = 10, 20
    n = 25
    # puck: A carries over the blue line (fr0-11), pass to B (fr12-19), B shoots fast into net (fr20-24)
    px = np.concatenate([np.linspace(-10, 30, 12), np.linspace(33, 62, 8),
                         np.array([64.0, 70.5, 77.0, 83.5, 90.0])])   # shot ~65 ft/s
    py = np.zeros(n)
    ax = np.clip(np.linspace(-12, 33, n), -12, 33); ay = np.zeros(n)
    bx = np.full(n, 64.0); by = np.zeros(n)
    dfx = np.full(n, 75.0); dfy = np.full(n, 12.0)
    ghx = np.full(n, 89.0); ghy = np.zeros(n)      # defending goalie at attacking net
    gax = np.full(n, -89.0); gay = np.zeros(n)
    for f in range(n):
        rows.append({"frame_index": f, "is_puck": True, "player_id": None, "team_id": None, "x_std": float(px[f]), "y_std": float(py[f])})
        rows.append({"frame_index": f, "is_puck": False, "player_id": A, "team_id": team_atk, "x_std": float(ax[f]), "y_std": float(ay[f])})
        rows.append({"frame_index": f, "is_puck": False, "player_id": B, "team_id": team_atk, "x_std": float(bx[f]), "y_std": float(by[f])})
        rows.append({"frame_index": f, "is_puck": False, "player_id": DEF, "team_id": team_def, "x_std": float(dfx[f]), "y_std": float(dfy[f])})
        rows.append({"frame_index": f, "is_puck": False, "player_id": GH, "team_id": team_def, "x_std": float(ghx[f]), "y_std": float(ghy[f])})
        rows.append({"frame_index": f, "is_puck": False, "player_id": GA, "team_id": team_atk, "x_std": float(gax[f]), "y_std": float(gay[f])})
    fr = pl.DataFrame(rows, schema_overrides={"player_id": pl.Int64, "team_id": pl.Int64})
    ctx = {"scorer_id": B, "scoring_team_id": team_atk, "def_goalie_id": GH, "home_goalie_id": GH, "away_goalie_id": GA}
    return fr, ctx, dict(A=A, B=B, DEF=DEF)


def test_reconstruct_synthetic():
    fr, ctx, ids = _synthetic_goal()
    o = R.reconstruct_goal(fr, ctx)
    # arrival is in the net mouth, release precedes arrival, flight fired
    assert config.NET_X <= abs(o["arrival_x"]) <= config.NET_BACK
    assert o["release_frame"] <= o["arrival_frame"]
    assert o["flight_detected"] is True
    # a pass A -> B is recovered, and B (scorer) is the last attacking carrier / on the shot
    passers = {(p["passer_id"], p["receiver_id"]) for p in o["passes"]}
    assert (ids["A"], ids["B"]) in passers
    # zone entry detected and carried by A
    assert o["entry"] and o["entry"]["entry_type"] in ("carried", "passed")
    # goalie excluded from carriers (defender GH never a carrier)
    carriers = {s["player_id"] for s in o["segments"]}
    assert 90 not in carriers and 91 not in carriers


def test_quality_formula():
    df = pl.DataFrame({"q_a": [True, True, False], "q_b": [True, True, True], "q_d": [True, False, True],
                       "q_c_crowd": [0, 2, 5], "season": ["2023-24"] * 3,
                       "game_id": [1, 2, 3], "event_id": [1, 2, 3]})
    s = quality.score_frame(df)
    # row0: 0.4+0.3+0.1+0.2*1 = 1.0, clean; row1: 0.4+0.3+0+0.2*(1/3)=0.766, not clean(d False)
    assert abs(s["quality_score"][0] - 1.0) < 1e-9 and s["is_clean"][0]
    assert not s["is_clean"][1]
    assert s["crowd_stratum"].to_list() == ["clean", "medium", "scramble"]


# ---------------------------------------------------------------- corpus/API (skip if unbuilt)
def _built():
    from gtrack import fuse
    return fuse.FUSED.exists() and fuse.EVENTS.exists()


@pytest.mark.skipif(not _built(), reason="fused corpus not built yet")
def test_corpus_shape():
    from gtrack import fuse, api
    g = pl.read_parquet(fuse.FUSED)
    assert g.height == config.EXPECTED_GOALS
    assert g["scorer_id"].null_count() == 0            # LAW-2 anchor present on every goal
    # ratio metric ships with absolute counts
    d = quality.distribution(g)
    assert d["n"] == config.EXPECTED_GOALS
    # API smoke
    row = g.row(0, named=True)
    one = api.goal(row["game_id"], row["event_id"])
    assert one["fused"]["scorer_id"] == row["scorer_id"]
    assert len(one["events"]) >= 1
