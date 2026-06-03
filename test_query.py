"""Test the query module."""
import os
import sys

sys.path.insert(0, '/Users/codytownsend/Desktop/nhl/NIR')

os.environ['GOOGLE_APPLICATION_CREDENTIALS'] = '/Users/codytownsend/Desktop/nhl/NIR/secrets/nhl-intel-sa.json'

from reporting.query import get_daily_report_data

# Test with date that has data
date = "2026-05-29"
results = get_daily_report_data(date)

print(f"Found {len(results)} rows for {date}")
print("=" * 80)

for row in results[:2]:
    print(f"\nGame {row['game_id']}: {row['team_abbrev']} ({row['home_away']})")
    print(f"  Score: {row['goals_for']}-{row['goals_against']}")
    print(f"  CF%: {row['cf_pct']:.1%}" if row['cf_pct'] else "  CF%: None")
    print(f"  Top Player: {row['top_player_name']} ({row['top_player_hot_cold']})" if row['top_player_name'] else "  Top Player: None")
