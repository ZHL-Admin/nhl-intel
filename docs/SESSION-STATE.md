# Session state — finalization plan progress

Working branch: **`finalization`** (10 commits ahead of the redesign work).
Last updated at the end of the shift-foundation + Edge-ingestion session.

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
range; COL ~0.2 hot.** Consistent with the documented top-bin over-prediction (model says
~21% on high-danger shots; actual ~17%) — same root cause as the HD-GSAx positive bias.
**OPEN DECISION (user-aware, not yet done):** optionally bolt an isotonic/Platt CALIBRATION
layer onto the xG model so top-end probabilities match reality, then rescore shot_xg (fixes
the COL-type overshoot + HD-GSAx bias). User asked to keep it noted; decide before/with Phase 3.

## Next up (fresh-context work)
1. **Phase 3** — team products: power ratings + deserved standings, identity fingerprints +
   style map, Streak Doctor, Edge zone-time conversion (blueprint section 5 + 12.1).
   Note: Phase 3.1 power ratings replace the interim WP/opponent-adjustment rating source
   (the single RATING_SOURCE constant in models_ml/config.py) — refit winprob after.
2. **(Optional, before/with Phase 3) xG top-end recalibration** — see "xG external validation" above.
3. **Partner-odds**: once in-season, confirm the american-odds JSON path in stg_partner_odds
   (only remaining ingestion gap; offseason-blocked). Unblocks the WP-vs-market calibration line.
4. **(Optional) rebuild int_shift_segments chain** to include 2010-15 shifts (heavy ~17min;
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
