# CLEANUP_CANDIDATES — evidence-backed, tiered

Originally a recommendation list. **A staged, reversible subset has now been EXECUTED on
branch `cleanup/safe-removals`** (code and docs only; no data touched; puck tracking intact).
The execution status is recorded below; the tier sections that follow are the original
evidence.

## Execution status (branch `cleanup/safe-removals`)

| step | action | items | commit |
|---|---|---|---|
| 1 | untrack (policy fix, not deleted) | `dbt/profiles.yml` | `a3a2535` |
| 2 | removed | `.grepout` | (was untracked; removed from disk, no commit) |
| 3 | deleted | `XGWormChart.{tsx,css}`, `ShotPressureChart.{tsx,css}`, `GoalTooltip.{tsx,css}` | `a6a7c39` |
| 4 | deleted + comment fix | `models_ml/fit_archetypes.py`, `archetypes_v1.joblib`; `nhl_daily.py` v1 comment | `7d1d1e9` |
| 5 | archived (`git mv`, not deleted) | 2 calibration + 5 dbt probes + 11 smokes + 4 findings -> `archive/` | `0620488` |
| 7 | docs synced | this file + DATA_PIPELINE/ML_MODELS/FRONTEND/README + `sources.yml` ghost fix | (this commit) |

**Deferred (left in place this pass, still open):**
- T2d ML research cluster (`analyze_*` x11, `build_playoff_weights.py`, `train_style_effect.py`)
  — before any future removal, confirm nothing reads `build_playoff_weights.py`'s
  `playoff_weights.json` output (not opened in the read-only pass).
- T2g five backend routes with no frontend caller — deferred to a scoped backend pass.
- All Tier 4 (BQ view orphans, stray `nhl_staging_staging` dataset, `raw_glossary`) —
  data-owner review, never a code-cleanup drop.

Everything below is the original evidence; items now carry an inline **[DONE]**, **[ARCHIVED]**,
or **[DEFERRED]** marker.

---

This was a recommendation list; the executed subset is marked above. The human decides on the
rest.

## TWO HARD RULES (read first)

1. **Code and docs may be listed for deletion. Data and ingested objects may NEVER be.**
   No BigQuery table, view, dataset, GCS object, ingested raw row, or data cache (including
   `scripts/ppt_cache/`) may appear in any delete list, regardless of whether a producer or
   consumer is found in code. An orphaned physical table goes to **Tier 4: investigate, do
   not drop**, never to Tier 1.
2. **Puck tracking is retained by owner decision.** Every puck-tracking element
   (`stg_ppt_tracking_frames`, `int_goal_release_frame`, `raw_ppt_replay`,
   `scripts/backfill_ppt_replay.py`, `scripts/smoke_ingest_ppt_replay.py`,
   `scripts/ppt_cache/`, and any ppt-derived object) is **Tier 3 (keep)** with the reason
   "reserved for future tool per owner," even though it does not reach a current shipped
   surface. This is an explicit exception to reverse reachability. It falls under Rule 1
   twice over for the data objects.

Tiers: **T1** safe to delete (zero refs + clearly junk/superseded/stub, source file only).
**T2** likely safe, verify with human (ambiguous signal). **T3** keep (reaches a surface or
load-bearing or protected). **T4** unknown / needs a live check (never a data delete).

---

## Tier 1 — safe to delete (source files only, zero references, unambiguous)

| path | type | why a candidate | evidence | recommended action |
|---|---|---|---|---|
| `.grepout` | root file | empty 0-byte scratch file, no purpose | `wc -c .grepout` = 0; `grep -r grepout` = no code reference | **[DONE]** removed (was untracked, so no commit; deleted from working tree) |

Only one item meets the strict T1 bar (zero refs AND unambiguously junk). Everything else
with zero references is a hand-run tool or a superseded artifact, which the bias-to-caution
rule places in T2.

---

## Tier 2 — likely safe, verify with human

**[ARCHIVED]** all five moved to `archive/dbt/` in commit `0620488` (retained for provenance,
not deleted).

