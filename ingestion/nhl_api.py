"""Client for NHL API data ingestion."""

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

BASE_URL = "https://api-web.nhle.com"
# Shift charts live on the stats REST host, not the api-web host.
STATS_REST_URL = "https://api.nhle.com/stats/rest/en"


def derive_season_from_game_id(game_id: int) -> str:
    """Derive season string from NHL game ID.

    NHL game IDs follow the format: SSSSTTNNNN where:
    - SSSS is the season start year (e.g., 2024 for 2024-25)
    - TT is the game type (02 = regular season, 03 = playoffs)
    - NNNN is the game number

    Args:
        game_id: NHL game ID as an integer.

    Returns:
        Season string in format "YYYY-YY" (e.g., "2024-25").
    """
    game_id_str = str(game_id)
    start_year = int(game_id_str[:4])
    end_year = start_year + 1
    return f"{start_year}-{str(end_year)[2:]}"


# Retry on 429 to handle NHL API rate limiting
@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
def get_schedule(date: str) -> dict:
    """Fetch all games scheduled for a given date.

    Args:
        date: Date string in YYYY-MM-DD format.

    Returns:
        Full API response dict containing game schedule data.
    """
    url = f"{BASE_URL}/v1/schedule/{date}"
    response = httpx.get(url, timeout=30.0)
    response.raise_for_status()
    return response.json()


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
def get_boxscore(game_id: str) -> dict:
    """Fetch boxscore data for a single game.

    Args:
        game_id: NHL game ID.

    Returns:
        Full boxscore API response dict.
    """
    url = f"{BASE_URL}/v1/gamecenter/{game_id}/boxscore"
    response = httpx.get(url, timeout=30.0)
    response.raise_for_status()
    return response.json()


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
def get_play_by_play(game_id: str) -> dict:
    """Fetch play-by-play event data for a single game.

    Args:
        game_id: NHL game ID.

    Returns:
        Full play-by-play API response dict.
    """
    url = f"{BASE_URL}/v1/gamecenter/{game_id}/play-by-play"
    response = httpx.get(url, timeout=30.0)
    response.raise_for_status()
    return response.json()


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
def get_shift_charts(game_id: str) -> dict:
    """Fetch shift-chart data for a single game.

    Source: api.nhle.com/stats/rest/en/shiftcharts?cayenneExp=gameId={id}

    Returns a dict with a "data" array; each element is one shift with fields
    including playerId, teamId, period, startTime/endTime ("MM:SS" within period),
    duration, shiftNumber, typeCode, eventNumber.

    Note on typeCode (verified empirically, not per the original plan text):
    typeCode 517 rows are REAL shifts; typeCode 505 rows are goal-event
    annotations and carry a null/empty duration. The robust rule for building
    shift intervals is therefore to exclude rows with a null/empty duration.

    Args:
        game_id: NHL game ID.

    Returns:
        Full shift-charts API response dict ({"data": [...], "total": N}).
    """
    url = f"{STATS_REST_URL}/shiftcharts"
    response = httpx.get(url, params={"cayenneExp": f"gameId={game_id}"}, timeout=30.0)
    response.raise_for_status()
    return response.json()


# NHL Edge reports confirmed live (see scripts/EDGE_FINDINGS.md). Each endpoint is a
# whole-season aggregate; metrics ship as value + league percentile + leagueAvg.
# NOTE the suffix is inconsistent: most reports end in "-detail", but "zone-time"
# does NOT. We therefore store the full report path segment per entity.
EDGE_SKATER_REPORTS = (
    "skating-speed-detail",
    "skating-distance-detail",
    "shot-speed-detail",
    "shot-location-detail",
    "zone-time",
)
EDGE_GOALIE_REPORTS = ("save-percentage-detail",)
EDGE_TEAM_REPORTS = ("shot-location-detail",)


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
def get_edge_detail(entity: str, entity_id: str, season: str, game_type: int, report: str) -> dict:
    """Fetch one NHL Edge per-metric report payload (season aggregate).

    Endpoint family (verified):
        GET /v1/edge/{entity}-{report}/{id}/{season}/{gameType}
    where ``report`` is the full path segment, e.g. "skating-speed-detail" or
    "zone-time" (the latter intentionally has no "-detail" suffix).

    Args:
        entity: One of "skater", "goalie", "team".
        entity_id: Player id (skater/goalie) or team id.
        season: Season as YYYYYYYY (e.g. "20242025").
        game_type: 2 = regular season, 3 = playoffs.
        report: Full report path segment.

    Returns:
        Full Edge payload dict for the (entity, season, gameType).
    """
    url = f"{BASE_URL}/v1/edge/{entity}-{report}/{entity_id}/{season}/{game_type}"
    response = httpx.get(url, timeout=30.0)
    response.raise_for_status()
    return response.json()


def get_edge_skater(player_id: str, season: str, game_type: int = 2, report: str = "skating-speed-detail") -> dict:
    """Fetch a skater's NHL Edge report (default skating-speed-detail)."""
    return get_edge_detail("skater", player_id, season, game_type, report)


