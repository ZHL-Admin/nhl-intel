# Backend API Reference

Compiled from the static-analysis inventory at
`docs/system/_inventory/30_backend.md`. Source domain: `backend/` (34 files) at
`/Users/codytownsend/Desktop/nhl/NIR/backend`. Every table/route claim carries a
`file:line` citation traced by static analysis and ripgrep (no live queries were
run).

## Hard rules (governing this document)

1. **data / ingested objects are never listed for deletion.** This reference
   reports facts about code, config, and docs only. Nothing here proposes
   dropping any ingested table, dataset, or object.
2. **Puck-tracking is retained by owner decision.** Not in scope for removal.

---

## 1. Architecture

The backend is a single module-level FastAPI application. There is **no app
factory**; `app = FastAPI(...)` is defined at module scope (`main.py:23`).

### Serving backend: DuckDB by default

`backend/main.py:19` runs `os.environ.setdefault("SERVING_BACKEND", "duckdb")`
**before** the routers import. In the default (production) configuration this
governs every "which table" answer below:

- No BigQuery client is opened on the request path.
  `BigQueryService.__init__` only opens a `bigquery.Client` when `_serving_mode`
  is False (`services/bigquery.py:28-56`).
- Every route reads the **local DuckDB serving file** built by the nightly
  `make export-serving` (`services/serving.py` → `models_ml/duck.py`; comment at
  `main.py:15-19`).
- Table-name helpers return **bare names** in serving mode:
  `get_full_table_id()` returns `table_name` unchanged (`bigquery.py:112-113`)
  and `get_models_table_id()` likewise (`bigquery.py:132-133`). The SQL strings
  still literally say `mart_*`, `stg_*`, `int_*`, and `nhl_models.*` (via
  `get_models_table_id`), but at runtime those resolve to same-named tables
  copied into the DuckDB serving file.

The DuckDB serving file is a denormalized copy of **mart tables**, **`nhl_models.*`
model-layer outputs**, **selected `stg_*` / `int_*` tables**, and a small number
of **serving-only** tables (prefix `serving_`) written by
`models_ml/precompute_serving.py`. The table names in this document are the
*logical sources* those DuckDB tables mirror. The only backend-observed
serving-only table is `serving_game_skater_box` (`bigquery.py:1039`, used only in
serving mode inside `get_skater_impact`).

### Legacy live path: BigQuery

Set `SERVING_BACKEND=bigquery` to bypass DuckDB and query BigQuery live (legacy
path, `bigquery.py:33`, `49-56`). Dataset routing by prefix then applies
(`bigquery.py:114-125`): `mart_*` → `nhl_mart`, `stg_*` / `int_*` →
`nhl_staging`, `raw_*` → `nhl_raw`, else `nhl_mart`; `get_models_table_id` →
`nhl_models`.

### Caching

Cache TTL is set by the `@cache(ttl=...)` decorator, backed by
`services/cache.py` `SimpleCache` — an **in-memory TTL cache** (default 300s).
In each route table below, "none" means no cache decorator is present.

### CORS

CORS is **fully open**: `allow_origins=["*"]` (`main.py:30-36`), carrying a
`TODO` to restrict in production. **Flagged.**

### Router registration

All 13 router modules are imported (`main.py:21`) and registered with
`app.include_router(...)` (`main.py:39-51`). Zero unregistered routers were
found — every `*.py` in `backend/routers/` (other than the empty `__init__.py`)
is registered.

| Router module | Prefix | `include_router` line |
|---|---|---|
| `routers/games.py`      | `/games`      | `main.py:39` |
| `routers/teams.py`      | `/teams`      | `main.py:40` |
| `routers/players.py`    | `/players`    | `main.py:41` |
| `routers/goalies.py`    | `/goalies`    | `main.py:42` |
| `routers/rankings.py`   | `/rankings`   | `main.py:43` |
| `routers/streaks.py`    | `/streaks`    | `main.py:44` |
| `routers/tools.py`      | `/tools`      | `main.py:45` |
| `routers/archetypes.py` | `/archetypes` | `main.py:46` |
| `routers/assets.py`     | `/assets`     | `main.py:47` |
| `routers/playoffs.py`   | `/playoffs`   | `main.py:48` |
| `routers/draft.py`      | `/draft`      | `main.py:49` |
| `routers/trades.py`     | `/trades`     | `main.py:50` |
| `routers/traders.py`    | `/traders`    | `main.py:51` |

Plus two app-level health routes defined directly in `main.py`: `GET /`
(`main.py:54`) and `GET /health` (`main.py:68`).

Response models (the `response_model=` Pydantic types) all live in
`models/schemas.py` (2406 lines).

---

## 2. Endpoint reference

