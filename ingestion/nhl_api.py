"""Client for NHL API data ingestion."""

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

BASE_URL = "https://api-web.nhle.com"


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
