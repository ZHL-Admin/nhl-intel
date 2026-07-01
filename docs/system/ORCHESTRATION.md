# Orchestration & Infrastructure

This is the compiled reference for how the NHL Intel pipeline is scheduled, what it
ingests, and what it ships. It is transcribed from the read-only inventory at
`docs/system/_inventory/50_infra.md`; every claim there cites a DAG task, a Makefile
target, a `serving_tables.yml` entry, an import, or a ripgrep hit. Nothing here has been
re-investigated.

## Hard rules (in force throughout)

1. **Data and ingested objects may never be recommended for deletion.** BigQuery tables
   (`nhl_raw.*`, `nhl_staging.*`, `nhl_mart.*`, `nhl_models.*`), GCS objects, raw data, and
   caches (including `scripts/ppt_cache/`) are out of scope for any deletion suggestion. Only
   code, config, and docs may ever be flagged, and this document flags nothing.
2. **Puck-tracking is retained by owner decision.** `scripts/backfill_ppt_replay.py`,
   `scripts/smoke_ingest_ppt_replay.py`, and `scripts/ppt_cache/` are never dead, regardless
   of how few references appear.

Items that are uncertain in the source are carried forward inline as **[UNCERTAIN]**.

---

## 1. The two DAGs

There are exactly two Airflow DAGs. **There is no backfill DAG.** Historical seeding is done
by a standalone script (`backfill_historical.py`, see section 6).

### 1a. `nhl_daily` — the full nightly pipeline

- **File:** `dags/nhl_daily.py`
- **Schedule:** `schedule_interval="0 13 * * *"` — daily at 13:00 UTC / 08:00 ET
  (`:395`, `catchup=False`, `start_date=datetime(2024, 1, 1)`).
- **default_args:** `owner="nhl-intel"`, `retries=2`, `retry_delay=5min`,
  `email_on_failure=True` (`:383-389`).
- **Shape:** two `PythonOperator`s bookend the graph (the ingest and the report). Everything
  in between is `BashOperator`s that shell into `python -m models_ml.*` / `python -m scripts.*`
  under `/opt/airflow`, plus dbt runs. The dbt command string (`:420-422`) is
  `cd /opt/airflow/dbt && dbt run --profiles-dir /opt/airflow/dbt --log-path /tmp/dbt_logs
  --target-path /tmp/dbt_target`, run with `_dbt_env` carrying the four `GCP_DATASET_*` vars
  (`:412-419`).
- **Monday gating:** many tasks are gated by a Jinja `weekday()==0` guard (`_mon`, `:501`).
  These are the weekly-cadence model builds; they are marked **[Mon]** in the table below.

**Task list (task_id → command → produces / consumes):**