Source legend: `mart` = `mart_*` (nhl_mart); `stg` / `int` = nhl_staging
staging / intermediate; `raw` = nhl_raw; `models` = `nhl_models.*` model
outputs; `serving` = serving-only (`serving_*`) table. All are read from the
DuckDB serving file in default mode (Section 1).

### games — `routers/games.py`

| Method | Path | file:line | Params | Handler → query fn | Primary tables (source) | Response model | TTL |
|---|---|---|---|---|---|---|---|
| GET | `/games/dates` | 22-24 | `from_date?`,`to_date?` (date) | inline SQL | `stg_games` (stg) | `List[GameDate]` | 3600 |
| GET | `/games/` | 91-93 | `date?`,`start_date?`,`end_date?`,`team_id?`,`season?` | inline SQL | `stg_games`, `mart_team_game_stats` (stg/mart) | `List[Game]` | 300 |
| GET | `/games/{game_id}` | 177-179 | `game_id` | inline SQL | `stg_boxscores`, `stg_games`, `mart_team_game_stats`, `mart_player_game_stats` (stg/mart) | `GameDetail` | 300 |
| GET | `/games/{game_id}/players` | 388-390 | `game_id` | inline SQL | `mart_player_game_stats`, `stg_rosters`, `int_shot_types` (mart/stg/int) | `GamePlayerStats` | 300 |
| GET | `/games/{game_id}/shots` | 517-519 | `game_id`, `situation="all"` | `bq.get_game_shots` | `int_shot_types` + `nhl_models.shot_xg` (int/models) | `GameShots` | 86400 |
| GET | `/games/{game_id}/winprob` | 630-632 | `game_id` | `bq.get_winprob` + `bq.get_winprob_goal_swings` | `nhl_models.win_probability`, `stg_play_by_play` (models/stg) | `WinProbSeries` | 86400 |
| GET | `/games/{game_id}/xgworm` | 679-681 | `game_id`, `situation="all"` | `bq.get_xg_worm` | `int_shot_attempts_all`, `stg_boxscores` (int/stg) | `List[XGWormPoint]` | 86400 |
| GET | `/games/{game_id}/goals` | 757-759 | `game_id` | `bq.get_game_goals` | `stg_play_by_play`, `stg_boxscores`, `stg_rosters` (stg) | `List[GoalDetail]` | 86400 |
| GET | `/games/{game_id}/goaltending` | 810-812 | `game_id` | `bq.get_goaltending` | `stg_play_by_play`, `int_shot_attempts_all`, `stg_boxscores`, `stg_rosters` (stg/int) | `List[GoaltenderStat]` | 86400 |
| GET | `/games/{game_id}/teamstats` | 829-831 | `game_id` | `bq.get_team_comparison` | `stg_boxscores`, `stg_play_by_play` (stg) | `TeamComparisonStats` | 86400 |
| GET | `/games/{game_id}/context` | 839-841 | `game_id` | `bq.get_game_context` | `stg_game_context`, `stg_games`, `stg_standings` (stg) | `GameContext` | 86400 |
| GET | `/games/{game_id}/pressure` | 850-852 | `game_id` | `bq.get_pressure_shots` | `int_shot_attempts_all`, `stg_boxscores` (int/stg) | `List[PressurePoint]` | 86400 |
| GET | `/games/{game_id}/specialteams` | 876-878 | `game_id` | `bq.get_special_teams` | `int_shot_attempts_all`, `stg_play_by_play`, `stg_boxscores` (int/stg) | `List[SpecialTeamsStat]` | 86400 |
| GET | `/games/{game_id}/goalie-danger` | 896-898 | `game_id` | `bq.get_goalie_danger` | `mart_goalie_game_stats`, `stg_boxscores`, `stg_rosters` (mart/stg) | `List[GoalieDangerStat]` | 86400 |
| GET | `/games/{game_id}/shot-quality` | 918-920 | `game_id` | `bq.get_shot_quality` | `int_shot_attempts_all`, `stg_boxscores` (int/stg) | `List[ShotQualityRow]` | 86400 |
| GET | `/games/{game_id}/skater-impact` | 946-948 | `game_id` | `bq.get_skater_impact` | serving: `serving_game_skater_box` + `int_shot_attempts_all`; BQ path: `raw_boxscores` + `int_shot_attempts_all` (serving/raw/int) | `List[SkaterImpact]` | 86400 |
| GET | `/games/{game_id}/preview` | 971-973 | `game_id` | `services.tools.matchup_preview` | see tools union (mart/stg/int/models) | `MatchupPreview` | 900 |

### teams — `routers/teams.py`

Router-level table union (both quote styles, `get_full_table_id` /
`get_models_table_id`): `mart_player_game_stats`, `mart_player_relative`,
`mart_player_zone_deployment`, `mart_team_game_stats`, `mart_team_identity`,
`mart_team_rolling`, `stg_boxscores`, `stg_rosters`, `stg_standings`,
`int_shot_share*`, `nhl_models.dim_current_roster`,
`nhl_models.player_situation_toi`, `nhl_models.streak_cards`,
`nhl_models.style_map`.

