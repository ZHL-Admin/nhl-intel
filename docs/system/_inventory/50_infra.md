# 50 — Orchestration & Infra Inventory

READ-ONLY inventory of the `orchestration_infra` domain (88 files): `dags/`, `ingestion/`,
`reporting/`, `insight_engine/`, `scripts/`, `tests/`, and the root infra/one-off files. Every
claim below cites its evidence (a DAG task definition, a Makefile target, a `serving_tables.yml`
entry, an import, or a ripgrep hit).

## HARD RULES (in force throughout this document)

1. **Data / ingested objects may NEVER be recommended for deletion.** BigQuery tables (`nhl_raw.*`,
   `nhl_staging.*`, `nhl_mart.*`, `nhl_models.*`), GCS objects, raw data, and caches (including
   `scripts/ppt_cache/`) are out of scope for any deletion suggestion. Only code/config/docs may
   ever be flagged, and this document flags nothing for deletion — it is an inventory.
2. **Puck-tracking is retained by owner decision.** `scripts/backfill_ppt_replay.py`,
   `scripts/smoke_ingest_ppt_replay.py`, and `scripts/ppt_cache/` are **never dead**, regardless of
   how few references ripgrep finds.

Uncertainty is labeled inline as **[UNCERTAIN]**.

---

## 1. Airflow DAGs

There are **exactly two** DAGs: `dags/nhl_daily.py` and `dags/offseason_forecast_intraday.py`.
There is **no** `nhl_historical_backfill` DAG (historical backfill is a standalone script — see §7).

### 1a. `nhl_daily` — the nightly pipeline

- **File:** `dags/nhl_daily.py`
- **Schedule:** `schedule_interval="0 13 * * *"` — daily at 13:00 UTC / 08:00 ET
  (`dags/nhl_daily.py:395`, `catchup=False`, `start_date=datetime(2024, 1, 1)`).
- **default_args:** `owner="nhl-intel"`, `retries=2`, `retry_delay=5min`, `email_on_failure=True`
  (`:383-389`).
- **Two PythonOperators run the ingest + report; everything in between is BashOperators that shell
  into `python -m models_ml.*` / `python -m scripts.*` under `/opt/airflow`, plus dbt runs.**

The `_dbt` command string (`:420-422`) is
`cd /opt/airflow/dbt && /home/airflow/.local/bin/dbt run --profiles-dir /opt/airflow/dbt
--log-path /tmp/dbt_logs --target-path /tmp/dbt_target`, run with `_dbt_env` carrying the four
`GCP_DATASET_*` vars (`:412-419`). Many tasks are Monday-gated via a Jinja `weekday()==0` guard
(`_mon`, `:501`).

**Task list (task_id → what it runs / produces-consumes):**