| task_id | operator / command | produces / consumes | cadence |
|---|---|---|---|
| `ingest_nhl_data` | Python `ingest_nhl_data` (`:400`) | 30-day lookback; via `ingestion.nhl_api` + `ingestion.loaders.load_json_to_bigquery` writes `raw_games, raw_boxscores, raw_play_by_play, raw_shift_charts, raw_ppt_replay, raw_game_landing, raw_game_right_rail, raw_standings, raw_partner_odds` (`:74-217`) | daily |
| `refresh_weekly_aux` | Python `refresh_weekly_aux` (`:406`) | `refresh_edge.refresh_season`; `get_skater_faceoffs`→`raw_statsrest_faceoffs`; `get_glossary`→`raw_glossary` (if empty); `ingest_draft_results.fetch_year`→`load_draft_results_to_bigquery` for current+prior draft year (`:246-296`) | **[Mon]** (`:229`) |
| `roster_refresh` | Bash `python -m scripts.refresh_rosters` (`:428`) | live 32-team roster → `raw_rosters`; gates the dbt staging pass | daily |
| `run_dbt_pre_xg` | Bash dbt run, excludes marts + shot intermediates (`:436`) | staging + non-mart intermediates before xG scoring | daily |
| `score_xg` | Bash `models_ml.score_xg --since ds-3` (`:443`) | incremental rescore → `nhl_models.shot_xg` | daily |
| `run_dbt_marts` | Bash dbt `--select path:models/mart int_shot_attempts...` (`:449`) | the marts | daily |
| `compute_ratings` | Bash `models_ml.compute_ratings` (`:459`) | `team_ratings` (before winprob) | daily |
| `simulate_deserved` | Bash `models_ml.simulate_deserved` (`:466`) | `deserved_standings` | daily |
| `compute_style_map` | Bash `models_ml.compute_style_map` (`:474`) | `style_map` | daily |
| `streak_doctor` | Bash `models_ml.streak_doctor` (`:482`) | `streak_cards` | daily |
| `train_rapm` | Bash `models_ml.train_rapm` (`:490`) | `player_impact` (~1-2h) | **[Mon]** |
| `build_event_leverage` | Bash dbt `--select int_event_leverage` (`:504`) | leverage intermediate (needs winprob) | daily |
| `compute_clutch` | Bash `models_ml.compute_clutch` (`:509`) | `player_clutch` | **[Mon]** |
| `compute_consistency` | Bash `models_ml.compute_consistency` (`:514`) | `player_consistency` | **[Mon]** |
| `compute_coach_trust` | Bash `models_ml.compute_coach_trust` (`:519`) | `player_coach_trust` | **[Mon]** |
| `compute_divergence` | Bash `models_ml.compute_divergence` (`:524`) | `divergence_board` | **[Mon]** |
| `compute_deployment_efficiency` | Bash `models_ml.compute_deployment_efficiency` (`:531`) | `deployment_efficiency` | **[Mon]** |
| `refresh_player_bio` | Bash `scripts.ingest_player_bio` (`:540`) | `raw_player_bio` | **[Mon]** |
| `refresh_player_draft_origin` | Bash `scripts.ingest_player_draft_origin` (`:547`) | `raw_player_draft_origin` | **[Mon]** |
| `fit_aging_curves` | Bash `models_ml.fit_aging_curves` (`:552`) | `aging_curves` | **[Mon]** |
| `compute_twins` | Bash `models_ml.compute_twins` (`:557`) | `player_twins` | **[Mon]** |
| `compute_physical` | Bash `models_ml.compute_physical` (`:562`) | `player_physical` | **[Mon]** |
| `compute_composite` | Bash `models_ml.compute_composite` (`:569`) | `player_composite` | **[Mon]** |
| `compute_gar` | Bash `models_ml.compute_gar` (`:581`) | `player_gar` | **[Mon]** |
| `write_archetypes` | Bash `models_ml.fit_archetypes_v2 --write`, single-thread BLAS (`:589`) | `player_archetypes` (loads committed GMM, no refit) | **[Mon]** |
| `train_linefit` | Bash `models_ml.train_linefit` (`:603`) | linefit artifact | **[Mon]** |
| `compute_team_needs` | Bash `models_ml.compute_team_needs` (`:611`) | `team_needs` | **[Mon]** |
| `roster_forecast` | Bash `models_ml.project_roster_forecast --full` (`:621`) | `roster_forecast`, `roster_moves`. Self-guards to offseason | **daily** |
| `compute_player_radar` | Bash `models_ml.compute_player_radar` (`:627`) | `player_radar` | **[Mon]** |
| `compute_goalie_radar` | Bash `models_ml.compute_goalie_radar` (`:632`) | `goalie_radar` | **[Mon]** |
| `compute_archetype_explainer` | Bash `models_ml.compute_archetype_explainer` (`:638`) | `archetype_gallery`, `player_style_map` | **[Mon]** |
| `compute_goalie_gar` | Bash `models_ml.compute_goalie_gar` (`:649`) | `goalie_gar` | **[Mon]** |
| `compute_overall` | Bash `models_ml.compute_overall` (`:658`) | `player_overall`, `goalie_overall` | **[Mon]** |
| `generate_verdicts` | Bash `models_ml.generate_verdicts --weekly` (`:668`) | `player_verdict` (Gemini-narrated, consistency-checked) | **[Mon]** |
| `contracts_match` | Bash `scripts.match_contracts` (`:678`) | `nhl_models.contract_player_map` | **[Mon]** |
| `build_contract_mart` | Bash dbt `--select mart_player_contracts` (`:684`) | `mart_player_contracts` | **[Mon]** |
| `compute_contract_value` | Bash `models_ml.compute_contract_value` (`:692`) | `player_contract_value` | **[Mon]** |
| `ingest_futures` | Bash `scripts.ingest_futures` (`:697`) | `raw_prospects`, `raw_draft_picks` | **[Mon]** |
| `compute_futures_value` | Bash `models_ml.compute_futures_value` (`:704`) | `futures_value` | **[Mon]** |
| `build_tradeable_assets` | Bash dbt `--select mart_tradeable_assets` (`:711`) | `mart_tradeable_assets` (built last) | **[Mon]** |
| `precompute_serving` | Bash `models_ml.precompute_serving --all` (`:720`) | the 6 precompute serving tables (section 3) | **[Mon]** |
| `export_serving` | Bash `scripts.export_to_duckdb` (`:728`) | **DuckDB serving file** `data/serving/nhl_intel.duckdb` (atomic swap) — SHIPPED | **[Mon]** |
| `score_winprob` | Bash `models_ml.score_winprob --since ds-3` (`:735`) | `win_probability` | daily |
| `generate_report` | Python `generate_daily_report` (`:741`) | **`output/report_YYYY-MM-DD.html`** — SHIPPED (section 3) | daily |
| `publish_report` | Python `publish_report_to_gcs` (`:747`) | uploads HTML to `gs://$REPORT_OUTPUT_BUCKET` (default `nhl-intel-reports`) — SHIPPED | daily |