| Method | Path | file:line | Params | Handler → query fn | Primary tables (source) | Response model | TTL |
|---|---|---|---|---|---|---|---|
| GET | `/teams/style-map` | 42-44 | `season?` | inline SQL | `nhl_models.style_map`, `mart_team_identity` (models/mart) | `StyleMap` | 3600 |
| GET | `/teams/{team_id}/streak` | 76-78 | `team_id`, `season?`, `window=10` | inline SQL | `nhl_models.streak_cards`, `mart_team_game_stats` (models/mart) | `StreakCard` | 1800 |
| GET | `/teams/{team_id}/identity` | 96-98 | `team_id`, `season?` | inline SQL | `mart_team_identity` (mart) | `TeamIdentity` | 3600 |
| GET | `/teams/{team_id}/lines` | 129-131 | `team_id`, `season?` | `services.tools.current_lines` (`teams.py:140`) | see tools union | `TeamLines` | 1800 |
| GET | `/teams/standings` | 155-157 | `season?` | inline SQL | `stg_standings`, `mart_team_game_stats` (stg/mart) | `List[StandingsRow]` | 600 |
| GET | `/teams/{team_id}` | 217-219 | `team_id`, `season?` | inline SQL | `mart_team_game_stats`, `mart_team_identity`, `mart_team_rolling`, `stg_boxscores` (mart/stg) | `TeamDetail` | 600 |
| GET | `/teams/{team_id}/insights` | 398-400 | `team_id`, `season?` | inline SQL | `mart_team_game_stats`, `mart_team_rolling` (mart) | `List[TeamInsight]` | 600 |
| GET | `/teams/{team_id}/edge` | 440-442 | `team_id`, `season?`, `game_type=2` | `bq.get_team_edge` | `mart_edge_team_profile` (mart) | `EdgeTeamProfile` | 86400 |
| GET | `/teams/{team_id}/trends` | 454-456 | `team_id`, `season?` | inline SQL | `mart_team_rolling`, `mart_team_game_stats` (mart) | `TeamTrends` | 600 |
| GET | `/teams/{team_id}/roster` | 534-536 | `team_id`, `season?` | inline SQL | `stg_rosters`, `mart_player_game_stats`, `nhl_models.dim_current_roster` (stg/mart/models) | `TeamRoster` | 600 |
| GET | `/teams/{team_id}/offseason` | 672-674 | `team_id`, `season?` | `services.offseason.offseason_team` (`teams.py:678`) | see offseason (below) | `OffseasonTeamDetail` | 3600 |
| GET | `/teams/{team_id}/vs/{opponent_id}` | 686-688 | `team_id`, `opponent_id`, `season?` | inline SQL | `mart_team_game_stats`, `stg_boxscores` (mart/stg) | `TeamVsOpponent` | 600 |
| GET | `/teams/{team_id}/deployment` | 766-768 | `team_id`, `season?` | inline SQL | `mart_player_zone_deployment`, `mart_player_relative` (mart) | `List[PlayerZoneDeployment]` | 21600 |
| GET | `/teams/{team_id}/situational` | 835-837 | `team_id`, `game_id`(req), `situation="all"` | `bq.get_team_situational` | `mart_team_stats_situational` (mart) | `List[TeamSituational]` | 21600 |

### players — `routers/players.py`

Router-level table union: `int_shot_attempts_all`, `int_shot_types`,
`mart_edge_player_profile`, `mart_goalie_season`, `mart_player_contracts`,
`mart_player_game_score`, `mart_player_game_stats`, `mart_player_situational`,
`mart_team_game_stats`, `stg_boxscores`, `stg_player_bio`, `stg_rosters`, plus
many `nhl_models.*`: `aging_curves`, `deployment_efficiency`,
`dim_current_roster`, `divergence_board`, `goalie_gar`, `player_archetypes`,
`player_clutch`, `player_coach_trust`, `player_composite`, `player_consistency`,
`player_contract_value`, `player_gar`, `player_overall`, `player_physical`,
`player_radar`, `player_twins`, `player_verdict`, `shot_xg`.

