# FEATURE_MAP — every feature traced to its source feed

One trace per user-facing feature, from the frontend component down through endpoint,
query, mart or serving table or model table, dbt intermediates, staging, and raw, to the
NHL source feed. This is the anchor for the cleanup list: anything not appearing in a trace
here (and not in the protected puck-tracking section) is a reachability question for
CLEANUP_CANDIDATES.md.

## Hard rules

1. Data and ingested objects are never listed for deletion anywhere in this pass.
2. Puck tracking is retained by owner decision; it has its own "built, not yet surfaced"
   section below and is Tier 3 (keep).

Notation: `page -> api method -> GET/POST route -> query -> tables`. Serving note: in the
default config the backend reads these tables from the DuckDB serving file, a nightly copy
of the listed marts/model tables (see DEPENDENCY_GRAPH.md).

---

## Surface S1 — the React frontend (21 routes, 18 pages)

### Games explorer (`/`) and Game detail (`/games/:gameId`)

| feature (component) | api -> route | tables | producers back to feed |
|---|---|---|---|
| Games list / date strip (`GamesExplorer`, `GameCard`, `GameOfTheNight`) | `getGameDates`,`getGamesByDate` -> `/games/dates`,`/games/` | `stg_games`, `mart_team_game_stats` | `stg_games` <- `raw_games`/`raw_boxscores`; mart <- `int_shot_attempts` <- `stg_play_by_play` <- `raw_play_by_play`, plus `nhl_models.team_ratings` |
| xG timeline (worm + pressure + winprob) (`GameTimelineStack`) | `getGameXGWorm`,`getGamePressure`,`getGameWinProb`,`getGameGoals` -> `/games/{id}/xgworm`,`/pressure`,`/winprob`,`/goals` | `int_shot_attempts_all`, `nhl_models.win_probability`, `stg_play_by_play`, `stg_boxscores` | shot attempts <- `stg_play_by_play` + `nhl_models.shot_xg`; win prob <- `score_winprob.py` <- `stg_boxscores`+`team_ratings`; all <- `raw_play_by_play` |
| Shot heatmap (`ShotMapKDE`) | `getGameShots` -> `/games/{id}/shots` | `int_shot_types` + `nhl_models.shot_xg` | `int_shot_types` <- `int_shot_attempts` <- `stg_play_by_play`; `shot_xg` <- `score_xg.py` |
| Skater impact box (`GameDetail` tables) | `getGameSkaterImpact` -> `/games/{id}/skater-impact` | serving `serving_game_skater_box` + `int_shot_attempts_all` | `serving_game_skater_box` <- `precompute_serving.py` <- `raw_boxscores` |
| Goaltending / danger / shot quality / special teams / team stats / context | `getGameGoaltending`,`getGameGoalieDanger`,`getGameShotQuality`,`getGameSpecialTeams`,`getGameTeamStats`,`getGameContext` -> corresponding `/games/{id}/*` | `int_shot_attempts_all`, `mart_goalie_game_stats`, `stg_play_by_play`, `stg_boxscores`, `stg_rosters`, `stg_game_context`, `stg_standings` | marts/int <- `stg_play_by_play`/`stg_boxscores` + `shot_xg`; context <- `raw_game_landing`/`raw_game_right_rail` |
| Matchup preview | `getGamePreview` -> `/games/{id}/preview` (`services.tools.matchup_preview`, `insight_engine.templates.matchup`) | tools union (`mart_team_*`, `nhl_models.team_ratings`, `player_archetypes`) | team ratings <- `compute_ratings.py`; archetypes <- `fit_archetypes_v2.py` |

### Player profile (`/players`, `/players/:playerId`)

