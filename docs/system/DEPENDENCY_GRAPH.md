# DEPENDENCY_GRAPH — cross-layer lineage and reverse reachability

How every layer connects, and which objects do (and do not) reach a shipped surface.
Built by joining the six domain inventories on names: frontend api call to backend route,
backend route to mart or serving table or model table, dbt node to its upstream via the
manifest, and ML output table to the dbt source of the same name.

## Hard rules (govern this document)

1. **Data and ingested objects may never be listed for deletion.** Every reachability
   statement about a BigQuery table, view, or ingested feed is a fact, never a delete
   recommendation. Only source files (code, config, docs) are ever proposed for cleanup,
   in CLEANUP_CANDIDATES.md.
2. **Puck tracking is retained by owner decision.** The ppt subsystem does not reach a
   current shipped surface and that is expected. It is Tier 3 (keep), an explicit exception
   to reverse reachability.

## Node types

The lineage has six node types. "Serving table" is a first-class node: much of the ML
layer reaches the frontend through the denormalized DuckDB serving file, not through marts.

| Node type | Where it lives | Produced by |
|---|---|---|
| raw feed | `nhl_raw.raw_*` (25 tables) | `ingestion/`, `scripts/*` |
| dbt staging/intermediate | `nhl_staging.{stg,int}_*` | dbt models |
| mart | `nhl_mart.mart_*` (21 physical) | dbt models |
| model table | `nhl_models.*` (44 physical) | `models_ml/*` Python |
| serving table | DuckDB `data/serving/nhl_intel.duckdb` + 6 `serving_*`/precompute tables | `scripts/export_to_duckdb.py`, `models_ml/precompute_serving.py` |
| app surface | frontend routes, daily HTML report | React, `reporting/` |

## The cross-layer join (request path)

```
mounted frontend route (App.tsx, 21 routes -> 18 pages)
  -> frontend/src/api/*.ts client method (axios apiClient)
    -> FastAPI route (backend/routers/*, 13 routers, ~70 routes; registered main.py:39-51)
      -> service query (inline SQL or backend/services/*.py)
        -> DuckDB serving file  (SERVING_BACKEND=duckdb default, main.py:19)
             which mirrors:  mart_* (all 21)  +  nhl_models.* (served subset)
                             +  serving_* (precompute)  +  selected stg_*/int_*
          -> producer:  dbt model (mart -> intermediate -> staging -> raw feed)
                     OR ML script (nhl_models.* <- models_ml/*.py <- marts/staging/raw)
```

Two consequences that drive reachability:

1. **The DuckDB serving file (`serving_tables.yml`, ~60 tables) is itself a shipped surface
   (S4).** Any table copied into it is part of the shipped datastore. Nearly every mart and
   every headline `nhl_models.*` table is listed there, so the bulk of the dbt DAG and the ML
   layer reaches the frontend even when no route reads a table by name.
2. **The report path is a separate shipped surface (S2/S3)** that reads exactly one mart,
   `mart_daily_report_feed`, so that mart reaches even though no frontend route or Python
   module references it (this resolves the "unknown" flagged in `_inventory/10_dbt.md`).

## Shipped surfaces (S)

| id | surface | entry | data it pulls from |
|---|---|---|---|
| S1 | React frontend (21 mounted routes) | `frontend/src/App.tsx` | backend routes -> DuckDB serving file |
| S2 | daily HTML report `output/report_YYYY-MM-DD.html` | `nhl_daily.generate_report` | `mart_daily_report_feed` + Gemini |
| S3 | GCS-published report `gs://nhl-intel-reports` | `nhl_daily.publish_report` | same as S2 |
| S4 | DuckDB serving file `data/serving/nhl_intel.duckdb` | `nhl_daily.export_serving` | `serving_tables.yml` (~60 tables) |
| S5 | 6 precompute serving tables | `nhl_daily.precompute_serving` | feed S4/S1 |

Internal-only, explicitly NOT a shipped surface: `raw_partner_odds` / `stg_partner_odds`
(partner-odds calibration, "never exposed via API/UI", `nhl_daily.py:210`).

## Reverse reachability result

Marking every object transitively required to produce S1–S5 as **reaching**:

### Reaches a shipped surface (the overwhelming majority)

- **All 24 `nhl.raw_*` feeds** except `raw_glossary` (0 consumers) and the ops table
  `raw_backfill_failures` are upstream of a served mart/model. Reaching.
- **All staging + intermediate models** except the ppt pair and `stg_partner_odds` are
  upstream of a served mart/model or are themselves exported to DuckDB. Reaching.
- **All 21 physical marts** are exported to DuckDB (S4) and/or feed the report (S2).
  Reaching. `mart_player_faceoff_zones` is in the serving copy but has no live endpoint
  reader (reaches S4 as shipped data, no live consumer — noted, never a delete target).