| Method | Path | file:line | Params | Handler → query fn | Response model | TTL |
|---|---|---|---|---|---|---|
| GET | `/players/deployment-board` | 364-366 | `situation="all"`, `limit=15` | inline SQL (`nhl_models.deployment_efficiency`, `player_archetypes`) | `DeploymentBoard` | 1800 |
| GET | `/players/{player_id}/deployment` | 389-391 | `player_id` | inline SQL | `List[PlayerDeploymentEntry]` | 1800 |
| GET | `/players/divergence-board` | 397-399 | `season?` | inline SQL (`nhl_models.divergence_board`) | `List[DivergenceBoardRow]` | 1800 |
| GET | `/players/search` | 446-448 | `q`(req), `limit=20`, `season?` | `services.tools.search_players` (`players.py:457`) | `List[PlayerSearchResult]` | 3600 |
| GET | `/players/{player_id}/summary` | 462-464 | `player_id`, `season?` | inline + composite helpers (`nhl_models.player_composite`, `player_archetypes`); **+ impact-context block** from `mart_player_impact_context` (`_impact_context_for`) | `PlayerSummary` (+ optional `impact_context`) | 1800 |
| GET | `/players/{player_id}/wowy` | (Phase 6.5) | `player_id`, `season?` | inline SQL over `mart_player_wowy` (+ `stg_rosters` for partner names) | `PlayerWowy` | 1800 |
| GET | `/players/{player_id}/preview` | 583-585 | `player_id`, `season?` | inline SQL | `PlayerPreview` | 1800 |
| GET | `/players/{player_id}/radar` | 593-595 | `player_id`, `season?` | `services.radar.player_radar` | `PlayerRadar` | 1800 |
| GET | `/players/{player_id}/verdict` | 656-658 | `player_id`, `season?` | inline SQL (`nhl_models.player_verdict`) | `PlayerVerdict` | 1800 |
| GET | `/players/{player_id}/value-neighbors` | 687-689 | `player_id`, `season?` | inline SQL (`nhl_models.player_gar`, `player_twins`) | `ValueNeighborhood` | 1800 |
| GET | `/players/{player_id}/trajectory` | 702-704 | `player_id` | inline SQL (`nhl_models.aging_curves`, `player_gar`) | `PlayerTrajectory` | 1800 |
| GET | `/players/{player_id}/reconciliation` | 768-770 | `player_id`, `season?` | inline SQL | `PlayerReconciliation` | 1800 |
| GET | `/players/leaders` | 822-824 | `position="ALL"`, `season?`, `limit=50` | inline SQL (`nhl_models.player_gar`, `goalie_gar`, `player_archetypes`) | `List[ArchetypeRankRow]` | 1800 |
| GET | `/players/{player_id}` | 951-953 | `player_id`, `season?` | inline SQL (`mart_player_game_stats`, `mart_edge_player_profile`, many `nhl_models.*`) | `PlayerDetail` | 600 |
| GET | `/players/archetypes/{archetype}` | 1111-1113 | `archetype`, `season?`, `limit=50` | inline SQL (`nhl_models.player_archetypes`) | `List[ArchetypeRankRow]` | 1800 |
| GET | `/players/{player_id}/edge` | 1164-1166 | `player_id`, `season?`, `game_type=2` | `bq.get_player_edge` (`mart_edge_player_profile`) | `EdgePlayerProfile` | 86400 |
| GET | `/players/{player_id}/trends` | 1179-1181 | `player_id`, `season?` | inline SQL (`mart_player_game_stats`) | `PlayerTrends` | 600 |
| GET | `/players/{player_id}/shot-quality` | 1267-1269 | `player_id`, `season?` | inline SQL (`int_shot_attempts_all` / `shot_xg`) | `PlayerShotQuality` | 1800 |
| GET | `/players/{player_id}/gamelog` | 1337-1339 | `player_id`, `season?`, `limit=20` | inline SQL (`mart_player_game_stats`, `mart_player_game_score`) | `PlayerGamelog` | 600 |
| GET | `/players/{player_id}/shots` | 1434-1436 | `player_id`, `season?` | inline SQL (`int_shot_types` / `int_shot_attempts_all`) | `PlayerShots` | 600 |
| GET | `/players/{player_id}/vs/{opponent_id}` | 1518-1520 | `player_id`, `opponent_id`, `season?` | inline SQL | `PlayerVsOpponent` | 600 |
| GET | `/players/{player_id}/situational` | 1593-1595 | `player_id`, `season?` | `bq.get_player_situational` (`mart_player_situational`, `nhl_models.player_situation_toi`, `mart_player_game_stats`) | `List[PlayerSituational]` | 21600 |
| GET | `/players/{player_id}/contract` | 1691-1693 | `player_id` | inline SQL (`mart_player_contracts`, `nhl_models.player_contract_value`) | `PlayerContract` | 1800 |

`players.py` also references `int_player_current_team` and `raw_ixg` in SQL
literals (seen via bare-name grep) that are not surfaced through the
`get_*_table_id` helpers; their exact per-route mapping was not individually
traced.

### goalies — `routers/goalies.py`

Table union: `mart_goalie_game_stats`, `mart_goalie_season`, `raw_war`,
`stg_player_bio`, `stg_rosters`, `nhl_models.goalie_gar`,
`nhl_models.goalie_overall`.

