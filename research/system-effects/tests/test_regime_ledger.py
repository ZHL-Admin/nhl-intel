"""Deterministic unit tests for the regime ledger logic (no network / no warehouse)."""
import polars as pl

from syseff import regime_ledger as R


def test_normalize_name():
    assert R.normalize_name("  Jon   Cooper ") == "Jon Cooper"
    assert R.normalize_name("Rod Brind’Amour") == "Rod Brind'Amour"  # curly -> straight
    assert R.normalize_name(None) is None
    assert R.normalize_name("   ") is None
    # NFC: composed vs decomposed accent collapse to the same string
    assert R.normalize_name("André Tourigny") == R.normalize_name("André Tourigny")


def _tg(rows):
    # rows: (team_id, syear, season_label, game_id, coach)
    return pl.DataFrame(
        {"team_id": [r[0] for r in rows],
         "season_start_year": [r[1] for r in rows],
         "season_label": [r[2] for r in rows],
         "game_id": [r[3] for r in rows],
         "game_date": [None] * len(rows),
         "coach": [r[4] for r in rows],
         "is_home": [True] * len(rows),
         "coach_source": ["t"] * len(rows)}
    )


def test_contiguous_and_midseason():
    # Team 1: coach A (2 g) then B (2 g) same season -> mid-season change to B.
    tg = _tg([
        (1, 2015, "2015-16", 2015020001, "A"),
        (1, 2015, "2015-16", 2015020002, "A"),
        (1, 2015, "2015-16", 2015020003, "B"),
        (1, 2015, "2015-16", 2015020004, "B"),
    ])
    lg = R.build_ledger(tg).sort("start_game_id")
    assert lg.height == 2
    a, b = lg.to_dicts()
    assert a["coach_name"] == "A" and a["games_in_regime"] == 2
    assert a["is_mid_season_change"] is False and a["predecessor_coach"] is None
    assert b["coach_name"] == "B" and b["is_mid_season_change"] is True
    assert b["predecessor_coach"] == "A"


def test_cross_season_single_regime_and_boundary_change():
    # Coach A spans two seasons contiguously -> ONE regime, seasons_spanned range.
    # Then coach B starts at the next season's game 1 -> boundary change, NOT mid-season.
    tg = _tg([
        (1, 2015, "2015-16", 2015020001, "A"),
        (1, 2015, "2015-16", 2015020002, "A"),
        (1, 2016, "2016-17", 2016020001, "A"),
        (1, 2017, "2017-18", 2017020001, "B"),
    ])
    lg = R.build_ledger(tg).sort("start_game_id")
    assert lg.height == 2
    a, b = lg.to_dicts()
    assert a["coach_name"] == "A" and a["games_in_regime"] == 3
    assert a["seasons_spanned"] == "2015-16..2016-17"
    assert b["is_mid_season_change"] is False   # season-boundary hire, not mid-season


def test_leave_and_return_two_regimes():
    # A -> B -> A within a season yields THREE regimes (A appears twice).
    tg = _tg([
        (1, 2015, "2015-16", 2015020001, "A"),
        (1, 2015, "2015-16", 2015020002, "B"),
        (1, 2015, "2015-16", 2015020003, "A"),
    ])
    lg = R.build_ledger(tg).sort("start_game_id")
    assert lg.height == 3
    assert lg["coach_name"].to_list() == ["A", "B", "A"]
    assert lg["predecessor_coach"].to_list() == [None, "A", "B"]
