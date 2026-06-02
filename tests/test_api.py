"""Simple sanity check for NHL API connectivity."""

from datetime import datetime, timedelta, UTC
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from ingestion.nhl_api import get_schedule


def test_fetch_schedule():
    """Find most recent date with games and print game IDs."""
    # Look back up to 7 days to find games
    for days_back in range(1, 8):
        target_date = (datetime.now(UTC) - timedelta(days=days_back)).date().isoformat()
        print(f"Checking {target_date}...")

        schedule_data = get_schedule(target_date)
        game_week = schedule_data.get("gameWeek", [])

        for day in game_week:
            games = day.get("games", [])
            if games:
                print(f"\nFound {len(games)} game(s) on {target_date}:")
                for game in games:
                    game_id = game.get("id")
                    away_team = game.get("awayTeam", {}).get("abbrev", "UNK")
                    home_team = game.get("homeTeam", {}).get("abbrev", "UNK")
                    print(f"  Game ID: {game_id} - {away_team} @ {home_team}")
                return target_date

    print("\nNo games found in the last 7 days")


if __name__ == "__main__":
    test_fetch_schedule()
