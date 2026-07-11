"""Typed parsers for cached shift and play-by-play payloads.

``parse_shifts`` and ``parse_pbp`` read the on-disk cache (never the network)
and return typed polars frames. Parsing is pure and deterministic so tests can
assert exact row counts and invariants against the cached fixtures.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import polars as pl

from . import config, paths

# ---------------------------------------------------------------------------
# Schemas (explicit so downstream code and tests can rely on dtypes)
# ---------------------------------------------------------------------------
SHIFT_SCHEMA: dict[str, Any] = {
    "game_id": pl.Int64,
    "player_id": pl.Int64,
    "team_id": pl.Int64,
    "team_abbrev": pl.Utf8,
    "period": pl.Int64,
    "shift_number": pl.Int64,
    "start_s": pl.Int64,        # seconds elapsed within the period
    "end_s": pl.Int64,          # seconds elapsed within the period
    "duration_s": pl.Int64,     # end_s - start_s
    "game_elapsed_start_s": pl.Int64,  # absolute game seconds (regulation math)
    "first_name": pl.Utf8,
    "last_name": pl.Utf8,
}

PBP_SCHEMA: dict[str, Any] = {
    "game_id": pl.Int64,
    "event_id": pl.Int64,
    "sort_order": pl.Int64,
    "period": pl.Int64,
    "period_type": pl.Utf8,
    "time_in_period_s": pl.Int64,
    "time_remaining_s": pl.Int64,
    "situation_code": pl.Utf8,
    "home_defending_side": pl.Utf8,
    "type_code": pl.Int64,
    "type_desc_key": pl.Utf8,
    "event_owner_team_id": pl.Int64,
    "x_coord": pl.Int64,
    "y_coord": pl.Int64,
    "zone_code": pl.Utf8,
    "details_json": pl.Utf8,
}


def _load(game_id: str, kind: str) -> Any:
    path: Path = paths.raw_game_path(game_id, kind)
    if not path.exists():
        raise FileNotFoundError(f"cached {kind} not found for {game_id}: {path}")
    return json.loads(path.read_text())


def mmss_to_seconds(value: str | None) -> int | None:
    if value is None or value == "":
        return None
    minutes, seconds = value.split(":")
    return int(minutes) * 60 + int(seconds)


def parse_shifts(game_id: str) -> pl.DataFrame:
    """Return real player shifts (typeCode == 517) as a typed frame.

    Embedded goal-marker rows (typeCode == 505) are dropped. Times are period
    clock "MM:SS" converted to seconds. ``game_elapsed_start_s`` uses standard
    1200s regulation periods (OT/SO caveat documented in the Phase 0 report).
    """
    payload = _load(game_id, "shifts")
    rows_in = payload.get("data", []) if isinstance(payload, dict) else []
    rows: list[dict[str, Any]] = []
    for r in rows_in:
        if r.get("typeCode") != config.SHIFT_TYPECODE_SHIFT:
            continue
        start_s = mmss_to_seconds(r.get("startTime"))
        end_s = mmss_to_seconds(r.get("endTime"))
        duration_s = None
        if start_s is not None and end_s is not None:
            duration_s = end_s - start_s
        period = r.get("period")
        game_elapsed = None
        if period is not None and start_s is not None:
            game_elapsed = (period - 1) * config.REGULATION_PERIOD_SECONDS + start_s
        rows.append({
            "game_id": r.get("gameId"),
            "player_id": r.get("playerId"),
            "team_id": r.get("teamId"),
            "team_abbrev": r.get("teamAbbrev"),
            "period": period,
            "shift_number": r.get("shiftNumber"),
            "start_s": start_s,
            "end_s": end_s,
            "duration_s": duration_s,
            "game_elapsed_start_s": game_elapsed,
            "first_name": r.get("firstName"),
            "last_name": r.get("lastName"),
        })
    return pl.DataFrame(rows, schema=SHIFT_SCHEMA, orient="row")


def parse_pbp(game_id: str) -> pl.DataFrame:
    """Return play-by-play events as a typed frame. Coordinates, zone, and
    event-owner team are lifted out of ``details``; the full details object is
    retained as a JSON string for event-specific parsing in later phases."""
    payload = _load(game_id, "pbp")
    plays = payload.get("plays", []) if isinstance(payload, dict) else []
    rows: list[dict[str, Any]] = []
    for p in plays:
        details = p.get("details") if isinstance(p.get("details"), dict) else {}
        pd = p.get("periodDescriptor") or {}
        rows.append({
            "game_id": payload.get("id"),
            "event_id": p.get("eventId"),
            "sort_order": p.get("sortOrder"),
            "period": pd.get("number"),
            "period_type": pd.get("periodType"),
            "time_in_period_s": mmss_to_seconds(p.get("timeInPeriod")),
            "time_remaining_s": mmss_to_seconds(p.get("timeRemaining")),
            "situation_code": p.get("situationCode"),
            "home_defending_side": p.get("homeTeamDefendingSide"),
            "type_code": p.get("typeCode"),
            "type_desc_key": p.get("typeDescKey"),
            "event_owner_team_id": details.get("eventOwnerTeamId"),
            "x_coord": details.get("xCoord"),
            "y_coord": details.get("yCoord"),
            "zone_code": details.get("zoneCode"),
            "details_json": json.dumps(details, sort_keys=True),
        })
    return pl.DataFrame(rows, schema=PBP_SCHEMA, orient="row")


def boxscore_player_ids(game_id: str) -> set[int]:
    """All playerId values in the boxscore (used to validate shift players)."""
    payload = _load(game_id, "boxscore")
    ids: set[int] = set()

    def walk(o: Any) -> None:
        if isinstance(o, dict):
            for k, v in o.items():
                if k == "playerId" and isinstance(v, int):
                    ids.add(v)
                else:
                    walk(v)
        elif isinstance(o, list):
            for x in o:
                walk(x)

    walk(payload)
    return ids