| task_id | operator / command | produces / consumes |
|---|---|---|
| `ingest_nhl_data` | Python `ingest_nhl_data` (`:400`) | Looks back 30 days, calls `ingestion.nhl_api` + `ingestion.loaders.load_json_to_bigquery`; writes raw `raw_games, raw_boxscores, raw_play_by_play, raw_shift_charts, raw_ppt_replay, raw_game_landing, raw_game_right_rail, raw_standings, raw_partner_odds` (`:74-217`) |
| `refresh_weekly_aux` | Python `refresh_weekly_aux` (`:406`) | Monday-only (`:229`). Calls `scripts.refresh_edge.refresh_season`, `get_skater_faceoffs`→`raw_statsrest_faceoffs`, `get_glossary`→`raw_glossary` (if empty), and `scripts.ingest_draft_results.fetch_year`→`load_draft_results_to_bigquery` for current+prior draft year (`:246-296`) |
| `roster_refresh` | Bash `python -m scripts.refresh_rosters` (`:428`) | Live 32-team roster → `raw_rosters`; gates the dbt staging pass |
| `run_dbt_pre_xg` | Bash dbt run, excludes marts + shot intermediates (`:436`) | Builds staging + non-mart intermediates before xG scoring |
| `score_xg` | Bash `python -m models_ml.score_xg --since ds-3` (`:443`) | Incremental rescore → `nhl_models.shot_xg` |
| `run_dbt_marts` | Bash dbt `--select path:models/mart int_shot_attempts...` (`:449`) | Builds the marts |
| `compute_ratings` | Bash `python -m models_ml.compute_ratings` (`:459`) | `team_ratings` (before winprob) |
| `simulate_deserved` | Bash `python -m models_ml.simulate_deserved` (`:466`) | `deserved_standings` |
| `compute_style_map` | Bash `python -m models_ml.compute_style_map` (`:474`) | `style_map` (daily) |
| `streak_doctor` | Bash `python -m models_ml.streak_doctor` (`:482`) | `streak_cards` |
| `train_rapm` | Bash `python -m models_ml.train_rapm`, Monday-only (`:490`) | `player_impact` (weekly, ~1-2h) |
| `build_event_leverage` | Bash dbt `--select int_event_leverage` (`:504`) | leverage intermediate (needs winprob) |
| `compute_clutch` | Bash `models_ml.compute_clutch`, Mon (`:509`) | `player_clutch` |
| `compute_consistency` | Bash `models_ml.compute_consistency`, Mon (`:514`) | `player_consistency` |
| `compute_coach_trust` | Bash `models_ml.compute_coach_trust`, Mon (`:519`) | `player_coach_trust` |
| `compute_divergence` | Bash `models_ml.compute_divergence`, Mon (`:524`) | `divergence_board` |
| `compute_deployment_efficiency` | Bash `models_ml.compute_deployment_efficiency`, Mon (`:531`) | `deployment_efficiency` |
| `refresh_player_bio` | Bash `python -m scripts.ingest_player_bio`, Mon (`:540`) | `raw_player_bio` |
| `refresh_player_draft_origin` | Bash `python -m scripts.ingest_player_draft_origin`, Mon (`:547`) | `raw_player_draft_origin` |
| `fit_aging_curves` | Bash `models_ml.fit_aging_curves`, Mon (`:552`) | `aging_curves` |
| `compute_twins` | Bash `models_ml.compute_twins`, Mon (`:557`) | `player_twins` |
| `compute_physical` | Bash `models_ml.compute_physical`, Mon (`:562`) | `player_physical` |
| `compute_composite` | Bash `models_ml.compute_composite`, Mon (`:569`) | `player_composite` |
| `compute_gar` | Bash `models_ml.compute_gar`, Mon (`:581`) | `player_gar` |
| `write_archetypes` | Bash `models_ml.fit_archetypes_v2 --write`, Mon, single-thread BLAS (`:589`) | `player_archetypes` (loads committed GMM, no refit) |
| `train_linefit` | Bash `models_ml.train_linefit`, Mon (`:603`) | linefit artifact |
| `compute_team_needs` | Bash `models_ml.compute_team_needs`, Mon (`:611`) | `team_needs` |
| `roster_forecast` | Bash `python -m models_ml.project_roster_forecast --full` (`:621`) | `roster_forecast`, `roster_moves`. **Runs DAILY** (self-guards to offseason) |
| `compute_player_radar` | Bash `models_ml.compute_player_radar`, Mon (`:627`) | `player_radar` |
| `compute_goalie_radar` | Bash `models_ml.compute_goalie_radar`, Mon (`:632`) | `goalie_radar` |
| `compute_archetype_explainer` | Bash `models_ml.compute_archetype_explainer`, Mon (`:638`) | `archetype_gallery`, `player_style_map` |
| `compute_goalie_gar` | Bash `models_ml.compute_goalie_gar`, Mon (`:649`) | `goalie_gar` |
| `compute_overall` | Bash `models_ml.compute_overall`, Mon (`:658`) | `player_overall`, `goalie_overall` |
| `generate_verdicts` | Bash `models_ml.generate_verdicts --weekly`, Mon (`:668`) | `player_verdict` (Gemini-narrated, consistency-checked) |
| `contracts_match` | Bash `python -m scripts.match_contracts`, Mon (`:678`) | `nhl_models.contract_player_map` |
| `build_contract_mart` | Bash dbt `--select mart_player_contracts`, Mon (`:684`) | `mart_player_contracts` |
| `compute_contract_value` | Bash `models_ml.compute_contract_value`, Mon (`:692`) | `player_contract_value` |
| `ingest_futures` | Bash `python -m scripts.ingest_futures`, Mon (`:697`) | `raw_prospects`, `raw_draft_picks` |
| `compute_futures_value` | Bash `models_ml.compute_futures_value`, Mon (`:704`) | `futures_value` |
| `build_tradeable_assets` | Bash dbt `--select mart_tradeable_assets`, Mon (`:711`) | `mart_tradeable_assets` (built LAST) |
| `precompute_serving` | Bash `python -m models_ml.precompute_serving --all`, Mon (`:720`) | the 6 precompute serving tables (see §5) |
| `export_serving` | Bash `python -m scripts.export_to_duckdb`, Mon (`:728`) | **DuckDB serving file** `data/serving/nhl_intel.duckdb` (atomic swap) — SHIPPED SURFACE |
| `score_winprob` | Bash `models_ml.score_winprob --since ds-3` (`:735`) | `win_probability` |
| `generate_report` | Python `generate_daily_report` (`:741`) | **`output/report_YYYY-MM-DD.html`** — SHIPPED SURFACE (see §3) |
| `publish_report` | Python `publish_report_to_gcs` (`:747`) | **Uploads the HTML to `gs://$REPORT_OUTPUT_BUCKET`** (default `nhl-intel-reports`) — SHIPPED SURFACE |