Note that `roster_forecast` runs **daily** despite sitting among the Monday-gated model
builds; it self-guards to the offseason and is a no-op in-season.

**Dependency spine (`:753-763`):**

```
ingest_nhl_data >> refresh_weekly_aux >> run_dbt_pre_xg >> score_xg >> run_dbt_marts
  >> compute_ratings >> score_winprob >> generate_report >> publish_report
```

Every branch below fans into `generate_report` (so the report waits on the whole graph),
and `export_serving` is the final sink.

- **Roster gate:** `ingest_task >> roster_refresh >> run_dbt_pre_xg` (`:766`).
- **Off ratings / marts:** `compute_ratings >> simulate_deserved / streak_doctor`;
  `run_dbt_marts >> compute_style_map` (`:770-772`).
- **RAPM fan-out:** `run_dbt_marts >> train_rapm >> {compute_composite, compute_gar,
  write_archetypes}` (`:775-777`).
- **Reconciliation:** `score_winprob >> build_event_leverage >> compute_clutch`; consistency
  and coach_trust off marts; `[compute_composite, compute_coach_trust] >> compute_divergence`;
  `[compute_composite, score_winprob] >> compute_deployment` (`:780-784`).
- **Trajectories:** `write_archetypes >> fit_aging_curves`; twins/physical off bio+marts
  (`:787-790`).
- **Draft origin:** `weekly_aux_task >> refresh_player_draft_origin` (`:793`).
- **Line-fit:** `[write_archetypes, train_rapm] >> train_linefit` (`:796`).
- **Team needs:** `[compute_composite, write_archetypes, compute_ratings] >>
  compute_team_needs` (`:798`).
- **Forecast:** `[compute_gar, compute_goalie_gar, fit_aging_curves, compute_ratings,
  train_linefit, compute_team_needs] >> roster_forecast` (`:800-801`).
- **Radars / goalie GAR / overall / verdicts** (`:804-811`).
- **Trade tool:** `run_dbt_marts >> contracts_match >> build_contract_mart`;
  `[...] >> contract_value`; `run_dbt_marts >> futures_ingest >> futures_value`;
  `[contract_value, futures_value] >> build_tradeable_assets` (`:816-820`).
- **Serving sink:** `[write_archetypes, train_rapm, run_dbt_marts] >> precompute_serving`;
  `[generate_report, precompute_serving, build_tradeable_assets] >> export_serving`
  (`:824-825`).

### 1b. `offseason_forecast_intraday` — the second forecast refresh

- **File:** `dags/offseason_forecast_intraday.py`
- **Schedule:** `schedule_interval="0 21 * * *"` — 21:00 UTC, 8h after `nhl_daily` (`:47`).
- **Purpose (docstring `:1-16`):** re-runs only the offseason forecast path a second time
  each day so signings and trades land promptly. The forecast job self-guards to the
  offseason and is a no-op once the next season starts, so it is harmless year-round.
- **Tasks and order (`:54-81`):**

```
refresh_rosters (python -m scripts.refresh_rosters)                        # -> raw_rosters
  >> dbt_roster_current (dbt --select stg_roster_current int_player_current_team)
  >> roster_forecast (python -m models_ml.project_roster_forecast --full)  # -> roster_forecast, roster_moves
  >> export_forecast (python -m scripts.export_to_duckdb --only roster_forecast,roster_moves)
```

The export is an **in-place `--only` update** of the DuckDB serving file (fast, no atomic
swap). The docstring notes the backend must reload the file to serve the update (`:14-16`).

---

## 2. Ingestion layer

- **`ingestion/nhl_api.py`** — the NHL API client. Fetchers used by the DAG:
  `get_schedule, get_boxscore, get_play_by_play, get_shift_charts, get_game_landing,
  get_game_right_rail, get_standings_by_date, get_partner_odds, get_ppt_replay,
  derive_season_from_game_id, get_skater_faceoffs, get_glossary` (imported in `nhl_daily.py:22-26,
  233`). Invoked from the two Python DAG tasks and from most `scripts/*` fetchers. One in-code
  comment at `:339` points at `scripts/smoke_ingest_roster.py`.
