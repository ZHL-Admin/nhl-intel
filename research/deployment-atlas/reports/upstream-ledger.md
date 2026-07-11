# Upstream defect ledger

Production defects discovered during the Atlas build. **None is fixed mid-project
without an explicit gate.** Each entry: evidence, affected consumers, proposed fix
layer. (Standing rule, effective Phase 4.)

| # | defect | status |
|---|---|---|
| 1 | stats shiftcharts feed returns empty; HTML fallback needed | **shipped (committed `3fe96d2`) — pending first nightly** |
| 2 | stale, dup-contaminated segment backbone | **fixed (rebuild P1, `9a98923`)** |
| 3 | `2013021108` missing pbp in BigQuery | **fixed (rebuild P2) — 211 segments confirmed (P3)** |
| 4 | no stints for the 2 gap-fetched games | **fixed (rebuild P2) — 409/364 segments confirmed (P3)** |
| D7 | corrupt period-5 shift rows (raw feed, a few reg-season games) | **fixed at staging (rebuild P1.6)** |
| D8 | Airflow scheduler off in this env (nightly ingestion/rebuilds dormant) | activation checklist (deliberate offseason) |
| D9 | 2019-20 malformed shift elements (empty `endTime`, `duration 00:00`) break `stg_shifts` casts | **fixed at staging (P4 guard) — no-op on output** |
| D10 | `compute_ratings` `merge_asof` idiom is production-image-dependent (fails on local pandas 3.0.3 and 1.5.3) | env-pinning runbook item (not a model defect) |

---

## 1. Stats shiftcharts feed failure (nightly gaps accrue)
- **Evidence:** `api.nhle.com/stats/rest/en/shiftcharts` returns 0 shift rows live
  for 563 games (57 in 2024-25, 505 in 2025-26, 1 in 2013-14); swept live 563/563
  empty, 0 recoverable. The daily DAG (`dags/nhl_daily.py`) ingests shifts only
  from this feed, so new gaps accrue each night. The HTML shift reports
  (`nhl.com/scores/htmlreports/…`) have the data (parser validated byte-for-byte
  vs JSON incl. OT).
- **Affected consumers:** `raw_shift_charts` → `stg_shifts` → `int_shift_segments`,
  RAPM (`player_impact`), every on-ice/WOWY mart, and the Atlas corpus.
- **Proposed fix layer:** ingestion. HTML fallback in the daily DAG when the JSON
  response is empty. **Being implemented by Workstream A** (2026-07-10).
- **History already backfilled** (563 games, 2026-07-10) — this entry is only the
  forward-looking nightly fix.

## 2. Stale, dup-contaminated segment backbone
- **Evidence (Phase 2):** `int_shift_segments` is a materialized table (built
  2026-07-06) that (a) contains **0 of 400 sampled backfilled games** and only
  895/1312 of 2025-26; (b) is built on **undeduplicated `stg_shifts`** (the raw
  NHL shift array repeats exact `(player,start,end)` rows; production inherits
  them); (c) has **no goal cut-points** (score not constant per segment).
- **Affected consumers:** `int_segment_context`, `int_on_ice_events`,
  `models_ml/train_rapm.py` → `player_impact`, and every mart reading segments.
- **Proposed fix layer:** dbt (dedup `stg_shifts` or add a dedup step; rebuild
  segments after the backfill; add goal cut-points if score-constant segments are
  wanted upstream) + a scheduled rebuild so it isn't stale. The Atlas works around
  it by deriving its own deduplicated, goal-cut stints in the research layer.

## 3. `2013021108` missing pbp
- **Evidence (Phase 3.4):** this 2013-14 game has shift data but **no row in
  `raw_play_by_play`** (BigQuery). It surfaced as the third of three
  shifts-without-warehouse-pbp games; Phase 1.2's missing-pbp check only covered
  2015+, so a pre-2015 pbp gap went unnoticed.
- **Affected consumers:** any pbp-derived model for that game (events, xG, stints);
  1 game, pre-2015 (secondary scope).
- **Proposed fix layer:** ingestion. Fetch `/v1/gamecenter/2013021108/play-by-play`
  and load to `raw_play_by_play` (idempotent). Trivial; batch with any pre-2015
  pbp coverage sweep.

## 4. No stints for the 2 gap-fetched games
- **Evidence (Phase 3.4):** `2023020651` and `2024020147` had missing pbp in
  BigQuery (fetched to the Atlas research cache in Phase 1). Their **events are in
  the Atlas events table**, but the Atlas stint builder sources home/away meta from
  `raw_play_by_play` (BigQuery), which lacks them — so no stints were built for
  these 2 games.
- **Affected consumers:** the Atlas stint table + per-player 5v5 rates (2 games,
  ~0.01% — negligible).
- **Proposed fix layer:** (a) ingestion — load these 2 games' pbp into
  `raw_play_by_play` (they exist at the pbp endpoint); or (b) research — build their
  stints from the cached pbp. Deferred; not material to any published table.

## D7. Corrupt period-5 shift rows (raw feed)
- **Evidence (rebuild P1):** a handful of regular-season games carry on-ice shift
  rows mislabelled **period ≥ 5** (period 5 is the shootout, which has no on-ice
  shifts) — e.g. `2021020972`, `2024021178`, `2024020695`, `2025020544` (3 period-5
  shifts each; shifts byte-identical between the Atlas and production pipelines).
  They caused the only per-game-seconds reconciliation misses in P1.
- **Affected consumers:** any per-game shift-span/segment total for those games; no
  5v5/analytical impact (the corrupt spans are outside 5v5).
