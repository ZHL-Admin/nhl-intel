"""Simple script to load only schedule data to raw_games.

This is used when boxscores and play-by-play are already loaded
but schedule data is missing from raw_games.
"""

import os
import sys
import time
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

from ingestion.nhl_api import get_schedule
from ingestion.loaders import load_json_to_bigquery


def collect_season_schedules(season: str):
    """Collect all schedule responses for a season.

    Args:
        season: Season string in format "YYYY-YY" (e.g., "2024-25").

    Returns:
        List of schedule API responses.
    """
    start_year = int(season.split("-")[0])
    api_season_id = int(f"{start_year}{start_year + 1}")

    print(f"\nCollecting schedule data for {season} (API ID: {api_season_id})")

    schedule_responses = []
    sample_days = [1, 10, 20]

    for month_offset in range(9):  # October through June
        target_month = 10 + month_offset
        target_year = start_year

        if target_month > 12:
            target_month -= 12
            target_year += 1

        for day in sample_days:
            target_date = f"{target_year}-{target_month:02d}-{day:02d}"

            try:
                schedule_data = get_schedule(target_date)
                game_week = schedule_data.get("gameWeek", [])

                # Check if this schedule has games for our season
                has_season_games = False
                for week_day in game_week:
                    games = week_day.get("games", [])
                    for game in games:
                        game_season = game.get("season")
                        if game_season == api_season_id:
                            has_season_games = True
                            break
                    if has_season_games:
                        break

                if has_season_games:
                    schedule_responses.append(schedule_data)
                    print(f"  Collected schedule for {target_date}")

                time.sleep(0.1)  # Small delay

            except Exception as e:
                print(f"  Warning: Could not fetch schedule for {target_date}: {e}")
                continue

    print(f"\nCollected {len(schedule_responses)} schedule responses\n")
    return schedule_responses


def main():
    season = "2024-25"

    # Collect schedule data
    schedules = collect_season_schedules(season)

    if not schedules:
        print("No schedule data collected")
        return

    # Load to BigQuery
    project_id = os.getenv("GCP_PROJECT_ID")
    dataset_raw = os.getenv("GCP_DATASET_RAW", "nhl_raw")

    print(f"Loading {len(schedules)} schedule responses to {dataset_raw}.raw_games")

    load_json_to_bigquery(
        project_id=project_id,
        dataset_id=dataset_raw,
        table_id="raw_games",
        data=schedules,
        season=season,
    )

    print(f"✓ Successfully loaded schedule data")


if __name__ == "__main__":
    main()
