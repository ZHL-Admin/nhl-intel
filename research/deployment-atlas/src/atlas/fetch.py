"""High-level, typed fetch helpers.

Each helper knows the URL template, cache path, and manifest key for one
resource kind. ``*_result`` variants never raise (used by ingestion so old-game
404s become findings); the plain variants return parsed JSON and raise on error.
"""

from __future__ import annotations

import json
from typing import Any

from . import config, paths
from .client import AtlasClient, FetchResult


def _json(data: bytes) -> Any:
    return json.loads(data.decode("utf-8"))


def _spec(game_id: str, kind: str) -> tuple[str, Any, str]:
    url = {
        "shifts": config.SHIFTCHARTS_URL,
        "pbp": config.PBP_URL,
        "boxscore": config.BOXSCORE_URL,
    }[kind].format(game_id=game_id)
    return url, paths.raw_game_path(game_id, kind), f"{game_id}/{kind}"


def game_resource(client: AtlasClient, game_id: str, kind: str, *, force: bool = False) -> Any:
    url, path, key = _spec(game_id, kind)
    return _json(client.fetch(url, path, key=key, force=force))


def game_resource_result(client: AtlasClient, game_id: str, kind: str, *,
                         force: bool = False) -> FetchResult:
    url, path, key = _spec(game_id, kind)
    return client.fetch_result(url, path, key=key, force=force)


def shifts(client: AtlasClient, game_id: str, *, force: bool = False) -> Any:
    return game_resource(client, game_id, "shifts", force=force)


def pbp(client: AtlasClient, game_id: str, *, force: bool = False) -> Any:
    return game_resource(client, game_id, "pbp", force=force)


def boxscore(client: AtlasClient, game_id: str, *, force: bool = False) -> Any:
    return game_resource(client, game_id, "boxscore", force=force)


def club_schedule(client: AtlasClient, team: str, season_id: str, *, force: bool = False) -> Any:
    url = config.CLUB_SCHEDULE_URL.format(team=team.upper(), season_id=season_id)
    path = paths.raw_schedule_path(team, season_id)
    return _json(client.fetch(url, path, key=f"schedule/{team.upper()}/{season_id}", force=force))


def score_by_date(client: AtlasClient, date: str, *, force: bool = False) -> Any:
    url = config.SCORE_BY_DATE_URL.format(date=date)
    path = paths.raw_score_path(date)
    return _json(client.fetch(url, path, key=f"score/{date}", force=force))