- **Fix layer / status:** **dbt staging — FIXED (P1.6, `9a98923`).** `stg_shifts`
  drops `period >= 5` rows for `game_type = '02'` only (playoff multi-OT untouched).
  After the fix the 4 games reconcile exactly against the Atlas capped at 3900s
  (end of regular-season OT). The **frozen Atlas side retains the corrupt spans**
  (built 2026-07-10, pre-fix) — documented as frozen-with-anomaly, not changed.

## D8. Airflow scheduler not running the daily DAG (activation checklist)
- **Evidence (rebuild P1):** the daily DAG (`dags/nhl_daily.py`) is correctly wired
  to rebuild the segment backbone (`run_dbt_pre_xg`) and marts (`run_dbt_marts`)
  nightly, but the tables sat at 2026-07-02/06 — the **scheduler was not executing
  the DAG**. This is a **deliberate offseason choice, not a defect**: nightly
  ingestion and rebuilds are intentionally dormant between seasons.
- **Activation checklist (owner action before the 2026-27 preseason):**
  1. Enable the daily DAG on the scheduler.
  2. Supervise the first two nightly runs: verify `check_shift_coverage` passes; and
     if any game's JSON shift feed is empty, confirm the **HTML fallback fires and
     writes provenance-marked rows** (`_source = html_shift_report`).
  3. Confirm the P1/P3 model changes (dedup, goal-cut segments, retrained
     `player_impact` + `shot_xg`) are rebuilding on cadence.
  4. **P4 environment-blocked re-runs (must not be forgotten):** run
     `compute_ratings` in the production image (it fails on local pandas, D10),
     then its five stale-prior dependents — `score_winprob`, `streak_doctor`,
     `simulate_deserved`, `roster_forecast`, `compute_team_needs` — and re-export;
     and re-run `compute_assessment` once the DuckDB serving file is unlocked.
  5. After both re-runs verify, **drop the `*_p4pre` audit snapshots** and note the
     drop in `docs/rebuild-reports/p4.md`.
- **Dependency:** the **frozen prospective 2026-27 mover test depends on this
  activation** — without the DAG running, 2026-27 shifts/pbp/xG/RAPM will not
  populate and the pre-registered test cannot be evaluated.
- **Concealment caveat (added P4):** the dormant scheduler **hid latent defects in
  rarely-rebuilt models** — e.g. D9 surfaced only when P4 first rebuilt
  `mart_player_game_stats` / `mart_team_identity` since the tables went stale. The
  first supervised nightly runs after activation should **expect and triage
  similar first-rebuild failures as pre-existing surfacings, not regressions.**

## D9. 2019-20 malformed shift elements break `stg_shifts` casts
- **Evidence (P4 consumer sweep):** 1,129 raw shift elements across **174 games**,
  all **2019-20 regular season** (typeCode 517), carry an **empty `endTime`** (`""`)
  with `duration '00:00'`. `stg_shifts.shift_end_seconds` computes
  `cast(split(end_mmss,':')[offset(1)] as int64)`; on `''` that errors
  (`Bad int64 value`) **before** the outer `duration_seconds between 1 and 1200`
  filter can drop the rows. Original JSON feed (no `_source` tag) — not the HTML
  backfill, not the P1 dedup/period-5 change.
- **Affected consumers:** `mart_player_game_stats`, `mart_team_identity` — the only
  models that scan the view to completion evaluating `shift_end_seconds` /
  `duration_seconds`. Both were stale (D8) so the defect stayed hidden.
- **Fix layer / status:** **dbt staging — FIXED (P4 guard).** `stg_shifts` `parsed`
  CTE now requires well-formed `start_mmss`/`end_mmss` before the cast. Proven a
  **no-op on output** (per-season row + duration + end checksums byte-identical
  pre/post, 16 seasons; see `docs/rebuild-reports/p4-blocker.md`), so the P1
  reconciliation stands. **Belt-and-suspenders** ingestion-layer normalization
  (skip/normalize empty-`endTime` elements at load) is proposed but **not urgent** —
  batch it with future ingestion work.

## D10. `compute_ratings` `merge_asof` is production-image-dependent
- **Evidence (P4):** `compute_ratings.add_trajectory_and_se` uses a version-specific
  `pd.merge_asof(..., right_on=<Series>)` idiom. It fails on **every locally
  available pandas** — 3.0.3 (research venv): incompatible datetime resolutions
  `[s]` vs `[us]`; 1.5.3 (a purpose-built py3.10 venv): a Cython `asof_join` ABI
  error. It runs only under the pandas the production Airflow image pins.
- **Affected consumers:** none in production (the DAG runs the pinned image); this
  bites **local/dev re-runs** of the value chain (e.g. the P4 sweep).
- **Fix layer / status:** **not a model defect — a dev-runbook env-pinning item.**
  Record the exact pandas/numpy pins the models_ml consumer chain needs, or provide
  a `requirements-ml.txt`, so local re-runs match production. Code left untouched.

---

## Note — R1 flag (P4, flag-only)
The three **projection** consumers that derive next-season value from the adjusted
lens with no raw component — `project_roster_forecast`, `compute_contract_value`
(`blended_war_rate` core), and `roster_player_projection` — **inherit the R1 −7.4%
stayer understatement**. The designated remedy is a **conditional raw/adjusted blend
keyed on stayer/mover status, weights fit against the R1 holdout**. This **must be
its own gated task**, not folded into a rebuild. Descriptive consumers (composite,
gar, radar, deployment, verdict, impact-context) are not affected. See
`docs/rebuild-reports/ratings-diff.md`.
