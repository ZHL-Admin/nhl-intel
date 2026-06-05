# NHL Analytics Dashboard API

FastAPI backend for the NHL Analytics Dashboard. Serves as a thin API layer over BigQuery mart tables.

## Deployment

The backend is deployed to GCP Cloud Run and accessible at:

**Production URL:** https://nhl-dashboard-api-1025423874823.us-central1.run.app

## API Endpoints

### Health Check
- `GET /` - Health check endpoint
- `GET /health` - Health check for Cloud Run

### Games
- `GET /games/` - List games with optional filters (start_date, end_date, team_id, season)
- `GET /games/{game_id}` - Get detailed game information
- `GET /games/{game_id}/players` - Get player stats for a specific game

### Teams
- `GET /teams/{team_id}` - Get team details and season stats
- `GET /teams/{team_id}/trends` - Get rolling trend data for a team
- `GET /teams/{team_id}/roster` - Get team roster with player stats
- `GET /teams/{team_id}/vs/{opponent_id}` - Get head-to-head stats against specific opponent

### Players
- `GET /players/{player_id}` - Get player details and season stats
- `GET /players/{player_id}/trends` - Get rolling trend data for a player
- `GET /players/{player_id}/gamelog` - Get game-by-game log for a player
- `GET /players/{player_id}/shots` - Get shot location data for a player
- `GET /players/{player_id}/vs/{opponent_id}` - Get player stats against specific opponent

## Local Development

### Prerequisites
- Python 3.11+
- GCP service account with BigQuery access
- Environment variables configured

### Setup

1. Install dependencies:
```bash
cd backend
pip install -r requirements.txt
```

2. Configure environment:
```bash
# Create .env file in project root with:
GCP_PROJECT_ID=nhl-intel-498216
GCP_DATASET_STAGING=nhl_staging
GOOGLE_APPLICATION_CREDENTIALS=secrets/nhl-intel-sa.json
```

3. Run locally:
```bash
cd backend
uvicorn main:app --reload --port 8000
```

4. Access API documentation:
- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc

## Deployment to Cloud Run

Deploy using gcloud CLI:

```bash
cd backend
gcloud run deploy nhl-dashboard-api \
  --source . \
  --platform managed \
  --region us-central1 \
  --allow-unauthenticated \
  --service-account nhl-intel-sa@nhl-intel-498216.iam.gserviceaccount.com \
  --set-env-vars "GCP_PROJECT_ID=nhl-intel-498216,GCP_DATASET_STAGING=nhl_staging" \
  --memory 512Mi \
  --timeout 60
```

## Architecture

- **Framework:** FastAPI
- **Data Source:** BigQuery (nhl_staging dataset)
- **Caching:** In-memory caching with TTL
- **Deployment:** GCP Cloud Run with auto-scaling
- **Authentication:** Service account-based (nhl-intel-sa)

## Data Notes

- All mart tables are currently in the `nhl_staging` dataset
- Expected goals (xG) metrics are not yet available in the data pipeline
- Season parameter is optional on all endpoints; defaults to current season
- `vs opponent` endpoints return `small_sample: true` flag when fewer than 3 games exist
- Duplicate records in responses are due to upstream data pipeline issues, not API issues

## Code Standards

All code follows the standards defined in NHL_INTEL_PROJECT.md:
- Type hints on all function signatures
- Docstrings using Google style
- Minimal, purposeful comments
- Small, single-purpose functions