**Dependency order (`:753-825`).** The linear spine (`:753-763`):

```
ingest_nhl_data >> refresh_weekly_aux >> run_dbt_pre_xg >> score_xg >> run_dbt_marts
  >> compute_ratings >> score_winprob >> generate_report >> publish_report
```

Plus these branches, all of which fan into `generate_report` (which therefore waits on the whole
graph), and `export_serving` as the final sink:

- `ingest_task >> roster_refresh >> run_dbt_pre_xg` (`:766`) — roster gates the staging pass.
- `compute_ratings >> simulate_deserved / streak_doctor` ; `run_dbt_marts >> compute_style_map` (`:770-772`).
- `run_dbt_marts >> train_rapm >> {compute_composite, compute_gar, write_archetypes}` (`:775-777`).
- Reconciliation: `score_winprob >> build_event_leverage >> compute_clutch`; consistency / coach_trust
  off marts; `[compute_composite, compute_coach_trust] >> compute_divergence`;
  `[compute_composite, score_winprob] >> compute_deployment` (`:780-784`).
- Trajectories: `write_archetypes >> fit_aging_curves`; twins/physical off bio+marts (`:787-790`).
- `weekly_aux_task >> refresh_player_draft_origin` (`:793`).
- Line-fit: `[write_archetypes, train_rapm] >> train_linefit` (`:796`).
- `[compute_composite, write_archetypes, compute_ratings] >> compute_team_needs` (`:798`).
- Forecast: `[compute_gar, compute_goalie_gar, fit_aging_curves, compute_ratings, train_linefit,
  compute_team_needs] >> roster_forecast` (`:800-801`).
- Radars, goalie GAR, overall, verdicts (`:804-811`).
- Trade tool: `run_dbt_marts >> contracts_match >> build_contract_mart`; `[...] >> contract_value`;
  `run_dbt_marts >> futures_ingest >> futures_value`; `[contract_value, futures_value] >>
  build_tradeable_assets` (`:816-820`).
- Serving sink: `[write_archetypes, train_rapm, run_dbt_marts] >> precompute_serving`;
  `[generate_report, precompute_serving, build_tradeable_assets] >> export_serving` (`:824-825`).

### 1b. `offseason_forecast_intraday` — the second daily refresh

- **File:** `dags/offseason_forecast_intraday.py`
- **Schedule:** `schedule_interval="0 21 * * *"` — 21:00 UTC, 8h after `nhl_daily` (`:47`).
- **Purpose (module docstring `:1-16`):** re-runs only the offseason forecast path a second time
  each day so signings/trades land promptly; the forecast job self-guards to the offseason and is a
  no-op once the next season starts, so it is harmless year-round.
- **Tasks + order (`:54-81`):**

```
refresh_rosters (python -m scripts.refresh_rosters)                       # -> raw_rosters
  >> dbt_roster_current (dbt --select stg_roster_current int_player_current_team)
  >> roster_forecast (python -m models_ml.project_roster_forecast --full) # -> roster_forecast, roster_moves
  >> export_forecast (python -m scripts.export_to_duckdb --only roster_forecast,roster_moves)
```

The export is an **in-place `--only` update** of the DuckDB serving file (fast, no atomic swap);
the docstring notes the backend must reload the file to serve the update (`:14-16`).

---

## 2. `ingestion/` — API client + BigQuery loaders

