"""Client for NHL API data ingestion."""

import json
import logging
import os
from pathlib import Path

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

logger = logging.getLogger(__name__)

BASE_URL = "https://api-web.nhle.com"
# Shift charts live on the stats REST host, not the api-web host.
STATS_REST_URL = "https://api.nhle.com/stats/rest/en"
# ppt-replay sprite files live on a Cloudflare-fronted host that 403s a bare request;
# it requires an nhl.com referer + a browser User-Agent (verified: plain httpx with
# these headers returns 200, no curl-impersonate needed).
WSR_HEADERS = {
    "Referer": "https://www.nhl.com/",
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
}
# Sprite files are immutable once a game is final; cache them on disk so re-runs of a
# backfill don't re-hit the host. Override with PPT_REPLAY_CACHE_DIR.
PPT_CACHE_DIR = Path(os.environ.get("PPT_REPLAY_CACHE_DIR", Path(__file__).parent.parent / "scripts" / "ppt_cache"))


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
        Full Edge payload dict, or None when the entity has no Edge data for that
        (season, gameType, report) — many skaters legitimately 404. A 404 returns
        None immediately (NOT retried); transient 429/5xx still retry via tenacity.
    """
    url = f"{BASE_URL}/v1/edge/{entity}-{report}/{entity_id}/{season}/{game_type}"
    response = httpx.get(url, timeout=30.0)
    if response.status_code == 404:
        return None
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
def get_player_landing(player_id: str) -> dict:
    """Fetch a player's bio/landing payload (Phase 4.4).

    Source: api-web.nhle.com/v1/player/{id}/landing. Carries birthDate,
    heightInInches, weightInPounds, shootsCatches, position — the bio needed for
    age curves and career twins (not present in boxscore rosterSpots).
    """
    url = f"{BASE_URL}/v1/player/{player_id}/landing"
    response = httpx.get(url, timeout=30.0)
    response.raise_for_status()
    return response.json()


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
def get_prospects(team_abbrev: str) -> dict:
    """Fetch a team's official prospect list (Trade tool futures layer).

    Source: api-web.nhle.com/v1/prospects/{TEAM}. Returns forwards/defensemen/goalies
    arrays of the org's controlled prospects (id, name, positionCode, birthDate,
    height/weight). Bounds the prospect universe to each org's published list.
    """
    url = f"{BASE_URL}/v1/prospects/{team_abbrev}"
    response = httpx.get(url, timeout=30.0)
    response.raise_for_status()
    return response.json()


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
def get_draft_picks(year: int | str, round: str | int = "all") -> dict:
    """Fetch historical draft RESULTS — every pick of a draft and the player taken.

    Source: api-web.nhle.com/v1/draft/picks/{year}/{round}. The {round} arg does NOT
    filter the payload (every round is always returned); pass "all". Returns
    {draftYear, draftYears, selectableRounds, state, picks[]}, where each pick carries
    round / pickInRound / overallPick / teamId / teamAbbrev and the player's name,
    positionCode, countryCode, height, weight, amateurLeague, amateurClubName.

    IMPORTANT: the payload carries NO player id (verified all years 1979-2025; see
    scripts/DRAFT_RESULTS_FINDINGS.md). player_id is resolved downstream by joining
    (draft_year, overall_pick) to each player's landing draftDetails — never by name.

    This is DISTINCT from raw_draft_picks (future pick ownership, ingest_futures.py):
    this is the historical record of who was actually selected at each slot.
    """
    url = f"{BASE_URL}/v1/draft/picks/{year}/{round}"
    response = httpx.get(url, timeout=30.0)
    response.raise_for_status()
    return response.json()


def season_to_api8(season: str) -> str:
    """Convert a season string "YYYY-YY" -> the 8-digit form the roster API wants.

    "2024-25" -> "20242025". The /roster/{TEAM}/{season8} path uses the 8-digit form.
    """
    start = int(season[:4])
    return f"{start}{start + 1}"


def api8_to_season(season8: str | int) -> str:
    """Convert the API's 8-digit season -> human "YYYY-YY". 20242025 -> "2024-25"."""
    s = str(season8)
    return f"{s[:4]}-{s[6:8]}"


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
def get_roster_seasons(team_abbrev: str) -> list[int]:
    """List every season (8-digit ints) a team has a published roster for.

    Source: api-web.nhle.com/v1/roster-season/{TEAM} -> e.g. [19271928, ..., 20252026].
    The max() is the current/latest published season — how we resolve "current"
    deterministically without the /roster/{TEAM}/current 307 redirect.
    """
    url = f"{BASE_URL}/v1/roster-season/{team_abbrev}"
    response = httpx.get(url, timeout=30.0)
    response.raise_for_status()
    return [int(s) for s in response.json()]


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
def get_roster_for_season8(team_abbrev: str, season8: str | int) -> dict:
    """Fetch a team's roster for an 8-digit season (the endpoint that actually serves data).

    Source: api-web.nhle.com/v1/roster/{TEAM}/{season8}. Returns {forwards, defensemen,
    goalies}; each player object carries id, headshot, firstName/lastName (localized
    objects), sweaterNumber, positionCode, shootsCatches, height/weight, birth fields.
    There is NO team field on the player object — affiliation is implied by the per-team
    endpoint, so callers tag rows with the team_abbrev they requested. Shape verified via
    scripts/smoke_ingest_roster.py against real output (see scripts/ROSTER_FINDINGS.md).
    """
    url = f"{BASE_URL}/v1/roster/{team_abbrev}/{season8}"
    response = httpx.get(url, timeout=30.0)
    response.raise_for_status()
    return response.json()


