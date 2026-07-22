# Stage 0 — The Frame Foundation

**Goal-Tracking research program** (`NIR/research/goal-tracking/`). Read-only over production; self-contained under this folder; own venv; `make stage0` reproduces from the local cache.

> **LAW 1 · GOALS-ONLY.** Every tracked sequence ended in a goal; there is no tracked non-goal in this data. You may DESCRIBE and ATTRIBUTE what happened on goals and build goal-as-the-unit measurements. You may NEVER make a predictive or comparative 'what causes goals / what wins' claim from this data alone.

> **LAW 2 · FUSION.** Tracking is faithful on position (scorer within stick-reach 88% in validation) and weak on exact stick attribution in traffic (38%). Attribution NEVER comes from geometry alone: the recorded scorer/assisters from stg_play_by_play are the anchor; tracking supplies context around those labels. Cluster-level credit is acceptable; deflection micro-mechanics may remain fuzzy and are labeled as such.


## 0.1 Scaffold & input audit

- **stg_ppt_tracking_frames**: 44,721,173 frame-entity rows / 25,946 goals (expected 44,721,173; match=True).
  - 2023-24: 13,138,873 rows / 8,618 goals (expected 8618; OK).
  - 2024-25: 15,616,698 rows / 8,635 goals (expected 8635; OK).
  - 2025-26: 15,965,602 rows / 8,693 goals (expected 8693; OK).
- **int_goal_release_frame**: 25,946 goals / 326,456 rows (expected 25,946 / 326,456).
- **STOP flag**: False (no mismatch beyond newly-ingested 2025-26 rows).

**Rule-4 inputs (path · timestamp · rowcount):**

| input | path | timestamp | rows |
|---|---|---|---|
| raw_ppt_replay (BQ) | nhl_raw.raw_ppt_replay | live | 25,946 |
| stg_play_by_play (BQ) | nhl_staging.stg_play_by_play | live | 6,545,861 |
| atlas_stints | research/deployment-atlas/data/parquet/stints.parquet | 2026-07-10T16:45:15 | 5,905,129 |
| atlas_player_5v5 | research/deployment-atlas/data/parquet/player_5v5.parquet | 2026-07-10T16:46:00 | 10,959 |
| atlas_rapm_variant | research/deployment-atlas/data/parquet/rapm_variant.parquet | 2026-07-10T18:01:54 | 13,434 |
| sysfx_team_season_fp | research/system-effects/data/parquet/team_season_fp.parquet | 2026-07-11T17:32:22 | 494 |
| sysfx_regime_ledger | research/system-effects/data/parquet/regime_ledger.parquet | 2026-07-11T21:08:05 | 235 |

**DAG ingestion task:** `ingest_nhl_data` in `dags/nhl_daily.py` — raw_ppt_replay is loaded inline in this task via load_json_to_bigquery(table_id='raw_ppt_replay')


## 0.2 The fused goal table

- `data/parquet/fused_goals.parquet`: **25,946 goals** (one row/goal), 63 columns.
- `data/parquet/goal_events.parquet`: **397,065 events** (one row/reconstructed event).
  - event types: segment=237,977, pass=81,672, release=25,946, arrival=25,946, entry=25,524.
- **strength state source**: situationCode=2,704, stint=23,242 (ice-derived from Atlas stints where a stint covers the goal second; else the sprite situationCode).
- **entry types**: off_frame_start=15,217, carried=7,613, dumped=1,606, passed=1,088, None=422.
- **flight detected** (release detector fired): 6,675 / 25,946 (25.7%).

**fused_goals schema (implemented):**

