# Session state — finalization plan progress

Working branch: **`finalization`**. Phases 0-5 COMPLETE; a **post-Phase-5 archetype-v2 refit +
skills-radar build** also COMPLETE (see the block below). Next: Phase 6 (insight engine, education
layer, site completion). Latest commits: 338d822 (radar FE+methodology), 3174337 (radar backend),
e25b7ed (radar data layer), b7c9226 (archetypes v2 A3), 3afd20f (v2 A1/A2). Read the **ARCHETYPE V2
+ RADAR** block first (it changes the archetype system Phase 6 detectors consume), then the
**PHASE 6 KICKOFF** block, then per-phase sections + `nhl-intel-finalization-plan.md`. Also read the
**LIVE ROSTER MEMBERSHIP** block below (current-team affiliation now comes from a live roster feed).

---

## ===== POSITION- & DEPLOYMENT-AWARE LINEUP BUILDERS (Phase 1 + Phase 2 COMPLETE) =====

**Why:** the lineup builders (Roster Builder auto-optimize, offseason-forecast lineups, roster
suggestions) seated forwards by the *listed* NHL position and stacked lines WAR-greedily. Two failures:
listed position is often wrong (J.T. Compher lists at LW but plays C), and best-C+best-LW+best-RW is
not how teams actually deploy (Edmonton splits McDavid & Draisaitl at 5v5).

**Phase 1 — effective position (DONE):**
- New nightly precompute `nhl_models.player_effective_position`
  (`models_ml/precompute_serving.build_player_effective_position`, registered in `serving_tables.yml`,
  built by the DAG `precompute_serving --all` step, exported to DuckDB): per player, the position he
  ACTUALLY plays (`C`/`L`/`R`/`F_FLEX`) from last-2-seasons faceoffs-per-game (`stg_statsrest_faceoffs`,
  GP-weighted), plus `locked`. Thresholds in `config.EFFECTIVE_POSITION` (C ≥ 7 fo/gp, W ≤ 2.5, ≥ 10 GP
  to lock). Validated on the disagreement list: Compher + 13 two-way centers flip to C; pure wingers
  (Kucherov, Marchand, Rantanen, Nylander) stay; real centers stay C.
- Consumed via `_load_effective_position` (tools.py, in `_forecast_inputs`) and
  `project_roster_forecast.load_effective_position` (offseason). Forward display position = effective
  (Compher shows C); `roster_suggest._pos_ok` matches on effective (F_FLEX matches any forward slot).
- **Soft-penalty assignment** replaces the greedy column-fill in `_ice_from_pool`: forwards are seated
  by `scipy.optimize.linear_sum_assignment` maximizing `projected_war − off_position_penalty` over
  (forward, slot). Penalties in `config.ROSTER_FORECAST` (`OFF_POSITION_PENALTY_CW=0.35`,
  `WING_SIDE_PENALTY=0.05`, F_FLEX=0). **The penalty shapes the ASSIGNMENT ONLY** — team WAR / points
  sum RAW `projected_war`, never net of penalties. The pure engine
  `project_roster_forecast.assign_forward_sides` is SHARED by the live tool AND
  `calibrate_roster_builder` so the calibration ices the exact rule. Deterministic (tie-break by
  player_id); a pool < 12 leaves replacement holes.
- **Recalibrated (Phase 1):** `LEAGUE_AVG_LINEUP_WAR 12.68`, `WAR_TO_RATING 0.03289`; projected-points
  MAE 10.52, verdict SHIP. Committed on branch `position-aware-lineups` (commit e3487b1).

**Phase 2 — deployment-aware line seeding (DONE):**
- Shared engine `project_roster_forecast.seed_and_assign_forwards` / `seed_and_assign_defense`: SEED
  observed 5v5 units (full member set present + unplaced, shared minutes ≥ floor), rank into line/pair
  order by combined projected WAR, then ASSIGN the rest via the Phase-1 assignment. Source = the team's
  `int_line_seasons` (base season, floor `LINE_SEED_MIN_5V5_MINUTES=100`) MERGED with `team_current_lines`
  (last-10, floor `..._CURRENT=30`) — a documented deviation from strict prefer-current/fall-back
  (10-game minutes never clear a season floor, so a strict rule seeds nothing in the offseason; season
  units dominate by minutes so recent-form units only fill gaps). Both tables already exported to DuckDB.
- Applied in `_ice_from_pool` (Roster Builder baseline + optimize, via `_seed_units` loader, cached) and
  the offseason forecast (`_full_lineup` seeded path, `load_seed_units`/`load_handedness` in main;
  ledger + delta math unchanged, flat build_lineup kept as the None fallback so pure-core tests pass).
  No per-edit model scoring — live edit path stays fast.
- **McDavid & Draisaitl split verified** (EDM optimize): McDavid F1C with his 250-min trio, Draisaitl
  F2C with his own trio (their together-trio is 88 min, below the floor). Compher still C. Deterministic.
- **Recalibrated (Phase 2):** `LEAGUE_AVG_LINEUP_WAR 12.09`, `WAR_TO_RATING 0.03540`; projected-points
  MAE **10.51** (~= 10.5), corr **0.465** (up from 0.427 — seeding helps), verdict SHIP.
- Docs: `roster-builder.md` (Effective position, Line assignment, Line seeding), `offseason-forecast.md`
  (steps 2 + 4).

## ===== LIVE ROSTER MEMBERSHIP — current team comes from a live feed, not just games =====

**Why:** a player's "current team" used to be derived only from the team_id on his most recent NHL
game (game types 01/02/03; intl excluded). In the offseason no games are played, so trades were
invisible until the traded player dressed for his new club. We added a live-roster feed so MEMBERSHIP
(the team LABEL) updates immediately.

**CRITICAL CAVEAT — membership != performance:** the live roster fixes the team LABEL only. A
just-traded player has ZERO games with his new club, so his impact/archetype/radar/value still
reflect old-team usage until he plays. On the team-roster surface a trade-in shows `games_played: 0`
and null per-60 rates by design. Do not "fix" that; it is the honest state.

**Pipeline (raw -> resolution -> serving):**
- `scripts/refresh_rosters.py` (`make roster-refresh`; DAG daily task `roster_refresh`, wired
  `ingest_task >> roster_refresh >> run_dbt_pre_xg`) -> `ingestion.nhl_api.get_roster()` per team ->
  `nhl_raw.raw_rosters` (one row per team+ingestion_date; forwards/defensemen/goalies serialized JSON
  strings + scalar `team_abbrev`/`season8`; autodetect loader, NOT partitioned).
- **Endpoint deviation (the API won):** the planned `/roster/{TEAM}/current` is a **307 redirect**;
  we resolve "current" as `max(/roster-season/{TEAM})` -> `/roster/{TEAM}/{season8}` (both 200). In
  deep offseason this resolves to the just-finished season until NHL publishes the next one, then it
  tracks the new season automatically. See `scripts/ROSTER_FINDINGS.md` (written from real payloads).
- `stg_roster_current` (staging): parses the serialized arrays, keeps the **newest ingestion per
  player** (`row_number() ... order by ingestion_date desc`), resolves team_id from `stg_games`
  (staging, NOT a mart — avoids a staging->mart inversion).
- `int_player_current_team` (intermediate): the resolution. `coalesce(live_team, latest_game_team)` —
  **live roster is source of truth; latest-game (01/02/03 filter) is the fallback so nobody is
  dropped** (UFAs/minor-leaguers/between-contract keep their last-game team). `team_source` flags which.
- `models_ml/precompute_serving.build_dim_current_roster` -> `nhl_models.dim_current_roster`: the
  resolved current team + live-preferred identity (name/pos/headshot), universe = current-season
  game players UNION live-roster players. **stg_rosters grain is UNCHANGED** (per-game historical).

**SERVING/DuckDB GOTCHA (this is what makes the FE update):** the backend serves request-time reads
from `data/serving/nhl_intel.duckdb` (`SERVING_BACKEND=duckdb`, the default) using BARE table names;
only the ~62 tables in `serving_tables.yml` exist there. `int_player_current_team`/`stg_roster_current`
are NOT exported, so **all request-time membership reads `dim_current_roster`** (which IS a serving
table and carries the resolved team): player picker/search (`services/tools.py`), `/teams/{id}/roster`,
`/players/{id}` team label, contract grader. After any membership change the FE only updates once you:
1) rebuild the dim: `python -m models_ml.precompute_serving --only dim_current_roster`,
2) re-export BQ->DuckDB: `make export-serving` (atomic swap of the serving file),
3) **restart the backend** — it runs as a detached `uvicorn main:app --port 8000` (NO --reload), so:
   `pkill -f "uvicorn main:app"; cd backend && export GOOGLE_APPLICATION_CREDENTIALS=$PWD/../secrets/nhl-intel-sa.json && nohup uvicorn main:app --port 8000 > ../backend_server.log 2>&1 &`
Verified end-to-end: Brady Tkachuk (8480801) resolves to FLA on `/players/8480801` and appears on
`/teams/13/roster` with `games_played: 0`. Hermetic tests: `tests/test_roster_ingest.py`.

---

## ===== ARCHETYPE V2 + SKILLS RADAR — READ FIRST (supersedes the v1 archetype system) =====

**Why:** v1 archetypes clustered mostly on offense; defense barely separated clusters (labels were
a display afterthought). v2 refits on an ENRICHED vector so defense/deployment DRIVE clustering,
and adds the percentile-within-position skills radar as the primary player-page visual.

**Archetypes v2 (current; model_version `archetypes_v2` in `nhl_models.player_archetypes`):**
- Fit: `models_ml/fit_archetypes_v2.py` + `archetype_features_v2.py` (build_v2 adds coach-trust
  composite+components, rink-adj hits/60, penalty diff/60, on-ice xGA suppression to the v1
  vector). F/D separate, k=12 each, persisted single-threaded at
  `artifacts/archetypes_v2.joblib` (FORCE-COMMITTED). Trait audit governs naming:
  `artifacts/archetype_trait_audit_v2.md` (universal ≥80% → name; distinctive centroid → descriptor).
- Names + descriptors: `config.ARCHETYPE_NAMES_V2` + `ARCHETYPE_DESCRIPTORS_V2` + family map
  `ARCHETYPE_FAMILY_V2` (human-confirmed). 12 F + 11 D labels.
- **Display-merge gotcha:** D3 and D4 are DISTINCT GMM components but map to ONE label
  **"Depth Defenseman"** (union universally low-PP+low-PK = depth). The row builder sums their
  weights so a mix shows it once. → 23 distinct primaries, not 24.
- **v1 ARCHETYPE_NAMES is retired** but kept in config for the old `fit_archetypes.py`. All live
  consumers (linefit_features, score_team_fit, compute_team_needs, metrics.ts, DAG, radar) use
  ARCHETYPE_NAMES_V2. Line-fit was retrained on v2 (identical metrics; arch cosine is label-invariant).