### 2a. dbt ad-hoc inspection scripts (source code, hand-run)
Zero functional inbound references (only listed in `_inventory/00_manifest.md`). Each opens
its own `bigquery.Client` for a one-off probe; superseded by proper tooling but may be
hand-run for debugging.

| path | evidence |
|---|---|
| `dbt/check_report_feed.py` | `rg` across repo: no importer/caller; standalone `__main__` probe of `mart_daily_report_feed` |
| `dbt/check_xgf.py` | same; schema probe of `mart_team_game_stats` |
| `dbt/query_metrics.py` | same; ad-hoc metric SELECT |
| `dbt/verify_calculations.py` | same; hard-coded single-game (2025030314, CAR) check |
| `dbt/verify_hot_cold.py` | same; hot_cold_flag trend check |

Recommendation: delete if the team keeps such probes in a scratchpad elsewhere; otherwise
move under a `dbt/scratch/` folder. Verify no personal workflow depends on them.

### 2b. Frontend orphans (zero importers from the mounted graph)

| path | evidence | note |
|---|---|---|
| `frontend/src/pages/DevComponents.tsx` | `rg DevComponents frontend/src` = only its own definition; not in `App.tsx` routes | internal component gallery, never mounted; keep only if used as a live dev storybook. **[DEFERRED]** left in place this pass (possible dev storybook) |
| `frontend/src/components/visualizations/XGWormChart.tsx` (+ `.css`) | 0 external importers; `GameDetail` uses `GameTimelineStack` instead | superseded standalone chart. **[DONE]** deleted in `a6a7c39` |
| `frontend/src/components/visualizations/ShotPressureChart.tsx` (+ `.css`) | 0 external importers; folded into `GameTimelineStack` | superseded standalone chart. **[DONE]** deleted in `a6a7c39` |
| `frontend/src/components/common/GoalTooltip.tsx` (+ `.css`) | only importers are the two orphaned charts above; not in `common/index.ts` barrel | transitively orphaned. **[DONE]** deleted in `a6a7c39` (typecheck passed) |

Caveat carried from `_inventory/40_frontend.md`: the `common/index.ts` barrel masks
per-symbol usage, so individual common primitives were not each proven unused. Do not delete
common primitives without a per-symbol check. The four above are non-common and proven.

### 2c. ML superseded generation (v1 archetypes)

**[DONE]** both deleted and the stale DAG comment fixed in commit `7d1d1e9`.

| path | type | evidence |
|---|---|---|
| `models_ml/fit_archetypes.py` | source (v1 script) | superseded by `fit_archetypes_v2.py`; run by none of the six invocation sources; v2 docstring says "supersedes fit_archetypes.py / archetypes_v1"; live pipeline (`nhl_daily.py:589`, `Makefile:135`) runs v2 |
| `models_ml/artifacts/archetypes_v1.joblib` | model artifact (not data) | loaded only by the superseded v1 script; live path uses `archetypes_v2.joblib` |

Per Rule 1 the joblib is a model file, not ingested data, so it may be listed here, but only
T2 for human confirmation. Also fix the stale DAG comment `nhl_daily.py:587-588` (says it
loads v1 joblib; the task runs v2).

### 2d. ML research / one-shot cluster (outputs not served)
None of these is referenced by the six invocation sources and none writes a served table.
They are the playoff-model research line plus two calibration one-shots. Verify against the
methodology docs (some may be intentionally retained as a research record) before removing.

Research (13): `models_ml/analyze_combined_validation.py`, `analyze_goalie_clutch.py`,
`analyze_goalie_clutch_impact.py`, `analyze_kitchen_sink.py`, `analyze_kitchen_sink_v2.py`,
`analyze_noise_demo.py`, `analyze_playoff_components.py`, `analyze_playoff_experience.py`,
`analyze_playoff_profile.py`, `analyze_series_features.py`, `analyze_series_model.py`,
`build_playoff_weights.py`, `train_style_effect.py`.

