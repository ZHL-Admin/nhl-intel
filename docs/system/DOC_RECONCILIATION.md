# DOC_RECONCILIATION — where the repo's docs diverge from the real system

> **Source-of-truth recommendation.** The five root planning docs
> (`NHL_INTEL_PROJECT.md`, `NHL_DASHBOARD_SPEC.md`, `NHL_DASHBOARD_DESIGN.md`,
> `NHL_DASHBOARD_UX.md`, `nhl-intel-finalization-plan.md`) should be treated as
> **historical product intent** — the design brief the system was built against,
> not a description of what shipped. This `docs/system/` set (this file plus the
> `_inventory/` inventories) should be treated as the **current source of truth**
> for how the system actually works. Where any doc disagrees with the code, the
> **code wins**. Nothing in this pass edits or deletes the planning docs; it only
> records the divergence.

This is a read-only reconciliation. Every divergence below cites its evidence:
either a planning/in-domain doc line, or a `_inventory/` section that was built by
static inspection of the code (git ls-files, `dbt parse`, ripgrep, route decorators,
and free INFORMATION_SCHEMA metadata queries).

## HARD RULES (govern this whole document)

1. **Data / ingested objects are NEVER listed for deletion.** This file reports
   documentation drift only. No BigQuery table/view, GCS object, DuckDB serving
   table, or ingested row is proposed for removal here. Where a stale doc names an
   object that no longer has a producer, that is a *documentation* fact, not a
   deletion call.
2. **Puck tracking is retained by owner decision.** `raw_ppt_replay`,
   `stg_ppt_tracking_frames`, `int_goal_release_frame`, `scripts/backfill_ppt_replay.py`,
   `scripts/smoke_ingest_ppt_replay.py`, `scripts/ppt_cache/`, and every ppt-derived
   ML/serving object are retained regardless of downstream reference count. They are
   never "dead" and are never a divergence-to-remove.

---

## 0. The five planning docs — gitignored, present, historical

Per `_inventory/00_manifest.md` (Manifest correction, lines 725-741): the five root
planning docs are **present on disk but GITIGNORED** (`.gitignore` lines 6-10), which
is why they were absent from the git-derived 554-file set and had to be added back as
in-scope reconciliation targets (bringing coverage to 559).

| file | bytes | role |
|---|---|---|
| `NHL_INTEL_PROJECT.md` | 33026 | architecture/engineering reference (v1 framing) |
| `NHL_DASHBOARD_SPEC.md` | 34703 | product spec "Version 2.0" |
| `NHL_DASHBOARD_DESIGN.md` | 27765 | design-token spec "Version 2.0" |
| `NHL_DASHBOARD_UX.md` | 23516 | information-architecture spec "Version 1.0" |
| `nhl-intel-finalization-plan.md` | 86798 | phased build plan (repo "as of 2026-06-12") |

These are the owner's product intent and are **never cleanup candidates**. They are,
however, stale on multiple concrete specifics. The four `NHL_*` docs each open with a
"single source of truth … reference at the start of every session" claim
(`NHL_INTEL_PROJECT.md:5`, `NHL_DASHBOARD_SPEC.md:4`, etc.); that framing is exactly
what this file supersedes for *system reality*. They remain useful for *why* things
exist (the Three Questions framework, metric definitions, design tokens).

### 0a. Retired dbt models the docs still assume as live — `int_xg_rates`, `int_zone_entries`

`NHL_INTEL_PROJECT.md` still documents two intermediate models that no longer exist as
dbt sources:

- `NHL_INTEL_PROJECT.md:351` — "`int_xg_rates` — historical conversion rates per season
  per shot zone and type (used to assign xG values)".
- `NHL_INTEL_PROJECT.md:352` — "`int_zone_entries` — zone entry events classified as
  controlled or uncontrolled".
