"""Filesystem layout helpers.

The preamble fixes the game-scoped raw layout:
    data/raw/{season}/{gameId}/shifts.json | pbp.json | boxscore.json

Two auxiliary resources (schedule per club+season, scores per date) are not
game-scoped; they live under reserved ``_schedule`` / ``_scores`` prefixes that
cannot collide with a numeric season directory.
"""

from __future__ import annotations

from pathlib import Path

from . import config


def season_for_game(game_id: str) -> str:
    """Return the 8-digit season id (e.g. ``20232024``) for a game id.

    Game id = {season_start_year:4}{type:2}{game_number:4}. The season spans
    start_year..start_year+1.
    """
    gid = str(game_id)
    if len(gid) != 10 or not gid.isdigit():
        raise ValueError(f"game_id must be 10 digits, got {game_id!r}")
    start_year = int(gid[:4])
    return f"{start_year}{start_year + 1}"


def game_type(game_id: str) -> str:
    """Return the 2-digit game-type component (``01`` pre, ``02`` reg, ``03`` po)."""
    return str(game_id)[4:6]


def raw_game_dir(game_id: str) -> Path:
    return config.RAW_DIR / season_for_game(game_id) / str(game_id)


def raw_game_path(game_id: str, kind: str) -> Path:
    """kind in {'shifts', 'pbp', 'boxscore'}."""
    if kind not in {"shifts", "pbp", "boxscore"}:
        raise ValueError(f"unknown game resource kind: {kind!r}")
    return raw_game_dir(game_id) / f"{kind}.json"


def raw_schedule_path(team: str, season_id: str) -> Path:
    return config.RAW_DIR / "_schedule" / f"{team.upper()}_{season_id}.json"


def raw_score_path(date: str) -> Path:
    """date is YYYY-MM-DD."""
    return config.RAW_DIR / "_scores" / f"{date}.json"


def ensure_parent(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    return path
