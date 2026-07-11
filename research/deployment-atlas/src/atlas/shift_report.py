"""Parser for NHL HTML shift (Time-On-Ice) reports.

Recovers shift data for games the stats-REST shiftcharts endpoint returns empty
(563 games in 2024-26; the endpoint has no data for them, verified live). The
HTML TOI reports at
    https://www.nhl.com/scores/htmlreports/{season8}/T{H|V}{gg}.HTM
(TH = home, TV = visitor) carry every player's shift-by-shift start/end.

Report structure (verified against 2025020001):
  * player block starts with a ``playerHeading`` cell: "# LASTNAME, FIRSTNAME"
  * then a column-header row, then 6-cell shift rows:
      [shift#, period, "start_elapsed / remaining", "end_elapsed / remaining",
       duration, event(G/P)]
  * ``start_elapsed`` is time elapsed in the period, so absolute game seconds =
    (period-1)*1200 + elapsed  -- identical to stg_shifts.
  * goalies additionally emit a per-period summary table (7-cell rows) that is
    skipped (rows whose first cell is not a pure integer shift number).

The parser yields shift rows keyed by (sweater_number); the caller resolves
sweater -> player_id / team_id from the game roster (pbp rosterSpots).
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from bs4 import BeautifulSoup

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


def _period_number(label: str) -> int | None:
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


def parse_report(html: str) -> list[ReportShift]:
    """Parse one TH/TV report into shift rows (one team's players)."""
    soup = BeautifulSoup(html, "lxml")
    out: list[ReportShift] = []
    cur_sweater: int | None = None
    cur_name: str | None = None

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


def report_url(game_id: str, side: str) -> str:
    """side: 'H' (home) or 'V' (visitor)."""
    gid = str(game_id)
    year = int(gid[:4])
    season8 = f"{year}{year + 1}"
    return f"https://www.nhl.com/scores/htmlreports/{season8}/T{side}{gid[4:]}.HTM"
