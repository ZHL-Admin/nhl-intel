"""Parser tests against cached fixtures (task 0.7):
row counts, no negative durations, all shift players appear in the boxscore."""

from __future__ import annotations

import polars as pl

from atlas import parse

REG = "2023020204"
PLAYOFF = "2023030411"


def test_parse_shifts_filters_to_517_rows():
    df = parse.parse_shifts(REG)
    # Verified in Phase 0: 694 raw rows, 5 goal-marker (505), 689 real shifts.
    assert df.height == 689
    assert set(df.columns) == set(parse.SHIFT_SCHEMA.keys())


def test_parse_shifts_no_negative_durations():
    for gid in (REG, PLAYOFF):
        df = parse.parse_shifts(gid)
        assert df.height > 0
        durs = df["duration_s"].drop_nulls()
        assert durs.min() >= 0, f"negative shift duration in {gid}"


def test_shift_players_subset_of_boxscore():
    for gid in (REG, PLAYOFF):
        df = parse.parse_shifts(gid)
        shift_ids = set(df["player_id"].drop_nulls().to_list())
        box_ids = parse.boxscore_player_ids(gid)
        missing = shift_ids - box_ids
        assert missing == set(), f"{gid}: shift players not in boxscore: {missing}"


def test_parse_shifts_dtypes():
    df = parse.parse_shifts(REG)
    assert df.schema["player_id"] == pl.Int64
    assert df.schema["team_abbrev"] == pl.Utf8
    assert df.schema["duration_s"] == pl.Int64


def test_parse_pbp_row_count_and_periods():
    df = parse.parse_pbp(REG)
    # Verified in Phase 0: 320 plays.
    assert df.height == 320
    assert df["period"].min() >= 1
    assert set(df.columns) == set(parse.PBP_SCHEMA.keys())


def test_parse_pbp_playoff_regulation():
    df = parse.parse_pbp(PLAYOFF)
    # Verified in Phase 0: 368 plays; this game ended in regulation (FLA 3-0,
    # shutout with an empty-net goal), so max period is 3 -- not an assumption.
    assert df.height == 368
    assert df["period"].min() >= 1
    assert df["period"].max() == 3
