# NHL Intel — system documentation (current source of truth)

Authoritative, code-derived documentation of the entire repository, produced by a read-only
audit that treated the running system (not the older planning docs) as the source of truth.
Every dependency edge and cleanup claim in this set is backed by a ripgrep result, a dbt
manifest entry, an import, a route registration, a Makefile/DAG task, or a free BigQuery
INFORMATION_SCHEMA metadata query. No file outside `docs/system/` was modified, and no
cost-incurring query (no `dbt run`, no row scan) was executed.

> The five root planning docs (`NHL_INTEL_PROJECT.md`, `NHL_DASHBOARD_SPEC.md`,
> `NHL_DASHBOARD_DESIGN.md`, `NHL_DASHBOARD_UX.md`, `nhl-intel-finalization-plan.md`) are
> **historical product intent** and are stale in places. Treat **this `docs/system/` set as
> the current source of truth**; see `DOC_RECONCILIATION.md` for item-by-item divergence.

## Two standing rules that govern the whole audit

1. **Data and ingested objects are never proposed for deletion.** Only source files (code,
   config, docs) may be listed for cleanup. Orphaned physical tables go to "investigate, do
   not drop."
2. **Puck tracking is retained by owner decision** — built ahead of a future tool, not
   surfaced yet, and never a cleanup candidate.

## How the system works, end to end

NHL Intel is a nightly analytics pipeline plus a served dashboard. Data flows in one
direction, from ingested feeds to a denormalized read store the app queries.

```
NHL public APIs + curated CSVs
      |  ingestion/ + scripts/*            (raw landings)
      v
  nhl_raw.raw_*            (25 ingested BigQuery tables)
      |  dbt staging (stg_*, views)
      v
  nhl_staging.stg_* / int_*   (23 staging + 20 intermediate models)
      |  dbt marts                          ML layer reads marts/staging,
      v                                      writes nhl_models.* (Python)
  nhl_mart.mart_*  (24 models) <---------->  nhl_models.*  (44 tables; 16 are dbt sources)
      |                                          |  models_ml/*.py (train_/score_/compute_)
      |   scripts/export_to_duckdb.py + precompute_serving.py
      v
  DuckDB serving file  data/serving/nhl_intel.duckdb   (~60 tables + 6 precompute)
      |  FastAPI backend (SERVING_BACKEND=duckdb default)
      v
  ~70 REST routes (13 routers)  ---- React + Vite frontend (21 routes, 18 pages)
      |
      +--- reporting/ -> daily HTML report (mart_daily_report_feed + Gemini) -> GCS
```

Orchestration is two Airflow DAGs: `nhl_daily` (`0 13 * * *`, the full pipeline, with many
Monday-gated weekly jobs) and `offseason_forecast_intraday` (`0 21 * * *`, a second forecast
refresh). There is **no** historical-backfill DAG; history is seeded by the standalone
`backfill_historical.py`. The request path does not touch BigQuery: the backend serves from
the nightly DuckDB copy, so almost every mart and headline model table reaches the frontend
through that serving file, and one mart (`mart_daily_report_feed`) reaches users through the
report instead.

### Layer ownership at a glance

| layer | tech | count | doc |
|---|---|---|---|
| ingestion + orchestration | Airflow, httpx, scripts | 2 DAGs, ingestion/, ~42 scripts | ORCHESTRATION.md |
| data pipeline | dbt + BigQuery | 67 models, 40 sources, 216 tests | DATA_PIPELINE.md |
| ML model layer | Python (models_ml/) | 73 scripts, 44 nhl_models tables | ML_MODELS.md |
| serving | DuckDB + precompute | ~60 tables | ORCHESTRATION.md, DEPENDENCY_GRAPH.md |
| backend | FastAPI | 13 routers, ~70 routes | BACKEND_API.md |
| frontend | React + Vite | 21 routes, 18 pages | FRONTEND.md |
| shipped outputs | frontend, HTML report, GCS, DuckDB | 5 surfaces | DEPENDENCY_GRAPH.md |

## Document index

Synthesis and reference (this pass):

- **DATA_PIPELINE.md** — every dbt model and source and ML-written table, by layer, with
  grain, purpose, inputs, outputs, downstream consumers; new-branch models and physical drift.
- **ML_MODELS.md** — every training/scoring/compute script, what it reads and writes,
  cadence, methodology pointers, duplication resolution, reachability of un-orchestrated jobs.
- **BACKEND_API.md** — every endpoint through its query to the marts/serving/model tables,
  response shape, caching, and the DuckDB-serving architecture.
- **FRONTEND.md** — every mounted page and component mapped to endpoints and data lineage,
  with the orphan list and duplication resolution.
- **FEATURE_MAP.md** — one trace per user-facing feature from component to source feed; the
  anchor for the cleanup list. Includes the "built, not yet surfaced" puck-tracking section.
- **ORCHESTRATION.md** — DAGs, schedules, tasks, ingestion, reporting, serving, infra, env.
- **DEPENDENCY_GRAPH.md** — the cross-layer lineage, serving-table node type, shipped
  surfaces, and the reverse-reachability result (what does and does not reach a surface).
