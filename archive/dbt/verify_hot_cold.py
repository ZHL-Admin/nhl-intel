from google.cloud import bigquery
import os

os.environ['GOOGLE_APPLICATION_CREDENTIALS'] = '/Users/codytownsend/Desktop/nhl/NIR/secrets/nhl-intel-sa.json'

client = bigquery.Client(project='nhl-intel-498216')

# Find a player with a clear trend (hot or cold)
query = """
WITH player_data AS (
  SELECT
    player_id,
    CONCAT(first_name, ' ', last_name) as player_name,
    game_date,
    ixg_per60,
    hot_cold_flag,
    AVG(ixg_per60) OVER (PARTITION BY player_id) as player_avg
  FROM `nhl-intel-498216.nhl_staging.mart_player_game_stats`
)
SELECT
  player_name,
  game_date,
  ixg_per60,
  player_avg,
  hot_cold_flag,
  CASE
    WHEN player_avg > 0 AND ixg_per60 > player_avg * 1.15 THEN 'hot'
    WHEN player_avg > 0 AND ixg_per60 < player_avg * 0.85 THEN 'cold'
    ELSE 'neutral'
  END as calculated_flag
FROM player_data
WHERE player_id IN (
  SELECT player_id
  FROM player_data
  WHERE hot_cold_flag = 'hot'
  GROUP BY player_id
  LIMIT 1
)
ORDER BY game_date
LIMIT 5
"""

print("Hot/Cold Flag Verification:")
print("=" * 100)
results = client.query(query).result()

for row in results:
    match = "✓" if row.hot_cold_flag == row.calculated_flag else "✗"
    print(f"{match} {row.player_name} on {row.game_date}: ixG/60={row.ixg_per60:.2f}, Avg={row.player_avg:.2f}, Flag={row.hot_cold_flag} (Expected: {row.calculated_flag})")

print("\nLogic:")
print("  hot: ixG/60 > season_avg * 1.15")
print("  cold: ixG/60 < season_avg * 0.85")
print("  neutral: otherwise")
