# Phase 1 — Data inventory & gap analysis (1.1 + 1.2)

**STOP GATE.** This is the 1.2 review artifact. No data was fetched this phase; all
evidence is from read-only reads of NIR source + free BigQuery metadata + three
small SELECTs (≤0.5 MB each). **Do not proceed to 1.3 (adapters) or any fetch
without approval.**

**Headline:** the Atlas's four hard requirements — shifts, events (coords +
penalties + goalie pulls), per-player boxscore TOI, and game enumeration — are
**already ingested in NIR's BigQuery** for the full modeling scope (2015-16 →
2025-26) and then some. The reconstruction backbone (`stg_shifts`,
`int_shift_segments`, `int_segment_context`, `int_on_ice_events`), the xG model,
and RAPM already exist. **The net new-fetch requirement for the whole scope is 2
play-by-play games.** Everything else is either direct reuse or a zero-fetch
re-parse of raw JSON already in the warehouse.

Scope: regular seasons **2015-16 → 2025-26** (playoffs cataloged, excluded from modeling).

---

## Warehouse

| item | value |
|---|---|
| Engine | **Google BigQuery** |
| Project | `nhl-intel-498216` |
| Datasets | `nhl_raw` (raw one-row-per-game JSON), `nhl_staging` (dbt), `nhl_models` (Python model outputs) |
| Access | service account `secrets/nhl-intel-sa.json` (read-only used here); `bq`/`gcloud` present |
| dbt | project `nhl_intel`, `~/.dbt/profiles.yml` → BigQuery, last run artifacts dated 2026-07-06 |

Provenance/cadence (evidence from `dags/nhl_daily.py`, `ingestion/nhl_api.py`,
`backfill_historical.py`, `scripts/ingest_shifts.py`, `deduplicate_raw_tables.py`):
all four raw tables are written by the **daily `nhl_daily` DAG** (`schedule 0 13 * * *`,
30-day lookback, `catchup=False`) via `ingestion/loaders.py` (WRITE_APPEND, autodetect),
plus one-off backfills. Backfill floor is **2010-11..2025-26** (`backfill_historical.py:569`,
`range(2010,2026)`; "2010-11 for xG depth"). Append-only; `raw_boxscores`/`raw_play_by_play`
deduped by `deduplicate_raw_tables.py`; shift/schedule backfills are idempotent by
skip-existing. No `2015` season floor exists — coverage is broader than the Atlas needs.

---

## 1.1 Inventory catalog

Columns mapped against the Atlas schemas from Phase 0 (`shifts`: player, game, period,
start_s, end_s, duration_s · `events`: coords, penalties, goalie pulls, situation).

### Raw layer — `nhl_raw` (one row per game; the true sources)

| asset | grain | Atlas-relevant contents (verified) | coverage | provenance / cadence |
|---|---|---|---|---|
| **raw_shift_charts** | 1/game; shift array as JSON string `data` | the shift feed. `typeCode 517`=shift, `505`=goal marker (null duration) | 2010-11..2025-26; **scope complete** (see coverage table) | `api.nhle.com/stats/rest/en/shiftcharts` (`ingestion/nhl_api.py:101`); daily DAG + `scripts/ingest_shifts.py` / `backfill_historical.py --tables shiftcharts`; append, skip-existing |
| **raw_play_by_play** | 1/game; `plays[]` + `rosterSpots[]` | events; `plays.details` **schema-confirmed** to carry `xCoord,yCoord,zoneCode`, penalty `descKey/committedByPlayerId/drawnByPlayerId/duration/typeCode`, `goalieInNetId`, `situationCode`, `homeTeamDefendingSide` | matches box except 2 in-scope reg games + 1 playoff | `api-web /gamecenter/{id}/play-by-play` (`nhl_api.py:85`); daily DAG + backfill; deduped |
| **raw_boxscores** | 1/game; nested teams | **`playerByGameStats.{away,home}.{forwards,defense,goalies}[].toi` present** (schema-confirmed) — per-player TOI for integrity checks | matches scope | `api-web /gamecenter/{id}/boxscore` (`nhl_api.py:69`); daily DAG + backfill; deduped |
| **raw_games** | 1/schedule-fetch; `gameWeek[].games[].{id,date}` | game-id enumeration spine | full | `api-web /schedule/{date}` (`nhl_api.py:53`); daily DAG + backfill |

### Staging — `nhl_staging` (dbt; read `dbt/models/staging/`)