```
  game_id: Int64
  event_id: Int64
  season: String
  game_date: Date
  home_team_id: Int64
  away_team_id: Int64
  scoring_team_id: Int64
  period: Int64
  period_type: String
  game_clock_seconds: Int64
  abs_game_seconds: Int64
  strength_state: String
  strength_source: String
  home_goalie_id: Int64
  away_goalie_id: Int64
  scorer_id: Int64
  assist1_id: Int64
  assist2_id: Int64
  shot_type: String
  pbp_shot_x: Int64
  pbp_shot_y: Int64
  goalie_id: Int64
  n_frames: Int64
  attack_sign: Float64
  smooth_method: String
  reconstruction_ok: Boolean
  release_frame: Int64
  release_x: Float64
  release_y: Float64
  arrival_frame: Int64
  arrival_x: Float64
  arrival_y: Float64
  release_arrival_gap: Int64
  flight_detected: Boolean
  n_segments: Int64
  n_passes: Int64
  entry_type: String
  entry_frame: Int64
  entry_x: Float64
  entry_y: Float64
  entry_carrier_id: Int64
  ew_disp_2s: Float64
  screen_opp: Int64
  screen_own: Int64
  screen_count_rel: Int64
  nd_scorer_rel: Float64
  nd_scorer_1s: Float64
  goalie_depth_rel: Float64
  goalie_lat_speed_rel: Float64
  scorer_speed_recep: Float64
  scorer_speed_rel: Float64
  release_clock: Float64
  entry_to_goal: Float64
  rush_flag: Boolean
  q_a: Boolean
  q_b: Boolean
  q_c_crowd: Int64
  q_d: Boolean
  release_entities_json: String
  arrival_entities_json: String
  quality_score: Float64
  is_clean: Boolean
  crowd_stratum: String
```

**Derived-geometry definitions as implemented** (fixed):

- `ew_disp_2s` — max lateral (y) puck swing that crosses the slot midline (y=0) in the 2.0 s (20 frames) before release; 0 if the puck's y does not span the midline in-window. ft.
- `screen_count_rel` (`screen_opp`/`screen_own`) — non-goalie bodies inside the triangle (puck, left post, right post) at release AND within 10 ft of crease center; split by team.
- `nd_scorer_rel`, `nd_scorer_1s` — nearest opponent-skater distance to the recorded scorer at release and 1.0 s (10 frames) prior, ft.
- `goalie_depth_rel` — defending goalie's distance off the goal line projected onto the puck→goalie ray, ft; `goalie_lat_speed_rel` — smoothed lateral (y) goalie speed at release, ft/s.
- `scorer_speed_recep`, `scorer_speed_rel` — smoothed scorer speed at his terminal-possession start (reception) and at release, ft/s. `release_clock` — seconds reception→release.
- `entry_to_goal` — seconds zone-entry→arrival; `rush_flag` = entry_to_goal ≤ 6.0 s (frozen).
- **RELEASE = the flight-start event** (first frame of the terminal ≥40 ft/s, ≥2-frame net-ward puck run); the `int_goal_release_frame` arrival anchor is stored separately as `arrival_frame`.
- All speeds are on Savitzky-Golay-smoothed trajectories (window=7=0.7 s, polyorder=2; 5-frame rolling-mean fallback for short tracks). Speeds are approximate, never headline athletic numbers.

**Parameter provenance (transparency, not silent deviation):** the reconstruction reuses the algorithm validated in `research/replay-probe` (net-mouth box; arrival = first in-net frame reached by a shot flight; nearest-skater carrier + loose-gap hysteresis; release = flight start). Stage-0 fixed parameters differ from replay-probe's exploratory defaults and are applied per this handoff: carrier radius 5.5 ft (replay-probe used 4.5); flight threshold 40 ft/s on smoothed speed (replay-probe used 35 ft/s raw). These are re-validated at 0.4 below.


**Rush-flag sensitivity** (rate among goals with a detected entry; frozen at 6.0 s):

| threshold | rush goals | rush rate | n with entry |
|---|---|---|---|
| ≤4.0 s | 7,859 | 0.7625 | 10,307 |
| ≤6.0 s | 9,304 | 0.9027 | 10,307 |
| ≤8.0 s | 10,012 | 0.9714 | 10,307 |

## 0.3 Clip-quality score

