"""Check mart_daily_report_feed data and schema."""
from google.cloud import bigquery
import os

os.environ['GOOGLE_APPLICATION_CREDENTIALS'] = '/Users/codytownsend/Desktop/nhl/NIR/secrets/nhl-intel-sa.json'

client = bigquery.Client(project='nhl-intel-498216')

# Get schema
schema_query = """
SELECT column_name, data_type
FROM `nhl-intel-498216.nhl_staging.INFORMATION_SCHEMA.COLUMNS`
WHERE table_name = 'mart_daily_report_feed'
ORDER BY ordinal_position
"""

print("mart_daily_report_feed Schema:")
print("=" * 70)
for row in client.query(schema_query).result():
    print(f"  {row.column_name}: {row.data_type}")

# Get most recent data
data_query = """
SELECT *
FROM `nhl-intel-498216.nhl_staging.mart_daily_report_feed`
ORDER BY game_date DESC
LIMIT 3
"""

print("\n\nMost Recent Data (3 rows):")
print("=" * 120)
for row in client.query(data_query).result():
    print(f"\nDate: {row.game_date} | Game: {row.game_id} | Team: {row.team_abbrev} ({row.home_away})")
    print(f"  Score: {row.goals_for}-{row.goals_against}")
    print(f"  CF%: {row.cf_pct:.1%}" if row.cf_pct else "  CF%: None")
    print(f"  HDCF/60: {row.hdcf_per60:.2f}, HDCA/60: {row.hdca_per60:.2f}")
    print(f"  Rolling CF% (5gp): {row.rolling_cf_pct_5gp:.1%}" if row.rolling_cf_pct_5gp else "  Rolling CF% (5gp): None")
    print(f"  Top Player: {row.top_player_name} ({row.top_player_points_per60:.2f} pts/60, {row.top_player_hot_cold})" if row.top_player_name else "  Top Player: None")