| model | grain | maps to Atlas | notes |
|---|---|---|---|
| **stg_shifts** | 1 / shift / player / game | **shifts — FULL** | `game_id, season, player_id, team_id, period, shift_number, shift_start_seconds, shift_end_seconds, duration_seconds`; excludes `505` via null duration; abs time `(period-1)*1200` (matches OT amendment: period 4 → 3600); keeps `1..1200s` (drops ~0.01% degenerate/corrupt) |
| **stg_play_by_play** | 1 / event | **events — near-full** | coords `x_coord,y_coord,zone_code`; `home_team_defending_side`; penalties `committed_by_player_id, drawn_by_player_id, duration, event_owner_team_id`; goalie pulls `goalie_in_net_id`+`situation_code`. **Does NOT surface penalty `descKey` or severity `typeCode`** (present in raw) |
| **stg_boxscores** | 1 / game | game meta only | **per-player TOI NOT staged** (parses team scores/SOG only) → the one real transform gap |
| **stg_games** | 1 / game | **enumeration — FULL** | `game_id, season, game_date, game_type, game_state, teams`; `game_type` from boxscore |
| **stg_rosters** | 1 / game / player | goalie exclusion | `player_id, team_id, position_code (C/L/R/D/G)` — needed to exclude goalies from skater counts (Amendment A) |

### Intermediate — the on-ice backbone (already the Atlas's Phase 2/3 targets)

| model | grain | relation to Atlas plan |
|---|---|---|
| **int_shift_segments** | (game_id, segment_index, player_id) | **= Phase 2 stints.** Boundary-union of shift starts/ends; carries `team_skater_count, team_goalie_count, is_goalie, position_code`. ⚠️ **Verify vs Amendment A:** existing cuts are at *shift* boundaries; Amendment A also wants **goals** as cut points so score is constant per stint. Score state lives in `int_segment_context` but goal-boundary cutting must be confirmed in Phase 2. |
| **int_segment_context** | (game_id, segment_index) | per-segment `strength_state` (shift-derived), `home/away_skaters/goalies`, `home_score/away_score/*_score_state`, zone start |
| **int_on_ice_events** | (game_id, event_id) | event→segment attribution with `on_ice_for[]/on_ice_against[]` |
| **int_shot_attempts / _all** | 1 / attempt | xG basis (5v5-only / all-situations) |
| **int_line_seasons** | season/team/line | exact trio/pair chemistry (not arbitrary-pair WOWY) |

### Models — `nhl_models` (Python outputs; `models_ml/`)

| source | grain | producer | relevance |
|---|---|---|---|
| **shot_xg** | (game_id, event_id) | `models_ml/score_xg.py` | the only xG source; unblocked/non-EN/non-SO by design (Phase 3 input; coverage to confirm at Phase 3) |
| **player_impact** | (player_id, season_window) | `models_ml/train_rapm.py` | full two-sided RAPM off/def/pp/pk + bootstrap SD (context; do not rebuild) |

Also present (context, not required): `player_composite`, `player_archetypes`, marts
`mart_player_onice / _toi_matrix / _wowy / int_player_onice_game` (the WOWY/on-ice layer).

### Season coverage — distinct games per season (scope; `shifts`=`pbp`=`box` unless noted)

Evidence: `COUNT(DISTINCT game_id)` grouped by season-start + game-type across the three raw tables.

| season | reg (02) shifts | reg pbp | reg box | playoff (03) |
|---|---|---|---|---|
| 2015-16 | 1230 | 1230 | 1230 | 91 |
| 2016-17 | 1230 | 1230 | 1230 | 87 |
| 2017-18 | 1271 | 1271 | 1271 | 84 (pbp 83) |
| 2018-19 | 1271 | 1271 | 1271 | 87 |
| 2019-20 | 1082 | 1082 | 1082 | **0 — bubble playoffs absent** |
| 2020-21 | 868 | 868 | 868 | 81 |
| 2021-22 | 1312 | 1312 | 1312 | 89 |
| 2022-23 | 1312 | 1312 | 1312 | 88 |
| 2023-24 | 1312 | **1311** | 1312 | 88 |
| 2024-25 | 1312 | **1311** | 1312 | 86 |
| 2025-26 | 1312 | 1312 | 1312 | 83 |

Regular-season **shift coverage is complete and equals boxscore coverage game-for-game**
(≈13,512 games). Reduced counts are real (2019-20 COVID stop = 1082; 2020-21 short season
= 868; 31-team seasons 2017-19 = 1271; 32-team = 1312). **Bonus:** 2010-11..2014-15 are
also fully present (shifts=pbp=box), available at **zero fetch** if the scope is ever
widened (per the standing exception) — out of default modeling scope.