| Method | Path | file:line | Params | Handler → query fn | Response model | TTL |
|---|---|---|---|---|---|---|
| GET | `/goalies/{goalie_id}/preview` | 132-134 | `goalie_id`, `season?` | inline (`mart_goalie_season`, `nhl_models.goalie_gar`, `goalie_overall`) | `GoaliePreview` | 1800 |
| GET | `/goalies/{goalie_id}/radar` | 142-144 | `goalie_id`, `season?` | `services.radar.goalie_radar` (`nhl_models.goalie_radar`) | `GoalieRadar` | 1800 |
| GET | `/goalies/{goalie_id}` | 166-168 | `goalie_id`, `season?` | inline (`mart_goalie_season`, `raw_war`, `stg_player_bio`) | `GoalieSeason` | 3600 |
| GET | `/goalies/{goalie_id}/gamelog` | 190-192 | `goalie_id`, `season?`, `limit=40` | inline (`mart_goalie_game_stats`) | `List[GoalieGameLogRow]` | 600 |

### rankings — `routers/rankings.py`

Table union: `mart_team_game_stats`, `mart_tradeable_assets`, `stg_rosters`,
`nhl_models.deserved_standings`, `nhl_models.goalie_gar`,
`nhl_models.player_gar`, `nhl_models.team_ratings`.

| Method | Path | file:line | Params | Handler → query fn | Response model | TTL |
|---|---|---|---|---|---|---|
| GET | `/rankings/power` | 47-49 | `season?` | inline (`nhl_models.team_ratings`, `mart_team_game_stats`) | `List[PowerRatingRow]` | 1800 |
| GET | `/rankings/deserved` | 78-80 | `season?` | inline (`nhl_models.deserved_standings`) | `List[DeservedStandingRow]` | 1800 |
| GET | `/rankings/value` | 186-188 | `scope="skaters"`, `position="ALL"`, `season?`, `sort="confidence"`, `limit=50` | inline (`nhl_models.player_gar`, `goalie_gar`) | `List[ValueRankingRow]` | 1800 |
| GET | `/rankings/surplus` | 268-270 | `order="surplus"`, `limit=25` | inline `_assets_board` (`mart_tradeable_assets`) + `services.contract_grade.grade_from_surplus` | `List[TradeableAsset]` | 1800 |
| GET | `/rankings/talent` | 286-288 | `type?`, `limit=25` | inline `_assets_board` (`mart_tradeable_assets`) | `List[TradeableAsset]` | 1800 |

### streaks — `routers/streaks.py`

| Method | Path | file:line | Params | Handler → query fn | Response model | TTL |
|---|---|---|---|---|---|---|
| GET | `/streaks/active` | 37-39 | `season?`, `window=DEFAULT_WINDOW` | inline (`nhl_models.streak_cards`, `mart_team_game_stats`) | `List[StreakCard]` | 1800 |

### tools — `routers/tools.py`

Delegates to `services.tools`, `services.trade_engine`,
`services.contract_grade`, `services.offseason`. `services/tools.py` table
union: `int_player_current_team`, `int_segment_context`, `int_shift_segments`,
`mart_goalie_season`, `mart_team_game_stats`, `mart_team_identity`,
`stg_boxscores`, `stg_game_context`, `stg_games`, `stg_player_bio`,
`stg_roster_current`, `stg_rosters`, and `nhl_models.player_archetypes`,
`nhl_models.player_composite`, `nhl_models.streak_cards`,
`nhl_models.team_ratings`.

| Method | Path | file:line | Params/body | Handler → query fn | Tables (source) | Response model | TTL |
|---|---|---|---|---|---|---|---|
| POST | `/tools/trade-evaluate` | 25-26 | body `TradeEvaluateRequest` | `trade_engine.evaluate` | `mart_player_contracts`, `mart_team_game_stats`, `mart_tradeable_assets` (mart) | `TradeEvaluateResponse` | none |
| POST | `/tools/contract-grade` | 39-41 | body `ContractGradeRequest` | `contract_grade.grade_contract` | `mart_player_contracts`, `stg_player_bio`, `nhl_models.player_situation_toi`, `nhl_models.aging_curves`, `nhl_models.player_archetypes` | `ContractGrade` | 3600 |
| POST | `/tools/line-fit` | 53-55 | body `LineFitRequest` | `tools.score_line` | tools union | `LineFitProjection` | 3600 |
| POST | `/tools/roster-evaluate` | 67-69 | body `RosterEvaluateRequest` | `tools.roster_evaluate` | tools union | `RosterEvaluateResponse` | 900 |
| POST | `/tools/roster-suggest` | 83-85 | body `RosterSuggestRequest` | `tools.roster_slot_suggestions` | tools union | `RosterSuggestResponse` | 900 |
| POST | `/tools/line-fit/suggestions` | 98-100 | body `LineFitRequest` | `tools.line_fit_suggestions` | tools union | `LineSuggestionsResponse` | 3600 |
| POST | `/tools/trade-fit` | 112-114 | body `TradeFitRequest` | `tools.trade_fit` | tools union | `TradeFitResult` | 3600 |
| GET | `/tools/trade-fit/best-teams` | 126-128 | `player_id`(req), `exclude_team?`, `season?` | `tools.best_team_fits` | tools union | `List[BestTeamFit]` | 3600 |
| GET | `/tools/offseason` | 142-144 | `season?` | `offseason.offseason_board` (`tools.py:147`) | `mart_team_game_stats`, `nhl_models.roster_forecast`, `nhl_models.roster_moves` + tools projections | `List[RosterForecastRow]` | 3600 |