- **`ingestion/nhl_api.py`** — the NHL API client. Exposes fetchers used by the DAG:
  `get_schedule, get_boxscore, get_play_by_play, get_shift_charts, get_game_landing,
  get_game_right_rail, get_standings_by_date, get_partner_odds, get_ppt_replay,
  derive_season_from_game_id, get_skater_faceoffs, get_glossary` (imported in
  `dags/nhl_daily.py:22-26, 233`). Invoked from the two Python DAG tasks and from most
  `scripts/*` fetchers. (One in-code comment at `:339` points at `scripts/smoke_ingest_roster.py`.)
- **`ingestion/loaders.py`** — BigQuery writers. Public functions: `load_json_to_bigquery`
  (`:47` — the generic raw-table writer used everywhere) and `load_draft_results_to_bigquery`
  (`:193` — used by `refresh_weekly_aux` for draft results). Helpers `_clean_empty_structs`,
  `_serialize_nested_fields`.
- Raw tables written **via the DAG's `ingest_nhl_data` task** (not via the standalone `refresh_*`
  scripts, which duplicate the same landings inline): `raw_games, raw_boxscores,
  raw_play_by_play, raw_shift_charts, raw_ppt_replay, raw_game_landing, raw_game_right_rail,
  raw_standings, raw_partner_odds` (`dags/nhl_daily.py:74-217`).
- `ingestion/logs/` exists (empty log dir).

---

## 3. `reporting/` — the daily HTML report (SHIPPED EXTERNAL OUTPUT)

The daily report is a real external artifact: **`output/report_YYYY-MM-DD.html`** (observed:
`output/report_2026-05-29.html`), uploaded to GCS.

Pipeline (all three modules imported inside `generate_daily_report`, `dags/nhl_daily.py:308-310`):

1. **`reporting/query.py`** — `get_daily_report_data(date)` reads a **single** mart table,
   `nhl_mart.mart_daily_report_feed`, for the given date (`query.py:23-50`). This is the only
   data source for the report.
2. **`reporting/llm_summary.py`** — `generate_summary(report_data)` calls **Gemini**
   (`gemini-2.0-flash-exp`) via `google.generativeai`, keyed on `LLM_API_KEY`; falls back to a
   deterministic `_generate_fallback_summary` if no key or on error (`llm_summary.py:34-131`).
3. **`reporting/render.py`** — `render_report(...)` renders Jinja2 template
   `reporting/templates/report.html` (the only template in that dir) into the HTML string
   (`render.py:19-34`).

**Which DAG tasks publish it:** `generate_report` (Python `generate_daily_report`) writes the file
to `output/report_{report_date}.html` where `report_date = execution_date - 1 day`
(`dags/nhl_daily.py:301-341`); `publish_report` (Python `publish_report_to_gcs`) xcom-pulls that
path and uploads it to `gs://$REPORT_OUTPUT_BUCKET` (default `nhl-intel-reports`), returning a
public URL `https://storage.googleapis.com/<bucket>/<blob>` (`:344-380`). The bucket is created by
`setup_gcs_bucket.py` (§7).

---

## 4. `insight_engine/` — deterministic insight templates (11 files)

- **Files (11):** `README.md`, `__init__.py`, `templates/__init__.py`, and 8 template modules:
  `divergence.py, line_fit.py, matchup.py, playoff_bracket.py, roster_forecast.py, team_fit.py,
  team_overview.py, value_gap.py`.
- **Purpose (`README.md`):** a **deterministic** insight system — "No LLM in the site path." Each
  insight is a Python format template with named slots, verified by a consistency checker.
- **[UNCERTAIN / DOC vs REALITY GAP]** The `README.md` describes `registry.py`, a `detectors/`
  directory, and `smoke.py` "built in Phase 6." **None of those exist on disk** — only `templates/`
  is present. Flag for DOC_RECONCILIATION: the README overstates the built structure. The
  *templates* are nonetheless **live and consumed**, so `insight_engine/` is not dead.
- **Consumers (ripgrep):** `backend/services/tools.py` imports
  `insight_engine.templates.line_fit.swap_reasons` (`:232`) and `templates.matchup` (`:397`);
  `backend/services/offseason.py` imports `templates.roster_forecast` (`:61`);
  `models_ml/score_line.py` imports `templates.line_fit` (`:26`); also referenced by
  `models_ml/{build_playoff_weights,compute_divergence,config,score_team_fit}.py`,
  `backend/routers/{playoffs,players,teams}.py`, and `tests/test_trade_fit_verdict.py`.