- **`ingestion/loaders.py`** — the BigQuery writers. Public functions: `load_json_to_bigquery`
  (`:47`, the generic raw-table writer used everywhere) and `load_draft_results_to_bigquery`
  (`:193`, used by `refresh_weekly_aux`). Helpers: `_clean_empty_structs`,
  `_serialize_nested_fields`.
- `ingestion/logs/` is an empty log dir.

**Raw tables that land inline via the DAG's `ingest_nhl_data` task** (`nhl_daily.py:74-217`),
not via the standalone `refresh_*` scripts:

```
raw_games, raw_boxscores, raw_play_by_play, raw_shift_charts, raw_ppt_replay,
raw_game_landing, raw_game_right_rail, raw_standings, raw_partner_odds
```

The standalone `refresh_*` scripts (`refresh_game_context`, `refresh_partner_odds`,
`refresh_standings`, `refresh_statsrest_faceoffs`) duplicate these same landings inline and
are on-demand / backfill utilities only — the nightly DAG does not call them. See the scripts
ledger in section 6.

---

## 3. Shipped external outputs (Phase C surfaces)

Beyond the React frontend, the scheduled DAGs publish these external / consumable surfaces.

**1. Daily HTML report — `output/report_YYYY-MM-DD.html`** (observed:
`output/report_2026-05-29.html`). Produced by `nhl_daily.generate_report`. The report
pipeline lives in `reporting/` and all three modules are imported inside
`generate_daily_report` (`nhl_daily.py:308-310`):

- **`reporting/query.py`** — `get_daily_report_data(date)` reads a **single** mart table,
  `nhl_mart.mart_daily_report_feed`, for the given date (`query.py:23-50`). This is the only
  data source for the report.
- **`reporting/llm_summary.py`** — `generate_summary(report_data)` calls **Gemini**
  (`gemini-2.0-flash-exp`) via `google.generativeai`, keyed on `LLM_API_KEY`; falls back to a
  deterministic `_generate_fallback_summary` if no key or on error (`llm_summary.py:34-131`).
- **`reporting/render.py`** — `render_report(...)` renders the Jinja2 template
  `reporting/templates/report.html` (the only template in that dir) into the HTML string
  (`render.py:19-34`).

`generate_report` writes the file to `output/report_{report_date}.html` where
`report_date = execution_date - 1 day` (`nhl_daily.py:301-341`).

**2. GCS-published report** — `publish_report` (`publish_report_to_gcs`) xcom-pulls that path
and uploads the same HTML to `gs://$REPORT_OUTPUT_BUCKET` (default `nhl-intel-reports`),
returning a public URL `https://storage.googleapis.com/<bucket>/<blob>` (`nhl_daily.py:344-380`).
The bucket is provisioned by `setup_gcs_bucket.py` (section 6).

**3. DuckDB serving file — `data/serving/nhl_intel.duckdb`** — the read-time datastore the
FastAPI backend serves from. Full rebuild by `nhl_daily.export_serving` (atomic swap);
incremental forecast update by `offseason_forecast_intraday.export_forecast` (in-place
`--only`). This IS a data object (hard rule 1: never delete) but is a shipped serving surface.

**4. Serving-table precomputes** — the 6 `kind: precompute` BigQuery tables
(`serving_tables.yml:119-124`), built by `nhl_daily.precompute_serving`, which then ride the
DuckDB export:

```
dim_current_roster, line_member_features, team_handedness,
team_current_lines, serving_game_skater_box, player_situation_toi
```

`best_team_fits` is explicitly NOT precomputed (live DuckDB + cache, `serving_tables.yml:125`).

**Internal-only (explicitly NOT a shipped surface):** the partner-odds snapshot
(`raw_partner_odds`) is labeled "INTERNAL CALIBRATION ONLY — never exposed via API/UI"
(`nhl_daily.py:210`).

---

## 4. Makefile targets and `serving_tables.yml`

These two files are the first-class invocation evidence for the `models_ml` and `scripts`
modules.

### 4a. Makefile targets

`Makefile:1` declares the `.PHONY` list. Every target and its recipe:

