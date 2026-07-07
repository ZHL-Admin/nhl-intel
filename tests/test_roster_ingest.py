"""Hermetic tests for live-roster ingestion helpers (no network/BigQuery required).

Covers the season<->api8 conversions and that get_roster() resolves "current" — preferring
the NEXT season's roster when it is already live (the /roster-season index lags the roster
endpoint in the offseason) and falling back to the indexed max otherwise — and tags the
payload with team_abbrev + season8 (see archive/scripts/ROSTER_FINDINGS.md).
"""

import sys
from pathlib import Path

REPO = Path(__file__).parent.parent
sys.path.insert(0, str(REPO))

from ingestion import nhl_api  # noqa: E402


def test_season_to_api8():
    assert nhl_api.season_to_api8("2024-25") == "20242025"
    assert nhl_api.season_to_api8("2025-26") == "20252026"


def test_api8_to_season():
    assert nhl_api.api8_to_season(20242025) == "2024-25"
    assert nhl_api.api8_to_season("20252026") == "2025-26"


def test_season_roundtrip():
    for s in ("2018-19", "2024-25", "2025-26"):
        assert nhl_api.api8_to_season(nhl_api.season_to_api8(s)) == s


def test_get_roster_prefers_next_season_when_live(monkeypatch):
    # Index maxes at 2025-26, but the 2026-27 roster endpoint is already live (offseason lag).
    monkeypatch.setattr(nhl_api, "get_roster_seasons",
                        lambda team: [19271928, 20252026, 20242025])
    probed = {}

    def fake_try(team, season8):
        probed["season8"] = season8
        return {"forwards": [{"id": 9}], "defensemen": [], "goalies": []}

    def boom(team, season8):  # must NOT be called when the next season is live
        raise AssertionError("fell back to indexed max despite a live next-season roster")

    monkeypatch.setattr(nhl_api, "_try_roster_for_season8", fake_try)
    monkeypatch.setattr(nhl_api, "get_roster_for_season8", boom)

    payload = nhl_api.get_roster("TOR")
    assert probed["season8"] == 20262027            # probed the NEXT season (max start year + 1)
    assert payload["season8"] == 20262027           # and resolved to it
    assert payload["team_abbrev"] == "TOR"          # tagged for the loader
    assert payload["forwards"] == [{"id": 9}]


def test_get_roster_falls_back_to_indexed_max_when_next_not_live(monkeypatch):
    # Next season not published yet -> probe returns None -> use the indexed max.
    monkeypatch.setattr(nhl_api, "get_roster_seasons",
                        lambda team: [19271928, 20252026, 20242025])
    monkeypatch.setattr(nhl_api, "_try_roster_for_season8", lambda team, season8: None)
    captured = {}

    def fake_for_season8(team, season8):
        captured["team"] = team
        captured["season8"] = season8
        return {"forwards": [{"id": 1}], "defensemen": [], "goalies": []}

    monkeypatch.setattr(nhl_api, "get_roster_for_season8", fake_for_season8)

    payload = nhl_api.get_roster("TOR")
    assert captured["season8"] == 20252026          # fell back to the indexed max
    assert captured["team"] == "TOR"
    assert payload["team_abbrev"] == "TOR"
    assert payload["season8"] == 20252026
    assert payload["forwards"] == [{"id": 1}]       # original payload preserved


def test_get_roster_raises_without_seasons(monkeypatch):
    monkeypatch.setattr(nhl_api, "get_roster_seasons", lambda team: [])
    try:
        nhl_api.get_roster("TOR")
        assert False, "expected ValueError when a team has no published roster seasons"
    except ValueError:
        pass
