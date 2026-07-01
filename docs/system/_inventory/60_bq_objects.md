# 60 — BigQuery Physical-Object Drift

Sub-agent 6 inventory. Cross-references every **physical** BigQuery table/view against its
**producer in code** (dbt model, ML script, or ingestion path) and surfaces drift in both
directions.

Generated: 2026-07-01. Read-only pass. This is the only file written by this sub-agent.

---

## Cost + safety rules (in force for this entire pass)

1. **INFORMATION_SCHEMA metadata queries ONLY.** Every BigQuery query in this document targets
   `<dataset>.INFORMATION_SCHEMA.TABLES`. These are free and scan **no table data / zero bytes**.
   No `SELECT *`, no `COUNT(*)`, no row-scanning query was run. If a check would have scanned
   bytes, it was skipped and flagged instead.
2. **No data is ever proposed for removal.** Every orphaned physical object found here is reported
   as **Tier 4 — "investigate, do not drop."** This pass may only ever recommend removing
   *source files* (code/config/docs), never a BigQuery table/view, GCS object, or ingested row.
3. **Puck-tracking objects are RETAINED by owner decision** and are never flagged as
   orphan-for-removal, even where unreferenced: `raw_ppt_replay`, `stg_ppt_tracking_frames`,
   `int_goal_release_frame`, and any `ppt_*` serving/model table.

**Auth used:** service account `nhl-intel-sa@nhl-intel-498216.iam.gserviceaccount.com`
(key at `secrets/nhl-intel-sa.json`), project `nhl-intel-498216`, via the `bq` CLI.
Authentication succeeded; all four+one datasets were reachable.

**Discovered layout:**
- Datasets present: `nhl_raw`, `nhl_staging`, `nhl_staging_staging` (unexpected — see §Orphans),
  `nhl_mart`, `nhl_models`. There is **no separate GCP "serving" dataset** — the serving layer is a
  **local DuckDB file**, `data/serving/nhl_intel.duckdb` (714 MB, present on disk; declared in
  `serving_tables.yml` → `meta.duckdb_path`). DuckDB cannot be introspected from this pass; its
  existence is recorded here from the repo only. It is a rebuildable read-only copy of BigQuery
  (`make export-serving` / `scripts/export_to_duckdb.py`), so nothing lives only there.
- `models_ml/config.py`: `MODELS_DATASET = "nhl_models"` (Python model outputs land here).
- `serving_tables.yml`: `staging_dataset: nhl_staging`, `mart_dataset: nhl_mart`,
  `models_dataset: nhl_models`.

---

## 1. Physical objects per dataset (from INFORMATION_SCHEMA)

Query run per dataset (only the dataset name changes):

```sql
SELECT table_name, table_type
FROM `nhl-intel-498216`.<dataset>.INFORMATION_SCHEMA.TABLES
ORDER BY table_name
```

### nhl_raw — 25 objects (all BASE TABLE)

raw_backfill_failures, raw_boxscores, raw_contracts, raw_contracts_rfa, raw_draft_picks,
raw_draft_results, raw_edge_goalies, raw_edge_skaters, raw_edge_teams, raw_game_landing,
raw_game_right_rail, raw_games, raw_glossary, raw_gm_tenures, raw_partner_odds, raw_play_by_play,
raw_player_bio, raw_player_draft_origin, raw_ppt_replay, raw_prospects, raw_rosters,
raw_shift_charts, raw_standings, raw_statsrest_faceoffs, raw_trades

### nhl_staging — 42 objects (mix of VIEW / BASE TABLE)

BASE TABLE: int_draft_player_value, int_event_leverage, int_goalie_shots, int_line_seasons,
int_on_ice_events, int_rink_bias, int_score_state_weights, int_segment_context, int_shift_segments,
int_shot_score_adj, int_shot_sequence