| Target | Recipe | Notes |
|---|---|---|
| `precompute-serving` | `python -m models_ml.precompute_serving --all` | also a DAG task |
| `export-serving` | `python -m scripts.export_to_duckdb` | also a DAG task |
| `verify-serving` | `SERVING_BACKEND=bigquery/duckdb python -m scripts.verify_serving_parity` + diff | parity proof BQ vs DuckDB |
| `setup` | venv + `pip install -r requirements.txt -r backend/requirements.txt` + `npm install` | |
| `dbt-build` | `cd dbt && dbt build --target dev` | |
| `backend` | `uvicorn main:app --reload --port 8000` | |
| `frontend` | `npm run dev` | |
| `test` | `pytest -q` | runs the `tests/` suite (per `pytest.ini`) |
| `edge-refresh` | `python -m scripts.refresh_edge --season $(SEASON)` | `SEASON ?= 2025-26` |
| `roster-refresh` | `python -m scripts.refresh_rosters --season $(SEASON)` | |
| `rapm` | `python -m models_ml.train_rapm` | |
| `deployment` | `python -m models_ml.compute_deployment_efficiency` | |
| `gar` / `gar-validate` | `models_ml.compute_gar` / `models_ml.validate_gar` | |
| `goalie-gar` / `goalie-gar-validate` | `models_ml.compute_goalie_gar` / `models_ml.validate_goalie_gar` | |
| `overall` | `models_ml.compute_overall` | |
| `linefit` | `models_ml.train_linefit` | |
| `team-needs` | `models_ml.compute_team_needs` | |
| `roster-forecast` / `roster-forecast-validate` | `models_ml.project_roster_forecast --full` / `models_ml.validate_roster_forecast` | |
| `roster-builder-calibrate` | `models_ml.calibrate_roster_builder` | |
| `roster-player-projection` | `models_ml.project_roster_player --write` | |
| `trade-fit-validate` | `models_ml.validate_trade_fit` | |
| `trade-engine-validate` | `SERVING_BACKEND=duckdb python -m backend.validate_trade_engine` | |
| `archetypes-v2` | `VECLIB_MAXIMUM_THREADS=1 OMP_NUM_THREADS=1 python -m models_ml.fit_archetypes_v2 --write` | |
| `radar` | `models_ml.compute_player_radar` + `compute_goalie_radar` | |
| `archetype-explainer` | `models_ml.compute_archetype_explainer` | |
| `contracts-load` / `contracts-match` | `scripts.load_contracts` / `scripts.match_contracts` | |
| `contract-value` | `models_ml.compute_contract_value` | |
| `futures-ingest` / `futures-value` | `scripts.ingest_futures` / `models_ml.compute_futures_value` | |
| `trade-data` | phony aggregate: `contracts-load contracts-match contract-value futures-ingest futures-value` | |
| `trades-load` / `trade-outcomes` | `scripts.load_trades` / `models_ml.compute_trade_outcomes` | NOT in the `.PHONY` line (`:1`) but ARE defined (`:170-173`) |

The Makefile is invocation evidence for these `scripts/`: `refresh_edge, refresh_rosters,
load_contracts, match_contracts, ingest_futures, load_trades, export_to_duckdb,
verify_serving_parity`.

### 4b. `serving_tables.yml`

Single source of truth for the DuckDB serving layer, consumed by `scripts/export_to_duckdb.py`
and `models_ml/duck.py`. `meta.duckdb_path: data/serving/nhl_intel.duckdb`,
`recent_seasons: 3`. The `tables:` list has ~60 entries in three groups:

- **`kind: source, cap: full/recent`** — staging views (`stg_games, stg_boxscores, stg_rosters,
  stg_play_by_play, stg_game_context, stg_standings, stg_player_bio, int_shot_types,
  int_shot_attempts_all, int_line_seasons`), all marts (`mart_team_game_stats` …
  `mart_tradeable_assets`), and all model tables (`shot_xg, win_probability, player_archetypes,
  player_composite, player_radar, goalie_radar, player_gar, goalie_gar, player_overall,
  goalie_overall, player_impact, player_clutch, player_consistency, player_verdict,
  player_coach_trust, divergence_board, deployment_efficiency, aging_curves, player_twins,
  player_physical, team_ratings, deserved_standings, style_map, streak_cards, team_needs,
  archetype_gallery, roster_forecast, roster_moves, roster_player_projection, player_style_map,
  player_contract_value, futures_value, pick_value_curve, draft_value_summary,
  draft_value_player, int_draft_player_value, player_pwar, trade_outcomes, stg_trades,
  stg_gm_tenures`).