---

## 5. `serving_tables.yml` + `Makefile` (invocation evidence)

### 5a. Makefile targets (all of them)

`Makefile:1` declares the `.PHONY` list. Every target and its recipe:

| Target | Recipe | Notes |
|---|---|---|
| `precompute-serving` | `python -m models_ml.precompute_serving --all` | builds precompute serving tables (also DAG task) |
| `export-serving` | `python -m scripts.export_to_duckdb` | materializes DuckDB serving file (also DAG task) |
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
| `trades-load` / `trade-outcomes` | `scripts.load_trades` / `models_ml.compute_trade_outcomes` | **Note:** `trades-load` and `trade-outcomes` are NOT in the `.PHONY` line (`:1`) but ARE defined (`:170-173`) |

The Makefile is first-class invocation evidence for `models_ml` scripts and for these `scripts/`:
`refresh_edge, refresh_rosters, load_contracts, match_contracts, ingest_futures, load_trades,
export_to_duckdb, verify_serving_parity`.

### 5b. `serving_tables.yml`

Single source of truth for the DuckDB serving layer, consumed by `scripts/export_to_duckdb.py` and
`models_ml/duck.py` (ripgrep). `meta.duckdb_path: data/serving/nhl_intel.duckdb`,
`recent_seasons: 3`. The `tables:` list has **~60 entries** in three groups:

- **`kind: source, cap: full/recent`** — staging views (`stg_games, stg_boxscores, stg_rosters,
  stg_play_by_play, stg_game_context, stg_standings, stg_player_bio, int_shot_types,
  int_shot_attempts_all, int_line_seasons`), all marts (`mart_team_game_stats` … `mart_tradeable_assets`),
  and all model tables (`shot_xg, win_probability, player_archetypes, player_composite, player_radar,
  goalie_radar, player_gar, goalie_gar, player_overall, goalie_overall, player_impact, player_clutch,
  player_consistency, player_verdict, player_coach_trust, divergence_board, deployment_efficiency,
  aging_curves, player_twins, player_physical, team_ratings, deserved_standings, style_map,
  streak_cards, team_needs, archetype_gallery, roster_forecast, roster_moves,
  roster_player_projection, player_style_map, player_contract_value, futures_value,
  pick_value_curve, draft_value_summary, draft_value_player, int_draft_player_value, player_pwar,
  trade_outcomes, stg_trades, stg_gm_tenures`).
- **`kind: precompute, built: true`** — the 6 tables built by `models_ml/precompute_serving.py`:
  `dim_current_roster, line_member_features, team_handedness, team_current_lines,
  serving_game_skater_box, player_situation_toi` (`:119-124`). `best_team_fits` is explicitly NOT
  precomputed (live DuckDB + cache, `:125`).
- `recent`-capped per-event tables: `stg_play_by_play, int_shot_types, int_shot_attempts_all,
  shot_xg, win_probability` (recent 3 seasons).

`export_to_duckdb.py` supports `--only`, `--all` [via manifest], `--dry-run`, `--into-existing`,
`--duckdb-path`, `--recent-seasons`; it builds a temp file and **atomically swaps** (`:104-210`),
except `--only`/`--into-existing` which patch in place (used by the intraday DAG).

---

## 6. `scripts/` — full ledger (42 `.py` + 4 FINDINGS.md)

Invocation legend: **DAG** = a task in one of the two DAGs; **Make** = a Makefile target;
**main-only** = has an `if __name__ == "__main__"` block and no other in-repo caller (manual /
on-demand). All paths relative to repo root; ripgrep run with `--glob '!docs/**'`.

### 6a. Ingest / refresh / load / match / export scripts

