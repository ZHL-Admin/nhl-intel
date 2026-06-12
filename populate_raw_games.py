"""Populate raw_games from existing boxscore data.

Since backfill_historical.py only loads boxscores and play-by-play,
this script creates schedule records in raw_games based on the games in raw_boxscores.
"""

import sys
from pathlib import Path
import os

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

from google.cloud import bigquery
from ingestion.loaders import load_json_to_bigquery

# Initialize BigQuery client
project_id = os.getenv("GCP_PROJECT_ID", "nhl-intel-498216")
dataset_raw = os.getenv("GCP_DATASET_RAW", "nhl_raw")
client = bigquery.Client(project=project_id)

# Query to get game list from raw_boxscores
query = f"""
SELECT DISTINCT
    gameDate,
    game_id
FROM `{project_id}.{dataset_raw}.raw_boxscores`
ORDER BY gameDate
"""

print("Querying games from raw_boxscores...")
query_job = client.query(query)
# Use to_dataframe() instead of result() to avoid API incompatibility issues
import pandas as pd
df = query_job.to_dataframe()
results = df.to_dict('records')

# Group games by date
games_by_date = {}
for row in results:
    # Convert date to string format
    game_date = row['gameDate']
    if hasattr(game_date, 'isoformat'):
        date_str = game_date.isoformat()
    else:
        date_str = str(game_date)

    if date_str not in games_by_date:
        games_by_date[date_str] = []
    games_by_date[date_str].append({'id': row['game_id']})

print(f"Found {len(games_by_date)} dates with {sum(len(g) for g in games_by_date.values())} total games")

# Create and load schedule records
for date_str, games in games_by_date.items():
    schedule_record = {
        'gameWeek': [{
            'date': date_str,
            'games': games
        }]
    }

    # Use the existing loader function which handles schema correctly
    load_json_to_bigquery(
        project_id=project_id,
        dataset_id=dataset_raw,
        table_id="raw_games",
        data=schedule_record,
        season="2024-25"  # This will be stored as string by the loader
    )

print(f"Successfully loaded {len(games_by_date)} schedule records to raw_games")