| feature (component) | api -> route | tables | producers |
|---|---|---|---|
| Player index / leaders (`Players`) | `getOverallLeaders`,`getValueRankings` -> `/players/leaders`,`/rankings/value` | `nhl_models.player_gar`,`goalie_gar`,`player_archetypes` | `compute_gar.py`/`compute_goalie_gar.py`; archetypes v2 |
| Skill radar (`SkillRadar`) | `getPlayerRadar` -> `/players/{id}/radar` (`services.radar`) | `nhl_models.player_radar` | `compute_player_radar.py` <- `player_impact`(RAPM)+`player_composite`+edge+marts |
| Player shot map (`ShotMap`) | via `/players/{id}/shots` | `int_shot_types` / `int_shot_attempts_all` | <- `stg_play_by_play` + `shot_xg` |
| Percentile strip (`StripPlot`) + summary | `getPlayerSummary` -> `/players/{id}/summary` | `nhl_models.player_composite`,`player_archetypes` | `compute_composite.py` <- `player_impact`+marts |
| Player Verdict | `getPlayerVerdict` -> `/players/{id}/verdict` | `nhl_models.player_verdict` | `generate_verdicts.py` (Gemini + `build_verdict_payload.py`) <- `player_overall`+radar+gar+impact |
| Value neighbors / trajectory / consistency / reconciliation | `getPlayerValueNeighbors`,`getPlayerTrajectory`,`getPlayerReconciliation` -> `/players/{id}/{value-neighbors,trajectory,reconciliation}` | `nhl_models.player_gar`,`player_twins`,`aging_curves` + marts | `compute_twins.py`,`fit_aging_curves.py`,`compute_gar.py` |
| Deployment board + player deployment | `getDeploymentBoard`,`getPlayerDeployment` -> `/players/deployment-board`,`/players/{id}/deployment` | `nhl_models.deployment_efficiency`,`player_archetypes` | `compute_deployment_efficiency.py` <- `player_composite`+`player_impact`+`win_probability`+segments |
| Divergence board | `getDivergenceBoard` -> `/players/divergence-board` | `nhl_models.divergence_board` | `compute_divergence.py` <- `player_coach_trust`+`player_composite` |
| Contract | `getPlayerContract` -> `/players/{id}/contract` | `mart_player_contracts`,`nhl_models.player_contract_value` | `compute_contract_value.py`; mart <- `stg_contracts`+`contract_player_map`(`scripts/match_contracts.py`) |
| Detail hub, trends, gamelog, situational, shot quality, vs-opponent | `/players/{id}` and sub-routes | `mart_player_game_stats`, `mart_player_game_score`, `mart_player_situational`, `nhl_models.player_situation_toi`, many `nhl_models.*` | `mart_player_game_stats` <- `int_shot_attempts_all`+`int_assists`+`int_shot_sequence`+`int_player_onice_game`+`stg_*` |

The RAPM/isolated-impact model (`nhl_models.player_impact`, `train_rapm.py`) is not a
standalone endpoint; it feeds the radar, composite, GAR, deployment, and verdict features
above. Its lineage: `int_on_ice_events` + `int_segment_context` + `int_shift_segments` +
`nhl_models.shot_xg` <- `stg_shifts`/`stg_play_by_play` <- `raw_shift_charts`/`raw_play_by_play`.

### Team profile (`/teams`, `/teams/:teamId`)

| feature | api -> route | tables | producers |
|---|---|---|---|
| Standings / index (`Teams`) | `getStandings` -> `/teams/standings` | `stg_standings`,`mart_team_game_stats` | <- `raw_standings`; mart <- shot attempts + `team_ratings` |
| Identity + style map (`TeamIdentityTab`,`StyleMapChart`) | `getTeamIdentity`,`getStyleMap` -> `/teams/{id}/identity`,`/teams/style-map` | `mart_team_identity`,`nhl_models.style_map` | `mart_team_identity` <- marts+`shot_xg`+edge; `compute_style_map.py` |
| Lines (`LineBoard`) | `getTeamLines` -> `/teams/{id}/lines` (`services.tools.current_lines`) | serving `team_current_lines`,`team_handedness` + tools union | `precompute_serving.py` <- `int_shift_segments`+`int_segment_context` |
| Form / trends / rolling (`TeamFormTab`,`RollingContextPanel`) | `getTeamTrends` -> `/teams/{id}/trends` | `mart_team_rolling`,`mart_team_game_stats` | rolling <- `mart_team_game_stats` |
| Deployment | `getTeamDeployment` -> `/teams/{id}/deployment` | `mart_player_zone_deployment`,`mart_player_relative` | <- `mart_team_zone_time`+`int_zone_entry_proxy`; relative <- `mart_player_game_stats`+`int_player_onice_game` |
| Streak card (`StreakDoctorCard`) | `getTeamStreak` -> `/teams/{id}/streak` | `nhl_models.streak_cards`,`mart_team_game_stats` | `streak_doctor.py` |
| Team radar / insights / vs-opponent / offseason | corresponding routes | `mart_team_*`, `nhl_models.roster_forecast`/`roster_moves` (offseason) | `project_roster_forecast.py` |

