"""Simple sanity check for NHL API connectivity."""

from datetime import datetime, timedelta
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from ingestion.nhl_api import get_schedule


def test_fetch_schedule():
    """Fetch yesterday's schedule and print game IDs."""
    yesterday = (datetime.utcnow() - timedelta(days=1)).date().isoformat()
    print(f"Fetching schedule for {yesterday}")

    schedule_data = get_schedule(yesterday)

    game_week = schedule_data.get("gameWeek", [])
    if not game_week:
        print("No games found for this date")
        return

    for day in game_week:
        games = day.get("games", [])
        if games:
            print(f"\nFound {len(games)} game(s):")
            for game in games:
                game_id = game.get("id")
                away_team = game.get("awayTeam", {}).get("abbrev", "UNK")
                home_team = game.get("homeTeam", {}).get("abbrev", "UNK")
                print(f"  Game ID: {game_id} - {away_team} @ {home_team}")


if __name__ == "__main__":
    test_fetch_schedule()