### archetypes — `routers/archetypes.py`

| Method | Path | file:line | Params | Query fn | Tables (source) | Response model | TTL |
|---|---|---|---|---|---|---|---|
| GET | `/archetypes` | 44-46 | `pos?` | inline `_cards_sync` | `nhl_models.archetype_gallery`, `mart_team_game_stats`, `stg_rosters` | `List[ArchetypeCard]` | 3600 |
| GET | `/archetypes/style-map` | 88-90 | `pos="F"` | inline `_style_map_sync` | `nhl_models.player_style_map` | `PlayerStyleMap` | 3600 |

### assets — `routers/assets.py`

| Method | Path | file:line | Params | Query fn | Tables (source) | Response model | TTL |
|---|---|---|---|---|---|---|---|
| GET | `/assets/search` | 51-53 | `q=""`, `type?`, `org?`, `limit=25` | inline `_search_sync` | `mart_tradeable_assets` (mart) | `List[TradeableAsset]` | 600 |

### playoffs — `routers/playoffs.py`

| Method | Path | file:line | Params | Query fn | Tables (source) | Response model | TTL |
|---|---|---|---|---|---|---|---|
| GET | `/playoffs/bracket` | 98-100 | `season?` | inline `_derive_bracket` | `nhl_models.team_ratings`, `mart_team_game_stats`, `mart_team_identity`, `stg_standings` | `PlayoffBracket` | 3600 |

### draft — `routers/draft.py`

| Method | Path | file:line | Params | Query fn | Tables (source) | Response model | TTL |
|---|---|---|---|---|---|---|---|
| GET | `/draft/pick-value-curve` | 23-25 | — | inline | `nhl_models.pick_value_curve` | `List[PickValueCurveRow]` | 86400 |
| GET | `/draft/theory-summary` | 37-39 | — | inline | `nhl_models.draft_value_summary` | `List[DraftTheorySummaryRow]` | 86400 |
| GET | `/draft/board` | 54-56 | `type="steals"`, `pos?`, `limit=25` | inline | `nhl_models.draft_value_player`, `int_draft_player_value` | `List[DraftBoardRow]` | 86400 |
| GET | `/draft/player/{player_id}` | 80-82 | `player_id` | inline | `nhl_models.draft_value_player`, `int_draft_player_value` | `Optional[DraftPlayerBlock]` | 86400 |

### trades — `routers/trades.py` → `services.trade_board`

Retrospective trade-outcome endpoints. `services/trade_board.py` reads
`nhl_models.trade_outcomes`, `nhl_models.player_pwar`, `mart_team_game_stats`,
`stg_gm_tenures`.

| Method | Path | file:line | Params | Query fn | Response model | TTL |
|---|---|---|---|---|---|---|
| GET | `/trades/board` | 21-23 | `sort="lopsided"`, `archetype?`, `season_from?`, `season_to?`, `limit=40`, `offset=0` | `trade_board.board` | `List[TradeBoardItem]` | 3600 |
| GET | `/trades/thesis-summary` | 38-40 | — | `trade_board.thesis_summary` | `ThesisSummary` | 3600 |
| GET | `/trades/board/{trade_id}` | 46-48 | `trade_id` | `trade_board.get_trade` | `TradeBoardItem` | 3600 |
| GET | `/trades/archetypes` | 56-58 | `season_from?`, `season_to?` | `trade_board.archetypes` | `List[ArchetypeAgg]` | 3600 |

### traders — `routers/traders.py` → `services.trade_board`

| Method | Path | file:line | Params | Query fn | Tables (source) | Response model | TTL |
|---|---|---|---|---|---|---|---|
| GET | `/traders/value-map` | 17-19 | `kind="team"`, `season_from?`, `season_to?` | `trade_board.value_map` | `nhl_models.trade_outcomes`, `nhl_models.player_pwar`, `stg_gm_tenures`, `mart_team_game_stats` | `List[ValueMapPoint]` | 3600 |
| GET | `/traders/{kind}/{entity_id}/dossier` | 31-33 | `kind`, `entity_id` | `trade_board.dossier` | same as above | `TraderDossier` | 3600 |

### app-level (no prefix)

| Method | Path | file:line | Response |
|---|---|---|---|
| GET | `/` | `main.py:54` | health dict |
| GET | `/health` | `main.py:68` | `{"status":"healthy"}` |