def get_edge_goalie(player_id: str, season: str, game_type: int = 2, report: str = "save-percentage-detail") -> dict:
    """Fetch a goalie's NHL Edge report (default save-percentage-detail)."""
    return get_edge_detail("goalie", player_id, season, game_type, report)


def get_edge_team(team_id: str, season: str, game_type: int = 2, report: str = "shot-location-detail") -> dict:
    """Fetch a team's NHL Edge report (default shot-location-detail)."""
    return get_edge_detail("team", team_id, season, game_type, report)


# ---------------------------------------------------------------------------
# Phase 1.3 surfaces: stats-REST faceoffs, game landing/right-rail, partner odds,
# glossary, standings-by-date. See scripts/STATSREST_FINDINGS.md for the probed
# report names and payload shapes that justify the parsing choices below.
# ---------------------------------------------------------------------------


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
def _get_statsrest_page(report: str, season_id: str, game_type: int, limit: int, start: int) -> dict:
    """Fetch one page of a stats-REST skater report (internal helper)."""
    url = f"{STATS_REST_URL}/skater/{report}"
    params = {
        "cayenneExp": f"seasonId={season_id} and gameTypeId={game_type}",
        "limit": limit,
        "start": start,
    }
    response = httpx.get(url, params=params, timeout=30.0)
    response.raise_for_status()
    return response.json()


def get_skater_faceoffs(season_id: str, game_type: int = 2, limit: int = 100) -> list[dict]:
    """Fetch every skater's season faceoff splits from the stats REST API.

    Report: GET api.nhle.com/stats/rest/en/skater/faceoffwins (richest report,
    carrying zone splits AND ev/pp/sh splits; faceoffpercentages is a redundant
    percentage-only view — see STATSREST_FINDINGS.md). Pages with limit/start
    until the reported total is reached.

    Args:
        season_id: Season as YYYYYYYY (e.g. "20242025").
        game_type: 2 = regular season, 3 = playoffs.
        limit: Page size (NHL caps effective page size around 100).

    Returns:
        List of per-player faceoff records (flat dicts) for the season.
    """
    out: list[dict] = []
    start = 0
    while True:
        page = _get_statsrest_page("faceoffwins", season_id, game_type, limit, start)
        rows = page.get("data", [])
        out.extend(rows)
        total = page.get("total", 0)
        start += limit
        if start >= total or not rows:
            break
    return out


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
def get_game_landing(game_id: str) -> dict:
    """Fetch the gamecenter landing payload for a game.

    Source: api-web.nhle.com/v1/gamecenter/{id}/landing. Carries summary.scoring
    (per-goal highlight links: goals[].highlightClipSharingUrl, .pptReplayUrl),
    three stars, and penalties.
    """
    url = f"{BASE_URL}/v1/gamecenter/{game_id}/landing"
    response = httpx.get(url, timeout=30.0)
    response.raise_for_status()
    return response.json()


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
def get_game_right_rail(game_id: str) -> dict:
    """Fetch the gamecenter right-rail payload for a game.

    Source: api-web.nhle.com/v1/gamecenter/{id}/right-rail. Carries gameInfo
    (scratches + coaches per team), seasonSeries + seasonSeriesWins, and
    teamGameStats (category/awayValue/homeValue comparison rows).
    """
    url = f"{BASE_URL}/v1/gamecenter/{game_id}/right-rail"
    response = httpx.get(url, timeout=30.0)
    response.raise_for_status()
    return response.json()


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
def get_partner_odds(country_code: str = "US") -> dict:
    """Fetch the current partner sportsbook odds snapshot.

    Source: api-web.nhle.com/v1/partner-game/{countryCode}/now. Returns
    currentOddsDate, bettingPartner, and a games[] array (empty in the offseason).
    INTERNAL CALIBRATION ONLY per blueprint 13.2 — never exposed via API/UI.
    """
    url = f"{BASE_URL}/v1/partner-game/{country_code}/now"
    response = httpx.get(url, timeout=30.0)
    response.raise_for_status()
    return response.json()


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
def get_glossary() -> dict:
    """Fetch the stats-REST glossary (term definitions) for Phase 6 concept cards.

    Source: api.nhle.com/stats/rest/en/glossary (the api-web /v1/glossary path is
    dead — 404). Returns {"data": [{id, abbreviation, definition}, ...], "total"}.
    """
    url = f"{STATS_REST_URL}/glossary"
    response = httpx.get(url, timeout=30.0)
    response.raise_for_status()
    return response.json()


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
def get_standings_by_date(date: str) -> dict:
    """Fetch league standings as of a given date.

    Source: api-web.nhle.com/v1/standings/{date} (date as YYYY-MM-DD). Returns
    {"standings": [...]} with one row per team carrying points/wins/losses/otLosses,
    league/conference/division sequences (ranks), and last-10 (l10*) splits.
    """
    url = f"{BASE_URL}/v1/standings/{date}"
    response = httpx.get(url, timeout=30.0)
    response.raise_for_status()
    return response.json()
