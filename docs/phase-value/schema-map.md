# Phase Value — Stage 0 schema map

Confirms every `(verify)` asset from the build spec Section 1 against the real repo, plus the eight
empirical verifications (Section 4.2). Authority: repo for mechanics, spec for intent. Recon script:
`models_ml/phase_value/stage0_recon.py` (read-only; last two complete seasons 2023-24, 2024-25).

## Datasets (BigQuery)
- Staging + **intermediate** dbt models materialize to **`nhl_staging`** (dbt `intermediate` config is
  `+schema: staging`). So `int_shot_sequence`, `int_shift_segments`, `int_segment_context`,
  `int_on_ice_events` all live in `nhl_staging`, NOT `nhl_mart`.
- Marts → `nhl_mart`. Model outputs (`shot_xg`, `player_impact`, and the new PV tables) → `nhl_models`.
- BQ access: service account `nhl-intel-sa@nhl-intel-498216`, key `secrets/nhl-intel-sa.json`; set
  `GCP_PROJECT_ID=nhl-intel-498216` and `GOOGLE_APPLICATION_CREDENTIALS=<key>`. `config.GCP_PROJECT_ENV`
  = `"GCP_PROJECT_ID"`.

## Asset name/location map (Section 1)
| Spec reference | Real location | Notes |
|---|---|---|
| `stg_play_by_play` | `nhl_staging.stg_play_by_play` (`dbt/models/staging/stg_play_by_play.sql`) | all spec columns present (see below) + rich detail ids |
| `stg_boxscores` | `nhl_staging.stg_boxscores` | `game_id, home_team_id, away_team_id` (+season/date) |
| `int_shift_segments` | `nhl_staging.int_shift_segments` | grain **(game_id, segment_index, player_id)**; `team_id, position_code, is_goalie, segment_start_seconds, segment_end_seconds, segment_duration, season, team_skater_count, team_goalie_count` |
| `int_segment_context` | `nhl_staging.int_segment_context` | grain **(game_id, segment_index)**; `home_skaters, away_skaters, home_goalies, away_goalies, strength_state, home_score, away_score, home_score_state, is_zone_start, zone_start_code, segment_start_seconds, segment_end_seconds, segment_duration, season`. Elapsed-seconds convention matches PBP. |
| `int_on_ice_events` | `nhl_staging.int_on_ice_events` | grain **(game_id, event_id)**; `sort_order, type_desc_key, event_owner_team_id, event_seconds, segment_index, on_ice_for[], on_ice_against[]`. Join to segments by `segment_index`; to PBP by `(game_id,event_id)`. Attribution: event in (segment_start, segment_end]. |
| `int_shot_sequence` | `nhl_staging.int_shot_sequence` | one row per unblocked attempt; `seq_type`, `strength`, `is_empty_net`, `elapsed_seconds`, coords. Blocked shots excluded. |
| `int_rink_bias` | `nhl_staging.int_rink_bias` | confirmed (not needed until any PV-A2 arena revisit) |
| `nhl_models.shot_xg` | `nhl_models.shot_xg` (produced by `models_ml/train_xg.py` / `score_xg.py`) | key **(game_id, event_id)**; cols `game_id, event_id, season, game_date, team_id, xg, base_rate, xg_contrib_*, model_version`. One row per unblocked, non-EN, non-shootout shot. |
| `nhl_models.player_impact` | `nhl_models.player_impact` | RAPM output; `player_id, season_window, off_impact, off_sd, def_impact, def_sd, pp_impact, pp_sd, pk_impact, pk_sd, toi_min, alpha, model_version`. The PV validation baseline. |
| `models_ml/train_rapm.py` | present | see "RAPM ancestor" below |
| `models_ml/config.py` | present | `GAR_CONFIG` = house comment style; `PHASE_VALUE_CONFIG` added |
| `models_ml/tune_sequence_thresholds.py` | **ABSENT** (PV-D001) | referenced by spec §5.5 + dbt comment as the mirror-pattern example, but the file does not exist. The mirror pattern itself is still followed (Python reference ↔ dbt SQL). |
| dbt vars | `dbt/dbt_project.yml` | `rush_window_seconds:4` reused; PV vars added |

## stg_play_by_play columns (confirmed, full)
`game_id, api_game_id, season, game_date, ingestion_date, event_id, period_number, period_type,
time_in_period (MM:SS str), time_remaining, situation_code, type_code, type_desc_key, sort_order,
home_team_defending_side, x_coord, y_coord, zone_code, shot_type, reason, secondary_reason,
shooting_player_id, scoring_player_id, goalie_in_net_id, assist1_player_id, assist2_player_id,
blocking_player_id, hitting_player_id, hittee_player_id, committed_by_player_id, drawn_by_player_id,
player_id, home_score, away_score, home_sog, away_sog, event_owner_team_id, duration, _loaded_at`.
Elapsed seconds: `(period_number-1)*1200 + MM*60 + SS` (verbatim from int_shot_sequence). Deduped by
`(game_id,event_id)` keeping latest ingestion.

