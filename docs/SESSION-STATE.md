# Session state — finalization plan progress

Working branch: **`finalization`**.
Last updated at the end of **Phase 3 (team products)** — power ratings, deserved standings,
team identity + style map, Streak Doctor all shipped, validated, and committed (commits
76f0c39, e845cb4, 54f1a07). Phases 0, 1, 2 complete before that. **Next: Phase 4 (player
project).** Read the "PHASE 3" and "Next up" sections below first, then
`nhl-intel-finalization-plan.md` for the Phase 4 prompts.

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

## Next up (fresh-context work)
1. **Phase 4.4** — career trajectories + twins (age curves per archetype, nearest-neighbor
   comparables, physical-aging overlay w/ burst-rate validation). Then Phase 5 (tools:
   Lineup Lab, trade fit, matchup previews). (4.1, 4.2, 4.3 DONE — see above.)
   ComponentStackBar + PercentileBarList + StreakDoctorCard + StripPlot built for reuse.
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