**Uncertainty note.** For inline-SQL routes, the containing router's table union
(both quote styles) was traced rather than executing each route's exact SQL body
line-by-line; where a route's exact subset within that union is not individually
confirmed, it is covered by the router-union note above. Routes that call a named
`bq.get_*` service method have exact tables (traced from the fn body in
`bigquery.py`, see Section 3).

---

## 3. Service-method → table map (`bq.get_*`)

Traced from `services/bigquery.py` method bodies. All 22 `BigQueryService.get_*`
methods have a router caller (verified by ripgrep across `routers/` +
`services/`).

| Method (bigquery.py:line) | Tables read |
|---|---|
| `get_player_edge` (136) | `mart_edge_player_profile` |
| `get_team_edge` (159) | `mart_edge_team_profile` |
| `get_game_context` (173) | `stg_game_context`, `stg_games`, `stg_standings` |
| `get_game_shots` (253) | `int_shot_types`, `nhl_models.shot_xg` |
| `get_winprob` (305) | `nhl_models.win_probability` |
| `get_winprob_goal_swings` (315) | `nhl_models.win_probability`, `stg_play_by_play` |
| `get_xg_worm` (344) | `int_shot_attempts_all`, `stg_boxscores` |
| `get_goaltending` (435) | `stg_play_by_play`, `int_shot_attempts_all`, `stg_rosters`, `stg_boxscores` |
| `get_team_comparison` (488) | `stg_boxscores`, `stg_play_by_play` |
| `get_pressure_shots` (540) | `int_shot_attempts_all`, `stg_boxscores` |
| `get_game_goals` (578) | `stg_play_by_play`, `stg_boxscores`, `stg_rosters` |
| `get_team_zone_time` (642) | `mart_team_zone_time` |
| `get_team_faceoffs` (672) | `mart_team_faceoffs` |
| `get_team_situational` (709) | `mart_team_stats_situational` |
| `get_player_situational` (753) | `mart_player_situational`, `nhl_models.player_situation_toi`, `mart_player_game_stats` |
| `get_player_zone_deployment` (814) | `mart_player_zone_deployment` |
| `get_player_shooting_luck` (847) | `mart_player_shooting_luck` |
| `get_player_relative` (879) | `mart_player_relative` |
| `get_special_teams` (909) | `int_shot_attempts_all`, `stg_play_by_play`, `stg_boxscores` |
| `get_goalie_danger` (968) | `mart_goalie_game_stats`, `stg_boxscores`, `stg_rosters` |
| `get_shot_quality` (994) | `int_shot_attempts_all`, `stg_boxscores` |
| `get_skater_impact` (1028) | serving: `serving_game_skater_box` + `int_shot_attempts_all`; BQ: `raw_boxscores` + `int_shot_attempts_all` |

`get_team_zone_time`, `get_team_faceoffs`, `get_player_zone_deployment`,
`get_player_shooting_luck`, and `get_player_relative` are defined and called by
routers, some indirectly via `/teams/{id}` or `/players/{id}` composition. None
are orphaned.

### Logical sources aggregated by dataset

**`nhl_models.*` (model-layer, from `models_ml/precompute_serving.py`):**
`shot_xg`, `win_probability`, `team_ratings`, `deserved_standings`,
`player_gar`, `goalie_gar`, `player_composite`, `player_archetypes`,
`player_overall`, `player_verdict`, `player_twins`, `player_clutch`,
`player_coach_trust`, `player_consistency`, `player_physical`, `player_radar`,
`goalie_radar`, `goalie_overall`, `player_contract_value`,
`deployment_efficiency`, `divergence_board`, `aging_curves`,
`dim_current_roster`, `player_situation_toi`, `streak_cards`, `style_map`,
`player_style_map`, `archetype_gallery`, `pick_value_curve`,
`draft_value_player`, `draft_value_summary`, `roster_forecast`, `roster_moves`,
`trade_outcomes`, `player_pwar`.

**`mart_*`:** `mart_team_game_stats`, `mart_team_identity`, `mart_team_rolling`,
`mart_team_stats_situational`, `mart_team_zone_time`, `mart_team_faceoffs`,
`mart_player_game_stats`, `mart_player_game_score`, `mart_player_situational`,
`mart_player_relative`, `mart_player_zone_deployment`,
`mart_player_shooting_luck`, `mart_player_contracts`, `mart_goalie_game_stats`,
`mart_goalie_season`, `mart_edge_player_profile`, `mart_edge_team_profile`,
`mart_tradeable_assets`.

**`stg_*` / `int_*`:** `stg_games`, `stg_boxscores`, `stg_play_by_play`,
`stg_rosters`, `stg_roster_current`, `stg_standings`, `stg_game_context`,
`stg_player_bio`, `stg_gm_tenures`, `int_shot_types`, `int_shot_attempts_all`,
`int_shot_share*`, `int_player_current_team`, `int_segment_context`,
`int_shift_segments`, `int_draft_player_value`.