| Script | Purpose | Writes | Invoked by (evidence) |
|---|---|---|---|
| `refresh_rosters.py` | live 32-team roster membership | `raw_rosters` | DAG `roster_refresh` + intraday `refresh_rosters`; Make `roster-refresh` |
| `refresh_edge.py` | NHL Edge season aggregates | `raw_edge_skaters/goalies/teams` | DAG `refresh_weekly_aux` (calls `refresh_season`); Make `edge-refresh` |
| `refresh_game_context.py` | gamecenter landing + right-rail | `raw_game_landing, raw_game_right_rail` | **main-only** (the DAG lands these inline via `nhl_api`, not this script). On-demand/backfill utility |
| `refresh_partner_odds.py` | partner odds snapshot (internal calibration) | `raw_partner_odds` | **main-only** (DAG lands inline). On-demand |
| `refresh_standings.py` | league standings-by-date | `raw_standings` | **main-only** (DAG lands inline). On-demand/backfill |
| `refresh_statsrest_faceoffs.py` | season faceoff splits | `raw_statsrest_faceoffs` | **main-only** (DAG lands inline in `refresh_weekly_aux`). On-demand |
| `ingest_player_bio.py` | player age/height/weight | `raw_player_bio` | DAG `refresh_player_bio` |
| `ingest_player_draft_origin.py` | authoritative draft-origin map | `raw_player_draft_origin` | DAG `refresh_player_draft_origin` |
| `ingest_draft_results.py` | historical draft results | `raw_draft_results` (+ `raw_draft_picks`) | DAG `refresh_weekly_aux` (`fetch_year`) |
| `ingest_futures.py` | org prospect lists + own picks | `raw_prospects, raw_draft_picks` | DAG `ingest_futures`; Make `futures-ingest` |
| `ingest_glossary.py` | stats-REST glossary (one-time) | `raw_glossary` | **main-only** (DAG `refresh_weekly_aux` calls `get_glossary` directly). One-time/on-demand |
| `ingest_shifts.py` | shift-chart backfill | `raw_shift_charts` | **main-only** (DAG lands shifts inline). Resumable backfill utility |
| `load_contracts.py` | contract CSV snapshot | `raw_contracts` | DAG `contracts_match` deps + Make `contracts-load` |
| `load_rfas.py` | pending-RFA CSV | `raw_contracts_rfa` | **main-only** + `tests/test_contract_rfa.py`. Manual snapshot load |
| `load_trades.py` | historical trades CSV | `raw_trades` | Make `trades-load`; `smoke_load_trades.py` |
| `load_gm_tenures.py` | curated GM-tenures CSV | `raw_gm_tenures` | **main-only** + `smoke_load_gm_tenures.py`. Manual load |
| `match_contracts.py` | resolve contracts→player_id | `nhl_models.contract_player_map` + `models_ml/artifacts/contract_match_report.md` | DAG `contracts_match`; Make `contracts-match` |
| `match_rfas.py` | resolve RFAs→player_id | RFA map | **main-only** + `tests/test_contract_rfa.py`. On-demand |
| `export_to_duckdb.py` | materialize DuckDB serving file | `data/serving/nhl_intel.duckdb` | DAG `export_serving` + intraday `export_forecast`; Make `export-serving` |
| `verify_serving_parity.py` | BQ vs DuckDB parity diff | (prints) | Make `verify-serving`; `models_ml/duck.py` |
| `backfill_edge.py` | backfill Edge across all seasons | edge raw tables | **main-only** (calls `refresh_edge`). Backfill utility |
| `backfill_ppt_replay.py` | backfill goal-tracking sprites | `raw_ppt_replay` | **main-only**. **RETAINED by owner (HARD RULE 2) — never dead** |
| `explore_edge.py` | Edge API exploration tool | (prints) | **main-only**. Dev exploration utility |
| `diagnose_contract_grades.py` | contract-grade diagnostics (PRINT ONLY) | nothing | **main-only**. Diagnostic; noted in MEMORY as a scoped diagnostic |
| `export_to_duckdb.py` | (see above) | | |

`scripts/__init__.py` makes `scripts` a package (enables `python -m scripts.*`).

### 6b. `smoke_*` scripts (all 12) — every one is **main-only, referenced by nothing** except its own FINDINGS doc

There is **no** smoke target in the Makefile and **no** smoke reference in either DAG (confirmed by
ripgrep). Each smoke script has exactly one `if __name__ == "__main__"` block and is run by hand.