def get_roster(team_abbrev: str) -> dict:
    """Fetch a team's CURRENT active roster (live membership, not game-derived).

    This is the live source of truth for who is on a club RIGHT NOW, so an offseason
    trade is reflected before the player dresses for a game.

    ENDPOINT DEVIATION (the API wins over the plan): the planned /roster/{TEAM}/current
    is a 307 redirect (empty body; httpx won't follow it by default and it can land on an
    unpublished season in the offseason). We instead resolve "current" deterministically
    as max(/roster-season/{TEAM}) and fetch that season's roster — both confirmed-200,
    fully-seen schemas. max(roster-season) becomes the new season the instant NHL
    publishes it, which is exactly the semantics /current points to.

    Returns the {forwards, defensemen, goalies} payload with two convenience keys added:
    "team_abbrev" (the team requested) and "season8" (the resolved season), so the
    loader/refresh can tag each row without re-deriving them.

    NOTE (membership != performance): this updates the player's TEAM LABEL only. A
    just-traded player has zero games with his new club, so his impact/archetype/radar/
    value still reflect old-team usage until he plays. See stg_roster_current /
    int_player_current_team and the team-roster surfaces for where this is consumed.
    """
    seasons = get_roster_seasons(team_abbrev)
    if not seasons:
        raise ValueError(f"no published roster seasons for team {team_abbrev}")
    season8 = max(seasons)
    payload = get_roster_for_season8(team_abbrev, season8)
    payload["team_abbrev"] = team_abbrev
    payload["season8"] = season8
    return payload


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
def get_players_by_current_team(team_id: int) -> dict:
    """Cross-check source: stats-REST players carrying currentTeamId directly.

    Source: api.nhle.com/stats/rest/en/players?cayenneExp=currentTeamId={id}. A second
    source of truth for current affiliation (the stats host, not api-web). Used ONLY to
    validate the api-web /roster membership during the smoke; never in the refresh path,
    so a player can't resolve to two teams.
    """
    url = f"{STATS_REST_URL}/players"
    response = httpx.get(url, params={"cayenneExp": f"currentTeamId={int(team_id)}"}, timeout=30.0)
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


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
def _fetch_ppt_metadata(game_id, event_id: int) -> dict | None:
    """Stage 1: goal metadata (carrying the sprite URL). None on 404/empty."""
    # The /goal/ path 307-redirects to /v1/ppt-replay/{gid}/{eid}; follow it.
    url = f"{BASE_URL}/v1/ppt-replay/goal/{game_id}/{event_id}"
    resp = httpx.get(url, timeout=30.0, follow_redirects=True)
    if resp.status_code == 404:
        return None
    resp.raise_for_status()
    return resp.json()