## The eight empirical verifications (2023-24 + 2024-25)
1. **Event-type frequencies.** All spec types present. Full set (desc): `faceoff, shot-on-goal, hit,
   stoppage, blocked-shot, missed-shot, giveaway, takeaway, penalty, goal, period-start, period-end,
   delayed-penalty, game-end, shootout-complete (163), failed-shot-attempt (24)`. The two extras map
   to the fallback row: `failed-shot-attempt` → LIVE no-op (counts toward unmapped, ~0.003%);
   `shootout-complete` → DEAD boundary (shootout is out of 5v5 scope anyway). All well under the 0.5% gate.
2. **Faceoff owner = WINNER — CONFIRMED, ground truth 1.0000 (n=81,523).** The definitive cross-check
   (spec's preferred "winning-player details if present"): raw `play.details.winningPlayerId`'s team
   (via `int_shift_segments`) equals `event_owner_team_id` on **100%** of faceoffs. Noisy next-event
   proxies (next-shot 0.69; OZ-faceoff next-shot 0.87; possession-clean next event 0.81) are all
   directionally consistent but understate it because possession genuinely turns over within seconds —
   they are not evidence of ambiguity. **STOP gate cleared.**
3. **Blocked-shot owner = BLOCKING (defending) team — CONFIRMED at 94.15% (STOP gate cleared).**
   Owner-relative `zone_code` on blocked-shot is 'D' 94.15% / 'O' 5.70% / 'N' 0.15%; both
   `shooting_player_id` and `blocking_player_id` are 100% populated. This is the **opposite** of the
   naive reading. **Mapping implication (binding):** on a `blocked-shot`, the shooting (attacking) team
   = `opponent(event_owner_team_id)`, and the zone must be flipped O↔D to express it attacker-relative.
   Intent PV-A1 (attacker retains possession) is preserved; GV7 anticipated this ("per Stage 0 finding").
4. **Stoppage reason column = `reason`** (also `secondary_reason`). Top values: `goalie-stopped-after-sog,
   icing, puck-in-netting, offside, puck-frozen, puck-in-crowd, puck-in-benches, tv-timeout,
   referee-or-linesman, hand-pass, high-stick, ...`. Available for `end_reason='stoppage'` sub-labeling.
5. **5v5 strength.** `int_segment_context.strength_state = '5v5'` (80.35% of segment-seconds) is the
   canonical 5v5 filter; matches int_shot_sequence's ICE derivation (`home_sk=away_sk=5 & both goalies`).
   PV uses `strength_state='5v5'` directly.
6. **zone_code nullness by type.** Null-by-design: `stoppage, period-start, period-end, game-end,
   delayed-penalty, shootout-complete` (100% null → never update zone_abs). Near-0% null on
   `faceoff/shot-on-goal/missed-shot/blocked-shot/hit/giveaway/takeaway`; `penalty` 0.6%, `goal` 0.3%.
7. **shot_xg coverage.** Keyed `(game_id, event_id)`; 246,948 rows vs 249,965 unblocked attempts =
   **98.8% matched**. The ~1.2% gap = empty-net/shootout attempts the xG model excludes + the 3
   pbp-only games. Acceptable; episode xG uses the matched set.
8. **game_date.** 0.000% null on `stg_play_by_play` → present on PBP directly (no boxscore join needed).

## RAPM ancestor (train_rapm.py) — reuse facts
- Constants: `MIN_SEGMENT_SECONDS = 5` (NOT 4 — see PV-D002), `ALPHAS = list(np.logspace(2,6,13))`
  (100..1e6, NOT "[250..8000]" — PV-D003; reuse by import), `CV_FOLDS = 5`, `DEFAULT_BOOTSTRAP = 100`,
  `REPLACEMENT_MIN_MINUTES = 100`, `WINDOW_WEIGHTS = [0.3,0.6,1.0]`, `SINGLE_SEASONS =
  ['2021-22'..'2025-26']`.
- Pipeline fns: `pull → expand_rows/expand_special → build_design (sparse two-sided player indicators +
  controls: score_state, zone, home, b2b, game-time bucket, season FE) → cv_alpha (game-grouped) →
  fit_coefs (ridge lsqr) → player_impacts (centering + def sign-flip) → bootstrap_sd`. Design builder is
  reusable in principle; extraction only if it's a pure refactor with a coefficient-diff regression test
  (Section 7.2), else mirror with a header pointer.

## Serving + backend patterns (Stage 6)
- `serving_tables.yml` entry shape: `- {name, dataset, kind: source|precompute, cap: full|recent,
  indexes: [...]}`. `player_impact` is `{name: player_impact, dataset: models, kind: source, cap: full,
  indexes: [player_id, season_window]}`. PV tables follow this (kind: source, they are BQ tables written
  by model jobs): `player_phase_value` indexed `[player_id, season_window]`; `state_values` indexed by
  its scope keys.
- Backend: `backend/routers/players.py`, pattern `@router.get("/{player_id}/<name>")` + `@cache(ttl=...)`,
  querying via `bq_service` which routes to the DuckDB serving adapter (`backend/services/serving.py`).
  Add `GET /players/{player_id}/phase-value` additively there.

## dev-season scoping
No pre-existing dbt season-scoping var (PV-D004). Added `phase_dev_seasons: []` in dbt_project.yml
(list of seasons to limit PV models in dev; empty = full).
