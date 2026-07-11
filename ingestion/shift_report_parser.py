"""Fallback shift-data recovery from the NHL HTML shift (Time-On-Ice) reports.

The stats-REST shiftcharts endpoint
(api.nhle.com/stats/rest/en/shiftcharts?cayenneExp=gameId={id}) began returning
an EMPTY ``data`` array for a large share of 2024-25 / 2025-26 games (verified
live: 0 shift rows for those games). The NHL HTML TOI reports at
    https://www.nhl.com/scores/htmlreports/{season8}/T{H|V}{gg6}.HTM
(TH = home, TV = visitor) still carry every player's shift-by-shift start/end
and let us recover the data.

This module is the PRODUCTION promotion of a research parser that was validated
byte-for-byte against the JSON feed on dual-source games (including overtime).
It is copied out once and has NO runtime dependency on research/.

Report structure (verified against 2025020001):
  * a player block starts with a ``playerHeading`` cell: "# LASTNAME, FIRSTNAME"
  * then a column-header row, then 6-cell shift rows:
      [shift#, period, "start_elapsed / remaining", "end_elapsed / remaining",
       duration, event(G/P)]
  * ``start_elapsed`` is time elapsed in the period, so absolute game seconds =
    (period-1)*1200 + elapsed -- identical to stg_shifts.
  * goalies also emit a per-period summary table (7-cell rows) that is skipped
    (rows whose first cell is not a pure integer shift number).

The parser yields shift rows keyed by (sweater_number); the caller resolves
sweater -> playerId / teamId from the game roster (pbp rosterSpots).

Provenance: every recovered shift element carries ``"_source":
"html_shift_report"``. Rows from the JSON feed have no ``_source`` key, so
``json_extract_scalar(shift, '$._source')`` distinguishes them downstream
(NULL => primary JSON, 'html_shift_report' => HTML fallback). This matches the
marker written by the 2026-07-10 historical backfill, so all recovered rows are
uniform.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Any, Callable, Optional

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

from ingestion.nhl_api import derive_season_from_game_id

logger = logging.getLogger(__name__)

# Provenance marker stamped on every element recovered from an HTML report.
SOURCE_MARKER = "html_shift_report"

# The HTML reports live on www.nhl.com and want a browser User-Agent + referer.
HTML_HEADERS = {
    "Referer": "https://www.nhl.com/",
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
}

_MMSS = re.compile(r"^\d{1,2}:\d{2}$")
_HEADER = re.compile(r"^(\d+)\s+(.+)$")  # "2 PETRY, JEFF"


@dataclass(frozen=True)
class ReportShift:
    sweater_number: int
    player_name: str
    period: int
    shift_number: int
    start_elapsed_s: int
    end_elapsed_s: int
    duration_s: int
    start_seconds: int   # absolute: (period-1)*1200 + start_elapsed
    end_seconds: int


def _mmss_to_s(v: str) -> int:
    m, s = v.split(":")
    return int(m) * 60 + int(s)


def _mmss(sec: int) -> str:
    return f"{sec // 60:02d}:{sec % 60:02d}"


def _period_number(label: str) -> Optional[int]:
    """Map the report's period column to a period number.

    Regulation periods are '1'/'2'/'3'. Overtime is labelled 'OT' (regular
    season, = period 4) or 'OT2'/'OT3'/... (playoff multi-OT, = 5/6/...).
    Shootout ('SO') has no real shifts and returns None (skip).
    """
    label = label.strip()
    if label.isdigit():
        return int(label)
    if label == "OT":
        return 4
    if label.startswith("OT") and label[2:].isdigit():
        return 3 + int(label[2:])  # OT2 -> 5, OT3 -> 6, ...
    return None  # 'SO' or header


def report_url(game_id: Any, side: str) -> str:
    """Build the HTML TOI report URL. ``side``: 'H' (home) or 'V' (visitor)."""
    gid = str(game_id)
    year = int(gid[:4])
    season8 = f"{year}{year + 1}"
    return f"https://www.nhl.com/scores/htmlreports/{season8}/T{side}{gid[4:]}.HTM"


def parse_report(html: str) -> list[ReportShift]:
    """Parse one TH/TV report into shift rows (one team's players)."""
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html, "lxml")
    out: list[ReportShift] = []
    cur_sweater: Optional[int] = None
    cur_name: Optional[str] = None

    for tr in soup.find_all("tr"):
        head = tr.find("td", class_="playerHeading")
        if head is not None:
            m = _HEADER.match(head.get_text(strip=True))
            if m:
                cur_sweater = int(m.group(1))
                cur_name = m.group(2).strip()
            continue
        if cur_sweater is None:
            continue

        cells = [c.get_text(strip=True) for c in tr.find_all("td")]
        if len(cells) != 6:
            continue
        shift_no, period, start_cell, end_cell, duration, _event = cells
        if not shift_no.isdigit():
            continue  # skips the "Shift #"/"Per" header rows
        per = _period_number(period)
        if per is None:
            continue  # 'SO' (no shifts) or unrecognized
        start_el = start_cell.split("/")[0].strip()
        end_el = end_cell.split("/")[0].strip()
        if not (_MMSS.match(start_el) and _MMSS.match(end_el) and _MMSS.match(duration)):
            continue
        s_el = _mmss_to_s(start_el)
        e_el = _mmss_to_s(end_el)
        offset = (per - 1) * 1200
        out.append(ReportShift(
            sweater_number=cur_sweater, player_name=cur_name or "",
            period=per, shift_number=int(shift_no),
            start_elapsed_s=s_el, end_elapsed_s=e_el, duration_s=_mmss_to_s(duration),
            start_seconds=offset + s_el, end_seconds=offset + e_el,
        ))
    return out