One-shot calibration (2), outputs already baked into config/vars:
`measure_goalie_reliability.py` (result hand-copied into
`config.GOALIE_GAR_CONFIG["RELIABILITY_K"]`), `tune_sequence_thresholds.py` (thresholds land
in `dbt_project.yml` vars). **[ARCHIVED]** both moved to `archive/models_ml/` in `0620488`
(with their provenance comments repointed and mapped in `archive/README.md`).

Recommendation: the 13 research scripts are **[DEFERRED]** (left in place this pass; keep if
the research record matters). Do not remove `build_playoff_weights.py` before confirming
nothing reads its `playoff_weights.json` output (not opened in the read-only pass).

### 2e. Developer smoke harnesses (main-only, dev tools)
All 12 `smoke_*` scripts are `__main__`-only with no DAG/Make/caller reference; paired with
the `*_FINDINGS.md` notes. `smoke_ingest_ppt_replay.py` is EXCLUDED (puck tracking, T3).

`scripts/smoke_ingest_draft_results.py`, `smoke_ingest_game_context.py`,
`smoke_ingest_glossary.py`, `smoke_ingest_partner_odds.py`, `smoke_ingest_roster.py`,
`smoke_ingest_shiftcharts.py`, `smoke_ingest_standings.py`,
`smoke_ingest_statsrest_faceoffs.py`, `smoke_load_gm_tenures.py`, `smoke_load_trades.py`,
`smoke_roster_source.py`.

**[ARCHIVED]** all 11 non-ppt smokes plus the 4 `*_FINDINGS.md` notes moved to
`archive/scripts/` in `0620488` (kept together; `smoke_ingest_ppt_replay.py` left in
`scripts/` per the puck-tracking rule).

### 2f. Root one-off utilities with uncertain steady-state need

| path | evidence | note |
|---|---|---|
| `populate_raw_games.py` | references `backfill_historical.py`; no DAG/Make | one-off repair paired with the manual backfill; likely superseded once the DAG runs, kept as backfill companion |
| `load_schedule_only.py` | main-only, no non-self refs | one-off schedule-only repair; likely superseded by the DAG's normal `raw_games` load |
| `deduplicate_raw_tables.py` | main-only | on-demand raw dedup maintenance; keep if raw dupes still occur |

`backfill_historical.py` and `setup_gcs_bucket.py` are NOT here (see T3 — they are the live
history-seeding path and the bucket bootstrap).

### 2g. Backend routes with no frontend caller (registered but unused from UI)
Code (route handlers), not data. Verify no external client uses them before removing.

`GET /streaks/active` (`streaks.py:37`), `GET /players/{id}/edge` (`players.py:1164`),
`GET /teams/{id}/edge` (`teams.py:440`), `GET /goalies/{id}/gamelog` (`goalies.py:190`),
`GET /archetypes/style-map` (`archetypes.py:88`). Evidence: `rg` of `frontend/src` for each
path = 0 hits. Some data is folded into other endpoints (edge into `/players/{id}` detail;
streaks via `/teams/{id}/streak`).

### 2h. Policy remediation (not a deletion)

| path | issue | action |
|---|---|---|
| `dbt/profiles.yml` | **tracked and committed** despite `.gitignore:39` and the project rule; contains 2 `keyfile:` filesystem paths (no key material inline; full history scan found no committed private key/password/token) | **[DONE]** `git rm --cached` in `a3a2535` (untracked; local working file kept). `dbt/profiles.yml.example` remains the tracked template |

### 2i. Stale in-domain docs (correct, do not delete blindly — see DOC_RECONCILIATION)
`backend/API_EXPANSION_SUMMARY.md` is a point-in-time changelog (references Cloud Run
revision `00020-sfd`); a candidate to archive/remove once its content is folded into current
docs. `backend/README.md`, `models_ml/README.md`, `insight_engine/README.md` are stale in
parts but still useful; correct rather than delete (DOC_RECONCILIATION.md details each).

---

## Tier 3 — keep (reaches a surface, load-bearing, or protected)