### Rankings (`/rankings`) and Playoffs (`/playoffs`)

| feature | api -> route | tables | producers |
|---|---|---|---|
| Power ratings | `getPowerRankings` -> `/rankings/power` | `nhl_models.team_ratings`,`mart_team_game_stats` | `compute_ratings.py` |
| Deserved standings | `getDeservedStandings` -> `/rankings/deserved` | `nhl_models.deserved_standings` | `simulate_deserved.py` (Monte Carlo) |
| Value rankings | `getValueRankings` -> `/rankings/value` | `nhl_models.player_gar`,`goalie_gar` | GAR jobs |
| Playoff bracket (`Playoffs`) | `getPlayoffBracket` -> `/playoffs/bracket` | `nhl_models.team_ratings`,`mart_team_game_stats`,`mart_team_identity`,`stg_standings` | ratings + marts |

### Tools (`/tools/*`)

| tool (page) | api -> route | tables / services | producers |
|---|---|---|---|
| Lineup Lab (`LineupLab`) | `lineFit`,`lineFitSuggestions` -> `/tools/line-fit*` (`services.tools.score_line` -> `models_ml/score_line.py`) | serving `line_member_features`,`int_line_seasons`, linefit artifact | `train_linefit.py` (`linefit_v1.joblib`) <- `int_line_seasons` <- on-ice backbone |
| Trade Fit (`TradeFit`) | `tradeFit`,`bestTeamFits` -> `/tools/trade-fit*` (`services.tools` -> `score_team_fit.py`) | `nhl_models.team_needs`,`player_composite/gar/archetypes/...` | `compute_team_needs.py`,`score_team_fit.py` |
| Trade Builder (`TradeBuilder`, `components/trade/*`) | `evaluateTrade` -> `/tools/trade-evaluate` (`services.trade_engine`) | `mart_player_contracts`,`mart_tradeable_assets`,`mart_team_game_stats` | `compute_contract_value.py`,`compute_futures_value.py` -> `mart_tradeable_assets` |
| Contract Grader (`ContractGrader`) | `gradeContract` -> `/tools/contract-grade` (`services.contract_grade`) | `mart_player_contracts`,`nhl_models.aging_curves/player_archetypes/player_situation_toi` | contract/aging/archetype jobs |
| Roster Builder (`RosterBuilder`) | `rosterEvaluate`,`rosterSuggest` -> `/tools/roster-{evaluate,suggest}` | tools union + `roster_player_projection` | `project_roster_player.py`,`score_team_fit.py` |
| Draft Value (`DraftValue`) | `getPickValueCurve`,`getDraftTheorySummary`,`getDraftBoard`,`getPlayerDraft` -> `/draft/*` | `nhl_models.pick_value_curve`,`draft_value_player`,`draft_value_summary`,`int_draft_player_value` | `fit_pick_value.py`,`run_draft_theory.py` (hand-run) <- `int_draft_player_value` <- `stg_draft_results`+`player_pwar` |
| Offseason forecast (`Offseason`, `forecast/*`) | `getOffseasonBoard`,`getTeamOffseason` -> `/tools/offseason`,`/teams/{id}/offseason` | `nhl_models.roster_forecast`,`roster_moves` | `project_roster_forecast.py` (daily + intraday DAG) |
| Trade Outcomes / Traders (`TradeOutcomes`, `components/trades/*`) | `getTradeBoard`,`getValueMap`,`getDossier`,... -> `/trades/*`,`/traders/*` (`services.trade_board`) | `nhl_models.trade_outcomes`,`player_pwar`,`stg_gm_tenures`,`mart_team_game_stats` | `compute_trade_outcomes.py` <- `stg_trades`(`raw_trades`)+`player_pwar`+`pick_value_curve` |

