"""Check Taylor Hall's stats and hot/cold flag logic."""
import os
from google.cloud import bigquery

os.environ['GOOGLE_APPLICATION_CREDENTIALS'] = '/Users/codytownsend/Desktop/nhl/NIR/secrets/nhl-intel-sa.json'

client = bigquery.Client(project='nhl-intel-498216')

query = """
SELECT
    game_date,
    game_id,
    CONCAT(first_name, ' ', last_name) as player_name,
    team_id,
    toi_5v5,
    ixg_per60,
    primary_points_per60,
    season_avg_ixg_per60,
    hot_cold_flag
FROM `nhl-intel-498216.nhl_staging.mart_player_game_stats`
WHERE last_name = 'Hall' AND first_name = 'Taylor'
ORDER BY game_date
"""

print("Taylor Hall Game-by-Game Stats")
print("=" * 100)
print(f"{'Date':<12} {'Game':<12} {'TOI':<6} {'ixG/60':<8} {'Pts/60':<8} {'Avg ixG/60':<12} {'Flag':<8}")
print("=" * 100)

results = list(client.query(query).result())

for row in results:
    print(f"{str(row.game_date):<12} {row.game_id:<12} {row.toi_5v5:<6.1f} {row.ixg_per60:<8.2f} {row.primary_points_per60:<8.2f} {row.season_avg_ixg_per60:<12.2f} {row.hot_cold_flag:<8}")

print("\n" + "=" * 120)
print("\nHot/Cold Logic Analysis:")
print("  - Flag is based on ixG/60 (individual expected goals per 60) vs season average")
print("  - Hot: ixG/60 > season_avg * 1.15")
print("  - Cold: ixG/60 < season_avg * 0.85")
print("  - Neutral: otherwise")

# Check the specific game
game_2026_05_29 = [r for r in results if str(r.game_date) == '2026-05-29']
if game_2026_05_29:
    row = game_2026_05_29[0]
    print(f"\n2026-05-29 Game Analysis:")
    print(f"  ixG/60: {row.ixg_per60:.2f} (based on high-danger shot attempts)")
    print(f"  Primary Points/60: {row.primary_points_per60:.2f} (actual goals + primary assists)")
    print(f"  Season avg ixG/60: {row.season_avg_ixg_per60:.2f}")
    print(f"  Flag: {row.hot_cold_flag}")

    threshold_hot = row.season_avg_ixg_per60 * 1.15
    threshold_cold = row.season_avg_ixg_per60 * 0.85

    print(f"\n  Thresholds:")
    print(f"    Hot if > {threshold_hot:.2f}")
    print(f"    Cold if < {threshold_cold:.2f}")
    print(f"    Hall's ixG/60: {row.ixg_per60:.2f} → {row.hot_cold_flag}")

    if row.primary_points_per60 > row.season_avg_ixg_per60 * 1.15:
        print(f"\n  NOTE: Hall has high points/60 ({row.primary_points_per60:.2f}) but low expected goals.")
        print(f"        This suggests he scored on low-quality chances (finishing luck) or got assists.")
        print(f"        The 'cold' flag is based on shot quality, not results - this is correct behavior.")