- **`kind: precompute, built: true`** — the 6 tables built by `models_ml/precompute_serving.py`
  (`:119-124`): `dim_current_roster, line_member_features, team_handedness, team_current_lines,
  serving_game_skater_box, player_situation_toi`. `best_team_fits` is explicitly NOT precomputed
  (`:125`).
- **`recent`-capped per-event tables:** `stg_play_by_play, int_shot_types,
  int_shot_attempts_all, shot_xg, win_probability` (recent 3 seasons).

`export_to_duckdb.py` supports `--only`, `--all` (via manifest), `--dry-run`,
`--into-existing`, `--duckdb-path`, `--recent-seasons`. It builds a temp file and **atomically
swaps** (`:104-210`), except `--only` / `--into-existing`, which patch in place (used by the
intraday DAG).

---

## 5. scripts/ ledger

Full ledger: 42 `.py` files + 4 `FINDINGS.md`. Invocation legend: **DAG** = a task in one of
the two DAGs; **Make** = a Makefile target; **main-only** = has an `if __name__ == "__main__"`
block and no other in-repo caller (manual / on-demand). `scripts/__init__.py` makes `scripts`
a package (enables `python -m scripts.*`).

### 5a. Ingest / refresh / load / match / export scripts

| Script | Purpose | Writes | Invoked by |
|---|---|---|---|
| `refresh_rosters.py` | live 32-team roster membership | `raw_rosters` | DAG `roster_refresh` + intraday `refresh_rosters`; Make `roster-refresh` |
| `refresh_edge.py` | NHL Edge season aggregates | `raw_edge_skaters/goalies/teams` | DAG `refresh_weekly_aux` (`refresh_season`); Make `edge-refresh` |
| `refresh_game_context.py` | gamecenter landing + right-rail | `raw_game_landing, raw_game_right_rail` | **main-only** (DAG lands these inline). On-demand/backfill |
| `refresh_partner_odds.py` | partner odds snapshot (internal calibration) | `raw_partner_odds` | **main-only** (DAG lands inline). On-demand |
| `refresh_standings.py` | league standings-by-date | `raw_standings` | **main-only** (DAG lands inline). On-demand/backfill |
| `refresh_statsrest_faceoffs.py` | season faceoff splits | `raw_statsrest_faceoffs` | **main-only** (DAG lands inline in `refresh_weekly_aux`). On-demand |
| `ingest_player_bio.py` | player age/height/weight | `raw_player_bio` | DAG `refresh_player_bio` |
| `ingest_player_draft_origin.py` | authoritative draft-origin map | `raw_player_draft_origin` | DAG `refresh_player_draft_origin` |
| `ingest_draft_results.py` | historical draft results | `raw_draft_results` (+ `raw_draft_picks`) | DAG `refresh_weekly_aux` (`fetch_year`) |
| `ingest_futures.py` | org prospect lists + own picks | `raw_prospects, raw_draft_picks` | DAG `ingest_futures`; Make `futures-ingest` |
| `ingest_glossary.py` | stats-REST glossary (one-time) | `raw_glossary` | **main-only** (DAG calls `get_glossary` directly). One-time/on-demand |
| `ingest_shifts.py` | shift-chart backfill | `raw_shift_charts` | **main-only** (DAG lands shifts inline). Resumable backfill |
| `load_contracts.py` | contract CSV snapshot | `raw_contracts` | DAG `contracts_match` deps + Make `contracts-load` |
| `load_rfas.py` | pending-RFA CSV | `raw_contracts_rfa` | **main-only** + `tests/test_contract_rfa.py`. Manual load |
| `load_trades.py` | historical trades CSV | `raw_trades` | Make `trades-load`; `smoke_load_trades.py` |
| `load_gm_tenures.py` | curated GM-tenures CSV | `raw_gm_tenures` | **main-only** + `smoke_load_gm_tenures.py`. Manual load |
| `match_contracts.py` | resolve contracts→player_id | `nhl_models.contract_player_map` + `models_ml/artifacts/contract_match_report.md` | DAG `contracts_match`; Make `contracts-match` |
| `match_rfas.py` | resolve RFAs→player_id | RFA map | **main-only** + `tests/test_contract_rfa.py`. On-demand |
| `export_to_duckdb.py` | materialize DuckDB serving file | `data/serving/nhl_intel.duckdb` | DAG `export_serving` + intraday `export_forecast`; Make `export-serving` |
| `verify_serving_parity.py` | BQ vs DuckDB parity diff | (prints) | Make `verify-serving`; `models_ml/duck.py` |
| `backfill_edge.py` | backfill Edge across all seasons | edge raw tables | **main-only** (calls `refresh_edge`). Backfill |
| `backfill_ppt_replay.py` | backfill goal-tracking sprites | `raw_ppt_replay` | **main-only**. **RETAINED by owner (hard rule 2) — never dead** |
| `explore_edge.py` | Edge API exploration tool | (prints) | **main-only**. Dev exploration |
| `diagnose_contract_grades.py` | contract-grade diagnostics (print only) | nothing | **main-only**. Diagnostic |