### Learn (`/learn/archetypes`)

`ArchetypeExplorer` (page) -> `getArchetypes` -> `/archetypes` -> `nhl_models.archetype_gallery`
+ `mart_team_game_stats` + `stg_rosters`. Producer: `compute_archetype_explainer.py` (reads
`archetypes_v2.joblib` via `archetype_features_v2.py`).

### Global (`NavBar`, `PlayerPicker`)

Player quick-search -> `searchPlayers` -> `/players/search` (`services.tools.search_players`)
-> serving `dim_current_roster` + `stg_rosters`. Producer: `precompute_serving.py`.

---

## Surface S2/S3 — the daily HTML report

`nhl_daily.generate_report` -> `reporting/query.get_daily_report_data` reads the single mart
`mart_daily_report_feed` -> `reporting/llm_summary` (Gemini `gemini-2.0-flash-exp`, fallback
deterministic) -> `reporting/render` (Jinja `reporting/templates/report.html`) ->
`output/report_YYYY-MM-DD.html` -> `publish_report` uploads to `gs://nhl-intel-reports`.

`mart_daily_report_feed` <- `mart_team_game_stats` + `mart_team_rolling` +
`mart_player_game_stats` <- the full staging/raw stack. This is the only consumer of that
mart and the reason it reaches a shipped surface despite zero code references elsewhere.

---

## Built, not yet surfaced (retained by owner decision)

### Puck tracking (ppt-replay)

An intentionally forward-built subsystem that reconstructs on-ice puck and skater positions
from ppt-replay goal sprites. It is **not currently surfaced on the frontend** and does not
reach any shipped surface. **Retained by owner decision; Tier 3 (keep) throughout; never a
cleanup candidate.** This is an explicit exception to reverse reachability.

| element | role |
|---|---|
| `nhl.raw_ppt_replay` | ingested sprite frames (`ingestion/loaders.py`, `scripts/backfill_ppt_replay.py`) |
| `stg_ppt_tracking_frames` | typed per-frame player+puck coordinates |
| `int_goal_release_frame` | the pinned goal release/arrival frame per game/event/entity |
| `scripts/backfill_ppt_replay.py` | sprite backfill utility |
| `scripts/smoke_ingest_ppt_replay.py` | manual ingest smoke |
| `scripts/ppt_cache/` (25,946 sprite files) | the sprite data cache (data — never delete) |

Methodology: `docs/methodology/ppt-replay-tracking.md`. When a future tool surfaces this,
`int_goal_release_frame` is the single tracked moment intended for the rink render.

### WOWY / on-ice + isolated-impact context (Phase 6, LIVE to the player profile)

The with-or-without-you / on-ice / impact-context feature, now surfaced on the **PlayerProfile
Impact & Value tab** (Phase 6.6). Two components:

| component (Impact & Value tab) | api → route | tables | producers back to feed |
|---|---|---|---|
| `players/WowyPartnerPanel` | `getPlayerWowy` → `/players/{id}/wowy` | `mart_player_wowy` (+ `stg_rosters` for names) | `mart_player_wowy` ← `int_segment_5v5_results` (+ `int_shift_segments`) ← `int_on_ice_events` / `int_segment_context` / `nhl_models.shot_xg` ← `stg_shifts` / `stg_play_by_play` ← `raw_shift_charts` / `raw_play_by_play` |
| `players/ImpactContextPanel` (beside `ImpactValuePanel`) | `getPlayerSummary` → `/players/{id}/summary`.`impact_context` | `mart_player_impact_context` | ← `nhl_models.player_impact` (RAPM, `train_rapm.py`) + `mart_player_entanglement` + `mart_player_carry` + `mart_player_onice`, all ← the segment stack above |

Underpinnings: `int_segment_5v5_results` and `int_player_onice_game` are wired upstream of the
live `mart_player_game_stats` (real per-player `on_ice_xgf_pct`) and `mart_player_relative`.
Serving is the DuckDB copy (Phase 6.4, BQ↔DuckDB parity verified). The panels render only for
skaters with data (goalies and low-minute players show nothing, per "hide sections that cannot
be populated"); the impact band widens for entangled players.