- **DOC_RECONCILIATION.md** — how the planning docs and in-domain READMEs diverge from the
  real system, item by item, with evidence.
- **CLEANUP_CANDIDATES.md** — tiered, evidence-backed recommendation list (nothing executed).

Raw evidence (the domain inventories the above are compiled from):

- `_inventory/00_manifest.md` — file manifest, domain split, coverage checklist, corrections.
- `_inventory/10_dbt.md`, `20_ml.md`, `30_backend.md`, `40_frontend.md`, `50_infra.md`,
  `60_bq_objects.md` — per-domain inventories with reference counts and evidence.

## Headline findings

- The three planning docs are stale; largest divergence is that they frame a thin
  BigQuery/Cloud Run layer while the shipped default path is DuckDB serving.
- `dbt/profiles.yml` is **tracked and committed** despite the project rule and `.gitignore`;
  recommend `git rm --cached` (policy fix, not a deletion).
- Four physical BigQuery objects have no code producer (`int_xg_rates`, `int_zone_entries`,
  and the stray `nhl_staging_staging` dataset's two views): Tier 4, investigate, do not drop.
- Five new WOWY/on-ice models exist in dbt but are not yet materialized; a new feature, not
  abandoned (two already feed live marts).
- The largest source-file cleanup cluster is the ML playoff-research line (13 `analyze_*` /
  research scripts) plus dev smoke harnesses; all Tier 2 (verify), none dead-certain.

## Coverage reconciliation (completeness gate)

Scope: **559 files** = 554 git-tracked/untracked-non-ignored + 5 gitignored-but-present
planning docs. Ignored (not counted): `.git`, `node_modules`, `dbt/target`, `__pycache__`,
`secrets/`, `.pytest_cache`, `logs/`, `frontend/dist|build`, `.dx/`, and data caches
(`scripts/ppt_cache/` 25,946 files, `scripts/*_samples/`, `data/`).

Every non-ignored file appears in at least one document:

| domain | files | where documented |
|---|---|---|
| dbt (87) | models/sources/tests/macros | DATA_PIPELINE.md + `_inventory/10_dbt.md`; 5 loose scripts + `profiles.yml` in CLEANUP_CANDIDATES.md |
| ml_python (75) | models_ml/*.py + artifacts | ML_MODELS.md + `_inventory/20_ml.md`; superseded/research items in CLEANUP_CANDIDATES.md |
| backend (34) | app/routers/services/schemas | BACKEND_API.md + `_inventory/30_backend.md`; `validate_trade_engine.py` noted T3 |
| frontend (215) | pages/components/api/utils | FRONTEND.md + `_inventory/40_frontend.md`; 4 orphans in CLEANUP_CANDIDATES.md |
| orchestration_infra (88) | dags/ingestion/reporting/insight_engine/scripts/tests/root | ORCHESTRATION.md + `_inventory/50_infra.md`; smokes/one-offs in CLEANUP_CANDIDATES.md |
| docs (40 + 5 gitignored = 45) | docs/ + root planning docs | DOC_RECONCILIATION.md + this README |
| other_data (15) | CSVs, .joblib, output HTML, `.grepout`, `.gitkeep` | recorded in `_inventory/00_manifest.md`; CSVs/joblib traced in DATA_PIPELINE/ML_MODELS; `.grepout` is CLEANUP T1; report HTML is ORCHESTRATION S2 |

Physical BigQuery objects (134) are inventoried in `_inventory/60_bq_objects.md`; the 4 with
no code producer are in CLEANUP_CANDIDATES.md Tier 4.

**Post-cleanup delta (branch `cleanup/safe-removals`).** The coverage above still holds after
the executed cleanup, with these tree changes: 7 source files deleted (`.grepout`; 3 frontend
components + their `.css`; `fit_archetypes.py` + `archetypes_v1.joblib`), `dbt/profiles.yml`
untracked, and **23 files moved into a new top-level `archive/`** (2 calibration + 5 dbt
probes + 11 smokes + 4 findings + `archive/README.md`). The `archive/` tree is documented in
`archive/README.md` and CLEANUP_CANDIDATES.md, so every moved file remains accounted for.
`scripts/smoke_ingest_ppt_replay.py` was intentionally left in `scripts/` (puck tracking).
Full per-step status and commit hashes are in CLEANUP_CANDIDATES.md.

**Files that could not be classified: none.** Two count reconciliations worth noting: the
brief's "75 ML scripts" resolves to 73 `models_ml/*.py` on disk (the 75 in the domain split
counts `README.md` + `__init__.py`); and the five planning docs are present on disk but
gitignored (added to scope explicitly). Both are recorded in `_inventory/00_manifest.md`.

## What this pass did not do

Read-only throughout. No source file outside `docs/system/` was modified, moved, or deleted;
no model, script, or config was changed; no `dbt run`/`dbt build` and no row-scanning query
was executed (only free INFORMATION_SCHEMA metadata). All deletion decisions remain with the
human, per CLEANUP_CANDIDATES.md.
