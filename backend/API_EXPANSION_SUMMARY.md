# Backend API Expansion Summary

## Status: Schemas Updated ✓

The Pydantic schemas have been successfully updated with all new fields:

### Updated Schemas
- `TeamGameStats`: Added period-by-period breakdowns (cf_p1-3, ca_p1-3, cf_pct_p1-3, xgf_p1-3, xga_p1-3, gf_p1-3, ga_p1-3)
- `PlayerGameStats`: Added first_assists, second_assists, ihdcf, pim, rush_attempts
- `TeamDetail`: Added oz_pct, nz_pct, dz_pct, faceoff_win_pct, oz_faceoff_win_pct, nz_faceoff_win_pct, dz_faceoff_win_pct
- `PlayerDetail`: Added first_assists, second_assists, ihdcf_per60, ozs_pct, dzs_pct, nzs_pct, relative_cf_pct, relative_xgf_pct, actual_shooting_pct, expected_shooting_pct, shooting_luck_delta
- `ShotAttempt`: Updated shot_type to always be present (not just for goals)

### New Schemas
- `PlayerZoneDeployment`: For zone deployment stats
- `PlayerSituational`: For player stats by situation (5v5, PP, PK, all)
- `TeamSituational`: For team stats by situation in a game
- `ShotData`: For shot coordinates with full metadata
- `XGWormPoint`: For cumulative xG differential over time

## Remaining Work

### 1. BigQuery Service Layer (backend/services/bigquery.py)

Add these query functions:

```python
def get_game_shots(game_id: str, situation: str = "all") -> list[dict]:
    """Fetch all shot coordinates for both teams in a game from int_shot_types."""

def get_xg_worm(game_id: str, situation: str = "all") -> list[dict]:
    """Fetch cumulative xG differential data points for the xG Worm chart."""

def get_team_zone_time(team_id: str, season: str, game_id: str | None = None) -> list[dict]:
    """Fetch zone time percentages from mart_team_zone_time."""

def get_team_faceoffs(team_id: str, season: str, game_id: str | None = None) -> dict:
    """Fetch faceoff statistics from mart_team_faceoffs."""

def get_team_situational(team_id: str, game_id: str, situation: str = "all") -> dict:
    """Fetch team stats for a specific game from mart_team_stats_situational."""

def get_player_situational(player_id: str, season: str) -> list[dict]:
    """Fetch player stats by situation from mart_player_situational."""

def get_player_zone_deployment(player_id: str, season: str) -> dict:
    """Fetch zone deployment from mart_player_zone_deployment."""

def get_player_shooting_luck(player_id: str, season: str) -> dict:
    """Fetch shooting luck metrics from mart_player_shooting_luck."""

def get_player_relative(player_id: str, season: str) -> dict:
    """Fetch relative performance from mart_player_relative."""
```

### 2. Router Updates

#### backend/routers/games.py
- Update `GET /games/{game_id}` to include period columns
- Update `GET /games/{game_id}/players` to include new player fields
- Add `GET /games/{game_id}/shots?situation=all`
- Add `GET /games/{game_id}/xgworm?situation=all`

#### backend/routers/teams.py
- Update `GET /teams/{team_id}` to include zone time and faceoff stats
- Update `GET /teams/{team_id}/trends` to include zone time trends
- Add `GET /teams/{team_id}/deployment?season=current`
- Add `GET /teams/{team_id}/situational?game_id={game_id}`

#### backend/routers/players.py
- Update `GET /players/{player_id}` to include all new fields
- Update `GET /players/{player_id}/shots` to use int_shot_types
- Add `GET /players/{player_id}/situational?season=current`

### 3. Cache Configuration (backend/services/cache.py)

Add TTL settings:
- `/games/{id}/shots`: 24 hours
- `/games/{id}/xgworm`: 24 hours
- `/teams/{id}/deployment`: 6 hours
- `/teams/{id}/situational`: 6 hours
- `/players/{id}/situational`: 6 hours

### 4. Frontend API Types (frontend/src/api/types.ts)

Create TypeScript interfaces matching all new Pydantic schemas.

### 5. Testing Checklist

Local testing (uvicorn main:app --reload):
- [ ] GET /games/{recent_game_id}/shots returns shot coordinates with shot_type
- [ ] GET /games/{recent_game_id}/xgworm returns time-series xG with goal markers
- [ ] GET /games/{recent_game_id} includes period breakdown columns
- [ ] GET /teams/12 includes oz_pct, nz_pct, dz_pct, faceoff_win_pct
- [ ] GET /teams/12/trends includes zone time per game
- [ ] GET /teams/12/deployment returns player zone deployment list
- [ ] GET /teams/12/situational?game_id={id} returns situational breakdown
- [ ] GET /players/8475722 includes all new fields
- [ ] GET /players/8475722/situational returns 4 rows (5v5, pp, pk, all)
- [ ] GET /players/8475722/shots includes shot_type in response

### 6. Deployment

```bash
cd backend
gcloud run deploy nhl-dashboard-api \
  --source . \
  --platform managed \
  --region us-central1 \
  --allow-unauthenticated \
  --service-account nhl-intel-sa@nhl-intel-498216.iam.gserviceaccount.com \
  --memory 512Mi \
  --timeout 60
```

## Implementation Priority

Given context limitations, the recommended approach is:

1. Complete BigQuery service layer functions (highest priority)
2. Update existing endpoints with new fields
3. Add new endpoints one-by-one
4. Test each endpoint as it's added
5. Update frontend types after backend is stable
6. Deploy when all endpoints pass local testing

The schemas are already complete and ready to use.
