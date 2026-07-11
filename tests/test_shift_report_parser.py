"""Tests for the production HTML shift-report fallback parser.

Hermetic tests (no network) cover parsing, period mapping, sweater->player
resolution, provenance marker, and the skip semantics of build_fallback_rows.

The dual-source reconciliation tests (network) parse the HTML reports for games
that ALSO have JSON shiftcharts and assert the recovered (teamId, playerId,
period, start_second, end_second) intervals match the JSON 517 rows EXACTLY --
including an overtime game (2023020145). They skip cleanly when offline.
"""

import sys
from pathlib import Path

import pytest

REPO = Path(__file__).parent.parent
sys.path.insert(0, str(REPO))

from ingestion import shift_report_parser as srp  # noqa: E402


# ---------------------------------------------------------------------------
# hermetic: period mapping + mm:ss
# ---------------------------------------------------------------------------
def test_period_number_regulation_ot_so():
    assert srp._period_number("1") == 1
    assert srp._period_number("3") == 3
    assert srp._period_number("OT") == 4      # regular-season OT
    assert srp._period_number("OT2") == 5     # playoff multi-OT
    assert srp._period_number("OT3") == 6
    assert srp._period_number("SO") is None   # shootout has no real shifts
    assert srp._period_number("Per") is None  # header label


def test_mmss_roundtrip():
    assert srp._mmss_to_s("00:34") == 34
    assert srp._mmss_to_s("12:05") == 725
    assert srp._mmss(34) == "00:34"
    assert srp._mmss(725) == "12:05"


def test_report_url():
    assert srp.report_url("2025020001", "H") == \
        "https://www.nhl.com/scores/htmlreports/20252026/TH020001.HTM"
    assert srp.report_url(2023020145, "V") == \
        "https://www.nhl.com/scores/htmlreports/20232024/TV020145.HTM"


# ---------------------------------------------------------------------------
# hermetic: parse_report on a synthetic report snippet
# ---------------------------------------------------------------------------
_SYNTH_HTML = """
<html><body><table>
<tr><td class="playerHeading">2 PETRY, JEFF</td></tr>
<tr><td>Shift #</td><td>Per</td><td>Start of Shift</td><td>End of Shift</td>
    <td>Duration</td><td>Event</td></tr>
<tr><td>1</td><td>1</td><td>0:00 / 20:00</td><td>0:45 / 19:15</td><td>0:45</td><td></td></tr>
<tr><td>2</td><td>OT</td><td>1:10 / 3:50</td><td>1:40 / 3:20</td><td>0:30</td><td>G</td></tr>
<tr><td>3</td><td>SO</td><td>0:00 / 0:00</td><td>0:00 / 0:00</td><td>0:00</td><td></td></tr>
<tr><td>TOT</td><td></td><td></td><td></td><td>1:15</td><td></td><td>summary</td></tr>
</table></body></html>
"""


def test_parse_report_extracts_shifts_and_skips_so_and_headers():
    shifts = srp.parse_report(_SYNTH_HTML)
    # regulation shift + OT shift; SO row skipped, header row skipped, 7-cell TOT skipped
    assert len(shifts) == 2
    s1, s2 = shifts
    assert (s1.sweater_number, s1.player_name) == (2, "PETRY, JEFF")
    assert (s1.period, s1.start_seconds, s1.end_seconds) == (1, 0, 45)
    # OT maps to period 4 -> absolute offset (4-1)*1200 = 3600
    assert (s2.period, s2.start_seconds, s2.end_seconds) == (4, 3600 + 70, 3600 + 100)
    assert s2.duration_s == 30


# ---------------------------------------------------------------------------
# hermetic: sweater->player resolution, provenance marker, fallback-row skips
# ---------------------------------------------------------------------------
def _fake_pbp():
    return {
        "game_id": 2025029999,
        "homeTeam": {"id": 10},
        "awayTeam": {"id": 20},
        "rosterSpots": [
            {"teamId": 10, "sweaterNumber": 2, "playerId": 8400002,
             "firstName": {"default": "Jeff"}, "lastName": {"default": "Petry"}},
            {"teamId": 20, "sweaterNumber": 9, "playerId": 8400009,
             "firstName": {"default": "Sam"}, "lastName": {"default": "Reinhart"}},
        ],
    }