VIEW: int_assists, int_goal_release_frame, int_player_current_team, int_shot_attempts,
int_shot_attempts_all, int_shot_types, **int_xg_rates**, **int_zone_entries**, int_zone_entry_proxy,
stg_boxscores, stg_contracts, stg_contracts_rfa, stg_draft_picks, stg_draft_results, stg_edge_goalies,
stg_edge_skaters, stg_edge_teams, stg_game_context, stg_games, stg_gm_tenures, stg_goalie_starts,
stg_partner_odds, stg_play_by_play, stg_player_bio, stg_ppt_tracking_frames, stg_prospects,
stg_roster_current, stg_rosters, stg_shifts, stg_standings, stg_statsrest_faceoffs, stg_trades

### nhl_staging_staging — 2 objects (both VIEW)  ⚠ unexpected dataset

stg_boxscores, stg_games

### nhl_mart — 21 objects (all BASE TABLE)

mart_daily_report_feed, mart_edge_player_profile, mart_edge_team_profile, mart_goalie_game_stats,
mart_goalie_season, mart_player_contracts, mart_player_faceoff_zones, mart_player_game_score,
mart_player_game_stats, mart_player_relative, mart_player_shooting_luck, mart_player_situational,
mart_player_zone_deployment, mart_team_faceoffs, mart_team_game_stats, mart_team_identity,
mart_team_identity_inputs, mart_team_rolling, mart_team_stats_situational, mart_team_zone_time,
mart_tradeable_assets

### nhl_models — 44 objects (all BASE TABLE)

aging_curves, archetype_gallery, contract_player_map, deployment_efficiency, deserved_standings,
dim_current_roster, divergence_board, draft_value_player, draft_value_summary, futures_value,
goalie_gar, goalie_overall, goalie_radar, line_member_features, pick_value_curve, player_archetypes,
player_clutch, player_coach_trust, player_composite, player_consistency, player_contract_value,
player_gar, player_impact, player_overall, player_physical, player_pwar, player_radar,
player_situation_toi, player_style_map, player_twins, player_verdict, rfa_player_map, roster_forecast,
roster_moves, serving_game_skater_box, shot_xg, streak_cards, style_map, team_current_lines,
team_handedness, team_needs, team_ratings, trade_outcomes, win_probability

**Local DuckDB serving file (not a BigQuery dataset):** `data/serving/nhl_intel.duckdb` — exists
(714 MB). Its object list is defined by the `tables:` manifest in `serving_tables.yml` (a copy of the
BigQuery staging/mart/model tables listed there). Not introspected here (metadata-only pass).

---

## 2. Producer cross-reference (per dataset)

### nhl_raw → ingestion / scripts
All 25 raw tables have an ingestion producer (grep of `ingestion/*.py` + `scripts/*.py`):

| raw table | producer(s) |
|---|---|
| raw_backfill_failures | `backfill_historical.py` (`…{dataset_raw}.raw_backfill_failures`) |
| raw_boxscores | `ingestion/loaders.py` |
| raw_contracts | `scripts/load_contracts.py` |
| raw_contracts_rfa | `scripts/load_rfas.py`, `scripts/match_rfas.py` |
| raw_draft_picks | `ingestion/loaders.py`, `ingestion/nhl_api.py` |
| raw_draft_results | `ingestion/loaders.py`, `scripts/ingest_draft_results.py` |
| raw_edge_goalies / _skaters / _teams | `ingestion/loaders.py`, `scripts/refresh_edge.py` |
| raw_game_landing | `ingestion/loaders.py`, `scripts/refresh_game_context.py` |
| raw_game_right_rail | `ingestion/loaders.py`, `scripts/refresh_game_context.py` |
| raw_games | `populate_raw_games.py`, `backfill_historical.py`, `dags/nhl_daily.py`, `load_schedule_only.py` |
| raw_glossary | `scripts/ingest_glossary.py` |
| raw_gm_tenures | `scripts/load_gm_tenures.py` |
| raw_partner_odds | `ingestion/loaders.py`, `scripts/refresh_partner_odds.py` |
| raw_play_by_play | `ingestion/loaders.py` |
| raw_player_bio | `scripts/ingest_player_bio.py` |
| raw_player_draft_origin | `scripts/ingest_player_draft_origin.py` |
| raw_ppt_replay | `ingestion/loaders.py`, `scripts/backfill_ppt_replay.py` — **puck-tracking, RETAINED** |
| raw_prospects | `scripts/ingest_futures.py` |
| raw_rosters | `ingestion/loaders.py`, `scripts/refresh_rosters.py` |
| raw_shift_charts | `ingestion/loaders.py`, `scripts/ingest_shifts.py` |
| raw_standings | `ingestion/loaders.py`, `scripts/refresh_standings.py` |
| raw_statsrest_faceoffs | `scripts/refresh_statsrest_faceoffs.py` |
| raw_trades | `scripts/load_trades.py` |