- **Season-sensitive:** a star can move clusters by season (e.g. McDavid is Elite Offensive Driver
  2021-24 but North-South Forward 2025-26 — a fast/conceding season). Labels are descriptive
  per-season regions; the radar carries the real signal regardless.

**Skills radar (Part B):** `models_ml/compute_player_radar.py` -> `nhl_models.player_radar`
(14 skater spokes), `compute_goalie_radar.py` -> `nhl_models.goalie_radar` (7 spokes). Percentile-
WITHIN-POSITION; **variable spoke set** (burst & impact/coach-trust spokes ABSENT pre-2021, omitted
not zeroed); honesty tag per spoke (skill/usage/style/proxy); sd whisker on noisy impact spokes.
Derived labels written alongside: Overall family / offensive sub-label (= primary v2 archetype) /
deployment-based defensive sub-label / descriptor. Backend `GET /players/{id}/radar` +
`/goalies/{id}/radar`. Frontend `components/visualizations/SkillRadar.tsx` (SVG, variable-length),
primary header visual on PlayerProfile; `src/api/labels.ts` `getPlayerLabels`/`playerLabelsFromRadar`
is the single source for player labels. docs/methodology/{archetypes.md (v2 section),player-radar.md}.

**Phase 6 implications:** insight detectors that reference archetypes/labels read v2 names from
`player_archetypes` (or `player_radar` labels via getPlayerLabels). `team_needs` regenerated on v2.
**Two deferred-to-Phase-6 items:** (1) ConceptTip per radar spoke — SkillRadar currently uses its
own hover tooltip; retrofit ConceptTip in 6.3. (2) list surfaces (PlayerPicker chip, Players index,
line/player fit) read the offensive sub-label from their batch payloads (same v2 source, no drift,
no N+1) rather than calling getPlayerLabels per row — intentional.

**Build/regenerate cadence:** `make archetypes-v2` (refit+write), `make radar` (both radars).
DAG: `compute_player_radar`/`compute_goalie_radar` after archetypes/marts; `write_archetypes` now
runs `fit_archetypes_v2 --write`. To re-audit before renaming: run `fit_archetypes_v2` (no --write).

---

## ===== PHASE 6 KICKOFF — READ THIS FIRST (for the next agent) =====

**Goal:** blueprint sections 7/8/9 / plan Phase 6 — the deterministic insight engine, education
layer, annotated moments, and remaining site architecture (Home, Learn, finished game tabs):
- **6.1 Insight engine core** (`insight_engine/`): registry.py (Insight classes: detector ->
  candidate facts, surprise 0-100, stakes 0-100, render -> {headline, body, link, numbers_used}).
  detectors/ one module per family (goaltending_theft, xg_result_divergence, special_teams_swing,
  comeback_leverage, streak_doctor_trigger, divergence_board_mover, breakout_player,
  chemistry_discovery, conversion_diagnosis, milestone_watch, cold_streak_physical — note the
  last is GATED: Phase 4.4 burst-decline validation FAILED, so do NOT ship that detector unless
  re-validated). score = 0.6*surprise + 0.4*stakes; per-surface caps. **CONSISTENCY CHECKER**
  (mandatory): render() declares numbers_used; checker verifies each vs the API value the target
  page renders, drops failures. Nightly `models_ml/run_insights.py` -> nhl_models.insights.
  Backend GET /insights/{feed,game/{id},team/{id}}.
- **6.2 Home page + game insight integration**: `/` becomes Home (move GamesExplorer to /games,
  update NavBar + GameCard links); insight feed (InsightCard), slate strip, style-map teaser,
  active Streak Doctor cards, divergence teaser. GameDetail insight banner; TeamProfile storylines.