| Smoke script | Referenced by anything? |
|---|---|
| `smoke_ingest_draft_results.py` | No non-self refs. main-only |
| `smoke_ingest_game_context.py` | No non-self refs. main-only |
| `smoke_ingest_glossary.py` | No non-self refs. main-only |
| `smoke_ingest_partner_odds.py` | No non-self refs. main-only |
| `smoke_ingest_ppt_replay.py` | No non-self refs — **RETAINED by owner (HARD RULE 2), never dead** |
| `smoke_ingest_roster.py` | Only a comment mention in `ingestion/nhl_api.py:339` + `ROSTER_FINDINGS.md`. main-only |
| `smoke_ingest_shiftcharts.py` | No non-self refs. main-only |
| `smoke_ingest_standings.py` | No non-self refs. main-only |
| `smoke_ingest_statsrest_faceoffs.py` | No non-self refs. main-only |
| `smoke_load_gm_tenures.py` | No non-self refs. main-only |
| `smoke_load_trades.py` | No non-self refs. main-only |
| `smoke_roster_source.py` | No non-self refs. main-only |

**Classification:** all smoke scripts are developer verification harnesses run on demand against
real API/BigQuery output. They are outside the pytest suite (`pytest.ini testpaths = tests`) and are
not wired into any DAG or Make target. This is expected — they are the manual counterpart to the
`*_FINDINGS.md` notes. (No deletion recommended; documenting status only.)

### 6c. FINDINGS docs (flag for DOC_RECONCILIATION, do not duplicate)

`scripts/DRAFT_RESULTS_FINDINGS.md`, `scripts/EDGE_FINDINGS.md`, `scripts/ROSTER_FINDINGS.md`,
`scripts/STATSREST_FINDINGS.md` — hand-written observations from running the corresponding smoke
scripts. **Flagged for DOC_RECONCILIATION; their content is not reproduced here.**

Other non-`.py` under `scripts/`: `draft_results_samples/`, `edge_samples/`, `ppt_cache/` (cache —
HARD RULE 1 + 2: never delete), `__pycache__/`.

---

## 7. Non-obvious ROOT files (each accounted for)

| File | What it is | Wired to anything? | Live vs superseded |
|---|---|---|---|
| `backfill_historical.py` | Standalone async historical backfill (docstring: "runs independently of Airflow," faster than the DAG). Referenced by `populate_raw_games.py`. | Referenced by `populate_raw_games.py`; no DAG/Make. | **Live one-off utility** — the intended way to seed history (there is NO backfill DAG). Run manually. |
| `populate_raw_games.py` | Creates `raw_games` schedule rows from existing `raw_boxscores` (because `backfill_historical.py` only loads boxscores/pbp). | References `backfill_historical.py`; no other refs. | One-off repair utility, paired with the backfill. Likely **superseded** in steady state once the DAG runs, but kept as a backfill companion. **[UNCERTAIN]** |
| `load_schedule_only.py` | Loads only schedule data into `raw_games` when boxscores/pbp already present. | No non-self refs. main-only. | One-off repair utility. Likely superseded by the DAG's normal `raw_games` load. **[UNCERTAIN]** |
| `deduplicate_raw_tables.py` | Removes duplicate game records from raw tables (keeps latest `ingestion_date`). | No non-self refs. main-only. | One-off maintenance utility; run on demand if raw dupes appear. |
| `setup_gcs_bucket.py` | Creates + configures the public GCS bucket `nhl-intel-reports` (the report-publish target). | No code refs, but it provisions the bucket `publish_report` writes to. | **Live infra bootstrap** (run once at setup). Ties to §3's shipped report. |
| `test_end_to_end.py` | Integration smoke: full report generation + GCS publish. | **Outside pytest** (see below). | Live on-demand integration smoke |
| `test_llm.py` | Smoke of `reporting/llm_summary` (Gemini). | Outside pytest. | Live on-demand smoke |
| `test_query.py` | Smoke of `reporting/query` (BigQuery). | Outside pytest. | Live on-demand smoke |
| `test_report.py` | Smoke of the full reporting pipeline. | Outside pytest. | Live on-demand smoke |

**The four root `test_*.py` are NOT collected by pytest.** `pytest.ini` sets `testpaths = tests`
and its comment states explicitly: "The repo-root `test_*.py` files are live-service integration
smoke scripts (NHL API, BigQuery, Gemini) that are run on demand, not part of `make test`." They
each hard-code `sys.path.insert(...)` and `GOOGLE_APPLICATION_CREDENTIALS=.../secrets/nhl-intel-sa.json`
— i.e. designed for manual local runs, not CI.

---

## 8. `tests/` — the pytest suite (`make test` / `pytest -q`)