- `NHL_INTEL_PROJECT.md:362` and `:413` further build on them ("xG rates are computed
  per season in `int_xg_rates`"; "mart_player_shooting_luck (depends on int_xg_rates)").

Reality (`_inventory/10_dbt.md` §1b, `_inventory/60_bq_objects.md` §3.1-3.2):

- There is **no** `int_xg_rates` dbt model. xG is now produced by the ML layer as
  `nhl_models.shot_xg` (`models_ml/score_xg.py`) and joined by the marts; the marts that
  the doc says "depend on int_xg_rates" (e.g. `mart_player_shooting_luck`,
  `mart_team_game_stats`) now read `nhl_models.shot_xg` instead.
- `int_zone_entries` was **renamed** to `int_zone_entry_proxy` (the honest "proxy"
  labeling). `int_zone_entry_proxy` is the live model (`_inventory/10_dbt.md:93`);
  `int_zone_entries` is not in the dbt manifest.
- Interestingly, the finalization plan itself *documents this migration in progress*:
  `nhl-intel-finalization-plan.md:77` ("Rename dbt model int_zone_entries to
  int_zone_entry_proxy"), `:300` ("int_xg_rates is retired (delete after refs are
  migrated) … marts now join nhl_models.shot_xg"), `:577` ("remove retired int_xg_rates").
  So the finalization plan is *newer* than `NHL_INTEL_PROJECT.md` on this point, but still
  predates completion: the physical BigQuery **views** `nhl_staging.int_xg_rates` and
  `nhl_staging.int_zone_entries` were left behind and persist with no producer
  (`_inventory/60_bq_objects.md` §3.1-3.2, "Tier 4 — investigate, do not drop"). Per HARD
  RULE 1 those BQ views are not proposed for deletion here; the point is only that both the
  reference doc (assumes them live) and the plan (assumes them deleted) diverge from the
  actual state (source `.sql` gone, physical view still there).

### 0b. Architecture pivot the plans predate — DuckDB serving, not BigQuery-on-request

Every planning doc frames the backend as a live BigQuery layer on Cloud Run, and the
finalization plan explicitly rules DuckDB **out of scope**:

- `NHL_INTEL_PROJECT.md:65` — "Backend API | FastAPI | Exposes mart tables as JSON API |
  Production on Cloud Run"; `:616` — "Thin layer over BigQuery mart tables".
- `nhl-intel-finalization-plan.md:53` — "If a fully offline build is ever wanted, that is
  a separate migration to DuckDB and is **out of scope** here."; `:602` — "a DuckDB
  migration would add weeks for no blueprint requirement". (`duckdb` appears 0 times in
  all four `NHL_*` docs.)

Reality (`_inventory/30_backend.md` §0, `_inventory/50_infra.md` §9, `_inventory/60_bq_objects.md`):

- `backend/main.py:19` sets `os.environ.setdefault("SERVING_BACKEND", "duckdb")` before the
  routers import, so the **default production request path reads a local DuckDB serving
  file**, not BigQuery. No `bigquery.Client` is opened on the request path in that mode.
- The serving file `data/serving/nhl_intel.duckdb` (714 MB) is built nightly by
  `scripts/export_to_duckdb.py` / `make export-serving` and atomically swapped
  (`dags/nhl_daily.py` `export_serving`), with an intraday `--only` refresh from
  `dags/offseason_forecast_intraday.py`.
- So the DuckDB serving layer the plan called a weeks-long out-of-scope migration is, in
  fact, the shipped architecture. This is the single largest planning-doc divergence.

### 0c. Whole product surfaces the "v2.0"/"v1.0" specs predate

The spec/design/UX docs (v2.0 / v1.0) and much of `NHL_INTEL_PROJECT.md` predate large
shipped feature areas. Concretely, the app now ships routes and model tables with no
counterpart in those docs (`_inventory/40_frontend.md` §1, `_inventory/30_backend.md` §1-2,
`_inventory/60_bq_objects.md`):

- **Tooling surfaces:** Offseason WAR forecast (`/tools/offseason`), Lineup Lab, Trade Fit,
  Trade Builder, Contract Grader, Roster Builder, Draft Value, Trade Outcomes, and the
  `/learn/archetypes` explainer — 11 lazy-loaded pages in `App.tsx:13-25`.
- **Backend routers** that the docs never mention: `rankings`, `streaks`, `tools`,
  `archetypes`, `assets`, `playoffs`, `draft`, `trades`, `traders`, `goalies` (13 routers
  total, ~70 routes).
- **ML/model tables** the docs predate: ~35 `nhl_models.*` outputs including `player_pwar`,
  `trade_outcomes`, `roster_forecast`/`roster_moves`, `player_verdict`, `player_radar`,
  `goalie_gar`, `deployment_efficiency`, `archetype_gallery`, and the WOWY/on-ice branch
  marts (`_inventory/60_bq_objects.md` §1).
- **Mart-count drift:** `nhl-intel-finalization-plan.md:11` describes "**11 mart tables**".
  Reality is **24** mart models (`_inventory/10_dbt.md` §1c). `NHL_INTEL_PROJECT.md`'s mart
  list is likewise a subset.

Treat the v2.0/v1.0 docs as design intent for the surfaces they *do* cover (Games, Teams,
Players, Rankings, the design tokens, the Three Questions framing), and as silent on
everything shipped afterward.

---

## 1. `backend/README.md` — stale on both architecture and scope

Evidence: the README file itself, cross-referenced to `_inventory/30_backend.md` §1-2, §5.

- **"thin API layer over BigQuery mart tables"** (`backend/README.md:3`, echoed `:88`
  "Data Source: BigQuery (nhl_staging dataset)"). Drift: the default request path is the
  **DuckDB serving file**, not live BigQuery (see §0b). The setup section only documents the
  BigQuery / `GOOGLE_APPLICATION_CREDENTIALS` path (`:50-56`, `:80`).
- **~14 endpoints listed** (`backend/README.md:17-33`: a handful of `/games`, `/teams`,
  `/players` routes). Drift: the app registers **~70 routes across 13 routers**
  (`_inventory/30_backend.md` §1-2). The endpoints the README lists *do* still exist and
  match — it is a correct-but-tiny subset that omits 10 entire routers.
- **"All mart tables are currently in the `nhl_staging` dataset"** (`backend/README.md:95`).
  Drift: marts materialize into **`nhl_mart`** (`_inventory/10_dbt.md` §3, `_inventory/60_bq_objects.md`
  §1: 21 physical `mart_*` tables in `nhl_mart`).
- **"Expected goals (xG) metrics are not yet available in the data pipeline"**
  (`backend/README.md:96`). Drift: xG is fully shipped — `nhl_models.shot_xg`, the
  `/games/{id}/xgworm` and `/games/{id}/shots` endpoints, and an `XGBreakdown` component
  all ship xG today (`_inventory/30_backend.md` §2 games table; `_inventory/40_frontend.md`).
- The production URL and Cloud Run deploy recipe (`:9`, `:74-83`) describe the legacy
  BigQuery-served deployment; keep as historical.

Recommendation: trust `_inventory/30_backend.md` §2 (or a live OpenAPI dump) as the route
list; treat the README as a partial legacy snapshot.

## 2. `backend/API_EXPANSION_SUMMARY.md` — point-in-time changelog, superseded

Evidence: the file itself, cross-referenced to `_inventory/30_backend.md` §5.

- It is a "Backend Complete & Deployed" changelog pinned to **Cloud Run revision
  `nhl-dashboard-api-00020-sfd`** (`API_EXPANSION_SUMMARY.md:14`, `:73`) and describes one
  expansion wave of **"9 new query functions"** in `bigquery.py` (`:32-42`:
  `get_game_shots`, `get_xg_worm`, `get_team_zone_time`, `get_team_faceoffs`,
  `get_team_situational`, `get_player_situational`, `get_player_zone_deployment`,
  `get_player_shooting_luck`, `get_player_relative`).
- Reality: **all 9 still exist**, but `backend/services/bigquery.py` now has **22** `get_*`
  methods (`_inventory/30_backend.md` §3, §4). The summary captures only that one wave and
  predates the trades/traders/draft/tools/offseason/serving-layer work.
- Its "Remaining Work" section (`:76-85`, frontend types to create) is long since done
  (`frontend/src/api/types.ts` exists and is actively modified).

This is a historical artifact, not a live API reference. Superseded.

## 3. `models_ml/README.md` — "versioned artifact" claim is only partly true

Evidence: the file itself, cross-referenced to `_inventory/20_ml.md` §6, §1.

- `models_ml/README.md:14-15` — "**Every shipped model writes a versioned artifact here**
  and a methodology doc to `docs/methodology/`."
- Reality (`_inventory/20_ml.md` §1, master table): **most** `compute_*` jobs write only a
  BigQuery table into `nhl_models.*` with a `model_version` **column** — they do **not**
  emit a joblib/txt file under `artifacts/`. Only a small set write a serialized artifact:
  `train_xg.py` (`xg_v1.txt` + manifest), `train_winprob.py` (`winprob_v1.joblib`),
  `train_linefit.py` (`linefit_v1.joblib`), `fit_archetypes_v2.py` (`archetypes_v2.joblib`,
  plus the superseded `archetypes_v1.joblib`), and `fit_pwar_anchor.py`
  (`pwar_anchor_v1.joblib` + manifest). The committed `artifacts/` directory bears this out
  (`_inventory/00_manifest.md` other_data: 5 joblib/manifest files, not one per model).
- The "one job per model … wired into `dags/nhl_daily.py`" and training-order claims
  (`:16-20`) are broadly accurate for the daily pipeline, but note the runbook seam: several
  Handoff-5 draft/pWAR jobs (`compute_pwar`, `fit_pwar_anchor`, `fit_pick_value`,
  `run_draft_theory`) are **not** wired into either DAG or a Makefile target and are hand-run
  refresh steps whose outputs are still served (`_inventory/20_ml.md` §5). Not dead, but not
  "wired into `nhl_daily`" as the README implies.

The methodology-doc half of the claim is also imperfect (see §5): many models have a
methodology doc, but the mapping is not strictly one-per-model.

## 4. `insight_engine/README.md` — describes structure that does not exist on disk

Evidence: the file itself, cross-referenced to `_inventory/50_infra.md` §4 and
`_inventory/00_manifest.md` (insight_engine listing, 11 files).

- `insight_engine/README.md:8-16` describes a "built in Phase 6" structure with:
  `registry.py` (a registry of `Insight` classes), a `detectors/` directory (one module per
  insight family), `templates/`, and `smoke.py` (runs every detector against a fixture date).
- Reality: **only `templates/` exists.** The on-disk tree is `README.md`, `__init__.py`,
  `templates/__init__.py`, and 8 template modules (`divergence.py`, `line_fit.py`,
  `matchup.py`, `playoff_bracket.py`, `roster_forecast.py`, `team_fit.py`,
  `team_overview.py`, `value_gap.py`). There is **no** `registry.py`, **no** `detectors/`,
  **no** `smoke.py` (`_inventory/00_manifest.md` lines 566-579; `_inventory/50_infra.md` §4).
- The `templates/` that *do* exist are **live and consumed** — `backend/services/tools.py`,
  `backend/services/offseason.py`, `models_ml/score_line.py`, several routers, and
  `tests/test_trade_fit_verdict.py` all import them (`_inventory/50_infra.md` §4). So the
  engine is not dead; the README simply overstates the built structure (it documents the
  Phase-6 blueprint, not what was implemented). The "No LLM in the site path" principle
  (`:2-3`) does still hold.

## 5. `docs/methodology/*` — treat as LIKELY CURRENT; minor drift only

The methodology docs are actively maintained and cross-reference cleanly to live model
jobs, so they are the **current** methodology source. Evidence: `_inventory/20_ml.md` §1
maps many methodology docs to their producing job (e.g. `power-ratings.md` ↔
`compute_ratings.py`, `value-gar.md` ↔ `compute_gar.py`, `offseason-forecast.md` ↔
`project_roster_forecast.py`, `contract-surplus.md` ↔ `compute_contract_value.py`,
`xg-model.md` ↔ `train_xg.py`, `win-probability.md` ↔ `train_winprob.py`,
`lineup-lab.md` ↔ `train_linefit.py`, `sequence-mining.md` ↔ `tune_sequence_thresholds.py`).
Three of them are modified in the current working tree (git status: `offseason-forecast.md`,
`power-ratings.md`, `trade-outcomes.md`), a further signal they are kept live.

Full set on disk (`_inventory/00_manifest.md` lines 659-690, docs domain — 32 topic docs +
`README.md`): `archetypes`, `composite`, `contract-surplus`, `deployment-efficiency`,
`draft-value`, `futures-value`, `goalie-clutch-preregistration`, `goaltending`,
`isolated-impact`, `lineup-lab`, `offseason-forecast`, `overall-rating`, `player-fit`,
`player-radar`, `player-verdict`, `power-ratings`, `ppt-replay-tracking`, `reconciliation`,
`roster-builder`, `roster-projection`, `score-state-adjustment`, `scorer-bias`,
`sequence-mining`, `streak-doctor`, `team-identity`, `trade-engine`, `trade-outcomes`,
`trajectories`, `value-gar`, `win-probability`, `xg-model`.

Spot-checked drift (small, in the index only — not in the methodology content):

- `docs/methodology/README.md:11-15` gives an "expected files as phases land" list of 18
  names. That list is **stale/incomplete** relative to the 32 topic docs now present: it
  omits everything shipped later (offseason-forecast, roster-builder, roster-projection,
  overall-rating, player-fit, player-radar, player-verdict, draft-value, futures-value,
  goalie-clutch-preregistration, deployment-efficiency, score-state-adjustment,
  ppt-replay-tracking, team-identity, trade-outcomes, value-gar), and it lists one file that
  was **never shipped under that name** — `edge-cross-validation.md` (no such file on disk).
  The index oversells being auto-maintained; the individual docs are the reliable part.
- `docs/methodology/README.md:8` says these render into the site's `/learn` library "(Phase 6)".
  Reality: the frontend mounts only `/learn/archetypes` (`_inventory/40_frontend.md` §1); a
  full methodology-library render is not wired. Minor divergence, flagged not resolved.

Net: trust the individual methodology `.md` files; treat their own `README.md`'s expected-file
list as an outdated planning artifact.

## 6. `scripts/*_FINDINGS.md` — observational hand-run smoke notes

Evidence: `_inventory/50_infra.md` §6b-6c.

`scripts/DRAFT_RESULTS_FINDINGS.md`, `scripts/EDGE_FINDINGS.md`, `scripts/ROSTER_FINDINGS.md`,
`scripts/STATSREST_FINDINGS.md` are **hand-written observations** captured while running the
matching `smoke_ingest_*` scripts against real NHL API / BigQuery output. They are not a spec
and were not regenerated:

- Each is the manual counterpart to a `smoke_*` script that is **main-only** — there is **no**
  smoke target in the `Makefile` and **no** smoke reference in either DAG, and the smoke
  scripts sit outside the pytest suite (`pytest.ini testpaths = tests`)
  (`_inventory/50_infra.md` §6b). So these findings are point-in-time developer notes tied to
  on-demand smoke runs, not continuously verified documentation.
- Treat them as historical field notes about data quirks (useful context), not as current
  guarantees about ingestion behavior. Cross-check against the live smoke script and the raw
  table before relying on any specific claim.

---

## Summary table

| doc | status | headline divergence | evidence |
|---|---|---|---|
| 5 root planning docs | historical intent | gitignored-but-present; predate DuckDB serving, ~35 model tables, 10 routers, and 11 tool surfaces; assume retired `int_xg_rates`/`int_zone_entries` | `_inventory/00_manifest.md` 725-741; `_inventory/30_backend.md` §0; `_inventory/60_bq_objects.md` §3 |
| `backend/README.md` | stale | "thin BigQuery layer, ~14 endpoints"; reality DuckDB-served, ~70 routes / 13 routers; xG "not yet available" but shipped; marts in `nhl_mart` not `nhl_staging` | `_inventory/30_backend.md` §0, §2, §5 |
| `backend/API_EXPANSION_SUMMARY.md` | superseded | point-in-time changelog (rev `00020-sfd`); its 9 functions still exist but `bigquery.py` now has 22 | `_inventory/30_backend.md` §3-5 |
| `models_ml/README.md` | partly wrong | "every shipped model writes a versioned artifact" — most `compute_*` write only a BQ table + `model_version` column; only 5 jobs emit joblib/txt | `_inventory/20_ml.md` §1, §6 |
| `insight_engine/README.md` | overstated | describes `registry.py` / `detectors/` / `smoke.py` "built in Phase 6" that do NOT exist; only live `templates/` is real | `_inventory/50_infra.md` §4; `_inventory/00_manifest.md` 566-579 |
| `docs/methodology/*` (topic docs) | current | actively maintained, map to live jobs; trust these | `_inventory/20_ml.md` §1 |
| `docs/methodology/README.md` | index stale | "expected files" list omits ~16 shipped docs and names a never-shipped `edge-cross-validation.md`; `/learn` render only partial | `_inventory/00_manifest.md` 659-690; `_inventory/40_frontend.md` §1 |
| `scripts/*_FINDINGS.md` | observational | hand-run smoke notes tied to main-only smoke scripts (no DAG/Make/pytest wiring) | `_inventory/50_infra.md` §6b-6c |