**No raw-dataset orphans.**

### nhl_staging + nhl_mart → dbt

Producers taken from `dbt/target/manifest.json` (67 enabled `model` nodes; schema `nhl_staging`
for `stg_`/`int_`, `nhl_mart` for `mart_`). Every physical `stg_*`, `int_*` (except two — see
Orphans) and every physical `mart_*` maps 1:1 to a dbt model of the same alias. This includes the
three mart tables not exported to serving (`mart_daily_report_feed`, `mart_player_faceoff_zones`,
`mart_team_identity_inputs`) — all are dbt models, so they have producers even though
`serving_tables.yml` doesn't copy them to DuckDB.

Puck-tracking staging views `stg_ppt_tracking_frames` and `int_goal_release_frame` are dbt models
(producers present) and are **RETAINED** regardless.

### nhl_models → ML scripts / serving_tables.yml

All 44 model tables have a producing `models_ml/*` script (or a `scripts/match_*` for the two map
tables). Grep pattern: table name quoted inside `models_ml/`, corroborated by `serving_tables.yml`.

| model table | producer | | model table | producer |
|---|---|---|---|---|
| aging_curves | `fit_aging_curves.py` / roster_forecast | | player_gar | `compute_gar.py` |
| archetype_gallery | `compute_archetype_explainer.py` | | player_impact | `train_rapm.py` |
| contract_player_map | `scripts/match_contracts.py` (→ nhl_models) | | player_overall | `compute_overall.py` |
| deployment_efficiency | `compute_deployment_efficiency.py` | | player_physical | `compute_physical.py` |
| deserved_standings | `simulate_deserved.py` | | player_pwar | `compute_pwar.py` |
| dim_current_roster | `precompute_serving.py` | | player_radar | `compute_player_radar.py` |
| divergence_board | `compute_divergence.py` | | player_situation_toi | `precompute_serving.py` |
| draft_value_player | `run_draft_theory.py` | | player_style_map | `compute_archetype_explainer.py` |
| draft_value_summary | `run_draft_theory.py` | | player_twins | `compute_twins.py` |
| futures_value | `compute_futures_value.py` | | player_verdict | `generate_verdicts.py` |
| goalie_gar | `compute_goalie_gar.py` | | rfa_player_map | `scripts/match_rfas.py` (→ nhl_models) |
| goalie_overall | `compute_overall.py` | | roster_forecast | `project_roster_forecast.py` |
| goalie_radar | `compute_goalie_radar.py` | | roster_moves | `project_roster_forecast.py` |
| line_member_features | `precompute_serving.py` | | serving_game_skater_box | `precompute_serving.py` |
| pick_value_curve | `fit_pick_value.py` | | shot_xg | `score_xg.py` |
| player_archetypes | `fit_archetypes*.py` / score_team_fit | | streak_cards | `streak_doctor.py` |
| player_clutch | `compute_clutch.py` | | style_map | `compute_style_map.py` |
| player_coach_trust | `compute_coach_trust.py` | | team_current_lines | `precompute_serving.py` |
| player_composite | `compute_composite.py` | | team_handedness | `precompute_serving.py` |
| player_consistency | `compute_consistency.py` | | team_needs | `compute_team_needs.py` |
| player_contract_value | `compute_contract_value.py` | | team_ratings | `compute_ratings.py` |
| | | | trade_outcomes | `compute_trade_outcomes.py` |
| | | | win_probability | `score_winprob.py` |