- **6.3 Education layer**: frontend/src/config/glossary.ts (concept keys -> {term, shortDef,
  longDef, methodologyHref}; seed from nhl_raw.raw_glossary where it exists, in-house for our
  metrics). Shared ConceptTip wraps stat labels site-wide (shows the on-screen number as the
  worked example). /learn route: concept index + methodology library (render docs/methodology/*.md
  via Vite import.meta.glob + react-markdown/marked — the one new FE dep). "Why this matters"
  threads: insight_engine/templates/concept_links.py maps template_id -> concept key.
- **6.4 Annotated moments**: top 2-3 plays per game by (xg x leverage), goals always eligible.
  RinkDiagram shared SVG (components/visualizations; refactor ShotMap/ShotMapKDE to consume a new
  frontend/src/config/rink.ts geometry module). Narration from xG decomposition
  (insight_engine/templates/moments.py). **GOAL moments render REAL tracking** from
  int_goal_release_frame (Phase 1.4) + optional animation stepping stg_ppt_tracking_frames; gate
  on tracking-row presence; non-goal moments fall back to event-inferred + must NOT claim tracking.
  Backend GET /games/{id}/moments. GameDetail Analytics tab Key Moments section.

**Inputs Phase 6 consumes (all built):** every nhl_models table (shot_xg, win_probability,
team_ratings, deserved_standings, style_map, streak_cards, player_impact, player_composite,
player_archetypes, player_clutch, player_consistency, player_coach_trust, divergence_board,
aging_curves, player_twins, player_physical, **insights** is new, **team_needs** Phase 5.3,
**linefit** artifact for chemistry_discovery). marts + int_shot_sequence (trigger events for
moments) + int_goal_release_frame + stg_ppt_tracking_frames + stg_game_context (highlight links).

**Patterns to reuse (don't reinvent):**
- **insight_engine/templates/** deterministic explanation modules now established: divergence.py,
  line_fit.py, team_fit.py, matchup.py. Phase 6 moments/concept_links follow the same shape
  (pure functions, every sentence references a number in the payload — the consistency rule).
- Frontend shared (components/common): ComponentStackBar, PercentileBarList, StreakDoctorCard,
  StripPlot, Tabs, TabNav, ChartPanel, MiniWorm, **PlayerPicker, LineProjection, LineSwapWidget,
  MatchupPreviewCard** (new in Phase 5). Lazy-load heavy/new routes via React.lazy + Suspense
  (App.tsx already does this for /tools).
- Backend: get_models_table_id() for nhl_models, get_full_table_id() routes mart_/stg_/int_ by
  prefix (**watch this — mart_goalie_season is a MART not a model table; that bit 5.3**). 1-seg
  routes under a prefix (/tools/x, /players/search) MUST register BEFORE /{id} param routes.
  Heavy sync model calls in async endpoints -> `fastapi.concurrency.run_in_threadpool`. The
  backend reaches the model layer by inserting the repo root on sys.path (see services/tools.py).
- Model jobs: argparse + --dry-run, write via models_ml/bq.write_df, weekly Monday-gate in DAG
  via the `_mon` jinja helper. Backend imports models_ml.score_line / score_team_fit as services.

**Gotchas that bit this session (still live):**
- `window` / `nulls` / `rows` are BQ reserved words (use window_kind etc.).
- **International-team pollution is REAL and bit Phase 5**: stg_rosters/player marts include 2026
  Olympic/4-Nations games whose team_id is a NATIONAL team (e.g. Kyle Connor's "latest 2024-25
  game" was USA, team_id 67). ALWAYS filter `substr(cast(game_id as string),5,2) in ('01','02',
  '03')` when picking a player's current team or enumerating players by team. TEAM marts already
  filter; player-side lookups do NOT.
- sklearn GMM is NOT reproducible here (threaded BLAS); line-fit/team-needs use deterministic
  LightGBM/cosine, fine. The LOCKED archetype GMM stays at artifacts/archetypes_v1.joblib.
- Artifacts dir is gitignored except .gitkeep — **force-add new model artifacts** (`git add -f
  models_ml/artifacts/linefit_v1.joblib`) like archetypes_v1.joblib, or the backend can't load them.
- pydantic v2 warns on `model_*` field names (protected namespace) — harmless, pre-existing.
- Env: `set -a && source .env && set +a && export GOOGLE_APPLICATION_CREDENTIALS=$PWD/secrets/
  nhl-intel-sa.json`. dbt always `--target dev`. `dbt/profiles.yml` is git-tracked-but-local
  (timeout_seconds=1800) — DO NOT commit it (the per-commit `git reset -q dbt/profiles.yml`).
- Working directory PERSISTS across Bash calls in this harness — a stray `cd` carries over; use
  absolute paths or re-`cd` to repo root.
- Backend uvicorn smoke: test via python urllib with a connection-retry loop (the shell's curl
  has been flaky); start server with run_in_background. Python stdout to a file is block-buffered
  — pass `python -u` when watching a long job's prints.

**Open/optional items (none block Phase 6):** partner-odds de-vig (offseason-blocked); xG
top-end recalibration (user ACCEPTED as-is, do not revisit); int_shift_segments 2010-15 rebuild
(deferred); incremental refactor of the segment chain (deferred); player-mart international-team
filter (cosmetic; the Phase 5 surfaces that needed it now filter at query time).

---

## Done & validated (committed)
- **Phase 0** — proxy relabeling (`zone_entry_proxy_*`), model-layer conventions
  (`models_ml/`, `insight_engine/`, `docs/methodology/`, `frontend/src/config/metrics.ts`),
  dbt vars, README + Makefile. dbt compile + pytest + frontend build all green.
- **Phase 1.1 — shift charts (COMPLETE)**
  - Ingestion: `get_shift_charts`, loader `raw_shift_charts`, `scripts/ingest_shifts.py`,
    `backfill_historical.py --tables {boxscore,pbp,shiftcharts}` (resumable shift-only path),
    daily DAG wired, `scripts/smoke_ingest_shiftcharts.py`.
  - **Full history backfilled: ~13,850 games, 2015-16→2025-26, 0 failures.**
  - Models: `stg_shifts` → `int_shift_segments` (53.1M rows) → `int_segment_context`
    (4.5M) → `int_on_ice_events` (4.3M), all materialized as tables.
  - **Validated: 81,762 goals at 99.95% on-ice attribution; ~48 5v5 min/game every season.**
  - Key corrections to the plan: typeCode **517 = real shifts, 505 = goal annotations**
    (plan had it backwards); event→segment uses **(start, end]** (goals carry the
    shift-end timestamp); excluded 0.01% degenerate/corrupt durations.
- **Phase 1.2 — Edge staging/marts/backend (COMPLETE)**
  - Read EDGE_FINDINGS + `edge_samples/` and built `stg_edge_skaters` (pivots the 5
    per-report rows → 1 typed row: speed/bursts, distance, shot speed, zone time all+es,
    zone starts, danger buckets), `stg_edge_goalies`, `stg_edge_teams`.
  - Marts `mart_edge_player_profile` (burst rates per 60 use **real** stg_shifts TOI,
    not the 15.0 placeholder), `mart_edge_team_profile` (danger-bucket shot shares).
    dbt build+test PASS=15. Validated: zone pcts sum to 1.0, 0 null TOI, burst rates finite.
  - Backend `GET /players/{id}/edge` + `GET /teams/{id}/edge` (+ EdgePlayerProfile/
    EdgeTeamProfile schemas, season-string→id helper). Both verified end-to-end.
  - `scripts/backfill_edge.py` (multi-season, resumable; reuses refresh_edge.refresh_season);
    Edge refresh wired into the weekly Monday-gated `refresh_weekly_aux` DAG task.
  - **Honest scope:** Edge goalie endpoint has NO HD/5v5 save-pct split (only gamesAbove900
    + last-10 save pct) — documented; danger goalie splits come from Phase 2.5 GSAx. Edge
    `team-zone-time` 404s, so team oz-time for 3.2 will TOI-weight skater zone time.
  - **Data:** marts currently hold the 15-entity 2024-25 sample only — a full
    `backfill_edge.py` run (2021-22→2025-26) populates the rest (kick off in background).

- **Phase 1.2 (original) — Edge ingestion layer**
  - **Real endpoint family discovered** (plan's `/v1/edge/skater-detail` was dead):
    `/v1/edge/{entity}-{report}/{id}/{season}/{gameType}`. Reports: skater
    skating-speed-detail / skating-distance-detail / shot-speed-detail /
    shot-location-detail / **zone-time** (no `-detail` suffix); goalie
    save-percentage-detail; team shot-location-detail. See `scripts/EDGE_FINDINGS.md`
    + saved payloads in `scripts/edge_samples/` (gitignored).
  - `get_edge_skater/goalie/team`, `scripts/explore_edge.py`, `scripts/refresh_edge.py`
    (resumable, `make edge-refresh SEASON=...`), `raw_edge_*` sources + loader.
  - Only a 15-entity sample ingested so far (2024-25) — run a full refresh per season.

- **Phase 1.3 — non-Edge API surfaces (CODE COMPLETE; full backfills pending)**
  - **All 5 surfaces probed live** (`scripts/STATSREST_FINDINGS.md`): faceoffs use
    `skater/faceoffwins` (zone + ev/pp/sh splits, paged); landing carries per-goal
    `highlightClipSharingUrl` + `pptReplayUrl` (the latter is real — note for 1.4);
    right-rail carries scratches/coaches/seasonSeries/teamGameStats; glossary lives on
    the **stats-REST host** (`/stats/rest/en/glossary`; api-web `/v1/glossary` is 404);
    standings-by-date gives ranks + l10 (offseason dates return 0 rows).
  - Ingestion: `get_skater_faceoffs/get_game_landing/get_game_right_rail/get_partner_odds/
    get_glossary/get_standings_by_date`; loader serialize-field + game_id-injection rules;
    `raw_*` sources. Refresh scripts (resumable, repo precedent = per-surface like Edge):
    `refresh_statsrest_faceoffs.py`, `refresh_game_context.py`, `refresh_standings.py`,
    `refresh_partner_odds.py`, `ingest_glossary.py`. Smoke tests for all 5 (all green).
  - Staging: `stg_statsrest_faceoffs`, `stg_standings`, `stg_game_context`,
    `stg_partner_odds` (de-vig; **INTERNAL ONLY**, no API/UI). Mart: `mart_player_faceoff_zones`.
    dbt build PASS=13. Validated: Crosby/Hischier/Larkin top faceoff vol, zone sums consistent;
    G4 context = 8 goals all w/ links, scratches/series/last10 parsed.
  - Backend: `GET /games/{id}/context` (joins last-10 from `stg_standings` as-of game date).
    Frontend: GameDetail Overview gets a **Matchup context** card (series/last-10/scratches via
    ComparisonRow) + scoring-timeline rows link to highlight video (`target=_blank`). `npm run build` green.
  - DAG: landing/right-rail/standings/partner-odds added to daily `ingest_nhl_data`;
    new weekly `refresh_weekly_aux` task (faceoffs + glossary, Monday-gated).
  - **Backfilled (both seasons):** game context = **3,340 games** (2025-26 + 2024-25) in
    raw_game_landing/right_rail, stg_game_context = 3,340 rows; standings daily for both
    seasons = **389 dates / 12,448 rows** in stg_standings. `refresh_game_context.py` flushes
    to BigQuery every `--batch-size` (200) games so a long run is durable/resumable mid-run.
  - **Only remaining gap:** `partner_odds` de-vig path is PENDING an in-season payload
    (offseason → games=[]); confirm the american-odds JSON path against the first live snapshot.
    `backfill_historical.py` intentionally NOT touched (per Edge precedent, new surfaces use
    their own refresh scripts).

- **Phase 1.4 — ppt-replay tracking + backfill floor (CODE COMPLETE; backfills running)**
  - **Plan was UPDATED** mid-project: ppt-replay is no longer a spike — it's confirmed-real
    tracking ingestion (re-read the plan if resuming; acceptance now requires raw_ppt_replay
    + stg_ppt_tracking_frames + int_goal_release_frame populated, transform orientation-checked).
  - **Task 1 (ppt-replay), DONE + validated, committed:** `get_ppt_replay` two-hop fetch
    (metadata → wsr.nhle.com sprite). wsr is Cloudflare-fronted: bare req 403s, **Referer +
    browser UA via plain httpx = 200 (no curl-impersonate needed here)**. On-disk sprite cache.
    onIce map → list (entityKey preserved) so BigQuery can UNNEST. `raw_ppt_replay`,
    `stg_ppt_tracking_frames`, `int_goal_release_frame` (release pinned geometrically: puck
    nearest a net — sprite has no frame→game-clock field). `backfill_ppt_replay.py` (resumable,
    ≤1 req/s, batch-flush), smoke test, methodology doc, DAG step after pbp.
    - **COORDINATE UNITS CORRECTED:** plan said "tenths of a foot / 2000×850"; observed raw is
      **inches** (2400×1020 = 12×200ft by 12×85ft). Transform = raw/12−100 (x), raw/12−42.5 (y).
      /10 put skaters 20ft past the boards; /12 puts all in-rink + release puck on the goal line.
    - Validated on 3 games (24 sprites): frame counts match, all entities in-rink, release puck
      at x_std≈±89 / y≈0.
  - **Task 2 (backfill floor → 2010-11), code DONE + committed:** `backfill_historical.py --all`
    now spans 2010-11→2025-26. Free-tier OK (core raw 5.0 GB for 11 seasons; +5 stays <10 GB).
  - **RUNNING NOW (detached nohup, ~home-dir logs):**
    (a) `backfill_historical --seasons 2010-11..2014-15 --tables boxscore pbp shiftcharts`
        (~/backfill_2010_2014.log);
    (b) full Edge backfill `backfill_edge --seasons 2024-25 2025-26` (~/edge_backfill2.log) —
        now durable: get_edge_detail returns None on 404 (no 3× retry), _ingest batch-flushes
        every 500 rows (the old accumulate-then-load-once was slow + lossy; fixed + committed).
  - **AFTER backfills finish (finalization steps):** (1) `dbt run --select mart_edge_player_profile
    mart_edge_team_profile` so the Edge marts reflect the full roster (they're TABLES; currently
    sample + partial); (2) print per-season row counts of stg_play_by_play + stg_shifts as the
    2010-2015 completion proof (both are views — no rebuild needed); (3) optionally rebuild the
    int_shift_segments chain to include 2010-15 (heavy ~17min — tied to the incremental refactor).

- **Historical coverage deepened (empirically-probed floors, backfills RUNNING):**
  Probed each surface before backfilling — the floors differ and are NOT what you'd assume:
  - **Edge floor = 2021-22** (McDavid 404s for 2020-21 and earlier). Backfilling
    2021-22→2025-26 (`~/edge_backfill_full.log`).
  - **ppt-replay floor = 2023-24** (2021-22 & 2022-23 goals 404 for BOTH regular-season and
    playoffs; narrower than Edge — replay sprites are a newer feature than tracking aggregates).
    Backfilling 2023-24/2024-25/2025-26 goals (`~/ppt_backfill_full.log`; long ~hours job;
    preseason goals skip fast as "not a tracked goal").
  - **Faceoffs go back to ≥2010-11** (non-tracking; full depth). Backfilling 2010-11→2023-24
    to match the 16-season core (`~/faceoffs_backfill.log`; fast).
  - 2010-2014 core (pbp/box/shifts) backfill DONE: **16 seasons (2010-11→2025-26)**, proof run.

## PHASE 1 INGESTION — COMPLETE & VERIFIED (all surfaces, all backfills landed)
Final state (verified):
- Core pbp/box/shifts: **16 seasons** 2010-11→2025-26.
- Edge: **5 seasons** 2021-22→2025-26; marts rebuilt — mart_edge_player_profile 4,737 rows
  (zone pcts sum to 1.0 every season; null TOI only 0/0/0/7/15), mart_edge_team_profile 160.
- Faceoffs: **16 seasons** (14,231 player-seasons).
- ppt-replay: **3 seasons** 2023-24→2025-26, **25,946 goal sprites**. dbt PASS=6;
  frame-count integrity 25,946/25,946; release-frame puck avg |x_std| = **89.0** (goal line),
  99.9% of puck-tracked goals at the net; ~6.6% goals have an untracked puck (null, handled).
- DB size: **20.58 GB** (raw 14.1 / staging 6.0 / mart 0.4). raw_ppt_replay 6.52 GB is the
  biggest table. ~$0.21/mo over the 10 GB free tier.

## PHASE 2 — core metric layer (IN PROGRESS)
- **2.1 Sequence mining (COMPLETE, committed 38aa7db).** `int_shot_sequence` (1.8M rows):
  one row per unblocked attempt, seq_type precedence label + seq_cross_ice royal-road flag,
  strength + is_empty_net from situation_code (zone_code orientation verified empirically:
  relative to event owner). Windows TUNED (`models_ml/tune_sequence_thresholds.py`):
  rush=4, forecheck=5, rebound=3 (kept; identical lift to 2). `mart_team_identity_inputs`
  (canonical per-game 5v5 seq shares for/against), joined into `mart_team_game_stats`;
  `mart_player_game_stats` gets real rush_attempts + per-seq individual counts. Backend
  additive seq fields. Validation: rebound 18.2% / rush 9.6% goal rates vs cycle 5.7% /
  point 2.1%; shares stable YoY; dbt PASS=21.
- **2.2 In-house xG model + decomposition (COMPLETE, validated).** `models_ml/`:
  `xg_features.py` (shared pull+features), `train_xg.py` (LightGBM, 1.51M train shots,
  val 2024-25 logloss 0.2206 AUC 0.744, holdout 2025-26 AUC 0.733; calibration + per-season
  xG-vs-goals within ~3% in `docs/methodology/xg-model.md`), `xg_decompose.py` (pred_contrib
  -> 5 prob-space buckets: location/shot_type/strength/sequence/game_state summing to xg),
  `score_xg.py` -> **nhl_models.shot_xg (1,755,430 rows)**, incremental `--since`. Artifact
  `models_ml/artifacts/xg_v1.txt` + manifest. **int_xg_rates RETIRED**; int_shot_attempts/
  _all now join shot_xg (dbt source `nhl_models`); all marts rebuilt (dbt PASS=46). Backend
  shots endpoints expose xg + contribs (alias `mx` — `xg.xg` collides); frontend `XGBreakdown`
  shared component + `xgBreakdownHTML/Text` consumed by ShotMap + ShotMapKDE tooltips.
  DAG split into pre-xg dbt -> score_xg -> marts dbt. `models_ml/bq.py` helper + db-dtypes dep.
  **Empty-net shots excluded (xg null, absent from shot_xg) by design.**
- **Env note:** `pip install db-dtypes` required for `.to_dataframe()` (in models_ml/requirements.txt).
  BigQuery `.to_dataframe(create_bqstorage_client=False)` is SLOW for ~1.7M rows (~10min);
  consider enabling bqstorage if it bites.
- **2.3 Scorer-bias + score/opponent adjustments (COMPLETE, validated).**
  `int_rink_bias` (hits/give/take multipliers per arena, rolling 3-season, team-mix-controlled,
  clipped 0.5-2.0; TOR hits 1.43x, CBJ 0.68x). `int_score_state_weights` (5v5 attempt rate by
  score state -> tied/state weight; trailing 0.96, leading 1.13). `int_shot_score_adj`
  (per-game score-weighted CF/xGF). mart_team_game_stats: raw+adj hits/give/take,
  cf_pct_score_adj/xgf_pct_score_adj, cf_pct_opp_adj/xgf_pct_opp_adj (interim opp = season-
  to-date opp strength, half-weighted; Phase 3 swaps source via the to_date CTE).
  mart_player_game_stats: raw+adj hits/give/take. Backend additive fields (team+player).
  Frontend: shared `ToggleSwitch` + `useAdjustedToggle` (localStorage nhlintel.adjusted,
  default OFF) wired into GameDetail ControlDangerBars (Adjusted toggle swaps CF/xGF to
  score-adj + events to rink-adj); ADJUSTMENT_GLOSSARY in metrics.ts (scorer_bias,
  score_adjustment). docs/methodology/scorer-bias.md (+ shot-distance calibration: only Utah
  arena 67 >2ft off) + score-state-adjustment.md. Validation: SJS/CHI move down, FLA/LAK up.
  **Follow-up:** season/rolling adjusted aggregates (TeamProfile/RollingContextPanel) need
  adjusted threaded through mart_team_rolling + teams router — deferred (per-game toggle works now).
- **2.4 Win probability + leverage (CODE COMPLETE; scoring backfill running).**
  `models_ml/winprob_features.py` (state backbone = int_segment_context expanded to a time
  grid; 30-bin seconds-remaining x score-diff[-3..3] INTERACTION one-hot + strength/OT/
  goalie-pulled + pregame rating prior). `train_winprob.py` LogisticRegression(lbfgs);
  **train logloss 0.496, holdout 2025-26 0.524** (calibration strong at extremes, mid
  deciles over-predict home ~5-13pts — interim, Phase 3 refits with real ratings via
  RATING_SOURCE). `score_winprob.py` -> nhl_models.win_probability (game_id, game_date,
  elapsed_seconds, home_wp, leverage); leverage = WP(+1 home) - WP(+1 away). Incremental --since.
  - **GOTCHAS:** (a) saga solver STALLS on 4.5M rows (I/O-bound, ~2min CPU in 25min) — use
    lbfgs. (b) `.to_dataframe` download dominates; train pull SQL-samples 1-in-4 games
    (GAME_SAMPLE) -> 1.23M rows in ~2.3min. (c) int_segment_context only covers **2015-16+**
    (2010-14 segment rebuild deferred), so WP trains/scopes 2015-2025, not 2012+.
  - Backend GET /games/{id}/winprob (series + per-goal WP swings; service get_winprob +
    get_winprob_goal_swings). Frontend: GameTimelineStack lane-1 now uses the SERVER series
    (getGameWinProb), added leverage to hover; **deleted utils/winProbability.ts** (client toy).
  - DAG: score_winprob step after run_dbt_marts. docs/methodology/win-probability.md.
  - **RUNNING:** full score_winprob backfill (all segment-covered seasons -> win_probability,
    ~/score_wp.log). Validate after: leverage peaks late in 1-goal games, blowout WP saturates.
- **2.5 Goaltending GSAx (COMPLETE, validated).** `int_goalie_shots` (all unblocked shots
  faced, goalie=goalie_in_net_id incl. ~98.5% of misses, empty-net excluded, danger tier +
  strength). `mart_goalie_game_stats` (xGA over ALL unblocked = calibrated; saves/save% on-goal
  only; GSAx by danger tier + strength). `mart_goalie_season` (season + last-10 rolling GSAx +
  NHL Edge `edge_last10_save_pct` second opinion — Edge has NO HD split, named distinctly from
  our_hd_gsax). Danger tiers in dbt vars (low<0.05, med 0.05-0.15, high>=0.15).
  - **KEY FIX:** xGA must sum over ALL unblocked shots (model's training population), NOT
    on-goal only — on-goal-only undershoots (5721 vs 8083 actual goals 2024-25); all-unblocked
    = 8294 (calibrated). League GSAx ~0 recent seasons. **Known bias:** HD GSAx league-positive
    (+556) from the xG top-bin over-prediction — documented, comparative not absolute.
  - Backend: new `/goalies/{id}` + `/goalies/{id}/gamelog` routers; `/games/{id}/goalie-danger`
    repointed to mart_goalie_game_stats. Frontend: GameDetail goalie panel adds "NHL Edge"
    column (per-goalie season last-10 save% via getGoalieSeason). docs/methodology/goaltending.md
    (our save% vs Edge corr 0.72). Validation: top-5 GSAx 2024-25 = Hellebuyck/Thompson/
    Shesterkin/Vasilevskiy/Montembeault (smell test ✓). dbt PASS=7.

## PHASE 2 — CORE METRIC LAYER COMPLETE (all 5 prompts)
seq mining -> in-house xG + decomposition -> rink/score/opp adjustments -> win prob + leverage
-> GSAx. nhl_models dataset now holds shot_xg (1.76M) + win_probability (~9.4M, 2015-26).
New model jobs: train_xg/score_xg, train_winprob/score_winprob, tune_sequence_thresholds.
Methodology docs: sequence-mining, xg-model, scorer-bias, score-state-adjustment, win-probability,
goaltending. **Next: Phase 3 (team products: power ratings, identity, Streak Doctor).**

### xG external validation (spot-check vs public models, 2026-06-15)
Compared our per-game xGF to Natural Stat Trick + MoneyPuck on one random game
(2024020626, MTL @ COL 2025-01-04): ours COL 2.71 / MTL 2.28 (all sit.), NST 2.35/2.13,
MoneyPuck 2.51/2.47. **Our game total (4.99) ≈ MoneyPuck (4.98); ordering agrees; MTL in
range; COL ~0.2 hot.** There is a small, documented top-bin over-prediction (model says
~21% on high-danger shots; actual ~17%) — same root cause as the HD-GSAx positive bias.
**DECISION (user, 2026-06-15): the xG model is ACCEPTED AS-IS.** No top-end recalibration
will be added; the bias is documented and comparative metrics (GSAx, ratings) are unaffected
in ordering. Do not revisit unless the user asks.

## PHASE 3 — team products (IN PROGRESS)
- **3.1 Power ratings + deserved standings (COMPLETE, validated).**
  - `models_ml/compute_ratings.py` -> **nhl_models.team_ratings** (40,918 rows, 16 seasons,
    one row per team-game = season-to-date rating THROUGH that game). Four goals/game
    components that cleanly partition goal differential (no double-count): **play_5v5**
    (score+opp-adjusted 5v5 xGF% -> goal diff/game), **finishing** (5v5 G-xGF, shrunk),
    **goaltending** (EV GSAx, shrunk), **special_teams** (PP+PK goals above expected).
    Opponent adj done IN PYTHON (half-weighted season-to-date, from score-adj xGF% only ->
    no circular dep on the mart's own opp_adj col). Weights fit by logistic (home-win on
    pregame component diffs, 2015-24), normalised to mean 1 (ranking invariant). Shrinkage
    **k=4000** for both finishing & goaltending, tuned by next-season MSE (interior optimum;
    correlation is scale-invariant -> wrong objective, fixed). Stores total + 4 weighted
    contribs (sum exactly to total) + raw components + bootstrap-style `rating_se` +
    `trajectory_15d` + `pregame_strength_share` (the [0,1] pregame opp-adj share the mart
    consumes). **game_type filter '02'/'03' only** (mart has preseason + 2026 Olympic/4-Nations
    international teams — excluded). Top 2025-26: COL +0.86, CAR +0.55, TBL +0.42.
  - `models_ml/simulate_deserved.py` -> **nhl_models.deserved_standings** (Monte Carlo 10k,
    Poisson(score-adj 5v5 xG + special-teams xG), NHL points incl. OT loser point via
    xG-share coin flip; regular season only). Validated: COL 121 actual / 107 deserved
    (+13.8), luckiest BOS/MTL/BUF (+22-23, high PDO), unluckiest VAN -16.3. SEED=13.
  - **RATING_SOURCE swapped to `power_rating`** (config.py) AND dbt var `rating_source`
    (dbt_project.yml). winprob_features PULL_SQL branches: power prior = pregame
    `lag(total_rating)` from team_ratings. **winprob refit + full rescore**: holdout logloss
    0.524 -> **0.52332**, train 0.496 -> **0.49456** (small lift by design — prior governs
    only early game). win_probability re-scored ~8.4M rows 2015-26. mart_team_game_stats
    `xgf_pct_opp_adj` now uses opponent's pregame_strength_share (CF stays interim).
    **Bootstrap note:** mart now depends on team_ratings as a dbt SOURCE; compute_ratings
    reads only the mart's score_adj col, so no dbt cycle — it's a documented fixpoint
    (mart uses prior run's ratings; ratings recompute from fresh marts). A truly fresh
    build needs interim first OR team_ratings pre-seeded (it exists now).
  - Backend `GET /rankings/power` + `/rankings/deserved` (rankings.py router, PowerRatingRow/
    DeservedStandingRow schemas). Frontend **/rankings** page (NavBar link) + shared
    **ComponentStackBar** (diverging stacked bar + uncertainty whisker, components/common —
    Phase 4 reuses for player composites); Power table (rank/team/GP/rating/bar/±/15d-traj)
    + Deserved tab (actual/deserved/p10-p90/luck). RATINGS_GLOSSARY tooltips in metrics.ts.
    tsc clean, npm build green. docs/methodology/power-ratings.md (auto-generated by
    compute_ratings: components, weights+interpretation, win-pred accuracy, k sweep, top-10).
  - DAG: run_dbt_marts -> **compute_ratings** -> score_winprob (winprob needs ratings now);
    compute_ratings -> **simulate_deserved** -> generate_report.

- **3.2 Team identity + style map + zone-time conversion (COMPLETE, validated).**
  - `mart_team_identity` (dbt, 988 rows) — one row per (season, team_id, **window_kind** in
    {season, last25}), regular+playoff only. Metrics: seq-type shares for/against, pace
    (5v5 ev/min), shot quality (5v5 xGF/attempt), shot volume/60, rink-adj hits/60,
    penalties taken/drawn per 60 (60-min-game approx), PP point-shot share, Edge oz/dz
    time pct (**TOI-weighted skater es zone time** — team-level Edge zone endpoint 404s,
    documented proxy), **territory-to-danger conversion** (5v5 xGF per OZ minute). Every
    metric has a `*_pctile` (percent_rank within season+window). 'window' is a BQ reserved
    word -> column named `window_kind`. Edge metrics null pre-2021-22.
  - `models_ml/compute_style_map.py` -> **nhl_models.style_map** (32 teams/season, 2D PCA of
    the fingerprint, orientation pinned: +x=shot volume, +y=shot quality; PC1 22% / PC2 17%
    variance; axis-end descriptions = top-3 loadings stored per row).
  - Backend: `GET /teams/{id}/identity` (per-window metrics+percentiles+league_size) and
    `GET /teams/style-map` (registered BEFORE /{team_id} so it isn't shadowed). **Also fixed a
    pre-existing 500 in `get_team_detail`**: 2026 Olympic/international games have 0 5v5 TOI ->
    `xgf/(toi/60)` divided by zero; wrapped in SAFE_DIVIDE. (NOTE: team-detail still ranks the
    international teams into the NHL pool — separate pre-existing pollution, not fixed here.)
  - Frontend: shared **PercentileBarList** (components/common, Phase 4 player cards reuse it);
    TeamProfile **Identity tab** (window toggle, grouped fingerprint bars, conversion panel
    with plain-English diagnosis from API ranks); Teams index **StyleMapChart** (SVG scatter
    of 32 logos in ChartPanel, axis annotations, click->team). FINGERPRINT_GROUPS in metrics.ts.
    tsc + build green. docs/methodology/team-identity.md.
  - DAG: run_dbt_marts -> compute_style_map (run daily; cheap PCA vs plan's weekly).
  - Validation: NYR/FLA high o-zone-time + low conversion (volume-over-quality); CBJ/WSH
    inverse (efficient). Fingerprints coherent: COL fast/rush/no-hits, NYR heavy forecheck,
    CAR rush+forecheck.

- **3.3 Streak Doctor (COMPLETE, validated).**
  - `models_ml/streak_doctor.py` -> **nhl_models.streak_cards** (one row per
    season/team/**window_games** in {5,10,20}; 'window' is a BQ reserved word). Five
    goal-scale components: shooting_luck (GF-xGF), goaltending (team GSAx), special_teams
    (non-5v5 goals above expected), schedule (mean opp power rating × games), play_change
    (window 5v5 score-adj xGF% − season baseline -> goals). **total_deviation = SUM of the
    five -> shares sum to exactly 1.0** (validated max err 0.0). Sustainability 0-100 =
    persistence-weighted (config.STREAK_PERSISTENCE: play 0.8/sched 0.5/ST 0.3/goalie 0.2/
    shooting 0.1) avg of |component shares|. Verdict = deterministic template; driver =
    largest component ALIGNED with sign(total_deviation) (fixed: was crediting opposing
    components). run_word from total_deviation sign. Notable = |points-pace z|>=1.5 OR
    streak>=4. Regular+playoff only.
  - Backend: `GET /teams/{id}/streak?window=10` + `GET /streaks/active` (notable, |z| desc;
    new streaks.py router + shared card_from_row helper imported by teams.py). StreakCard/
    StreakComponent schemas.
  - Frontend: shared **StreakDoctorCard** (components/common; verdict + ComponentStackBar
    decomposition + sustainability gauge + depth-3 table; embeddable for Phase 6 Home).
    TeamProfile **Form tab** (TeamFormTab, window 5/10/20 toggle) + **auto-renders on
    Overview when is_notable**. tsc + build green. docs/methodology/streak-doctor.md.
  - DAG: compute_ratings -> streak_doctor -> generate_report.
  - Validation: 96 cards; OTT goaltending-dominant surge (+12.9 GSAx), DET goaltending slump
    (-11.2); WSH/STL/COL shooting-luck surges low sustainability (15-28); NYI play-change
    surge highest (50).

## PHASE 3 — TEAM PRODUCTS COMPLETE (3.1 power ratings+deserved, 3.2 identity+style map+
## conversion, 3.3 Streak Doctor). New nhl_models tables: team_ratings, deserved_standings,
## style_map, streak_cards. New endpoints: /rankings/{power,deserved}, /teams/{id}/identity,
## /teams/style-map, /teams/{id}/streak, /streaks/active. New shared FE: ComponentStackBar,
## PercentileBarList, StreakDoctorCard. RATING_SOURCE swapped to power_rating everywhere.

### International teams removed from all team marts (user request, 2026-06-15)
The data includes 2026 Olympic / 4-Nations games (game_id type codes 09/19/20) played by
NATIONAL teams (CAN/USA/SWE/FIN/CZE/... ids 60-67, 5096, 6773, 6775, 6776, 7228). These were
polluting team-level views (and caused a div-by-zero in get_team_detail via 0 5v5 TOI).
**Fix:** every team mart now filters `substr(game_id,5,2) in ('01','02','03')` (NHL pre/reg/
playoff only) at its `games`/`base` CTE — mart_team_game_stats, mart_team_rolling,
mart_team_stats_situational, mart_team_zone_time, mart_team_faceoffs. All Phase 3 jobs already
filtered to '02'/'03', so they were never affected. get_team_detail SAFE_DIVIDE guard kept as
defensive code. **STILL OUTSTANDING:** player-level marts (mart_player_*) may still attribute
Olympic games to national team_ids — clean those the same way during Phase 4 if they surface.

## PHASE 4 — player project (IN PROGRESS)
- **4.1 RAPM isolated impact (COMPLETE, validated).** `models_ml/train_rapm.py` ->
  **nhl_models.player_impact** (6,193 rows). Two-sided ridge on 5v5 stints
  (int_shift_segments x int_segment_context; target = attacking xGF/60 via int_on_ice_events
  -> shot_xg). Each skater: off + def coef; controls score-state/zone-start(shared, effect is
  symmetric)/home/B2B/season FE. CV lambda (flat under strong reg, ~8000). Game-resample
  bootstrap SDs. Separate PP(5v4)/PK model -> pp_impact/pk_impact. 3yr weighted window +
  single seasons. Validation: coefs centre 0; top off (MacKinnon/Tkachuks/Matthews/Barkov)
  + def (Pelech/Reinhart/Toews) + PP (Nugent-Hopkins/Marner) smell-test; **single-season O
  impact YoY r=0.43** (target 0.3-0.5). Low-TOI shrunk toward 0 (uncertainty = proximity to
  prior, documented). `make rapm`; weekly DAG. docs/methodology/isolated-impact.md.
- **4.2 Composite + archetypes (COMPLETE, validated).**
  - `compute_composite.py` -> **nhl_models.player_composite** (6,744 rows): goals-scale
    components (EV off/def = RAPM x TOI, PP, PK, finishing = G-ixG shrunk by k=350, penalty
    diff x 0.2, goalie GSAx) + total + total_sd (quadrature). Top-20 = league's best;
    goalies Shesterkin/Thompson/Hellebuyck. docs/methodology/composite.md.
  - `fit_archetypes.py` + `archetype_features.py` -> **nhl_models.player_archetypes** (3,299
    rows, soft memberships). Per-position GMM (F=12, D=12). Feature set includes a
    **pp_dependency** feature (z(PP-point share) - z(5v5 RAPM off)) that splits dual-threat
    stars from PP-merchants (user-requested; F7 blend resolved). **GMM is NON-reproducible
    here** (threaded BLAS, not fixed by random_state) and unstable (raw likelihood collapses a
    giant scorer bucket) -> we fix k=12, **select best-separated seed by silhouette**, run
    single-threaded, and **persist the model to models_ml/artifacts/archetypes_v1.joblib
    (FORCE-COMMITTED, gitignored dir)**. report/--write/API all LOAD that joblib. Names are in
    config.ARCHETYPE_NAMES (24, human-approved; D8 "Bottom-Pair Defensive D" replaced the
    defunct "Sheltered Puck-Mover"). docs/methodology/archetypes.md.
  - Backend: GET /players/{id} extended (composite_components + archetype mix); new
    GET /players/archetypes/{archetype} (ranked by composite). **Repaired 4 pre-existing
    stale-column breakages in get_player_detail** (primary_assists->first_assists,
    offensive_zone_starts + the whole zone/shooting-luck/relative service methods drifted to
    a per-game schema, ihdcf_per60->ihdcf) — /players/{id} was fully 500ing.
  - Frontend: PlayerProfile archetype mix line + composite ComponentStackBar (uncertainty
    whisker); Players index rank-within-archetype (position toggle + archetype select + per-row
    stack). ARCHETYPES + COMPOSITE_COMPONENTS in metrics.ts. tsc + build green.
  - DAG: run_dbt_marts -> train_rapm -> {compute_composite, write_archetypes} (weekly, Monday).
  - **Still OUTSTANDING (player-mart hygiene):** player marts may include 2026 Olympic/intl
    games (game_id type 09) attributed to national team_ids — filter to '01'/'02'/'03' like the
    team marts when convenient (low exposure: no UI path to a national-team player page).

- **4.3 Reconciliation + divergence board (COMPLETE, validated).**
  - **clutch**: dbt `int_event_leverage` (shots -> win_probability leverage; both bucketed to a
    global 10s grid since WP grid is segment-offset; 2015+ only). `compute_clutch.py` ->
    **nhl_models.player_clutch**: leverage-weighted ixG vs raw, permutation p (1000 shuffles).
    p-dist ~uniform; top = Toffoli/Eriksson Ek/Matthews.
  - **consistency**: dbt `mart_player_game_score` (game-score family, weights in dbt vars gs_*,
    blocks from pbp). `compute_consistency.py` -> **nhl_models.player_consistency** (mean/sd/IQR,
    good-game/no-show shares, consistency index = pctile of mean/sd within position).
  - **coach trust**: `compute_coach_trust.py` -> **nhl_models.player_coach_trust** (z-scored
    within position, weighted: PK share / **DZ-faceoff deployment** / protect-lead rate /
    road-home ratio; config.COACH_TRUST_WEIGHTS). DZ-faceoff recovered via owner-relative
    pbp zone_code (D=winner's d-zone, flip for loser) + int_on_ice_events on-ice skaters
    (the earlier "symmetry blocks it" reasoning was wrong — outcome symmetry ≠ deployment).
    Post-icing draws = future refinement. Top trust = Glendening/Stenlund/Jake Evans.
  - **divergence**: `compute_divergence.py` -> **nhl_models.divergence_board** (trust_z -
    composite_z within position, top/bottom 15, min 500 5v5 min). Deterministic explanations in
    **insight_engine/templates/divergence.py** (Phase 6 reuses). Trusted>value: Lindgren/
    Glendening/Goodrow; value>trust: MacKinnon/Q.Hughes/Panarin.
  - Backend: GET /players/{id}/reconciliation + GET /players/divergence-board (registered
    before /{player_id}). Frontend: PlayerProfile **Reconciliation section** (clutch panel w/
    confidence phrase, **StripPlot** consistency viz [new components/visualizations], trust);
    Players index **Divergence Board tab** (Tabs) w/ explanations. tsc+build green.
  - DAG: score_winprob -> build_event_leverage -> compute_clutch; marts -> {consistency,
    coach_trust}; {composite, coach_trust} -> divergence (weekly Monday). docs/methodology/
    reconciliation.md. **NOTE bootstrap:** int_event_leverage excluded from run_dbt_pre_xg
    (needs win_probability) and built after score_winprob.

- **4.4 Trajectories + twins (COMPLETE, validated).**
  - **Prereq ingested:** player bio (birthDate/height/weight) — was MISSING everywhere.
    `ingestion.get_player_landing` + `scripts/ingest_player_bio.py` -> raw_player_bio (3,745
    players) -> `stg_player_bio` (view). Age = years to season Oct 1.
  - **Historical archetypes**: `fit_archetypes --write` now also scores 2015-16..2020-21 via the
    locked GMM with Edge+RAPM neutralized to scaler means (reduced-feature), flagged
    edge_imputed. player_archetypes now 7,119 rows (3299 tracking + 3820 historical). **Burst-
    defined clusters collapse** pre-tracking (Elite Speed Driver 63->8, Elite Offensive D 40->2)
    — documented. (No archetypes pre-2015: segments start 2015-16.)
  - `fit_aging_curves.py` -> **nhl_models.aging_curves** (15 keys: 13 archetypes + All Forwards/
    All Defensemen fallback). Production = **points/82** (composite is tracking-era only).
    Delta method, **each delta attributed to season-t archetype** (no scramble). Peaks 23-25 (F).
  - `compute_twins.py` -> **nhl_models.player_twins** (age-aligned cosine kNN through age A,
    >=2 seasons; cross-tracking-boundary -> reduced_features tag; +twin next-3-yr pts/82).
    McDavid twins = MacKinnon/Crosby/Eichel/Backstrom/Draisaitl.
  - `compute_physical.py` -> **nhl_models.player_physical**. **Burst-decline flag VALIDATION
    FAILED**: corr(burst_change_t, prod_change_t+1) = 0.064 (p=0.01, n=1588) — negligible,
    below 0.10 bar -> **flag WITHHELD**, negative result published (blueprint-anticipated).
  - Backend GET /players/{id}/trajectory (curve band w/ position fallback + label, path, twins,
    physical). Frontend PlayerProfile **Career Trajectory section** (recharts path-over-band,
    twins list w/ pre-tracking tag, burst trend). docs/methodology/trajectories.md. DAG: weekly
    bio refresh + aging/twins/physical after archetypes/marts.

## PHASE 4 — PLAYER PROJECT COMPLETE (4.1 RAPM, 4.2 composite+archetypes, 4.3 reconciliation+
## divergence, 4.4 trajectories+twins). nhl_models: player_impact, player_composite,
## player_archetypes, player_clutch, player_consistency, player_coach_trust, divergence_board,
## aging_curves, player_twins, player_physical. New ingest: player bio. New shared FE:
## ComponentStackBar, PercentileBarList, StreakDoctorCard, StripPlot.

## PHASE 5 — signature tools (COMPLETE, validated)
- **5.1 Line-fit model (COMPLETE, validated; commit 9c03134).**
  - dbt `int_line_seasons` (16,119 rows): every forward trio ('F3') / defense pair ('D2') sharing
    >= var('line_min_5v5_minutes')=30 of 5v5 ice in a season (2015-16+), from int_shift_segments x
    int_segment_context. A segment belongs to a line when exactly those skaters are the team's
    forwards(3)/D(2). Targets: on-ice xGF% / xGF60 / xGA60 (xGF = owning team's xG over its
    segments via int_on_ice_events x shot_xg; xGA = opponent's) + for-shot seq-type mix.
    reg+playoff only. dbt PASS=6.
  - `models_ml/linefit_features.py` (shared by train + score): per-(player,season) member features
    reuse archetype_features.build(min_5v5=1) + finishing(goals-ixg) + 24-d archetype-mix vector +
    handedness + per-season TEAM (filtered to NHL game types — intl pollution) + headshot.
    aggregate_line -> mean/min/max of scalar feats + pairwise (archetype cosine, shot-loc dist,
    handedness balance, burst spread, oz-tilt mean).
  - `models_ml/train_linefit.py`: LightGBM 3 heads, GroupKFold by season, minutes-weighted.
    **Beats both FAIR baselines** at xGF% MAE 0.0471 vs mean-of-members-LEAVE-THIS-LINE-OUT 0.0527
    and team-season avg 0.0485 (R2 +0.24/+0.36/+0.22). **KEY:** the naive "mean of members' on-ice
    xGF%" baseline LEAKS the target (a high-min line dominates its members' on-ice numbers) — the
    honest baseline subtracts the line's own xgf/xga from each member first; only then does the
    model win. Artifact `models_ml/artifacts/linefit_v1.joblib` (FORCE-COMMITTED, gitignored dir).
  - Chemistry blend w_obs=min/(min+150) (config.LINEFIT_OBS_PRIOR_MINUTES). Explanations
    `insight_engine/templates/line_fit.py` (top pred_contrib per concept -> reasons + 1 risk;
    LIMITATIONS_FOOTER verbatim). `models_ml/score_line.py(player_ids, season)` handles trio/pair/
    5-unit (splits 3F+2D), cross-team "deeper extrapolation" + rookie interval widening, grade A-F.
  - Backend POST /tools/line-fit, GET /players/search (before /{id}), GET /teams/{id}/lines
    (current lines over last 10 games, each projected). DAG `train_linefit` weekly after
    [write_archetypes, train_rapm]; Makefile `linefit`. docs/methodology/lineup-lab.md (generated).
- **5.2 Lineup Lab UI + swap widget (COMPLETE; commit 766cdcb).** Shared **PlayerPicker**
  (debounced /players/search, keyboard nav, headshot+team+archetype chip), **LineProjection**
  (grade badge, xGF% confidence band, reasons/risk, observed-blend note, extrapolation/rookie
  labels, depth-3 member table, limitations footer), **LineSwapWidget** (components/common).
  /tools index + /tools/lineup-lab (lazy-loaded via React.lazy/Suspense in App.tsx). LineSwapWidget
  embedded on TeamProfile **Lines tab**. NavBar Tools link. tsc + build green.
- **5.3 Player fit + matchup previews (COMPLETE, validated; commit 956d013).**
  - `models_ml/compute_team_needs.py` -> **nhl_models.team_needs** (long format: team_id, season,
    need_type archetype|component, key, label, team_value, reference_value, gap=ref-team). Team
    archetype mix = TOI-weighted player mixes; component totals = summed composite; reference =
    avg of top-8 teams by power rating (config.TEAM_NEEDS_TOP_N). `models_ml/score_team_fit.py`:
    fit = 100*(0.5*cos(player_arch, need_arch+) + 0.5*cos(player_comp+, need_comp+)); reasons in
    `insight_engine/templates/team_fit.py`. Validated: McDavid fits NJD (51.9, needs EV offense)
    over NYR; reasons reference real gap numbers.
  - Backend POST /tools/trade-fit; frontend /tools/trade-fit (PlayerPicker + style-map team
    selector, fit score, reasons, need profile via PercentileBarList, archetype chips).
  - Matchup previews: backend GET /games/{id}/preview (FUT/PRE only; 400 for played) composes
    power ratings, starter goalie last-10 GSAx (mart_goalie_season — a MART), identity-fingerprint
    style clash (`insight_engine/templates/matchup.py`), season series (stg_game_context), notable
    streaks (streak_cards), pregame WP from the power-rating diff (config.PREVIEW_* logistic).
    Frontend **MatchupPreviewCard** (components/common) on GameDetail's unplayed-game view. DAG
    `compute_team_needs` weekly; Makefile `team-needs`.

## PHASE 5 — SIGNATURE TOOLS COMPLETE (5.1 line-fit, 5.2 Lineup Lab UI + swap widget, 5.3 trade
## fit + matchup previews). nhl_models: int_line_seasons (staging), team_needs. Artifact:
## linefit_v1.joblib. New templates: line_fit, team_fit, matchup. New endpoints: /tools/line-fit,
## /tools/trade-fit, /players/search, /teams/{id}/lines, /games/{id}/preview. New shared FE:
## PlayerPicker, LineProjection, LineSwapWidget, MatchupPreviewCard.

## Next up (fresh-context work)
1. **Phase 6** — insight engine + education + site completion (blueprint 7/8/9): 6.1 deterministic
   insight engine (registry/detectors/consistency-checker -> nhl_models.insights), 6.2 Home page +
   game insight banners, 6.3 education layer (concept cards, /learn, methodology library), 6.4
   annotated moments (RinkDiagram + real ppt tracking for goals). insight_engine/templates/ pattern
   established (divergence, line_fit, team_fit, matchup). NOTE the cold_streak_physical detector is
   GATED OFF — Phase 4.4 burst-decline validation failed.
2. **Partner-odds**: once in-season, confirm the american-odds JSON path in stg_partner_odds
   (only remaining ingestion gap; offseason-blocked). Unblocks the WP-vs-market calibration line.
3. **(Optional) rebuild int_shift_segments chain** to include 2010-15 shifts (heavy ~17min;
   tied to the incremental refactor). stg_shifts (view) already covers 16 seasons; WP/segments
   currently 2015-16+ only.

## Deferred (revisit AFTER all ingestion finishes — user-confirmed, not now)
- **Storage compaction/optimization.** DB is ~14.3 GB now (past the 10 GB free tier;
  ~$0.09/mo) and heading to ~19 GB once ppt-replay (+~3 GB) lands and the int_shift_segments
  chain is rebuilt for 16 seasons (+~1.5 GB). Biggest tables: raw_shift_charts (6.2 GB),
  int_shift_segments (4.9 GB), raw_play_by_play (0.9 GB), raw_ppt_replay (→~3 GB). Levers:
  compress verbose serialized-JSON raw tables, or drop raw layers for older seasons once
  staging/marts are built. Cost is trivial; purely a tidiness pass. Do NOT do it mid-ingestion.
4. **Incremental refactor (important):** make `int_shift_segments`/`int_segment_context`/
   `int_on_ice_events` incremental by game so the nightly run doesn't rescan 11 seasons
   (the monolithic build is ~17 min and needs the raised timeout below).

## Environment gotchas (bit us this session)
- Use the project venv or `pip install -U "google-cloud-bigquery>=3.20"` — older versions
  fail with `_blocking_poll() got an unexpected keyword argument 'retry'`. Pinned in requirements.
- dbt: always `--target dev` locally; the segmentation rebuild needs
  `timeout_seconds` raised in `dbt/profiles.yml` (set to 1800 locally; default 300 times out).
  profiles.yml is gitignored — set this in any new environment.
- Always `set -a; source .env; set +a` and export `GOOGLE_APPLICATION_CREDENTIALS` first.

## Resume commands
```bash
# env
cd /Users/codytownsend/Desktop/nhl/NIR && set -a && source .env && set +a
export GOOGLE_APPLICATION_CREDENTIALS=$PWD/secrets/nhl-intel-sa.json
# full Edge refresh for a season (when ready to populate beyond the sample)
python -m scripts.refresh_edge --season 2025-26
# explore real Edge payloads (already saved under scripts/edge_samples/)
python scripts/explore_edge.py --season 20242025
```

## Operating model (from docs/HANDOFF-*.md)
I write code + `scripts/smoke_ingest_*` per surface; long backfills/training run in the
background (I have network + BigQuery access here). Model jobs get `--dry-run/--sample/--resume`
+ a pasteable report. Archetype naming (Phase 4.2) is the one human-in-the-loop step.
No placeholders/mock data — features die or are labeled proxies when the API can't support them.

## VALUE — GAR/WAR companion model (post-Phase-5 add)
- `models_ml/compute_gar.py` -> **nhl_models.player_gar** (5,944 rows): goals-reality companion
  to RAPM (**RAPM untouched** — only read). ev_offense/pp = ACTUAL goals + weighted assists
  (0.7/0.5) above a depth-replacement rate, normalized to league goals (no triple-count);
  ev_defense/pk borrow RAPM x TOI (xG) -> "mostly actual"; penalty/faceoff minor. WAR=GAR/6.
  All constants in `config.GAR_CONFIG`. Strength from pbp situation_code ('1551'=5v5);
  replacement = team-depth pool (F>9/D>6 by 5v5 TOI). `make gar` / `make gar-validate`; DAG
  `train_rapm >> compute_gar` (Monday-gated).
- **Stability FINDING (validate_gar.py, genuine result):** folk wisdom is half-backwards —
  production sticky r=0.66, RAPM isolated rate noisier r=0.38, only finishing residual r=0.35 is
  luck-flavored. Reads are ASYMMETRIC: Impact>>Value is the better-grounded buy-low case.
  Constants in `config.GAR_STABILITY_YOY`; cited verbatim in the UI + doc (consistency rule).
- Backend: `/players/{id}` gains a `value` block (GAR/WAR + components + value/impact percentiles
  + asymmetric read via `insight_engine/templates/value_gap.py`); `/rankings/value` leaderboard.
- Frontend: shared **ImpactValuePanel** (two percentile lenses + gap + read + prominent Value
  uncertainty band + r-value footer) under SkillRadar on PlayerProfile; Rankings **Value (GAR/WAR)**
  tab. docs/methodology/value-gar.md (+ cross-link from isolated-impact.md).
- Validated: Kucherov GAR #4 / RAPM-off #11, Panarin #11 / #40 (intended value>impact gap);
  distribution right-skewed; replacement sensitivity spearman 0.998. tsc+build+pytest green;
  no dbt models added.

## VALUE PART 2 — Goalie GAR/WAR + cross-position currency + per-player Overall + Players UX
(post-VALUE add; **RAPM + skater GAR jobs/tables/artifacts untouched** — goalie work only READS
the GSAx marts; verified `git diff` touches no train_rapm/compute_gar/compute_composite).
- **Goalie GAR** `models_ml/compute_goalie_gar.py` -> **nhl_models.goalie_gar** (656 rows): goals
  SAVED above a replacement BACKUP, decomposed `hd/md/ld_saves` (EV by danger) + `pk_goaltending`
  (special) — the four partition all faced shots, sum to GAR. SAME `GOALS_PER_WIN=6` as skaters
  (asserted at import) so WAR is the cross-position unit. Same season_window convention as skater
  GAR (single 2021-22..2025-26 + 3yr `2023-24_2025-26`). Replacement = backups (games-rank>32,
  ≥150sh), GSAx/shot per tier+strength. Band = binomial save-outcome sd × 1.6 instability infl ->
  visibly WIDER than skaters. All constants `config.GOALIE_GAR_CONFIG` + `GOALIE_GAR_COMPONENTS`.
  `make goalie-gar` / `goalie-gar-validate`; DAG `run_dbt_marts >> compute_goalie_gar`.
  **validate_goalie_gar.py PASSED**: top=Hellebuyck/Shesterkin/Thompson/Swayman/Sorokin; dist
  replacement-centred; **YoY r~0.24** (low -> wide bands justified); replacement spearman .996-.999;
  cross-position #1 goalie 1.6x #1 skater WAR (same neighbourhood, not 3x).
- **Per-player Overall** `models_ml/compute_overall.py` -> **player_overall (4,482)** + **goalie_overall
  (1,025)**: within-position percentile, averaged-and-RE-percentiled. Skaters = 0.55*Production(GAR
  pctile) + 0.45*Play-Driving(RAPM composite pctile), computed with the SAME percent_rank/floor as
  `_value_block` so the components MATCH the card numbers (consistency). Goalies = goalie_radar axis
  pctiles (gsax .40/hd .30/consistency .20/workload .10). `config.OVERALL_WEIGHTS[_GOALIE]`.
  **CARD-ONLY, never a sort key** — no /rankings/overall (test asserts; only detail routers read
  the tables). `make overall`; DAG `[compute_gar,compute_composite,compute_goalie_gar,
  compute_goalie_radar] >> compute_overall`.
- **Backend**: `/rankings/value?scope=skaters|goalies|all` (all = mixed, **WAR-sorted** via pure
  `merge_value_rows_by_war`; rows carry `entity_kind`/`component_kind`). `/goalies/{id}` gains
  `value`(GoalieValue)+`overall`; `/players/{id}` value block gains `overall`. Schemas: ValueRankingRow
  extended (entity/component_kind, war_sd), +GoalieValue/OverallSummary/OverallComponent, GOALIE_GAR_LABELS.
- **Frontend**: shared **OverallSummary** (number + components ALWAYS together; renders nothing
  without components — hard rule; reuses PercentileBarList + the Impact-vs-Value read), wired into
  PlayerProfile (skater value.overall; goalie value stack + overall). **Players page rebuilt**
  (Part D): one consolidated control bar (Show All/F/D/G · Rank by WAR/RAPM/GAR concept-first w/
  unit tag · season), uniform ranked list (NO podium, rows navigate to detail), mixed All = simple
  WAR magnitude bars (entity-tinted, wider goalie bands, 'G' tag) + filtered = component bars behind
  a Colors toggle. `Tabs` gained optional `tag`+`disabled`. metrics `GOALIE_VALUE_COMPONENTS`
  (distinct save-tier palette). Removed dead podium/expansion CSS.
- Docs: value-gar.md goalie section + new **overall-rating.md**. tsc+build+pytest(5)+dbt compile green.
- **KNOWN/INTENDED:** the mixed `All` leaderboard is goalie-heavy at the top (a starter influences
  more goal outcomes than all but the best skaters) — the honest result on a shared win scale; the
  WIDE goalie bands + caption communicate the cross-position order is soft (principle 6). Replacement
  level is the documented lever if levels ever need shifting; rankings are stable to it.
  **→ SUPERSEDED by the reliability-shrinkage pass below.**

## VALUE PART 3 — goalie reliability-shrinkage + confidence-aware leaderboard
Problem fixed: goalies floated above McDavid on the mixed WAR board purely on noisy point estimates
carrying huge bands. Fixed at the ROOT (shrink) + PRESENTATION (confidence sort + prominent bands).
**RAPM + skater GAR untouched** (verified git diff touches no train_rapm/compute_gar/compute_composite).
- **Part 1** `models_ml/measure_goalie_reliability.py`: method-of-moments reliability of goalie
  GSAx/shot per danger tier -> reliability(n)=n/(n+k). Measured k: hd 277, md 1125, pk 599, **ld→∞
  (no talent signal on routine shots)**, overall 2028. YoY rate r~0.19, rises with workload.
  Stored in `config.GOALIE_GAR_CONFIG['RELIABILITY_K']`.
- **Part 2** `compute_goalie_gar.py`: per-tier empirical-Bayes shrinkage
  `shrunk_b = neutral_b + reliability(shots_b)*(raw_b - neutral_b)`, neutral_b = league
  above-replacement rate × this goalie's tier shots (keeps volume credit, regresses the rate). The
  DISPLAYED gar/war/components are now SHRUNK; `raw_gar`/`raw_war` stored for transparency. **Band
  de-inflated** (removed the old ×1.6 INSTABILITY_INFLATION — instability is now in the shrinkage, no
  double-count): band = pure binomial sampling sd (~±2.2 WAR single-season, still ~3× skaters).
  Validated: 2024-25 top goalie raw +8.0 WAR → shrunk +4.0; point order alone now top-5 = skaters,
  Hellebuyck #6; #1 goalie 0.8× #1 skater.
- **Part 3** confidence-aware sort: `/rankings/value?sort=confidence|point` (DEFAULT confidence) ranks
  by `war − k·war_sd`, `config.CONFIDENCE_SORT_K=0.5` (started 1.0, tuned down — a full sd buried
  goalies; 0.5 keeps elite goalies visible ~rank 12 while confident skaters lead). Mixed merge sorts
  by this key (test asserts confidence-default + WAR-not-GAR). `merge_value_rows_by_war`→`merge_value_rows`.
- **Part 4** prominent bands: MagnitudeBar is now an error-bar (translucent range + end caps + point
  tick) so wide goalie bands visibly overlap neighbours = tiers not exact ranks.
- **Part 5** propagated everywhere (mixed/goalie leaderboard, goalie detail value+raw readout). FE:
  getValueRankings gains `sort`; Players page Order toggle (Confidence-adjusted | Point); captions +
  methnote updated. docs/methodology/value-gar.md goalie section rewritten (reliability curve,
  shrinkage form, confidence sort, k tuning). tsc+build+pytest(6)+dbt compile green.

## PLAYER DETAIL CARD (PlayerRowExpansion) + radar/stats correctness fixes
- **Card layout** (`components/players/PlayerRowExpansion.{tsx,css}`): the inline player-detail card
  is **two-column ~46/54** — LEFT: identity + archetype chips + a condensed bordered **Overall card**
  (lead percentile + compact Production/Play-Driving bars row 1, WAR/GAR readout row 2) + season-stats
  table + "View full profile"; RIGHT: the value-vs-impact verdict then the large **SkillRadar**
  (legend + caption beneath). (Iterated full-width-stacked → 2-col per user pref.)
- **OverallSummary** gained a `variant='strip'` (condensed bordered card; HARD RULE still holds:
  number never without its component percentiles; note moved to an info tooltip).
- **Shared `PlayerAvatar`** (`components/common`) extracted — Players rows, divergence/deployment
  rows, and the card all reuse it (dropped the per-surface `pav`/`pxe-av` copies).
- **SkillRadar**: viewBox padded horizontally so long spoke labels stay IN bounds (no overflow);
  per-vertex percentile numbers moved inboard. NOTE: a later **compact-mode** refactor (small-multiple
  archetype gallery, `compact`/`shortLabels`/`arcGroups` props) supersedes the inboard numbers in
  compact mode and removed the full-mode per-vertex number text.
- **B1 radar spoke bug FIXED** (`compute_player_radar.py`): `rush_offense` + `cycle_forecheck` spokes
  were a SHARE of the player's own attempts (penalised high-volume creators — McDavid rush 26th).
  Now a per-60 RATE (consistent with shot_volume/playmaking). Re-verified: McDavid rush 26→82, cycle
  29→92; MacKinnon 95/98; Matthews 89/93. **player_radar rewritten** (display table; no model
  retrain). McDavid's "North-South Forward" archetype for 2025-26 is a hard-1.00 season-sensitive v2
  assignment (Elite Offensive Driver 2021-25) — NOT a bug; the archetype uses share-of-mix (style),
  distinct from the volume spoke.
- **B2 stat-rank display**: the season-stats column is a within-position RANK (G 4th, A 1st); xGF%
  "150th" is a CORRECT raw rank (McDavid 150 / 479 forwards in on-ice 5v5 xGF%, value verified) — not
  a percentile bug. Now rendered "**rank / pool**" (e.g. 150 / 479) so it never reads as a broken
  0-100 percentile. Display-only (source was correct).
- **Players "Usage & Value" tab**: the situation filter (All/5v5/PP/PK/Key moments) moved INTO the
  consolidated toolbar card to match the Player-Rankings tab. `DeploymentBoard` now takes `situation`
  as a controlled prop; `DEPLOYMENT_SITUATIONS` exported as the single source.

## VALUE PART 4 — Player Fit rebuilt as MULTI-DIMENSION fit
Old tool = single cosine(player-profile, team need-vector) with positive-gaps-only + cosine floored
at 0 → a D addressing a defensive need at a defense-STRONG team scored ~0 (position was never a term;
a surplus team's need vector was empty where the player was strong). **Rebuilt** (`score_team_fit.py`
→ structured payload; `POST /tools/trade-fit`):
- FIVE separate dimensions, none floored at 0: (1) **POSITIONAL gate** (position+handedness+role,
  bounded [0.55,1] → relevant player never zeros, MULTIPLIES the blend); (2) **NEED** (team_needs gap
  weighted by where the player provides value, sigmoid-mapped; surplus ~0.15, neutral, NEVER
  negative/red; no redundancy penalty); (3) **STYLE** (rush-vs-forecheck/cycle ORIENTATION match — a
  within-entity ratio, comparable across the player-pctile-within-pos vs team-pctile-within-league
  scale mismatch — vs mart_team_identity); (4) **LINE** (swap into the team's current top unit, project
  with score_line; carries its interval); (5) **QUALITY** (WAR pctile within position + RAPM).
- `overall = positional_gate * weighted_avg(need .28/style .24/line .20/quality .28)` → A-F bands; all
  constants `config.TRADE_FIT`. Deterministic verdict naming drivers + the "can't see injury/cap/
  roster" caveat. Grade ALWAYS shown WITH its 5 dimensions.
- Validated (`validate_trade_fit.py` / `make trade-fit-validate`): Slavin→strong-def VGK now **C 56**
  (was ~0); same player diverges by team (Hutson VGK B vs CHI A); style differs (McDavid CAR 93 vs CBJ
  53); below-replacement D → F (correct). No max(0,) clamp; headline never F for a relevant contributor.
- Backend additive: `FitDimension` + restructured `TradeFitResult` (overall_grade/score, verdict,
  dimensions[]); `BestTeamFit` gains `grade`; `best_team_fits` is a lightweight no-line variant.
- FE `TradeFit.tsx`: headline card (grade + verdict) + 5 decomposed dimension rows (label · level bar
  + tangible-driver note · value); colour discipline (low-need amber, mismatch orange, never red);
  model-estimate softness band on line/quality. docs/methodology/player-fit.md. **No retrain** of
  RAPM/GAR/composite/archetype. tsc+build+pytest(6)+dbt compile green.
- **Gotcha this session:** the harness temp fs (`/private/tmp/claude-501/.../tasks`) kept hitting
  ENOSPC, swallowing Bash stdout — route long output to a repo file and Read it. Also a parallel
  agent's `SkillRadar.tsx` compact-mode work left an unused-var that blocked the build; removed it in
  the working tree (left unstaged for that change's owner).

## PLAYER FIT REBUILD (v3 — supersedes VALUE PART 4 above; quality FLOORS fit, never caps)
Re-architected from first principles: quality was still acting as a *ceiling* (a quality-weighted
blend). Now **quality FLOORS fit, never caps it**, and **need is the core** (it absorbs position).
- **Composition** (`models_ml/score_team_fit.py`): `match = weighted(need .55 / style .20 / line .25)`;
  `floor = FLOOR_CAP(0.55) * overall_quality_pctile`; `fit = floor + (1-floor)*match`. So match drives
  the upside UNCAPPED (a need-serving specialist can grade high) and talent only raises the floor (a
  star is never a poor fit). **Quality is a SEPARATE axis** in the payload, never folded into match.
  The positional gate and the quality-weighted dimension are GONE.
- **Need by component-and-role vs OWN depth** (`models_ml/compute_team_needs.py` → `team_needs`
  **team_needs_v2**, 480 rows): role (C/W/D/G) × component (EV off/def, PP, PK, finishing; goaltending
  for G). `team_strength = Σ composite component over the team's players at that role`;
  `need = 1 - league_pctile`. Replaces the top-8 benchmark. `opp_c = team_need_c × player_strength_c`
  (within-role pctile); `need_score = 0.7·max(opp) + 0.3·mean(opp)` (specialist + breadth). Handedness
  is a small modifier inside need. **Finishing is EXCLUDED for D** (tiny shrunk sample → noise that
  spiked lucky-goal depth-D need). Position is absorbed — a center scores vs the team's center depth.
- **Line = complementarity** (talent-independent): sum of the line model's PAIRWISE pred_contribs
  (arch overlap, shot-loc variety, handedness, pace spread, tilt) via sigmoid, NOT the absolute xGF.
- **Goalies**: need-only (goaltending depth × goalie quality) + the same floor; no style/line.
- **Surface**: `TradeFitResult` now carries `quality` (FitQualityAxis), `dimensions` (need w/
  `breakdown`, style, line), `need_breakdown`, `role` — kept `overall_grade/score/verdict` for the
  trade engine. FE `TradeFit.tsx`: TWO axes (Fit grade+score | Quality pctile/label) side by side,
  then the decomposition with the need component-by-role breakdown bars. docs/methodology/player-fit.md
  rewritten.
- **Validated** (`make trade-fit-validate`, 2025-26, ALL FOUR hold): specialist Mikheyev (depth, 44th)
  → A 80.2 at PK-needy WSH; McDavid varies A 89.8 (MTL) → B 75.3 (CAR), floor never breached (min 74.5
  ≥ B); Chiarot (below-replacement) → F 38.6 even at his best team; goalie Swayman → A 95.2 at
  goalie-needy VGK. Trade engine re-validated (`make trade-engine-validate`) — fit overlay reads sane,
  shape unchanged. pytest 15 / tsc / dbt compile green. **No retrain** of RAPM/GAR/composite/archetype.
- **Ops**: `team_needs` schema changed → re-export to the serving file after recompute
  (`python -m scripts.export_to_duckdb --only team_needs`; needs the backend stopped to unlock duckdb).
  Validation runs FAST in `SERVING_BACKEND=duckdb` (line_member_features precomputed); compute mode is
  slow (live feature build). DuckDB gotcha: `position` is reserved — never use it as an output alias.

## PLAYER FIT — projected talent + UI/narrative fixes (follow-up pass)
The quality FLOOR (and the displayed quality) now uses a forward PROJECTION, not last season — so a
contract-year/one-off spike no longer inflates fit. `score_team_fit._skater_projection /
_goalie_projection` (cached): recency-weight last ~3 GAR seasons (1.0/0.6/0.3, also by games) ->
regress toward 0 by sample+volatility (`REGRESS_GAMES_K=22`) -> age forward one season on the
archetype curve (flat for goalies) -> percentile within position. Constants
`config.PLAYER_FIT_PROJECTION`. Reads only serving tables (player_gar/goalie_gar/stg_player_bio/
player_archetypes/aging_curves) — **no new table, no serving re-export needed** this pass. Quality axis
gains `last_war`; the note says "Projects to Nth … last season Y" on a spike, and the band widens.
- Validated: older spikes regress more than young (mean proj/last 0.71 vs 0.80); the 4 fit behaviors
  still hold (McDavid A→B, specialist A, Chiarot F, Swayman A); trade-engine fit overlay sane; pytest 15.
- **UI/narrative fixes (same pass):** central ordinal fixed (`92th`→`92nd`) — `models_ml/textfmt.ordinal`
  (backend prose) + `frontend/src/utils/format.ordinal` (SkillRadar, TeamRadar, PlayerProfile, TradeFit,
  matchup fingerprint). Need-breakdown labels show FULL component names (was CSS-truncated to an
  ambiguous "Even-stren…"). Need caption anchors on the INTERSECTION (max need×strength), not biggest-
  need + biggest-strength glued together; honest "doesn't address their hole" when no overlap. Verdict
  is now player-specific only; the fit-vs-quality + "can't see" caveat lives ONCE in the UI footnote.