### 5b. `smoke_*` scripts (all 12) — every one main-only, referenced by nothing but its own FINDINGS doc

There is **no** smoke target in the Makefile and **no** smoke reference in either DAG. Each
smoke script has exactly one `if __name__ == "__main__"` block and is run by hand.

| Smoke script | Referenced by anything? |
|---|---|
| `smoke_ingest_draft_results.py` | No non-self refs. main-only |
| `smoke_ingest_game_context.py` | No non-self refs. main-only |
| `smoke_ingest_glossary.py` | No non-self refs. main-only |
| `smoke_ingest_partner_odds.py` | No non-self refs. main-only |
| `smoke_ingest_ppt_replay.py` | No non-self refs — **RETAINED by owner (hard rule 2), never dead** |
| `smoke_ingest_roster.py` | Only a comment in `ingestion/nhl_api.py:339` + `ROSTER_FINDINGS.md`. main-only |
| `smoke_ingest_shiftcharts.py` | No non-self refs. main-only |
| `smoke_ingest_standings.py` | No non-self refs. main-only |
| `smoke_ingest_statsrest_faceoffs.py` | No non-self refs. main-only |
| `smoke_load_gm_tenures.py` | No non-self refs. main-only |
| `smoke_load_trades.py` | No non-self refs. main-only |
| `smoke_roster_source.py` | No non-self refs. main-only |

All smoke scripts are developer verification harnesses run on demand against real API /
BigQuery output. They are outside the pytest suite (`pytest.ini testpaths = tests`) and are
not wired into any DAG or Make target — the manual counterpart to the `*_FINDINGS.md` notes.
No deletion recommended; status only.

### 5c. FINDINGS docs (flag for DOC_RECONCILIATION, do not duplicate)

`scripts/DRAFT_RESULTS_FINDINGS.md`, `scripts/EDGE_FINDINGS.md`, `scripts/ROSTER_FINDINGS.md`,
`scripts/STATSREST_FINDINGS.md` — hand-written observations from running the corresponding
smoke scripts. Flagged for DOC_RECONCILIATION; content not reproduced.

Other non-`.py` under `scripts/`: `draft_results_samples/`, `edge_samples/`, `ppt_cache/`
(cache — hard rules 1 + 2: never delete), `__pycache__/`.

---

## 6. Root one-off utilities

These live at the repo root and are each accounted for. `backfill_historical.py` is the
history-seeding path in the absence of any backfill DAG.

| File | What it is | Wired to anything? | Status |
|---|---|---|---|
| `backfill_historical.py` | standalone async historical backfill (docstring: "runs independently of Airflow," faster than the DAG) | referenced by `populate_raw_games.py`; no DAG/Make | **Live one-off utility** — the intended way to seed history (there is NO backfill DAG). Run manually |
| `populate_raw_games.py` | creates `raw_games` schedule rows from existing `raw_boxscores` (backfill only loads boxscores/pbp) | references `backfill_historical.py`; no other refs | one-off repair, paired with the backfill. Likely superseded in steady state but kept as a companion. **[UNCERTAIN]** |
| `load_schedule_only.py` | loads only schedule data into `raw_games` when boxscores/pbp already present | no non-self refs. main-only | one-off repair. Likely superseded by the DAG's normal `raw_games` load. **[UNCERTAIN]** |
| `deduplicate_raw_tables.py` | removes duplicate game records from raw tables (keeps latest `ingestion_date`) | no non-self refs. main-only | one-off maintenance utility; run on demand if raw dupes appear |
| `setup_gcs_bucket.py` | creates + configures the public GCS bucket `nhl-intel-reports` | no code refs, but provisions the bucket `publish_report` writes to | **Live infra bootstrap** (run once at setup). Ties to the shipped report in section 3 |

**The four root `test_*.py` are outside the pytest suite.** `pytest.ini` sets
`testpaths = tests`, and its comment states explicitly that the repo-root `test_*.py` files are
live-service integration smoke scripts (NHL API, BigQuery, Gemini) run on demand, not part of
`make test`. Each hard-codes `sys.path.insert(...)` and
`GOOGLE_APPLICATION_CREDENTIALS=.../secrets/nhl-intel-sa.json` — designed for manual local runs,
not CI.