---

## 1.2 Gap matrix (requirements × status)

| Atlas requirement | status | evidence | gap action |
|---|---|---|---|
| **Shifts** (player, game, start, end) | ✅ **Exists & usable** | `stg_shifts` full grain; coverage == box, 2015-26 | none — export from BQ |
| **Events + coordinates** | ✅ **Exists & usable** | `stg_play_by_play.x_coord/y_coord/zone_code` + `home_team_defending_side` | none |
| **Events — goalie pulls** | ✅ **Exists & usable** | `goalie_in_net_id` + `situation_code` digit | none |
| **Events — penalties (ledger)** | ⚠️ **Exists (raw) / partial (staging)** | raw `plays.details` has `descKey, committedBy, drawnBy, duration, typeCode`; `stg_play_by_play` omits `descKey` + severity `typeCode` | **zero-fetch re-parse** from `raw_play_by_play` for the standalone penalty ledger (Amendment A) |
| **Boxscore per-player TOI** | ⚠️ **Exists (raw) / missing (staging)** | `raw_boxscores.playerByGameStats…toi` schema-confirmed; `stg_boxscores` game-level only | **zero-fetch re-parse** from `raw_boxscores` for integrity test 1.4a |
| **Game enumeration** | ✅ **Exists & usable** | `stg_games` spine + `game_type` filter | none |

No requirement is outright **missing**. Two are "raw-present, not staged" → **transform, not fetch.**

### Proposed minimal ingestion plan (gaps only)

**Fetch gap — 2 requests total.** For the entire modeling scope, exactly two
regular-season games have a boxscore + shifts but no pbp:

| game_id | season | has shifts | has pbp |
|---|---|---|---|
| `2023020651` | 2023-24 | ✅ | ❌ |
| `2024020147` | 2024-25 | ✅ | ❌ |

→ Refetch play-by-play for these 2 game_ids via the Phase 0 client (cache under
`research/deployment-atlas/data/raw/`, preamble rate/backoff rules). **Estimated: 2 API
requests.** (Playoff pbp gaps — 1 game in 2017, and the entire 2019-20 bubble playoffs —
are left uncatalogued-for-fetch: playoffs are excluded from modeling.)

**Transform gaps — 0 fetches.** Both handled by read-only re-parse of existing BQ raw:
1. **Per-player TOI** ← `raw_boxscores.playerByGameStats` (for 1.4a).
2. **Penalty ledger** (`committedBy, drawnBy, team, descKey, typeCode, duration, start`)
   ← `raw_play_by_play.plays.details` (Amendment A standalone table).

**Assembly (proposed for 1.3, pending approval).** `src/atlas/sources.py` = read-only
BigQuery adapters that materialize Atlas `shifts.parquet` + `events.parquet` (+ TOI +
penalty-ledger) under `research/deployment-atlas/data/parquet/` from `nhl_staging`/`nhl_raw`.
Production tables are never written. The only network is the 2-game pbp backfill above,
plus the 5-game raw refetch that integrity test **1.4d** already requires.

### Flags to resolve when their phase arrives (not blockers now)
- **Stint boundaries vs Amendment A:** confirm `int_shift_segments` cuts at goals (not just
  shift boundaries) so score is constant per stint — or derive Atlas stints adding goal
  cut-points. (Phase 2.)
- **Empty-shift usability** for in-scope seasons is asserted from matching game counts +
  the Phase 0 spot-check (2015020001 = 832 shifts); the definitive per-game confirmation is
  integrity test **1.4a** (shift-TOI vs boxscore-TOI), post-approval.
- **xG coverage** (`shot_xg`) across 2015-26 to be verified when Phase 3 begins.

---

## Decision requested

Approve the plan above to proceed to **1.3** (build read-only `sources.py` adapters;
materialize Atlas Parquet from BigQuery) and **1.4** (integrity tests), with a
**2-game pbp fetch** as the only scope gap-fetch. Specifically, please confirm:

1. **Reuse NIR's BigQuery** (`stg_shifts`, `stg_play_by_play`, `raw_boxscores`,
   `stg_games`) as the Atlas source of record, rather than re-fetching the corpus.
2. **Zero-fetch re-parse** for per-player TOI and the penalty ledger is acceptable.
3. **Fetch only the 2 missing pbp games** (`2023020651`, `2024020147`).
4. Whether to **include 2010-11..2014-15** (present at zero fetch) or hold to 2015-16+.

**Stopping here for review per task 1.2. Not proceeding to 1.3 without approval.**