score = 0.4·a + 0.3·b + 0.1·d + 0.2·max(0,(3−c_crowd)/3); CLEAN = a∧b∧d (a=scorer within 5.5 ft of puck in final 1.5 s pre-release; b=no puck gap >0.5 s in final 5.0 s; d=flight detector fired; c_crowd=bodies within 5.5 ft of puck at release).

- **Overall CLEAN fraction: 22.2%** (5,755 / 25,946).

| season | goals | CLEAN | CLEAN % | mean score | stratum clean/med/scramble |
|---|---|---|---|---|---|
| 2023-24 | 8,618 | 1,983 | 23.0% | 0.824 | 7,450 / 1,042 / 126 |
| 2024-25 | 8,635 | 1,889 | 21.9% | 0.820 | 7,372 / 1,108 / 155 |
| 2025-26 | 8,693 | 1,883 | 21.7% | 0.819 | 7,437 / 1,104 / 152 |

Score histogram (0.1 bins): 0.0:2, 0.1:12, 0.2:6, 0.3:139, 0.4:827, 0.5:703, 0.6:287, 0.7:3,283, 0.8:15,165, 0.9:4,856, 1.0:666.

## 0.4 Validation gate (60 goals, pre-stated)

Deterministic sample: 20 per crowd-stratum, balanced across seasons (7/7/6), ordered within each (season×stratum) cell by md5(game_id-event_id). n=60, CLEAN in sample=9.

**Verdict rules** (LAW-2 anchored, judged against the pbp labels and the trajectory): *carrier_chain_faithful* = the recorded scorer is the reconstructed last attacking carrier (the shooter) OR within stick-reach (5.5 ft) of the puck at release, with an attacking carrier present; *release_faithful* = puck moves net-ward release→arrival AND an attacking skater is within 6 ft of the puck at release AND 0 ≤ gap ≤ 20 frames. (See the proxy note below on the two tracking artifacts deliberately not counted against the chain.)

- **CLEAN clips — carrier-chain faithful: 100%; release-frame faithful: 100%** (bar = 90% each).
- Scramble stratum (no bar): carrier 90%, release 100%.
- **Supplementary** (not the pre-stated gate; broader basis than the 9 CLEAN clips the crowd-stratified 60-sample contains): a deterministic **45-CLEAN-clip** set scores carrier 100%, release 93%.
- **GATE: PASS**

*Verdict-proxy note:* the automated carrier-chain check judges whether the recorded scorer is the reconstructed last attacking carrier (the shooter) OR is within stick-reach of the puck at release. Two documented tracking artifacts — an incidental defender puck-touch mid-cycle, and a shot fly-by (the puck passing within stick reach of a defender in flight) — are NOT counted against the chain, as neither changes who the reconstruction identifies as the shooter. On every CLEAN clip sampled, the scorer is the reconstructed last attacking carrier.

| stratum | n | n_clean | carrier faithful | release faithful |
|---|---|---|---|---|
| clean | 20 | 5 | 80% | 75% |
| medium | 20 | 4 | 85% | 85% |
| scramble | 20 | 0 | 90% | 100% |

**Per-goal verdicts (60):**

