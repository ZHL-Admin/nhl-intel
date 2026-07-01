from google.cloud import bigquery
import os

os.environ['GOOGLE_APPLICATION_CREDENTIALS'] = '/Users/codytownsend/Desktop/nhl/NIR/secrets/nhl-intel-sa.json'

client = bigquery.Client(project='nhl-intel-498216')

query = """
SELECT
  game_date,
  game_id,
  team_abbrev,
  home_away,
  shot_attempts_for,
  shot_attempts_against,
  cf_pct,
  high_danger_for,
  high_danger_against,
  hdcf_per60,
  hdca_per60
FROM `nhl-intel-498216.nhl_staging.mart_team_game_stats`
ORDER BY game_date DESC
LIMIT 5
"""

query_job = client.query(query)
results = query_job.result()

print("\nRecent Game Metrics:")
print("=" * 120)
for row in results:
    print(f"\nGame: {row.game_id} | Date: {row.game_date} | Team: {row.team_abbrev} ({row.home_away})")
    print(f"  Shot Attempts: {row.shot_attempts_for} for, {row.shot_attempts_against} against")
    print(f"  CF%: {row.cf_pct:.2%}" if row.cf_pct else "  CF%: None")
    print(f"  High-Danger: {row.high_danger_for} for, {row.high_danger_against} against")
    print(f"  HDCF/60: {row.hdcf_per60:.2f}, HDCA/60: {row.hdca_per60:.2f}")