`pytest.ini` → `testpaths = tests`. Nine test modules, all described as **hermetic** (no
network/BigQuery/DuckDB) except `test_api.py`:

| Test file | Coverage (from module docstring) |
|---|---|
| `test_api.py` | Sanity check for NHL API connectivity (**live**, hits the real API) |
| `test_contract_grade_basket.py` | Contract grades — consensus deals land in expected band |
| `test_contract_grade_roundtrip.py` | Hermetic round-trip of the contract-grade valuation curve |
| `test_contract_rfa.py` | Hermetic pending-RFA ingestion into the tradeable-asset layer (imports `scripts.load_rfas`, `scripts.match_rfas`) |
| `test_roster_forecast.py` | Hermetic offseason roster forecast |
| `test_roster_ingest.py` | Hermetic live-roster ingestion helpers |
| `test_trade_engine.py` | Hermetic trade evaluation engine |
| `test_trade_fit_verdict.py` | Hermetic context-aware trade-fit verdict (imports `insight_engine`) |
| `test_value_overall.py` | Hermetic cross-position WAR + card-only Overall |

The suite centers on the **trade/contract/roster-forecast/value** layer; there are no dbt or
model-training tests here (those validate via `make *-validate` targets, §5a). `scripts/*_FINDINGS.md`
exist as manual-smoke notes (see §6c) — flagged for DOC_RECONCILIATION, not duplicated.

---

## 9. Shipped external outputs (Phase C shipped surfaces)

Beyond the React frontend, scheduled DAGs publish these external/consumable surfaces:

1. **Daily HTML report** — `output/report_YYYY-MM-DD.html`, rendered by `reporting/render.py` from
   `nhl_mart.mart_daily_report_feed` + a Gemini summary. Produced by `nhl_daily.generate_report`.
2. **GCS-published report** — the same HTML uploaded to
   `gs://$REPORT_OUTPUT_BUCKET` (default `nhl-intel-reports`), public URL
   `https://storage.googleapis.com/<bucket>/<file>`. Produced by `nhl_daily.publish_report`; bucket
   provisioned by `setup_gcs_bucket.py`.
3. **DuckDB serving file** — `data/serving/nhl_intel.duckdb`, the read-time datastore the FastAPI
   backend serves from. Full rebuild by `nhl_daily.export_serving` (atomic swap); incremental
   forecast update by `offseason_forecast_intraday.export_forecast` (in-place `--only`). This IS a
   data object (HARD RULE 1: never delete) but is a shipped serving surface for Phase C.
4. **Serving-table precomputes** — the 6 `kind: precompute` BigQuery tables (`serving_tables.yml:119-124`)
   built by `nhl_daily.precompute_serving`, which then ride the DuckDB export.

**Internal-only (explicitly NOT a shipped surface):** the partner-odds snapshot
(`raw_partner_odds`) is labeled "INTERNAL CALIBRATION ONLY — never exposed via API/UI"
(`dags/nhl_daily.py:210`).

---

## 10. Container / infra root files (for completeness)

- **`Dockerfile`** — `FROM apache/airflow:2.8.1-python3.11`, installs `requirements.txt`.
- **`docker-compose.yml`** — services: `postgres` (`postgres:14`, container `nhl-postgres`),
  `airflow-webserver` (`nhl-airflow-webserver`), `airflow-scheduler` (`nhl-airflow-scheduler`),
  volume `postgres-db-volume`.
- **`start_airflow.sh`** — local dev launcher: sets `AIRFLOW_HOME=~/airflow`, loads `.env`, starts
  webserver (:8080, admin/admin) + scheduler.
- **`requirements.txt`** — `httpx, pydantic, python-dotenv, pytest, respx, jinja2, tenacity,
  google-cloud-bigquery>=3.20, google-generativeai, google-cloud-storage`.
- **`.env.example`** — `GCP_PROJECT_ID`, `GCP_DATASET_{RAW,STAGING,MART}`,
  `GOOGLE_APPLICATION_CREDENTIALS`, `LLM_API_KEY`, `LLM_PROVIDER=gemini`, `REPORT_OUTPUT_BUCKET`,
  `AIRFLOW_SMTP_EMAIL/PASSWORD`. (Note: DAGs also read `GCP_DATASET_MODELS`, not listed in the
  example — **[UNCERTAIN / minor DOC gap]**.)
