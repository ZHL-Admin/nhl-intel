"""Hermetic tests for live-roster ingestion helpers (no network/BigQuery required).

Covers the season<->api8 conversions and that get_roster() resolves "current" as the
MAX published season and tags the payload with team_abbrev + season8 — the endpoint
deviation (we don't use the /current 307; see scripts/ROSTER_FINDINGS.md).
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


def test_get_roster_resolves_max_season_and_tags(monkeypatch):
    # Seasons returned out of order; get_roster must pick the MAX as "current".
    monkeypatch.setattr(nhl_api, "get_roster_seasons",
                        lambda team: [19271928, 20252026, 20242025])
    captured = {}

    def fake_for_season8(team, season8):
        captured["team"] = team
        captured["season8"] = season8
        return {"forwards": [{"id": 1}], "defensemen": [], "goalies": []}

    monkeypatch.setattr(nhl_api, "get_roster_for_season8", fake_for_season8)

    payload = nhl_api.get_roster("TOR")
    assert captured["season8"] == 20252026          # max season chosen
    assert captured["team"] == "TOR"
    assert payload["team_abbrev"] == "TOR"          # tagged for the loader
    assert payload["season8"] == 20252026
    assert payload["forwards"] == [{"id": 1}]       # original payload preserved


def test_get_roster_raises_without_seasons(monkeypatch):
    monkeypatch.setattr(nhl_api, "get_roster_seasons", lambda team: [])
    try:
        nhl_api.get_roster("TOR")
        assert False, "expected ValueError when a team has no published roster seasons"
    except ValueError:
        pass
