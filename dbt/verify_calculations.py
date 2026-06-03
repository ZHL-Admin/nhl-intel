from google.cloud import bigquery
import os

os.environ['GOOGLE_APPLICATION_CREDENTIALS'] = '/Users/codytownsend/Desktop/nhl/NIR/secrets/nhl-intel-sa.json'

client = bigquery.Client(project='nhl-intel-498216')

# Game 2025030314 - CAR away - CF% = 67.50%, HDCF/60 = 56.25
game_id = '2025030314'
team_id = 12  # CAR team ID (need to verify)

# First, get CAR's team_id from the game
team_query = """
SELECT DISTINCT team_id, team_abbrev
FROM `nhl-intel-498216.nhl_staging.mart_team_game_stats`
WHERE game_id = 2025030314 AND team_abbrev = 'CAR'
"""
team_result = client.query(team_query).result()
for row in team_result:
    team_id = row.team_id
    print(f"CAR team_id: {team_id}")

# Now verify shot attempts
verify_query = f"""
SELECT
  event_owner_team_id,
  COUNT(*) as shot_attempts,
  SUM(CASE WHEN is_high_danger THEN 1 ELSE 0 END) as high_danger_attempts
FROM `nhl-intel-498216.nhl_staging.int_shot_attempts`
WHERE game_id = {game_id}
GROUP BY event_owner_team_id
ORDER BY event_owner_team_id
"""

print(f"\nRaw shot attempts for game {game_id}:")
print("=" * 70)
results = client.query(verify_query).result()

car_for = 0
car_hd_for = 0
opponent_for = 0
opponent_hd_for = 0

for row in results:
    if row.event_owner_team_id == team_id:
        car_for = row.shot_attempts
        car_hd_for = row.high_danger_attempts
        print(f"CAR (team {row.event_owner_team_id}): {row.shot_attempts} shot attempts, {row.high_danger_attempts} high-danger")
    else:
        opponent_for = row.shot_attempts
        opponent_hd_for = row.high_danger_attempts
        print(f"Opponent (team {row.event_owner_team_id}): {row.shot_attempts} shot attempts, {row.high_danger_attempts} high-danger")

print("\nCalculated Metrics:")
print("=" * 70)
total_attempts = car_for + opponent_for
cf_pct = (car_for / total_attempts) * 100 if total_attempts > 0 else 0
hdcf_per60 = (car_hd_for / 48.0) * 60.0
hdca_per60 = (opponent_hd_for / 48.0) * 60.0

print(f"CF%: {car_for}/{total_attempts} = {cf_pct:.2f}%")
print(f"HDCF/60: ({car_hd_for}/48)*60 = {hdcf_per60:.2f}")
print(f"HDCA/60: ({opponent_hd_for}/48)*60 = {hdca_per60:.2f}")

print("\nExpected from mart_team_game_stats:")
print("=" * 70)
print("CF%: 67.50%")
print("HDCF/60: 56.25")
print("HDCA/60: 22.50")

print("\n✓ Calculations verified!" if abs(cf_pct - 67.50) < 0.01 else "\n✗ Mismatch detected!")
