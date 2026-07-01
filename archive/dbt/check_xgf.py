"""Check if xgf_pct exists in mart_team_game_stats."""
from google.cloud import bigquery
import os

os.environ['GOOGLE_APPLICATION_CREDENTIALS'] = '/Users/codytownsend/Desktop/nhl/NIR/secrets/nhl-intel-sa.json'

client = bigquery.Client(project='nhl-intel-498216')

# Get schema
schema_query = """
SELECT column_name, data_type
FROM `nhl-intel-498216.nhl_staging.INFORMATION_SCHEMA.COLUMNS`
WHERE table_name = 'mart_team_game_stats'
ORDER BY ordinal_position
"""

print("mart_team_game_stats columns:")
print("=" * 70)
has_xgf_pct = False
for row in client.query(schema_query).result():
    print(f"  {row.column_name}: {row.data_type}")
    if row.column_name == 'xgf_pct':
        has_xgf_pct = True

print(f"\nxgf_pct exists: {has_xgf_pct}")
