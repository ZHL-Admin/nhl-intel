import pytest

from atlas import paths


def test_season_for_game_regular():
    assert paths.season_for_game("2023020204") == "20232024"


def test_season_for_game_playoff():
    assert paths.season_for_game("2023030411") == "20232024"


def test_game_type():
    assert paths.game_type("2023020204") == "02"
    assert paths.game_type("2023030411") == "03"
    assert paths.game_type("2015010001") == "01"


def test_raw_game_path_layout():
    p = paths.raw_game_path("2023020204", "pbp")
    assert p.parts[-3:] == ("20232024", "2023020204", "pbp.json")


def test_raw_game_path_rejects_bad_kind():
    with pytest.raises(ValueError):
        paths.raw_game_path("2023020204", "nope")


def test_season_for_game_validates_length():
    with pytest.raises(ValueError):
        paths.season_for_game("123")