def _normalize_frames(frames: list) -> list:
    """Convert each frame's onIce MAP (keyed by dynamic entity keys) into a LIST.

    NHL serves onIce as {entityKey: {id, playerId, x, y, ...}}; BigQuery can't UNNEST a
    JSON object with dynamic keys, so we flatten onIce to an array of entity objects with
    the original map key preserved as `entityKey` (nothing is lost). Frame timeStamp and
    order are unchanged. The puck remains the entity with entityKey '1' (empty player/team).
    """
    out = []
    for fr in frames:
        on_ice = fr.get("onIce", {}) or {}
        if isinstance(on_ice, dict):
            entities = []
            for key, ent in on_ice.items():
                e = dict(ent)
                e["entityKey"] = key
                entities.append(e)
            out.append({"timeStamp": fr.get("timeStamp"), "onIce": entities})
        else:
            out.append(fr)  # already a list (defensive)
    return out


@retry(stop=stop_after_attempt(4), wait=wait_exponential(multiplier=1, min=2, max=15))
def _fetch_ppt_sprite(sprite_url: str) -> list | None:
    """Stage 2: the sprite frame array from the Cloudflare-fronted wsr host.

    Requires the nhl.com referer + browser UA (a bare request 403s). Honors 429 via
    tenacity's exponential backoff. Returns None on a confirmed 404/empty.
    """
    resp = httpx.get(sprite_url, headers=WSR_HEADERS, timeout=30.0, follow_redirects=True)
    if resp.status_code == 404:
        return None
    resp.raise_for_status()
    return resp.json()


def get_ppt_replay(game_id, event_id: int, use_cache: bool = True) -> dict | None:
    """Fetch ppt-replay goal tracking: metadata + per-frame player/puck coordinates.

    Two hops: (1) the goal metadata endpoint, which carries `goal.pptReplayUrl`;
    (2) the sprite file on wsr.nhle.com (referer/UA-gated). The sprite URL is read
    from the metadata rather than constructed, so a future scheme change can't silently
    break us. Sprites are immutable once a game is final, so they are cached on disk.

    Args:
        game_id: NHL game id.
        event_id: Play-by-play eventId of a GOAL (the /goal/ path only returns a
            full payload for actual goals).
        use_cache: Read/write the on-disk sprite cache (PPT_CACHE_DIR).

    Returns:
        {"game_id", "event_id", "goal_metadata", "frames", "frame_count"} or None if
        the event has no sprite (not a goal, or no tracking for that game).
    """
    cache_path = PPT_CACHE_DIR / f"{game_id}_ev{event_id}.json"
    if use_cache and cache_path.exists():
        try:
            return json.loads(cache_path.read_text())
        except Exception:  # noqa: BLE001 — corrupt cache entry; re-fetch
            pass

    meta = _fetch_ppt_metadata(game_id, event_id)
    if not meta:
        return None
    goal = meta.get("goal") or {}
    sprite_url = goal.get("pptReplayUrl")
    if not sprite_url:
        logger.info("ppt-replay %s/%s has no pptReplayUrl (not a tracked goal)", game_id, event_id)
        return None

    frames = _fetch_ppt_sprite(sprite_url)
    if not frames:
        return None

    result = {
        "game_id": game_id,
        "event_id": event_id,
        "goal_metadata": goal,
        "frames": _normalize_frames(frames),
        "frame_count": len(frames),
    }
    if use_cache:
        try:
            PPT_CACHE_DIR.mkdir(parents=True, exist_ok=True)
            cache_path.write_text(json.dumps(result))
        except Exception as e:  # noqa: BLE001 — cache is best-effort
            logger.warning("ppt-replay cache write failed for %s/%s: %s", game_id, event_id, e)
    return result