| game-event | season | stratum | clean | crowd | scorer | rel/arr | flight | entry | passes | carrier✓ | release✓ |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 2023020143-158 | 2023-24 | clean | · | 1 | 8478420 | 81/82 | · | off_frame_start | 5 | · | · |
| 2023020260-809 | 2023-24 | clean | · | 1 | 8477346 | 81/82 | · | off_frame_start | 3 | · | Y |
| 2023020729-782 | 2023-24 | clean | · | 1 | 8482124 | 77/78 | · | off_frame_start | 3 | Y | Y |
| 2023020803-1000 | 2023-24 | clean | Y | 1 | 8475169 | 83/86 | Y | passed | 3 | Y | Y |
| 2023020822-877 | 2023-24 | clean | · | 1 | 8481557 | 75/75 | · | dumped | 2 | Y | · |
| 2023021216-268 | 2023-24 | clean | · | 1 | 8483431 | 70/84 | · | dumped | 4 | Y | · |
| 2023030165-138 | 2023-24 | clean | · | 1 | 8477501 | 74/76 | · | carried | 3 | Y | · |
| 2024020246-1162 | 2024-25 | clean | · | 1 | 8476292 | 92/94 | · | off_frame_start | 2 | Y | · |
| 2024020293-852 | 2024-25 | clean | Y | 1 | 8479316 | 85/89 | Y | carried | 1 | Y | Y |
| 2024020555-855 | 2024-25 | clean | Y | 1 | 8480012 | 86/89 | Y | off_frame_start | 2 | Y | Y |
| 2024020569-679 | 2024-25 | clean | Y | 1 | 8478042 | 94/97 | Y | off_frame_start | 3 | Y | Y |
| 2024020732-717 | 2024-25 | clean | · | 1 | 8476881 | 98/100 | · | off_frame_start | 4 | · | Y |
| 2024021039-1019 | 2024-25 | clean | · | 1 | 8477986 | 108/111 | · | carried | 0 | Y | Y |
| 2024021065-374 | 2024-25 | clean | · | 1 | 8480800 | 86/91 | · | off_frame_start | 2 | Y | Y |
| 2025020052-1001 | 2025-26 | clean | · | 1 | 8476880 | 94/96 | · | off_frame_start | 4 | Y | Y |
| 2025020115-1009 | 2025-26 | clean | · | 1 | 8481013 | 91/93 | · | carried | 3 | Y | Y |
| 2025020428-141 | 2025-26 | clean | Y | 1 | 8482758 | 86/90 | Y | off_frame_start | 7 | Y | Y |
| 2025020505-552 | 2025-26 | clean | · | 1 | 8482113 | 96/96 | · | carried | 4 | Y | Y |
| 2025020681-1035 | 2025-26 | clean | · | 1 | 8484801 | 99/100 | · | off_frame_start | 2 | · | Y |
| 2025021201-516 | 2025-26 | clean | · | 1 | 8478483 | 89/91 | · | carried | 6 | Y | Y |
| 2023020001-165 | 2023-24 | medium | · | 2 | 8475158 | 77/83 | · | carried | 2 | · | Y |
| 2023020212-1125 | 2023-24 | medium | · | 2 | 8482087 | 82/84 | · | off_frame_start | 2 | Y | · |
| 2023020335-1136 | 2023-24 | medium | · | 2 | 8478434 | 78/79 | · | off_frame_start | 1 | Y | Y |
| 2023020647-842 | 2023-24 | medium | Y | 2 | 8476389 | 77/79 | Y | off_frame_start | 2 | Y | Y |
| 2023021086-1151 | 2023-24 | medium | · | 2 | 8475166 | 79/80 | · | off_frame_start | 4 | Y | · |
| 2023021278-718 | 2023-24 | medium | · | 2 | 8476887 | 82/84 | · | off_frame_start | 1 | Y | Y |
| 2023021310-215 | 2023-24 | medium | · | 2 | 8476312 | 79/81 | · | off_frame_start | 4 | · | Y |
| 2024020022-874 | 2024-25 | medium | · | 2 | 8481546 | 94/95 | · | off_frame_start | 3 | Y | Y |
| 2024020332-1055 | 2024-25 | medium | · | 2 | 8478402 | 94/94 | · | carried | 2 | · | Y |
| 2024020486-715 | 2024-25 | medium | · | 2 | 8483397 | 96/101 | · | off_frame_start | 3 | Y | Y |
| 2024020661-421 | 2024-25 | medium | · | 2 | 8480023 | 95/95 | · | carried | 4 | Y | Y |
| 2024020959-945 | 2024-25 | medium | · | 2 | 8477987 | 100/101 | · | off_frame_start | 3 | Y | Y |
| 2024021086-353 | 2024-25 | medium | · | 2 | 8480459 | 89/90 | · | off_frame_start | 4 | Y | Y |
| 2024021242-1029 | 2024-25 | medium | · | 2 | 8480459 | 95/97 | · | off_frame_start | 4 | Y | Y |
| 2025020172-869 | 2025-26 | medium | Y | 2 | 8480748 | 95/99 | Y | carried | 3 | Y | Y |
| 2025020473-841 | 2025-26 | medium | Y | 2 | 8479378 | 97/99 | Y | off_frame_start | 4 | Y | Y |
| 2025020530-1098 | 2025-26 | medium | · | 2 | 8478831 | 93/96 | · | off_frame_start | 5 | Y | Y |
| 2025020582-352 | 2025-26 | medium | · | 2 | 8475158 | 96/97 | · | off_frame_start | 5 | Y | Y |
| 2025020621-496 | 2025-26 | medium | Y | 2 | 8479336 | 98/100 | Y | carried | 3 | Y | Y |
| 2025020686-1129 | 2025-26 | medium | · | 2 | 8484158 | 99/100 | · | carried | 3 | Y | · |
| 2023020119-166 | 2023-24 | scramble | · | 3 | 8479325 | 61/63 | · | off_frame_start | 2 | Y | Y |
| 2023020140-446 | 2023-24 | scramble | · | 3 | 8476925 | 74/75 | · | passed | 7 | · | Y |
| 2023020239-242 | 2023-24 | scramble | · | 3 | 8477505 | 77/79 | · | off_frame_start | 4 | Y | Y |
| 2023020959-427 | 2023-24 | scramble | · | 3 | 8479996 | 86/88 | · | carried | 4 | Y | Y |
| 2023021021-902 | 2023-24 | scramble | · | 3 | 8482740 | 78/80 | · | off_frame_start | 6 | Y | Y |
| 2023021302-988 | 2023-24 | scramble | · | 3 | 8481167 | 76/78 | · | off_frame_start | 1 | Y | Y |
| 2023030183-234 | 2023-24 | scramble | · | 3 | 8475786 | 79/79 | · | off_frame_start | 3 | Y | Y |
| 2024020433-397 | 2024-25 | scramble | · | 3 | 8475810 | 88/90 | · | carried | 5 | Y | Y |
| 2024020655-844 | 2024-25 | scramble | · | 3 | 8482511 | 92/94 | · | off_frame_start | 4 | Y | Y |
| 2024020893-217 | 2024-25 | scramble | · | 4 | 8483573 | 103/103 | · | carried | 3 | Y | Y |
| 2024021011-228 | 2024-25 | scramble | · | 3 | 8475786 | 101/101 | · | off_frame_start | 5 | Y | Y |
| 2024021139-761 | 2024-25 | scramble | · | 3 | 8482691 | 108/112 | · | off_frame_start | 4 | Y | Y |
| 2024021145-573 | 2024-25 | scramble | · | 3 | 8482201 | 96/98 | · | off_frame_start | 6 | Y | Y |
| 2024030121-706 | 2024-25 | scramble | · | 3 | 8479314 | 102/102 | · | off_frame_start | 8 | Y | Y |
| 2025020132-706 | 2025-26 | scramble | · | 4 | 8481524 | 97/99 | · | off_frame_start | 6 | Y | Y |
| 2025020220-556 | 2025-26 | scramble | · | 4 | 8478414 | 118/118 | · | off_frame_start | 2 | Y | Y |
| 2025020748-934 | 2025-26 | scramble | · | 4 | 8475913 | 103/103 | · | carried | 5 | Y | Y |
| 2025020856-769 | 2025-26 | scramble | · | 3 | 8482740 | 97/99 | Y | off_frame_start | 2 | Y | Y |
| 2025021126-1056 | 2025-26 | scramble | · | 3 | 8476483 | 63/63 | · | off_frame_start | 3 | · | Y |
| 2025021146-955 | 2025-26 | scramble | · | 3 | 8480873 | 97/98 | · | carried | 2 | Y | Y |

