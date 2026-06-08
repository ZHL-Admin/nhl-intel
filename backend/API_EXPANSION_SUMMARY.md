# Backend API Expansion Summary

## Status: Backend Complete & Deployed ✓

The FastAPI backend has been fully expanded to expose all new mart layer data and deployed to production at:
**https://nhl-dashboard-api-1025423874823.us-central1.run.app**

All backend work completed:
- ✓ Pydantic schemas updated with new fields
- ✓ BigQuery service layer with 9 new query functions
- ✓ All routers updated with new endpoints and fields
- ✓ Caching configuration added for new endpoints
- ✓ Local testing passed
- ✓ Deployed to Cloud Run (revision: nhl-dashboard-api-00020-sfd)

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

## Completed Work

### BigQuery Service Layer ✓
All 9 new query functions implemented in backend/services/bigquery.py:
- `get_game_shots()` - Fetch shot coordinates from int_shot_types with situation filtering
- `get_xg_worm()` - Fetch cumulative xG differential for worm charts
- `get_team_zone_time()` - Fetch zone time percentages from mart_team_zone_time
- `get_team_faceoffs()` - Fetch faceoff statistics from mart_team_faceoffs
- `get_team_situational()` - Fetch situational breakdowns from mart_team_stats_situational
- `get_player_situational()` - Fetch player stats by situation
- `get_player_zone_deployment()` - Fetch zone deployment stats
- `get_player_shooting_luck()` - Fetch shooting luck metrics
- `get_player_relative()` - Fetch relative performance metrics

### Router Updates ✓

**backend/routers/games.py:**
- ✓ Updated `GET /games/{game_id}` to include all period breakdown columns
- ✓ Updated `GET /games/{game_id}/players` to include new player fields (first_assists, second_assists, ihdcf, pim, rush_attempts)
- ✓ Updated `GET /games/{game_id}/shots?situation=all` to use int_shot_types with situation filtering
- ✓ Added `GET /games/{game_id}/xgworm?situation=all` for cumulative xG worm chart data
- ✓ Fixed season format conversion (string "YYYY-YY" to integer YYYYYYYY)

**backend/routers/teams.py:**
- ✓ Updated `GET /teams/{team_id}` to include zone time and faceoff percentages
- ✓ Added `GET /teams/{team_id}/deployment?season=current` for player zone deployment
- ✓ Added `GET /teams/{team_id}/situational?game_id={id}` for situational breakdowns

**backend/routers/players.py:**
- ✓ Updated `GET /players/{player_id}` to include zone deployment, shooting luck, and relative stats
- ✓ Updated `GET /players/{player_id}/shots` to use int_shot_types
- ✓ Added `GET /players/{player_id}/situational?season=current` for situational breakdowns

### Cache Configuration ✓
All new endpoints configured with appropriate TTLs:
- `/games/{id}/shots`: 24 hours (86400s)
- `/games/{id}/xgworm`: 24 hours (86400s)
- `/teams/{id}/deployment`: 6 hours (21600s)
- `/teams/{id}/situational`: 6 hours (21600s)
- `/players/{id}/situational`: 6 hours (21600s)

### Testing & Deployment ✓
- ✓ Local testing passed for game detail endpoint with period breakdowns
- ✓ Deployed to Cloud Run (revision: nhl-dashboard-api-00020-sfd)
- ✓ Production verification passed

## Remaining Work

### Frontend API Types (frontend/src/api/types.ts)
Create TypeScript interfaces matching the new Pydantic schemas:
- XGWormPoint
- PlayerZoneDeployment
- PlayerSituational
- TeamSituational
- ShotData
- Update existing types with new fields (TeamGameStats, PlayerGameStats, TeamDetail, PlayerDetail, ShotAttempt)