- **Puck tracking (protected, owner decision):** `stg_ppt_tracking_frames`,
  `int_goal_release_frame`, `raw_ppt_replay`, `scripts/backfill_ppt_replay.py`,
  `scripts/smoke_ingest_ppt_replay.py`, `scripts/ppt_cache/`. Reason: reserved for future
  tool per owner.
- **New WOWY / on-ice models (this branch):** `int_segment_5v5_results`,
  `int_player_onice_game`, `mart_player_onice`, `mart_player_toi_matrix`,
  `mart_player_wowy`, `dbt/tests/assert_toi_matrix_symmetric.sql`. Reason: new feature;
  two already feed live marts; all pending `dbt run`. Data objects, never delete.
- **Draft / pWAR ML cluster (reaches shipped surfaces, hand-run cadence):**
  `models_ml/compute_pwar.py`, `fit_pwar_anchor.py`, `fit_pick_value.py`,
  `run_draft_theory.py` and artifact `pwar_anchor_v1.joblib`. Reason: outputs (`player_pwar`,
  `pick_value_curve`, `draft_value_*`, `futures_value`) are served and feed `/draft/*` and
  the trade tools.
- **`train_winprob.py`** (+ `winprob_v1.joblib`): trainer for the live `win_probability`
  path (`score_winprob.py` runs in the DAG). Keep.
- **Live one-offs / infra:** `backfill_historical.py` (the history-seeding path, since there
  is no backfill DAG), `setup_gcs_bucket.py` (provisions the report bucket), the four root
  `test_*.py` integration smokes (intentionally outside pytest per `pytest.ini` comment),
  `backend/validate_trade_engine.py` (wired to `Makefile: trade-engine-validate`), all
  `*-validate` ML scripts (wired to Makefile targets).
- **Everything else** in dbt, backend, frontend, ingestion, reporting, insight_engine that
  appears in a FEATURE_MAP.md trace.
- **Data never deletable:** all `nhl.raw_*`, all marts, all `nhl_models.*`, the DuckDB
  serving file, `stg_partner_odds`/`raw_partner_odds` (internal calibration by design).

---

## Tier 4 — unknown / needs a live check (never a data delete)

From `_inventory/60_bq_objects.md`. These are physical BigQuery objects with no producer in
code. **Do not drop.** The resolving check is listed per item.

| object | type | evidence of no producer | resolving check |
|---|---|---|---|
| `nhl_staging.int_xg_rates` | VIEW | no `.sql` source, absent from manifest, only stale `dbt/target` artifacts reference it | confirm no ad-hoc/notebook query reads it, then leave in place (a former dbt model whose `.sql` was removed) |
| `nhl_staging.int_zone_entries` | VIEW | same; distinct from the live `int_zone_entry_proxy` | same |
| `nhl_staging_staging.stg_boxscores` | VIEW | entire `nhl_staging_staging` dataset has zero code references; residue of a fixed schema-name concatenation bug | confirm no consumer, then the whole stray dataset is a candidate for a DBA to review (not this pass) |
| `nhl_staging_staging.stg_games` | VIEW | same | same |
| `nhl.raw_glossary` | BASE TABLE (data) | 0 dbt consumers | reference data ingested for future concept cards; keep (ingested data, never delete) |

Also T4 (code, needs a runtime confirmation, not static): the 5 no-frontend-caller routes in
2g could instead be resolved by an access-log check to see if any external client calls them.

---

## Summary counts

| tier | count (items/clusters) | nature |
|---|---|---|
| T1 delete | 1 file | `.grepout` |
| T2 verify | ~40 files across 9 clusters | ad-hoc scripts, frontend orphans, v1 archetypes, research cluster, smokes, one-off utils, unused routes, profiles.yml untrack, stale doc |
| T3 keep | the rest | reaching / load-bearing / protected |
| T4 investigate | 4 BQ views + 1 raw table + 5 routes | never a data drop |

Nothing in this document has been deleted or modified. Data and ingested objects are
never proposed for removal. Puck tracking is retained by owner decision.