- **All 44 `nhl_models.*` tables** are either in `serving_tables.yml` (served) or upstream of
  a served table (`contract_player_map`, `rfa_player_map` feed the served
  `mart_player_contracts`). Reaching. This includes the draft/pWAR cluster: `player_pwar`,
  `pick_value_curve`, `draft_value_player/summary`, `futures_value` are served and feed the
  `/draft/*` endpoints and `mart_tradeable_assets`. **The scripts that write them
  (`compute_pwar`, `fit_pwar_anchor`, `fit_pick_value`, `run_draft_theory`) therefore reach
  a shipped surface** even though no DAG/Makefile auto-runs them (hand-run cadence).

### Does NOT reach a current shipped surface

Split by category. **None of the data objects here are deletion candidates.**

| object | type | why not reaching | disposition |
|---|---|---|---|
| `stg_ppt_tracking_frames`, `int_goal_release_frame`, `raw_ppt_replay` | dbt / raw data | ppt subsystem not surfaced yet | **Tier 3 keep — puck tracking retained by owner (explicit exception)** |
| `mart_player_onice`, `mart_player_toi_matrix`, `mart_player_wowy` | new marts (leaf) | Phase 6 feature; materialized + validated (6.1), not yet in serving/backend | **Tier 3 keep — new feature, serving/wiring pending (6.4/6.5); data, never delete** |
| `mart_player_entanglement`, `mart_player_carry` | new marts (Phase 6.2) | read the WOWY marts; feed the impact-context spine; not yet served | **Tier 3 keep — new feature, serving/wiring pending (6.4/6.5); data, never delete** |
| `mart_player_impact_context` | new mart (Phase 6.3) | reads `nhl_models.player_impact` + entanglement/carry/onice; the impact-context spine; not yet served | **Tier 3 keep — new feature, serving/wiring pending (6.4/6.5); data, never delete** |
| `stg_partner_odds` / `raw_partner_odds` | dbt / raw data | internal calibration, intentionally never exposed | Tier 3 keep (intentional internal; data) |
| `raw_glossary` | raw data | 0 consumers (reference data ingested for future concept cards) | Tier 4 data — investigate, never drop |
| `nhl_staging.int_xg_rates`, `nhl_staging.int_zone_entries` | physical BQ views | no code producer (former dbt models, `.sql` removed; views left behind) | **Tier 4 — investigate, do not drop** |
| `nhl_staging_staging.stg_boxscores`, `nhl_staging_staging.stg_games` | physical BQ views (stray dataset) | residue of a fixed schema-name concatenation bug; zero code references | **Tier 4 — investigate, do not drop** |

Note the nuance on the Phase 6 marts: `int_segment_5v5_results` and `int_player_onice_game`
DO reach, because they are wired upstream of the live `mart_player_game_stats` and
`mart_player_relative`. The leaf marts (`mart_player_onice/_toi_matrix/_wowy`) and the 6.2
diagnostics (`mart_player_entanglement`, `mart_player_carry`) are materialized and validated
but terminal until Phase 6.4 (serving) + 6.5 (the `/players/{id}/wowy` endpoint and the
impact-context block) wire them to a shipped surface. New feature, not abandoned.

### Source files (code/docs) that reach nothing shipped

These are the actual cleanup inputs (data never is). Full evidence and tiering in
CLEANUP_CANDIDATES.md. Summary of the not-reaching source-file set:

- `.grepout` (empty 0-byte root file).
- 5 dbt ad-hoc inspection scripts (`dbt/check_report_feed.py`, `check_xgf.py`,
  `query_metrics.py`, `verify_calculations.py`, `verify_hot_cold.py`) — zero functional
  callers.
- 4 frontend orphans (`pages/DevComponents.tsx`, `visualizations/XGWormChart.tsx`,
  `visualizations/ShotPressureChart.tsx`, `common/GoalTooltip.tsx` transitively).
- ML superseded generation: `models_ml/fit_archetypes.py` (v1) + `archetypes_v1.joblib`.
- ML research cluster (outputs not served): 11 `analyze_*.py` + `build_playoff_weights.py` +
  `train_style_effect.py`; and 2 one-shot calibration scripts
  (`measure_goalie_reliability.py`, `tune_sequence_thresholds.py`) whose outputs are baked
  into `config.py` / dbt vars.
- 12 `smoke_*` dev harnesses (main-only) and several main-only root/one-off utilities.
- 5 registered backend routes with no frontend caller (`/streaks/active`,
  `/players/{id}/edge`, `/teams/{id}/edge`, `/goalies/{id}/gamelog`,
  `/archetypes/style-map`).
- Policy item (not a deletion): `dbt/profiles.yml` is tracked and should be untracked.

## Hub nodes (highest fan-out — handle with care)

From the manifest child_map + reference counts:

- `mart_team_game_stats` (dbt downstream 5; backend 26, ML 37 raw refs) and
  `mart_player_game_stats` (dbt 4; backend 20, ML 25) are the two hub marts.
- `nhl_models.shot_xg` feeds 8 dbt models + the RAPM/segment stack.
- `stg_play_by_play` and `stg_boxscores` are the staging hubs (17 and 15 downstream models).
- `int_shift_segments` -> `int_segment_context` / `int_on_ice_events` ->
  `int_segment_5v5_results` is the on-ice backbone shared by RAPM, WOWY, line-fit, and
  coach-trust.