**No nhl_models orphans.** (`contract_player_map` and `rfa_player_map` are not in
`serving_tables.yml`, but both are legitimately produced into `nhl_models` by the `scripts/match_*`
join steps — intermediate map tables, not exported to serving.)

---

## 3. KEY DELIVERABLE — physical objects with NO producer found in code (**Tier 4: investigate, do not drop**)

Four physical objects have no current producing dbt model, ML script, or ingestion path. **None may
be dropped by this pass** — all are Tier 4. The likely cause in every case is a *removed or
misconfigured source file* whose already-materialized BigQuery object was left behind (dbt does not
drop the physical relation when you delete a model's `.sql`).

### 3.1 `nhl_staging.int_xg_rates` (VIEW) — Tier 4
- Empty producer search:
  - `find dbt/models -name "int_xg_rates.sql"` → **no source file** (`ls dbt/models/intermediate/int_xg_rates.sql` → "No such file or directory").
  - Not present in `dbt/target/manifest.json` model nodes (grep of manifest → not found).
  - `grep -rlE "int_xg_rates" --include=*.py --include=*.sql --include=*.yml .` (excl. pycache) → **no live reference** (only stale `dbt/target/compiled/…/int_xg_rates.sql` and `dbt/target/run/…/int_xg_rates.sql` build artifacts remain).
- Interpretation: a **former dbt model** whose source `.sql` was deleted; the physical VIEW persists.
- Action: investigate/confirm nothing reads it, then (source-file cleanup only) the stale
  `dbt/target/compiled|run/.../int_xg_rates.sql` artifacts are regenerated by dbt and need no manual
  action. **Do not drop the BigQuery view in this pass.**

### 3.2 `nhl_staging.int_zone_entries` (VIEW) — Tier 4
- Empty producer search (identical evidence to 3.1):
  - No `dbt/models/**/int_zone_entries.sql` source file.
  - Absent from `manifest.json` model nodes. Note: the manifest **does** contain a *different*
    model `int_zone_entry_proxy` (which is physically present and has a producer) — `int_zone_entries`
    is a separate, now-unproduced object, not a rename alias of it.
  - `grep -rlE "int_zone_entries" …` (excl. pycache) → only stale `dbt/target/compiled|run` artifacts.
- Interpretation: **former dbt model**, source removed, physical VIEW left behind.
- Action: investigate; **do not drop.**

### 3.3 `nhl_staging_staging.stg_boxscores` (VIEW) — Tier 4
### 3.4 `nhl_staging_staging.stg_games` (VIEW) — Tier 4
- The entire **`nhl_staging_staging` dataset** is unexpected. It holds only these two stale views.
- Empty producer search:
  - `grep -rlE "nhl_staging_staging|staging_staging" --include=*.py --include=*.yml --include=*.sql .`
    (excl. pycache) → **zero references.** No config, dbt profile, or script targets this dataset.
  - `serving_tables.yml` sets `staging_dataset: nhl_staging` (single `_staging`), and
    `models_ml/config.py` never mentions it.
- Interpretation: residue of a past **dbt custom-schema concatenation** (`target.schema` +
  `+schema: staging` → `nhl_staging` + `_staging` = `nhl_staging_staging`). The repo now has
  `dbt/macros/generate_schema_name.sql`, which almost certainly overrides that behavior to emit the
  bare `nhl_staging`; the two views built under the old naming were orphaned when the macro/config was
  fixed. They are frozen copies of `stg_boxscores` / `stg_games`.
- Action: investigate and confirm no consumer, then this is a data-object orphan; **do not drop** in
  this pass. Only the (already-fixed) schema-name macro is the relevant source artifact — no source
  change is recommended here.

> **Excluded from all orphan concern (RETAINED, owner decision):** `raw_ppt_replay`,
> `stg_ppt_tracking_frames`, `int_goal_release_frame`. All three additionally *do* have producers, but
> they are marked RETAINED here explicitly per the retention rule and must never be flagged for removal.

---

## 4. Reverse drift — producer declared in code but NO physical object in BigQuery

Five dbt models are **enabled** (`config.enabled = true`), materialized `table`, and have a source
`.sql` under `dbt/models/`, yet **no matching physical table exists** in `nhl_mart` / `nhl_staging`.
This is "producer with no object" drift — the models were added/kept in the dbt project but have not
been materialized (never run, excluded from the last `dbt build` selection, or the last run of them
failed). Not an orphan-for-removal; a **build/coverage gap to resolve**.

| declared dbt model | source file | manifest config | physical object? |
|---|---|---|---|
| `mart_player_onice` | `dbt/models/mart/mart_player_onice.sql` | table, enabled | **absent from nhl_mart** |
| `mart_player_toi_matrix` | `dbt/models/mart/mart_player_toi_matrix.sql` | table, enabled | **absent from nhl_mart** |
| `mart_player_wowy` | `dbt/models/mart/mart_player_wowy.sql` | table, enabled | **absent from nhl_mart** |
| `int_player_onice_game` | `dbt/models/intermediate/int_player_onice_game.sql` | table, enabled | **absent from nhl_staging** |
| `int_segment_5v5_results` | `dbt/models/intermediate/int_segment_5v5_results.sql` | table, enabled | **absent from nhl_staging** |

These five form a coherent WOWY/on-ice/segment-results lineage (`int_player_onice_game` →
`int_segment_5v5_results` → `mart_player_onice`/`_wowy`/`_toi_matrix`), suggesting an in-progress or
paused feature branch of the dbt project that has not yet been materialized to BigQuery. Recommended
follow-up: either run/select these models in the nightly `dbt build`, or (if abandoned) remove their
`.sql` **source files** — that is a source-file cleanup this pass may recommend, and it would also
prevent them re-appearing as declared-but-absent.

No ML-output table declared in `serving_tables.yml` was found missing from `nhl_models` — all
`models`-dataset entries in the serving manifest exist physically.

---

## 5. Summary

| Check | Result |
|---|---|
| Datasets enumerated | `nhl_raw`, `nhl_staging`, `nhl_staging_staging`, `nhl_mart`, `nhl_models` (+ local `data/serving/nhl_intel.duckdb`, not introspected) |
| Physical objects total | 25 raw + 42 staging + 2 staging_staging + 21 mart + 44 models = **134** |
| Physical objects with a producer | 130 |
| **Tier 4 orphans (no producer; investigate, do not drop)** | **4** — `nhl_staging.int_xg_rates`, `nhl_staging.int_zone_entries`, `nhl_staging_staging.stg_boxscores`, `nhl_staging_staging.stg_games` |
| Puck-tracking objects | `raw_ppt_replay`, `stg_ppt_tracking_frames`, `int_goal_release_frame` — **RETAINED**, never flag |
| Reverse drift (declared dbt model, no object) | **5** — `mart_player_onice`, `mart_player_toi_matrix`, `mart_player_wowy`, `int_player_onice_game`, `int_segment_5v5_results` |
| Bytes scanned by this pass | **0** (INFORMATION_SCHEMA metadata only) |

Nothing in this document recommends dropping any BigQuery object, GCS object, or ingested row.
Only source-file cleanups are ever suggested (the abandoned dbt `.sql` files in §4, if confirmed dead).
