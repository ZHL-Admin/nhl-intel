"""Shared fixtures. Ensures the cached game payloads the parser tests rely on
are present (fetching once if missing), so `make test` is reliable after a
fresh checkout. Network is only touched on the first run."""

from __future__ import annotations

import pytest

from atlas import fetch, paths
from atlas.client import AtlasClient

# Modern fixtures with known-good shift + pbp coverage.
FIXTURE_GAMES = ["2023020204", "2023030411"]


@pytest.fixture(scope="session", autouse=True)
def ensure_fixtures() -> None:
    missing = [
        g for g in FIXTURE_GAMES
        if not all(paths.raw_game_path(g, k).exists() for k in ("shifts", "pbp", "boxscore"))
    ]
    if not missing:
        return
    with AtlasClient() as client:
        for g in missing:
            for kind in ("shifts", "pbp", "boxscore"):
                fetch.game_resource(client, g, kind)