# ---------------------------------------------------------------------------
# fetch
# ---------------------------------------------------------------------------
@retry(stop=stop_after_attempt(4), wait=wait_exponential(multiplier=1, min=2, max=30))
def fetch_report(game_id: Any, side: str, *, client: Optional[httpx.Client] = None) -> str:
    """Fetch one HTML TOI report (home 'H' / visitor 'V'). Retries transient errors."""
    url = report_url(game_id, side)
    if client is not None:
        resp = client.get(url, headers=HTML_HEADERS)
    else:
        resp = httpx.get(url, headers=HTML_HEADERS, timeout=30.0, follow_redirects=True)
    resp.raise_for_status()
    return resp.text


# ---------------------------------------------------------------------------
# roster resolution (from the in-memory play-by-play rosterSpots)
# ---------------------------------------------------------------------------
def roster_from_pbp(pbp: dict) -> tuple[Optional[int], Optional[int], dict[tuple[int, int], tuple]]:
    """Return (home_team_id, away_team_id, {(team_id, sweater): (playerId, first, last)}).

    Reads the same rosterSpots that the JSON path already ingests, so no extra
    network/BigQuery call is needed in the daily flow.
    """
    home_id = (pbp.get("homeTeam") or {}).get("id")
    away_id = (pbp.get("awayTeam") or {}).get("id")
    rmap: dict[tuple[int, int], tuple] = {}
    for rs in pbp.get("rosterSpots", []) or []:
        team_id = rs.get("teamId")
        sweater = rs.get("sweaterNumber")
        if team_id is None or sweater is None:
            continue
        first = (rs.get("firstName") or {}).get("default")
        last = (rs.get("lastName") or {}).get("default")
        rmap[(team_id, sweater)] = (rs.get("playerId"), first, last)
    return home_id, away_id, rmap


def build_shift_elements(
    game_id: Any,
    pbp: dict,
    *,
    fetch: Optional[Callable[[Any, str], str]] = None,
    html_by_side: Optional[dict[str, str]] = None,
) -> tuple[list[dict], list[str]]:
    """Build the raw_shift_charts element list for one game from its HTML reports.

    Elements match the JSON 517-row shape (playerId/teamId/period/shiftNumber/
    startTime/endTime/duration/...) plus the ``_source`` provenance marker.

    Args:
        game_id: NHL game id.
        pbp: that game's play-by-play payload (for rosterSpots + team ids).
        fetch: report fetcher (game_id, side) -> html; defaults to fetch_report.
        html_by_side: pre-fetched {'H': html, 'V': html} to bypass the network
            (used by tests).

    Returns:
        (elements, warnings). ``warnings`` lists unresolved sweater numbers.
    """
    fetch = fetch or fetch_report
    home_id, away_id, rmap = roster_from_pbp(pbp)
    elements: list[dict] = []
    warnings: list[str] = []
    gid_int = int(game_id)
    for side, team_id in (("H", home_id), ("V", away_id)):
        if html_by_side is not None:
            html = html_by_side.get(side, "")
        else:
            html = fetch(game_id, side)
        for sh in parse_report(html):
            key = (team_id, sh.sweater_number)
            if key not in rmap:
                warnings.append(f"{gid_int} {side} sweater {sh.sweater_number} unresolved")
                continue
            pid, fn, ln = rmap[key]
            elements.append({
                "playerId": pid, "teamId": team_id,
                "period": sh.period, "shiftNumber": sh.shift_number,
                "startTime": _mmss(sh.start_elapsed_s), "endTime": _mmss(sh.end_elapsed_s),
                "duration": _mmss(sh.duration_s),
                "typeCode": 517, "detailCode": 0,
                "firstName": fn, "lastName": ln, "gameId": gid_int,
                "eventDescription": None, "eventDetails": None,
                "teamAbbrev": None, "teamName": None, "hexValue": None,
                "eventNumber": None, "id": None,
                "_source": SOURCE_MARKER,  # provenance marker (queryable)
            })
    return elements, warnings


def build_fallback_rows(
    game_ids: list,
    pbp_by_gid: dict,
    *,
    fetch: Optional[Callable[[Any, str], str]] = None,
    html_by_gid: Optional[dict] = None,
) -> tuple[list[dict], list[str]]:
    """Build raw_shift_charts rows (one per game) for the empty-shift fallback.

    Each row matches the shape the JSON path writes: {id, game_id, data}. The
    ``data`` element list is left as a Python list here; the loader serializes it
    to a JSON string (same as the JSON path), so downstream stg_shifts is
    identical regardless of source.

    Returns (rows, warnings). Games with no resolvable pbp, or that produced zero
    elements, are SKIPPED (never written as empties) and reported in warnings.
    """
    rows: list[dict] = []
    warnings: list[str] = []
    for gid in game_ids:
        pbp = pbp_by_gid.get(gid)
        if pbp is None:
            warnings.append(f"{gid} no play-by-play in memory; skipped")
            continue
        html_by_side = html_by_gid.get(gid) if html_by_gid else None
        elements, warns = build_shift_elements(
            gid, pbp, fetch=fetch, html_by_side=html_by_side)
        warnings.extend(warns)
        if not elements:
            warnings.append(f"{gid} HTML fallback produced 0 shifts; skipped")
            continue
        rows.append({"id": gid, "game_id": gid, "data": elements})
    return rows, warnings
