# NHL Edge ingestion findings (Phase 1.2)

Status: **endpoints discovered and live.** The plan's assumed
`/v1/edge/skater-detail/{id}/{season}` was wrong on two counts: Edge is split into
**per-metric** endpoints, and the path carries a **gameType** segment.

## Real endpoint family (probed live, season 20242025, verified)
```
GET https://api-web.nhle.com/v1/edge/{entity}-{category}-detail/{id}/{season}/{gameType}
```
- `entity` ∈ {skater, goalie, team}
- `season` = `YYYYYYYY` (e.g. `20242025`)
- `gameType` = `2` (regular season) or `3` (playoffs)

### Confirmed working categories
| Endpoint | Top-level keys |
|---|---|
| `skater-skating-speed-detail` | `topSkatingSpeeds[10]`, `skatingSpeedDetails` |
| `skater-skating-distance-detail` | `skatingDistanceLast10`, `skatingDistanceDetails` |
| `skater-shot-speed-detail` | `hardestShots`, `shotSpeedDetails` |
| `skater-shot-location-detail` | `shotLocationDetails`, `shotLocationTotals` |
| `goalie-save-percentage-detail` | `savePctgLast10`, `savePctgDetails` |
| `team-shot-location-detail` | `shotLocationDetails`, `shotLocationTotals` |
| `skater-zone-time` (**no `-detail` suffix**) | `zoneTimeDetails[4 by strength]`, `zoneStarts` |

**Suffix quirk:** all reports end in `-detail` **except `zone-time`**. The ingestion
stores the full report path segment per entity to handle this (see `nhl_api.py`).

### Aggregation semantics (important)
Each payload is a **whole-season aggregate** for that (player/team, season,
gameType). Burst counts are season totals; the `top*`/`hardest*` arrays are the
player's N peak single moments, each tagged with the game it occurred in. So Edge
is profile/trend data joined by `(id, season, gameType)` — **never** joined to
individual plays (matches the blueprint constraint).

### Metric substructure (the useful shape)
`skatingSpeedDetails`:
- `maxSkatingSpeed`: `{imperial, metric, percentile, leagueAvg{imperial,metric}, overlay{game...}}`
- `burstsOver22`, `bursts20To22`, `bursts18To20`: each `{value, percentile, leagueAvg}`
  - e.g. Stützle 2024-25: burstsOver22 = `{value: 33, percentile: 0.9917, leagueAvg: 3.6889}`

So every Edge metric ships as **value + league percentile + league average** — we
store all three (the percentile/avg are free context the blueprint wants for the
PercentileBarList and conversion panels).

## Zone time (resolved)
`GET /v1/edge/skater-zone-time/{id}/{season}/{gameType}` (no `-detail`). Returns:
- `zoneTimeDetails`: a list of 4 rows, one per `strengthCode` (e.g. `all`, plus
  strength splits), each with `offensiveZonePctg` / `neutralZonePctg` /
  `defensiveZonePctg`, and for each a `*Percentile` and `*LeagueAvg`.
- `zoneStarts`: `offensive/neutral/defensiveZoneStartsPctg` (+ percentiles).

This is **per-skater** by strength. `team-zone-time` 404s, so team-level oz-time
for the conversion diagnosis (3.2) is derived by TOI-weighting skater zone time, or
falls back to the event-derived `mart_team_zone_time` proxy (labeled a proxy).

## Build plan (from these real fields)
1. `get_edge_skater/goalie/team(id, season, game_type, category)` in `ingestion/nhl_api.py`.
2. Raw tables `raw_edge_skaters/goalies/teams`, one row per `(id, season, gameType, category)`
   with the payload serialized (resilient to per-category shape differences).
3. `stg_edge_*` parsing typed columns (value/percentile/leagueAvg per metric; last10 where present).
4. `mart_edge_player_profile` / `mart_edge_team_profile`.
5. Backend `GET /players/{id}/edge`, `GET /teams/{id}/edge`; `refresh_edge.py` + `backfill_edge.py`.

## Season coverage
Tracking era only. Confirmed for 20242025. `explore_edge.py` records the earliest
season that returns data when the backfill runs.