**serving-only (`serving_*`):** `serving_game_skater_box` — used only in serving
mode by `get_skater_impact` (`bigquery.py:1039`); replaces the un-exported nested
`raw_boxscores` (`bigquery.py:1051`, legacy BQ path only).

**`raw_*` (legacy BQ path only, not exported to serving):** `raw_boxscores`
(`get_skater_impact` BQ branch), plus bare-name refs `raw_war` (`goalies.py`)
and `raw_ixg` (`players.py`).

---

## 4. Endpoints with no frontend caller

The following routes are **registered but no UI reference was found** (ripgrep of
`frontend/src` returned zero hits for each). These are candidate backend-only /
dead-from-UI endpoints. **Verify before any action; this is not a data
deletion** — the underlying tables remain in use elsewhere.

| Route | file:line | Notes |
|---|---|---|
| `GET /streaks/active` | `streaks.py:37` | ripgrep of `frontend/src` for `streaks/active` and `/streaks` → 0 hits. Streak data reaches the UI via `/teams/{id}/streak` and `nhl_models.streak_cards`-backed fields instead. |
| `GET /players/{player_id}/edge` | `players.py:1164` | no `/edge` literal in `frontend/src`. Edge data appears folded into `/players/{id}` detail. |
| `GET /teams/{team_id}/edge` | `teams.py:440` | no `/edge` literal in `frontend/src`. |
| `GET /goalies/{goalie_id}/gamelog` | `goalies.py:190` | no `goalies/.../gamelog` literal in `frontend/src`. |
| `GET /archetypes/style-map` | `archetypes.py:88` | frontend references `/teams/style-map` but not `/archetypes/style-map`. |

Frontend prefix hit-counts for orientation: `/players` 24, `/games` 18,
`/teams` 14, `/tools` 11, `/rankings` 7, `/archetypes` 4, `/draft` 4,
`/trades` 4, `/goalies` 3, `/traders` 2, `/assets` 1, `/playoffs` 1,
`/streaks` 0.

**No orphaned service query functions.** All 22 `bq.get_*` methods and all
public service entry points have router callers. Two internal-only helpers,
`services/tools.py:latest_roster_season` (called at `tools.py:37,111,234,336`)
and `services/tools.py:get_same_tier_candidates` (called at `tools.py:258`), have
no router caller but are invoked from within other service functions — reported
for completeness, not orphaned.

---

## 5. In-domain doc drift (DOC_RECONCILIATION flags)

Two in-domain docs are **stale relative to the registered routes** and should be
reconciled, not trusted as current. Details are not duplicated here — see
`docs/system/_inventory/30_backend.md` §5 and route table Section 2 above (or an
OpenAPI dump from the live app) as source of truth.

- **`backend/README.md`** describes the backend as "a thin API layer over
  BigQuery mart tables" (line 3) and lists ~14 endpoints. **Drift:** the default
  request path is now DuckDB-served (Section 1), and the app actually registers
  **~70 routes** across 13 routers. Entire routers (`rankings`, `streaks`,
  `tools`, `archetypes`, `assets`, `playoffs`, `draft`, `trades`, `traders`,
  `goalies`) and most `games` / `teams` / `players` sub-routes are absent. The
  endpoints it does list still exist and match — it is a correct-but-tiny subset.

- **`backend/API_EXPANSION_SUMMARY.md`** is a point-in-time "Backend Complete &
  Deployed" changelog (references Cloud Run revision
  `nhl-dashboard-api-00020-sfd`). It captures one expansion wave of 9 query
  functions; `bigquery.py` now has 22 `get_*` methods. **Drift:** a historical
  artifact predating the trades/traders/draft/tools/offseason/serving-layer work.
  Flag as superseded.

**Recommendation:** treat Section 2 of this reference (or a live OpenAPI dump) as
source of truth; mark both docs as historical/partial. Do not duplicate their
content here.

---

## Appendix: file coverage

Entrypoint `main.py`; models `models/schemas.py` (2406 lines) +
`models/__init__.py`. Routers: 13 (Section 1). Services: `bigquery.py` (facade +
22 `get_*`), `serving.py` (DuckDB adapter), `cache.py` (in-memory TTL cache),
`tools.py`, `trade_engine.py`, `trade_board.py`, `offseason.py`,
`contract_grade.py`, `radar.py`, `services/__init__.py`. Non-Python/config:
`Dockerfile`, `requirements.txt`, `.env` / `.env.example`, `.gcloudignore`,
`README.md` + `API_EXPANSION_SUMMARY.md` (Section 5),
`validate_trade_engine.py` (standalone validation script, not imported by the
app, not a route). `__pycache__` excluded.