| File | What it smokes |
|---|---|
| `test_end_to_end.py` | full report generation + GCS publish |
| `test_llm.py` | `reporting/llm_summary` (Gemini) |
| `test_query.py` | `reporting/query` (BigQuery) |
| `test_report.py` | the full reporting pipeline |

---

## 7. tests/ pytest suite and insight_engine/

### 7a. `tests/` — the pytest suite (`make test` / `pytest -q`)

`pytest.ini` → `testpaths = tests`. Nine test modules, all hermetic (no network/BigQuery/DuckDB)
except `test_api.py`:

| Test file | Coverage |
|---|---|
| `test_api.py` | NHL API connectivity sanity check (**live**, hits the real API) |
| `test_contract_grade_basket.py` | contract grades — consensus deals land in expected band |
| `test_contract_grade_roundtrip.py` | hermetic round-trip of the contract-grade valuation curve |
| `test_contract_rfa.py` | hermetic pending-RFA ingestion into the tradeable-asset layer (imports `scripts.load_rfas`, `scripts.match_rfas`) |
| `test_roster_forecast.py` | hermetic offseason roster forecast |
| `test_roster_ingest.py` | hermetic live-roster ingestion helpers |
| `test_trade_engine.py` | hermetic trade evaluation engine |
| `test_trade_fit_verdict.py` | hermetic context-aware trade-fit verdict (imports `insight_engine`) |
| `test_value_overall.py` | hermetic cross-position WAR + card-only Overall |

The suite centers on the trade / contract / roster-forecast / value layer. There are no dbt or
model-training tests here (those validate via `make *-validate` targets, section 4a).

### 7b. `insight_engine/` — deterministic insight templates (11 files)

- **Files (11):** `README.md`, `__init__.py`, `templates/__init__.py`, and 8 template modules:
  `divergence.py, line_fit.py, matchup.py, playoff_bracket.py, roster_forecast.py, team_fit.py,
  team_overview.py, value_gap.py`.
- **Purpose (`README.md`):** a **deterministic** insight system — "No LLM in the site path."
  Each insight is a Python format template with named slots, verified by a consistency checker.
- **[UNCERTAIN — DOC vs REALITY GAP, flag for DOC_RECONCILIATION]** The `README.md` describes a
  `registry.py`, a `detectors/` directory, and a `smoke.py` "built in Phase 6." **None of those
  exist on disk** — only `templates/` is present. The README overstates the built structure.
  The templates themselves are live and consumed, so `insight_engine/` is not dead.
- **Consumers:** `backend/services/tools.py` imports
  `insight_engine.templates.line_fit.swap_reasons` (`:232`) and `templates.matchup` (`:397`);
  `backend/services/offseason.py` imports `templates.roster_forecast` (`:61`);
  `models_ml/score_line.py` imports `templates.line_fit` (`:26`); also referenced by
  `models_ml/{build_playoff_weights,compute_divergence,config,score_team_fit}.py`,
  `backend/routers/{playoffs,players,teams}.py`, and `tests/test_trade_fit_verdict.py`.

---

## 8. Container / infra

- **`Dockerfile`** — `FROM apache/airflow:2.8.1-python3.11`, installs `requirements.txt`.
- **`docker-compose.yml`** — services: `postgres` (`postgres:14`, container `nhl-postgres`),
  `airflow-webserver` (`nhl-airflow-webserver`), `airflow-scheduler` (`nhl-airflow-scheduler`),
  volume `postgres-db-volume`.
- **`start_airflow.sh`** — local dev launcher: sets `AIRFLOW_HOME=~/airflow`, loads `.env`,
  starts webserver (:8080, admin/admin) + scheduler.
- **`requirements.txt`** — `httpx, pydantic, python-dotenv, pytest, respx, jinja2, tenacity,
  google-cloud-bigquery>=3.20, google-generativeai, google-cloud-storage`.
- **`.env.example`** — `GCP_PROJECT_ID`, `GCP_DATASET_{RAW,STAGING,MART}`,
  `GOOGLE_APPLICATION_CREDENTIALS`, `LLM_API_KEY`, `LLM_PROVIDER=gemini`, `REPORT_OUTPUT_BUCKET`,
  `AIRFLOW_SMTP_EMAIL/PASSWORD`.
  - **[UNCERTAIN — minor DOC gap, flag for DOC_RECONCILIATION]** The DAGs also read
    `GCP_DATASET_MODELS`, which is NOT listed in `.env.example`.