_HOME_HTML = _SYNTH_HTML
_VISITOR_HTML = """
<html><body><table>
<tr><td class="playerHeading">9 REINHART, SAM</td></tr>
<tr><td>1</td><td>1</td><td>0:00 / 20:00</td><td>0:50 / 19:10</td><td>0:50</td><td></td></tr>
<tr><td class="playerHeading">99 GHOST, PLAYER</td></tr>
<tr><td>1</td><td>1</td><td>0:00 / 20:00</td><td>0:40 / 19:20</td><td>0:40</td><td></td></tr>
</table></body></html>
"""


def test_build_shift_elements_resolves_and_marks_source():
    elems, warns = srp.build_shift_elements(
        2025029999, _fake_pbp(),
        html_by_side={"H": _HOME_HTML, "V": _VISITOR_HTML})

    # home #2 (2 shifts: reg + OT), visitor #9 (1 shift) resolve; visitor #99 unresolved
    assert len(elems) == 3
    assert all(e["_source"] == srp.SOURCE_MARKER for e in elems)
    assert all(e["typeCode"] == 517 and e["gameId"] == 2025029999 for e in elems)

    home = [e for e in elems if e["teamId"] == 10]
    vis = [e for e in elems if e["teamId"] == 20]
    assert {e["playerId"] for e in home} == {8400002}
    assert {e["playerId"] for e in vis} == {8400009}
    assert home[0]["firstName"] == "Jeff" and home[0]["lastName"] == "Petry"

    # ghost sweater 99 not in roster -> one warning, not an element
    assert any("99 unresolved" in w for w in warns)


def test_build_fallback_rows_skips_missing_pbp_and_empty_games():
    # gid A: resolvable -> a row; gid B: no pbp in memory -> skipped, warned
    pbp_by_gid = {2025029999: _fake_pbp()}
    rows, warns = srp.build_fallback_rows(
        [2025029999, 2025020000], pbp_by_gid,
        html_by_gid={2025029999: {"H": _HOME_HTML, "V": _VISITOR_HTML}})
    assert [r["game_id"] for r in rows] == [2025029999]
    assert rows[0]["id"] == 2025029999 and isinstance(rows[0]["data"], list)
    assert any("2025020000 no play-by-play" in w for w in warns)


# ---------------------------------------------------------------------------
# network: dual-source reconciliation against the JSON feed (byte-for-byte)
# ---------------------------------------------------------------------------
def _interval_set(elements):
    """Set of (teamId, playerId, period, start_second, end_second) over real 517 shifts."""
    out = set()
    for d in elements:
        if d.get("typeCode") != 517 or not d.get("duration"):
            continue
        p = d["period"]

        def _s(mmss):
            a, b = mmss.split(":")
            return (p - 1) * 1200 + int(a) * 60 + int(b)

        out.add((d["teamId"], d["playerId"], p, _s(d["startTime"]), _s(d["endTime"])))
    return out


def _reconcile(game_id):
    httpx = pytest.importorskip("httpx")
    try:
        jr = httpx.get("https://api.nhle.com/stats/rest/en/shiftcharts",
                       params={"cayenneExp": f"gameId={game_id}"}, timeout=30.0)
        jr.raise_for_status()
        json_data = jr.json()["data"]
        pbp = httpx.get(f"https://api-web.nhle.com/v1/gamecenter/{game_id}/play-by-play",
                        timeout=30.0).json()
    except Exception as e:  # noqa: BLE001 — offline / rate limited => skip, don't fail
        pytest.skip(f"network unavailable for reconciliation of {game_id}: {e}")

    pbp["game_id"] = game_id
    elems, warns = srp.build_shift_elements(game_id, pbp)
    assert _interval_set(elems) == _interval_set(json_data), \
        f"HTML fallback intervals differ from JSON 517 rows for {game_id}"
    assert not warns, f"unresolved sweaters for {game_id}: {warns[:5]}"


@pytest.mark.network
def test_reconcile_regulation_game():
    _reconcile(2025020001)


@pytest.mark.network
def test_reconcile_overtime_game():
    # 2023020145 went to overtime -- exercises OT period mapping end-to-end.
    _reconcile(2023020145)