**Representative inspection detail** (carrier-chain segments · pass count · entry · release vs arrival):

- `2023021216-268` [clean] scorer=8483431 assists=(8478474,8482699): chain 8474166[0-5] -> 8477447[12-13] -> 8478474[14-14] -> 8477384[32-33] -> 8478403[34-36] -> 8482699[39-48] -> 8478474[49-52] -> 8483431[55-68] -> 8474166[70-70]; entry=dumped@75; release@70 arrival@84 (gap 14); scorer_dist@release=15.2ft; carrier✓=True release✓=False.
- `2023020822-877` [clean] scorer=8481557 assists=(8477451,8482122): chain 8482122[0-13] -> 8477451[21-31] -> 8476539[33-33] -> 8481557[60-70] -> 8475188[72-73] -> 8482624[74-119]; entry=dumped@39; release@75 arrival@75 (gap 0); scorer_dist@release=20.7ft; carrier✓=True release✓=False.
- `2023021086-1151` [medium] scorer=8475166 assists=(8477479,8479318): chain 8476853[3-14] -> 8480043[20-29] -> 8479318[35-62] -> 8477948[63-63] -> 8477479[64-69] -> 8477948[70-70] -> 8477479[71-71] -> 8480068[72-76] -> 8475166[77-77] -> 8480068[78-79] -> 8477479[82-95] -> 8477948[96-103] -> 8480068[104-104] -> 8482159[105-112]; entry=off_frame_start@None; release@79 arrival@80 (gap 1); scorer_dist@release=9.6ft; carrier✓=True release✓=False.
- `2023020647-842` [medium] scorer=8476389 assists=(8475184,8478550): chain 8482109[0-31] -> 8478550[47-58] -> 8476897[60-60] -> 8475184[64-64] -> 8476389[76-76] -> 8475181[77-78] -> 8482109[93-110]; entry=off_frame_start@None; release@77 arrival@79 (gap 2); scorer_dist@release=5.1ft; carrier✓=True release✓=True.
- `2023020959-427` [scramble] scorer=8479996 assists=(8476925,8474151): chain 8474151[17-21] -> 8477425[25-26] -> 8474568[27-27] -> 8479996[34-64] -> 8476925[67-76] -> 8471677[77-77] -> 8479525[79-79] -> 8479996[80-84] -> 8479525[85-85] -> 8481524[86-86] -> 8478508[96-107] -> 8481524[112-119]; entry=carried@51; release@86 arrival@88 (gap 2); scorer_dist@release=9.2ft; carrier✓=True release✓=True.
- `2023021021-902` [scramble] scorer=8482740 assists=(8475168,8478975): chain 8475168[0-8] -> 8481581[13-22] -> 8475168[26-37] -> 8478975[42-51] -> 8478911[52-52] -> 8482740[53-53] -> 8478911[54-54] -> 8473453[55-57] -> 8475168[64-70] -> 8473453[71-71] -> 8478911[72-73] -> 8482740[74-78] -> 8478911[90-94] -> 8482702[95-96] -> 8478911[97-117] -> 8473453[118-119]; entry=off_frame_start@None; release@78 arrival@80 (gap 2); scorer_dist@release=4.2ft; carrier✓=True release✓=True.

## 0.5 The API (`gtrack.api`)

Typed, read-only accessors over the fused corpus; LAW 1 & LAW 2 verbatim in the module docstring and in `goal()`'s docstring.

- `goal(game_id, event_id) -> {fused, events}`
- `goals(season=None, team=None, clean_only=False, min_quality=None) -> DataFrame`
- `player_goals(player_id, involvement in {scorer, assister, any}) -> DataFrame`
- `goalie_goals_against(goalie_id) -> DataFrame`
- `team_goals(team_id, season=None, side in {for, against}) -> DataFrame`

## Reproducibility

- `make stage0` = audit → fuse (from cache) → validate → tests → report. BigQuery pulls are cached once to `data/cache`; downstream reads are offline. Seed = 20260714.
- Tests: `pytest tests` (see run log). Data/venv are gitignored; the project removes by folder delete.

**STOP for owner review.**
