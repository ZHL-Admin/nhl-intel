"""Synthetic unit tests for stint derivation logic (goal cut-points, strength,
score attribution, start type). Pure — no corpus/network needed."""

from __future__ import annotations

import polars as pl

from atlas import stints


def _shifts(rows):
    return pl.DataFrame(rows, schema={"player_id": pl.Int64, "team_id": pl.Int64,
                                      "shift_start_seconds": pl.Int64,
                                      "shift_end_seconds": pl.Int64})


def _goals(rows):
    return pl.DataFrame(rows, schema={"event_second": pl.Int64, "event_owner_team_id": pl.Int64})


def _fo(rows):
    return pl.DataFrame(rows, schema={"event_second": pl.Int64, "event_owner_team_id": pl.Int64,
                                      "zone_code": pl.Utf8})


def _full_5v5():
    # 5 home skaters (team 1) + home goalie 100; 5 away (team 2) + away goalie 200; all on [0,100]
    rows = [{"player_id": i, "team_id": 1, "shift_start_seconds": 0, "shift_end_seconds": 100} for i in range(1, 6)]
    rows += [{"player_id": 100, "team_id": 1, "shift_start_seconds": 0, "shift_end_seconds": 100}]
    rows += [{"player_id": 10 + i, "team_id": 2, "shift_start_seconds": 0, "shift_end_seconds": 100} for i in range(1, 6)]
    rows += [{"player_id": 200, "team_id": 2, "shift_start_seconds": 0, "shift_end_seconds": 100}]
    pos = {100: True, 200: True}  # goalies
    return _shifts(rows), pos


def test_goal_splits_and_score_state():
    shifts, pos = _full_5v5()
    goals = _goals([{"event_second": 50, "event_owner_team_id": 1}])  # home goal at 50
    rows = stints._build_game(1, "2023-24", 1, 2, False, shifts, goals, _fo([]), pos)
    df = pl.DataFrame(rows, schema=stints.STINT_SCHEMA)
    # goal at 50 splits [0,100] into [0,50] and [50,100]
    assert df.height == 2
    assert df["start_seconds"].to_list() == [0, 50]
    # score constant per stint: first 0-0, second 1-0
    assert df["home_score"].to_list() == [0, 1]
    assert df["score_state"].to_list() == [0, 1]
    assert df["strength_state"].to_list() == ["5v5", "5v5"]
    assert df["home_goalie_id"].to_list() == [100, 100]


def test_strength_from_ice_short_handed():
    # away team down to 4 skaters after second 50 (one away skater's shift ends)
    shifts, pos = _full_5v5()
    shifts = shifts.with_columns(
        shift_end_seconds=pl.when((pl.col("player_id") == 11))
        .then(50).otherwise(pl.col("shift_end_seconds")))
    rows = stints._build_game(1, "2023-24", 1, 2, False, shifts, _goals([]), _fo([]), pos)
    df = pl.DataFrame(rows, schema=stints.STINT_SCHEMA)
    # [0,50] 5v5, [50,100] 5v4 (away lost a skater) -- strength from the ice
    assert df.filter(pl.col("start_seconds") == 50)["strength_state"].item() == "5v4"


def test_start_type_from_faceoff():
    shifts, pos = _full_5v5()
    # neutral-zone faceoff by home at second 0
    fo = _fo([{"event_second": 0, "event_owner_team_id": 1, "zone_code": "N"}])
    rows = stints._build_game(1, "2023-24", 1, 2, False, shifts, _goals([]), fo, pos)
    df = pl.DataFrame(rows, schema=stints.STINT_SCHEMA)
    assert df.filter(pl.col("start_seconds") == 0)["start_type"].item() == "NZ"
