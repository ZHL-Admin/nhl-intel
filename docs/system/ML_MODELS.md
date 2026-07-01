# ML Models Reference (`models_ml/`)

> **Cleanup applied (branch `cleanup/safe-removals`).** `models_ml/fit_archetypes.py` (v1)
> and `artifacts/archetypes_v1.joblib` were **deleted** (`7d1d1e9`); the live archetype path
> is `fit_archetypes_v2.py` only. `measure_goalie_reliability.py` and
> `tune_sequence_thresholds.py` were **moved to `archive/models_ml/`** (`0620488`). Rows
> below describe pre-cleanup state; see CLEANUP_CANDIDATES.md for status.

A reference for the Python model layer. This document compiles evidence gathered in
`docs/system/_inventory/20_ml.md` (the ML domain inventory) and the orchestration cadence
recorded in `docs/system/_inventory/50_infra.md` (sections 1a and 5a). It is a prose-plus-tables
reference, not a fresh investigation. Every classification below traces back to a cited ripgrep hit,
import line, Makefile target, `serving_tables.yml` entry, or DAG task in those inventories.

## Hard rules (binding on this whole document)

1. **Data and ingested objects may never be recommended for deletion; only code, config, or docs
   may be flagged.** joblib model artifacts are *model files*, not ingested data, so a superseded
   artifact (for example `archetypes_v1.joblib`) *may* be a future Tier-2 cleanup candidate. This
   document records that fact but recommends no deletion of anything. Tiering decisions are deferred
   to `CLEANUP_CANDIDATES.md`.
2. **Puck tracking is retained by owner decision.** All tracking-derived feature and serving code
   is never dead regardless of how few references it has. In this layer that covers
   `archetype_features.py`, `archetype_features_v2.py`, `compute_player_radar.py`,
   `compute_physical.py`, `compute_twins.py`, `fit_aging_curves.py`, `train_linefit.py`,
   `compute_goalie_radar.py`, `compute_archetype_explainer.py`, and the `fit_archetypes*` pair (all
   carry `ppt`/`tracking` references).

---

## 1. Overview

`models_ml/` is the Python model layer. Every job in it reads from BigQuery (staging, mart, and
prior model tables), computes a model output, and writes a table into the `nhl_models` dataset with
a `model_version` column. Those `nhl_models.*` tables are then consumed two ways:

- **dbt reads 16 of them as sources** (declared in `dbt/models/raw/sources.yml`), so model outputs
  can be joined back into marts.
- **The FastAPI backend reads them through a DuckDB serving copy.** The nightly DAG exports the
  served subset into `data/serving/nhl_intel.duckdb`, and the backend queries that file on the
  request path instead of hitting BigQuery live.

The working tree holds **73** `models_ml/*.py` files (`ls models_ml/*.py | wc -l` returns `73`,
including `__init__.py`). The critical invocation rule for this layer references "75 ML scripts";
that figure could not be reconciled against the 73 on disk and is flagged as an unresolved
discrepancy in `20_ml.md`, not an error here.

### `config.py`: constants and `MODEL_VERSION` strings

`models_ml/config.py` is the single source of model-layer constants (over 900 lines). It holds:

- **Dataset and env-var names:** `GCP_PROJECT_ENV = "GCP_PROJECT_ID"` (the env var name, never the
  literal project id) at L20, and `MODELS_DATASET = "nhl_models"` (the output dataset for every
  write) at L22. Staging and mart dataset literals live in `bq.py`, not here.
- **Authoritative `MODEL_VERSION` strings** for many jobs: `ROSTER_FORECAST` = `roster_forecast_v1`
  (L463), `DEPLOYMENT` = `deployment_v1` (L664), `CONTRACT_VALUE` = `contract_value_v2` (L748),
  `FUTURES` = `futures_value_v1` (L782), `ANCHOR_VERSION` = `pwar_anchor_v1` (L791), `PWAR_VERSION`
  = `player_pwar_v1` (L792), `CURVE_VERSION` = `pick_value_curve_v1` (L830), `THEORY_VERSION` =
  `draft_value_v1` (L833), `trade_outcomes_v2` (L842), and `verdict_v1` (L897).
- **Archetype label maps** `ARCHETYPE_NAMES` / `ARCHETYPE_NAMES_V2`, and two import-time asserts
  (L450, L610) that fail loudly if the skater/goalie/forecast `GOALS_PER_WIN` constants ever drift
  out of agreement.

Some jobs instead hold their version literal inline (for example `xg_v1`, `ratings_v1`, `gar_v1`);
the master table below records where each `model_version` comes from.

### `bq.py`: the write path and DuckDB request-path routing

`models_ml/bq.py` is the thin BigQuery helper every job imports. Its roles:

- `client()` / `project()` (L22-27): build the client and read the project id from
  `os.environ[config.GCP_PROJECT_ENV]`.
- `staging()` / `mart()` / `models()` (L30-39): return backticked fully-qualified table
  identifiers. Staging and mart dataset names are hardcoded here (`STAGING_DATASET = "nhl_staging"`,
  `MART_DATASET = "nhl_mart"`, L18-19); the models dataset comes from `config.MODELS_DATASET`.
- `query_df()` (L42-57): **the read path. It routes to `duck.query_df` when `duck.serving_active()`
  is true** (serving mode), otherwise runs BigQuery with the Storage-API fast path. This routing is
  what lets `score_line` / `score_team_fit` read the DuckDB serving file on the request path.
- `write_df()` (L71-85): **the single write path** into `nhl_models.<table>` (WRITE_TRUNCATE by
  default, optional clustering). `ensure_models_dataset()` creates the dataset on first write.
- `delete_partition_since()` (L88-100): supports idempotent `--since` incremental rescores, used by
  `score_xg` and `score_winprob`.

`duck.py` is the companion DuckDB serving shim (BigQuery-to-DuckDB SQL rewrite) that `bq.query_df`
delegates to when serving is active.

---

## 2. Master table: every training / scoring / compute script

Reads are the dataset-qualified source tables each script queries; a script's own output table is
shown under Writes, not Reads. A blank "n/a" means no dataset-qualified table (the script reads via an
imported feature module or the DuckDB serving file, so its read list is a lower bound).

**Invocation legend** (the six sources from the critical rule):
`D` = `dags/nhl_daily.py` · `O` = `dags/offseason_forecast_intraday.py` · `M` = Makefile ·
`Y` = `serving_tables.yml` (its **output table** appears in the manifest) ·
`P` = imported by `precompute_serving.py` · `H3` = `docs/HANDOFF-3-ml-runbook.md` ·
`helper` = not a `__main__` entry point (imported by live code).

| File | Purpose | Reads (dataset.table) | Writes (dataset.table) | Invocation | model_version | Methodology doc |
|---|---|---|---|---|---|---|
| `__init__.py` | package marker | n/a | n/a | helper (package) | n/a | n/a |
| `bq.py` | BigQuery client / query_df / write_df; DuckDB routing on read | routes to `duck` when `SERVING_BACKEND=duckdb` | writes `nhl_models.<t>` for callers (`write_df` L71) | helper (every job) | n/a | n/a |
| `config.py` | model-layer constants + `MODEL_VERSION` strings | n/a | n/a | helper; `H3` names `models_ml/config` | holds most `*_VERSION` literals | contract-surplus, offseason-forecast, overall-rating, player-fit, power-ratings, roster-builder, roster-projection, streak-doctor, value-gar |
| `duck.py` | DuckDB serving shim + BQ→DuckDB SQL rewrite | serving file | n/a | helper (via `bq.query_df`) | n/a | n/a |
| `textfmt.py` | shared text formatters for server prose | n/a | n/a | helper (backend tools, score_team_fit, insight_engine) | n/a | n/a |
| `xg_features.py` | shared xG feature engineering (Phase 2.2) | staging.stg_boxscores, stg_play_by_play, int_shot_sequence | n/a | helper (score_xg, train_xg, xg_decompose) | n/a | xg-model.md (via train/score) |
| `xg_decompose.py` | per-shot xG + additive decomposition | via xg_features | n/a | helper (score_xg, train_xg) | n/a | n/a |
| `train_xg.py` | train the in-house xG model (Phase 2.2) | models.shot_xg (self, scoring probe) | artifact `xg_v1.txt` + `xg_v1_manifest.json` | `H3` (L41 `train_xg --full`); `Y`→shot_xg | `xg_v1` | methodology/xg-model.md |
| `score_xg.py` | score every shot with xG + decomposition | models.shot_xg (self, `--since` delete) | **models.shot_xg** (L71/74) | `D` score_xg (L443); `Y`→shot_xg | `xg_v1` | n/a |
| `winprob_features.py` | shared win-prob features (Phase 2.4) | mart.mart_team_game_stats, models.team_ratings, staging.int_segment_context, stg_boxscores | n/a | helper (score_winprob, train_winprob) | n/a | n/a |
| `train_winprob.py` | train win-probability model (Phase 2.4) | models.team_ratings, win_probability, staging.stg_partner_odds | artifact `winprob_v1.joblib` + manifest | **none of six by module** (hand-run; §5) | `winprob_v1` | methodology/win-probability.md |
| `score_winprob.py` | score WP + leverage per game | staging.stg_boxscores | **models.win_probability** (L73/89) | `D` score_winprob (L735); `Y`→win_probability | `winprob_v1` | n/a |
| `train_rapm.py` | isolated-impact RAPM on the xG layer (Phase 4.1) | models.shot_xg, staging.int_on_ice_events, int_segment_context, int_shift_segments, stg_games, stg_rosters | **models.player_impact** (L418) | `D` train_rapm (L490, Mon); `M` `rapm` (L63); `Y`→player_impact | `rapm_v1` | n/a |
| `compute_ratings.py` | power ratings with components (Phase 3.1) | mart.mart_team_game_stats, mart_goalie_game_stats, models.shot_xg, deserved_standings, staging.int_shot_sequence | **models.team_ratings** (L372) | `D` compute_ratings (L459); `Y`→team_ratings | `ratings_v1` | methodology/power-ratings.md |
| `simulate_deserved.py` | deserved standings Monte Carlo | mart.mart_team_game_stats, models.shot_xg, staging.int_shot_score_adj, int_shot_sequence, stg_boxscores | **models.deserved_standings** (L188) | `D` simulate_deserved (L466); `Y`→deserved_standings | n/a | n/a |
| `compute_style_map.py` | league style map PCA (Phase 3.2) | mart.mart_team_identity | **models.style_map** (L136) | `D` compute_style_map (L474); `Y`→style_map | `style_map_v1` | n/a |
| `streak_doctor.py` | streak sustainability cards (Phase 3.3) | mart.mart_team_game_stats, mart_goalie_game_stats, mart_team_identity_inputs, models.shot_xg, team_ratings, staging.int_shot_sequence, stg_boxscores | **models.streak_cards** (L251) | `D` streak_doctor (L482); `Y`→streak_cards | n/a | streak-doctor.md (via config) |
| `archetype_features.py` (v1) | shared archetype/feature assembly (Phase 4.2, reused 4.4) | mart.mart_edge_player_profile, mart_player_game_stats, models.player_impact, staging.int_segment_context, int_shift_segments, int_shot_sequence, stg_boxscores, stg_play_by_play | n/a | **helper n/a LIVE via `linefit_features`** (§4) | n/a | n/a |
| `archetype_features_v2.py` | enriched v2 feature vector | mart.mart_player_game_stats, models.player_coach_trust, shot_xg, staging.int_on_ice_events, int_segment_context, int_shift_segments, stg_play_by_play | n/a | helper (fit_archetypes_v2, compute_archetype_explainer) | n/a | n/a |
| `fit_archetypes.py` (v1) | per-position GMM archetypes (Phase 4.2) | staging.stg_rosters; loads `archetypes_v1.joblib` | **models.player_archetypes** (L195) + `archetypes_v1.joblib` | **none of six n/a SUPERSEDED** (§4/§5) | `archetypes_v1` | n/a |
| `fit_archetypes_v2.py` | enriched refit; emits player_archetypes | staging.stg_rosters; loads/saves `archetypes_v2.joblib` | **models.player_archetypes** (L324) + `archetypes_v2.joblib` | `D` write_archetypes (L589); `M` `archetypes-v2` (L135); `Y`→player_archetypes | `archetypes_v2` | n/a |
| `fit_aging_curves.py` | aging curves per archetype (Phase 4.4) | mart.mart_player_game_stats, models.player_archetypes, staging.stg_player_bio | **models.aging_curves** (L138) | `D` fit_aging_curves (L552); `Y`→aging_curves | `aging_v1` | n/a |
| `compute_composite.py` | composite value stack (Phase 4.2) | mart.mart_goalie_game_stats, mart_player_game_stats, models.player_impact, staging.int_segment_context, int_shift_segments, stg_play_by_play, stg_rosters | **models.player_composite** (L202) | `D` compute_composite (L569); `Y`→player_composite | `composite_v1` | n/a |
| `compute_clutch.py` | leverage-weighted clutch production (Phase 4.3) | staging.int_event_leverage, stg_rosters | **models.player_clutch** (L112) | `D` compute_clutch (L509); `Y`→player_clutch | `clutch_v1` | n/a |
| `compute_coach_trust.py` | coach-trust deployment signals (Phase 4.3) | staging.int_on_ice_events, int_segment_context, int_shift_segments, stg_games, stg_play_by_play, stg_rosters | **models.player_coach_trust** (L151) | `D` compute_coach_trust (L519); `Y`→player_coach_trust | `coach_trust_v1` | methodology/reconciliation.md |
| `compute_consistency.py` | consistency profile (Phase 4.3) | mart.mart_player_game_score, stg_rosters | **models.player_consistency** (L90) | `D` compute_consistency (L514); `Y`→player_consistency | `consistency_v1` | n/a |
| `compute_divergence.py` | divergence board (Phase 4.3) | models.player_coach_trust, player_composite, staging.stg_rosters | **models.divergence_board** (L99) | `D` compute_divergence (L524); `Y`→divergence_board | `divergence_v1` | n/a |
| `compute_deployment_efficiency.py` | deployment efficiency (divergence rework) | models.player_composite, player_impact, win_probability, staging.int_segment_context, int_shift_segments, stg_rosters | **models.deployment_efficiency** (L277) | `D` (L531); `M` `deployment` (L68); `Y`→deployment_efficiency | `deployment_v1` (config) | n/a |
| `compute_twins.py` | career twins (Phase 4.4) | mart.mart_player_game_stats, staging.stg_player_bio, stg_rosters | **models.player_twins** (L159) | `D` compute_twins (L557); `Y`→player_twins | `twins_v1` | n/a |
| `compute_physical.py` | physical-aging overlay / early-warning (Phase 4.4) | mart.mart_edge_player_profile, mart_player_game_stats | **models.player_physical** (L99) | `D` compute_physical (L562); `Y`→player_physical | `physical_v1` | methodology/trajectories.md |
| `compute_gar.py` | Value GAR/WAR (goals-reality companion to RAPM, Phase 6) | mart.mart_player_faceoff_zones, mart_player_game_stats, models.player_impact, staging.int_segment_context, int_shift_segments, stg_boxscores, stg_play_by_play, stg_rosters | **models.player_gar** (L321) | `D` compute_gar (L581); `M` `gar` (L74); `Y`→player_gar | `gar_v1` | methodology/value-gar.md |
| `compute_goalie_gar.py` | goalie GAR/WAR, cross-position currency | staging.int_goalie_shots, stg_rosters | **models.goalie_gar** (L214) | `D` compute_goalie_gar (L649); `M` `goalie-gar` (L82); `Y`→goalie_gar | `goalie_gar_v1` | n/a |
| `compute_overall.py` | within-position Overall summary (card only) | models.player_composite, player_gar, goalie_radar, staging.stg_rosters | **models.player_overall + goalie_overall** (L149/152) | `D` compute_overall (L658); `M` `overall` (L89); `Y`→player_overall, goalie_overall | `overall_v1`, `goalie_overall_v1` | n/a |
| `compute_player_radar.py` | skater skills radar (Part B) | mart.mart_edge_player_profile, mart_player_game_stats, models.player_archetypes, player_coach_trust, player_composite, player_impact, staging.int_shift_segments, stg_play_by_play | **models.player_radar** (L218) | `D` compute_player_radar (L627); `M` `radar` (L139); `Y`→player_radar | `radar_v1` | n/a |
| `compute_goalie_radar.py` | goalie skills radar (Part B2) | mart.mart_goalie_game_stats, mart_goalie_season | **models.goalie_radar** (L120) | `D` compute_goalie_radar (L632); `M` `radar` (L140); `Y`→goalie_radar | `goalie_radar_v1` | n/a |
| `compute_archetype_explainer.py` | archetype gallery + player style-map (reads v2 artifacts) | mart.mart_team_game_stats, models.player_composite, player_radar, staging.stg_rosters; loads `archetypes_v2.joblib` (via features_v2) | **models.archetype_gallery + player_style_map** (L234/236) | `D` (L638); `M` `archetype-explainer` (L145); `Y`→archetype_gallery, player_style_map | `archetypes_v2` | n/a |
| `generate_verdicts.py` | Player Verdict n/a Gemini narration + checker + persist | mart.mart_player_game_stats, models.player_overall (payload via `build_verdict_payload`) | **models.player_verdict** (L235/237) | `D` generate_verdicts (L668); `Y`→player_verdict | `verdict_v1` (config) | n/a |
| `build_verdict_payload.py` | deterministic verdict evidence payload | mart.mart_edge_player_profile, mart_player_game_stats, mart_player_shooting_luck, models.player_archetypes, player_consistency, player_gar, player_impact, player_overall, player_radar | n/a | helper (via generate_verdicts) | n/a | n/a |
| `compute_team_needs.py` | team need profiles for Player Fit (role×component) | mart.mart_team_game_stats, models.player_composite, team_ratings, staging.stg_rosters | **models.team_needs** (L156) | `D` compute_team_needs (L611); `M` `team-needs` (L99); `Y`→team_needs | `team_needs_v2` | n/a |
| `train_linefit.py` | train Lineup Lab line-fit model (Phase 5.1) | models.shot_xg, staging.int_line_seasons, int_on_ice_events, int_segment_context, int_shift_segments | artifact `linefit_v1.joblib` | `D` train_linefit (L603); `M` `linefit` (L94) | `linefit_v1` (config) | methodology/lineup-lab.md |
| `linefit_features.py` | shared line-fit feature assembly | models.player_archetypes, staging.stg_player_bio, stg_rosters (imports `archetype_features` v1) | n/a | helper n/a LIVE (precompute L32, train_linefit, score_line, backend tools) | n/a | n/a |
| `score_line.py` | line-fit scoring service (Phase 5.1) | models.line_member_features, staging.int_line_seasons | n/a | helper/service (backend tools, score_team_fit, project_roster_forecast, insight_engine) | n/a | lineup-lab (via train) |
| `score_team_fit.py` | Player Fit scoring service (rebuilt) | mart team stats/identity, models player_archetypes/composite/gar/goalie_gar/overall/radar/team_current_lines/team_handedness/team_needs/aging_curves, staging segments/bio/rosters/boxscores | n/a | helper/service (backend tools, trade_engine, compute_team_needs, project_roster_forecast, validate_trade_fit, insight_engine) | n/a | methodology/player-fit.md |
| `validate_trade_fit.py` | Player Fit validation (quality floors) | models.goalie_gar, player_composite, player_gar, player_overall, team_needs, staging.stg_rosters | n/a (reads only) | `M` `trade-fit-validate` (L125) | n/a | n/a |
| `project_roster_forecast.py` | offseason roster forecast (team next-season rating) | models.team_ratings, staging.stg_rosters (player_archetypes WHERE mv='archetypes_v2', L496; via score_line/score_team_fit) | **models.roster_forecast + roster_moves** (L938/940) | `D` roster_forecast (L621); `O` (L68); `M` `roster-forecast` (L105); `Y`→roster_forecast, roster_moves | `roster_forecast_v1` (config) | methodology/offseason-forecast.md |
| `validate_roster_forecast.py` | backtest calibration for the forecast (reads only) | team_ratings / deserved_standings via helpers | n/a | `M` `roster-forecast-validate` (L108) | n/a | methodology/offseason-forecast.md |
| `project_roster_player.py` | component season-ahead projection (Roster Builder) | models.roster_player_projection (self) | **models.roster_player_projection** (L766) | `M` `roster-player-projection` (L120); `Y`→roster_player_projection | `roster_player_v1` (L39) | roster-projection.md (via config) |
| `calibrate_roster_builder.py` | calibrate/validate Roster Builder absolute rating (reads only) | reads serving file under `SERVING_BACKEND=duckdb` | n/a (writes nothing) | `M` `roster-builder-calibrate` (L114) | n/a | roster-builder.md (via config) |
| `compute_contract_value.py` | contract surplus in cap-share (Trade tool) | mart.mart_player_contracts, models.aging_curves, goalie_gar, player_archetypes, player_gar, player_situation_toi, staging.stg_player_bio, stg_rosters | **models.player_contract_value** (L729) | `D` contract_value (L691); `M` `contract-value` (L158); `Y`→player_contract_value | `contract_value_v2` (config) | methodology/contract-surplus.md |
| `compute_futures_value.py` | prospects + picks in contract currency (Trade tool) | models.pick_value_curve, staging.stg_draft_picks, stg_prospects | **models.futures_value** (L204) | `D` futures_value (L704); `M` `futures-value` (L164); `Y`→futures_value | `futures_value_v1` (config) | n/a |
| `compute_trade_outcomes.py` | trade-outcome retrospective in realized WAR (Handoff 5 D) | mart.mart_player_game_stats, mart_team_game_stats, models.pick_value_curve, player_pwar, staging.stg_trades | **models.trade_outcomes** (L424) | `M` `trade-outcomes` (L173); `Y`→trade_outcomes | `trade_outcomes_v2` (config) | n/a |
| `compute_pwar.py` | apply pWAR anchor to every player-season 2010-26 (Handoff 5 B) | mart.mart_goalie_season, mart_player_game_stats, models.goalie_gar, player_gar, staging.stg_player_bio; loads `pwar_anchor_v1.joblib` | **models.player_pwar** (L140) | **not named by six by module**; `Y`→player_pwar; cited `sources.yml:186`. Hand-run (§5) | `player_pwar_v1` (config) | n/a |
| `fit_pwar_anchor.py` | fit box-score→real-WAR anchor (Handoff 5 B) | mart.mart_goalie_season, mart_player_game_stats, models.goalie_gar, player_gar, staging.stg_player_bio | artifact `pwar_anchor_v1.joblib` + manifest | **not named by six**; feeds compute_pwar. Hand-run (§5) | `pwar_anchor_v1` (config) | n/a |
| `fit_pick_value.py` | empirical draft pick-value curve (Handoff 5 B) | models.aging_curves, staging.int_draft_player_value | **models.pick_value_curve** (L139) | **not named by six by module**; `Y`→pick_value_curve; feeds futures_value + trade_outcomes. Hand-run (§5) | `pick_value_curve_v1` (config) | n/a |
| `run_draft_theory.py` | "85% theory" + steal/bust draft summaries (Handoff 5 B) | models.pick_value_curve, staging.int_draft_player_value | **models.draft_value_player + draft_value_summary** (L144/146) | **not named by six by module**; `Y`→draft_value_player, draft_value_summary. Hand-run (§5) | `draft_value_v1` (config) | n/a |
| `measure_goalie_reliability.py` | measure goalie-save reliability → config `RELIABILITY_K` | staging.int_goalie_shots | n/a (prints; hand-copied into config) | **not named by six**; only in `config.py:388` comment. One-shot calibration (§5) | n/a | value-gar.md |
| `tune_sequence_thresholds.py` | tune sequence-mining windows (Phase 2.1) | SQL-heavy; not dataset-qualified in-file | n/a | **not named by six** (H3 mentions "2.1 sweep" generically). One-shot calibration (§5) | n/a | methodology/sequence-mining.md |
| `analyze_combined_validation.py` | playoff combined-model joint fit + bootstrap CIs | mart.mart_team_game_stats, models.team_ratings | n/a | **research; none of six** (§5) | n/a | n/a |
| `analyze_goalie_clutch.py` | pre-registered goalie leverage-clutch study | mart.mart_goalie_game_stats, models.shot_xg, win_probability, staging.int_shot_sequence | n/a | **research; none of six** (§5) | n/a | methodology/goalie-clutch-preregistration.md |
| `analyze_goalie_clutch_impact.py` | goalie clutch impact test | mart goalie/team stats, models.shot_xg/team_ratings/win_probability, staging.int_shot_sequence | n/a | **research; none of six** (§5) | n/a | n/a |
| `analyze_kitchen_sink.py` | elastic-net "all features" playoff study | mart goalie/player/team stats + identity, models.team_ratings | n/a | **research; none of six** (§5) | n/a | n/a |
| `analyze_kitchen_sink_v2.py` | kitchen-sink v2 (adds goalie-clutch) | via imports | n/a | **research; none of six** (§5) | n/a | n/a |
| `analyze_noise_demo.py` | feature-selection noise demonstration | via imports | n/a | **research; none of six** (§5) | n/a | n/a |
| `analyze_playoff_components.py` | re-weight power-rating components for playoffs | mart.mart_team_game_stats, models.team_ratings | n/a | **research; none of six** (§5) | n/a | n/a |
| `analyze_playoff_experience.py` | does playoff experience predict series outcomes | mart.mart_player_game_stats, mart_team_game_stats, models.team_ratings | n/a | **research; none of six** (§5) | n/a | n/a |
| `analyze_playoff_profile.py` | do team profiles over/under-perform in playoffs | mart.mart_team_game_stats, mart_team_identity, models.team_ratings | n/a | **research; none of six** (§5) | n/a | n/a |
| `analyze_series_features.py` | test playoff-specific series features | mart goalie/player/team stats, models.player_composite, team_ratings | n/a | **research; none of six** (§5) | n/a | n/a |
| `analyze_series_model.py` | series-level playoff model calibration | mart.mart_goalie_game_stats, mart_team_game_stats, models.team_ratings | n/a | **research; none of six** (§5) | n/a | n/a |
| `build_playoff_weights.py` | build playoff-specific component re-weighting | mart.mart_team_game_stats, models.team_ratings | artifact `playoff_weights.json` (inferred; §5 uncertainty) | **research; none of six** (§5) | n/a | n/a |
| `train_style_effect.py` | does style matchup swing a playoff series | mart.mart_team_game_stats, mart_team_identity, models.team_ratings | n/a | **research; none of six** (§5) | n/a | n/a |
| `validate_gar.py` | GAR validation (YoY stability, reads only) | models.player_impact | n/a | `M` `gar-validate` (L76) | n/a | methodology/value-gar.md |
| `validate_goalie_gar.py` | goalie-GAR validation (reads only) | models.player_gar, staging.stg_rosters | n/a | `M` `goalie-gar-validate` (L84) | n/a | methodology/value-gar.md |
| `precompute_serving.py` | build the DuckDB serving inputs (§3) | many (see §3) | **6 nhl_models serving tables** (§3) | `D` precompute_serving (L720); `M` `precompute-serving` (L11); is source (3) itself | n/a | n/a |

### Cadence summary (from the two DAGs and the Makefile)

- **`nhl_daily` DAG** (`0 13 * * *`, daily 13:00 UTC) runs the nightly spine and most compute jobs.
  Many are Monday-gated via a `weekday()==0` guard (train_rapm, the whole clutch/consistency/
  coach-trust/divergence/deployment reconciliation block, aging/twins/physical, archetypes, linefit,
  team-needs, radars, goalie-gar, overall, verdicts, the contract/futures trade-tool block, and
  precompute/export). `score_xg`, `compute_ratings`, `simulate_deserved`, `style_map`,
  `streak_doctor`, `score_winprob`, and `roster_forecast` run daily.
- **`offseason_forecast_intraday` DAG** (`0 21 * * *`, 21:00 UTC) re-runs only
  `project_roster_forecast --full` and patches the DuckDB serving file in place, so offseason
  signings land twice a day.
- **Makefile targets** are the manual counterpart (`make gar`, `make linefit`, `make archetypes-v2`,
  `make trade-outcomes`, the `*-validate` targets, etc.) and are first-class invocation evidence.

---

## 3. The `precompute_serving.py` seam

`models_ml/precompute_serving.py` is the ML-to-frontend seam. It forces
`os.environ["SERVING_BACKEND"] = "bigquery"` (L28) so it always reads BigQuery and writes back into
`nhl_models` via `bq.write_df(df, name)` (L283). The entry point is
`python -m models_ml.precompute_serving --all|--only …` (L19-20), and a `BUILDERS` dict (L250-257)
maps 6 table names to their builder function plus dataset (`"nhl_models"` for all six).

It is invoked as DAG task `precompute_serving` (nhl_daily L720, Monday-gated) and Makefile target
`precompute-serving` (L11), and it is itself source (3) in the six-source rule. The only `models_ml`
module it imports besides `bq`/`config` is `linefit_features` (L32).

### The 6 serving tables it writes (all → `nhl_models`, WRITE_TRUNCATE)

| Serving table | Builder fn | Reads | serving_tables.yml |
|---|---|---|---|
| `dim_current_roster` | `build_dim_current_roster` (L49) | staging.stg_rosters, stg_roster_current, int_player_current_team, mart.mart_team_game_stats, models.player_archetypes | `:119` (precompute, built: true) |
| `line_member_features` | `build_line_member_features` (L242) → `linefit_features.build_member_features` | via linefit_features: models.player_archetypes, staging.stg_player_bio, stg_rosters, + archetype_features v1 inputs | `:120` (precompute, built: true) |
| `team_handedness` | `build_team_handedness` (L101) | staging.int_shift_segments, int_segment_context, stg_player_bio | `:121` (precompute, built: true) |
| `team_current_lines` | `build_team_current_lines` (L124) | staging.stg_boxscores, int_shift_segments, int_segment_context, mart.mart_team_game_stats | `:122` (precompute, built: true) |
| `serving_game_skater_box` | `build_serving_game_skater_box` (L178) | nhl_raw.raw_boxscores (L187) | `:123` (precompute, built: true) |
| `player_situation_toi` | `build_player_situation_toi` (L210) | staging.int_shift_segments, int_segment_context, stg_games | `:124` (precompute, built: true) |

### Consumers of the seam

`serving_tables.yml:139-147` documents the endpoint-to-serving mapping:

- `dim_current_roster` replaces the per-call `ARRAY_AGG(team_id …)` over `stg_rosters` for
  search / leaders / archetypes / divergence.
- `line_member_features` feeds live line-fit on DuckDB.
- `team_handedness` and `team_current_lines` feed `/teams/{id}/lines` and player-fit.
- `serving_game_skater_box` replaces the raw_boxscores UNNEST for `/games/{id}/skater-impact`.

`best_team_fits` is intentionally **not** precomputed (`serving_tables.yml:125`): it runs live on
DuckDB and is cached. All six precompute outputs are present in `serving_tables.yml` and marked
`built: true`.

---

## 4. Duplication resolution

### `archetype_features.py` (v1) vs `archetype_features_v2.py`: both live, different consumers

Both modules are live; neither is superseded-and-dead. They serve different downstream consumers:

- **v1 `archetype_features.py`** is imported by `linefit_features.py:26`
  (`from models_ml import archetype_features, bq, config`) and by v1 `fit_archetypes.py:34`. Because
  `linefit_features` is reachable from the six sources (`precompute_serving.py:32`, `train_linefit`,
  `score_line`, `backend/services/tools.py`), the v1 feature module **rides the live line-fit path**
  and is not dead.
- **v2 `archetype_features_v2.py`** is imported by `fit_archetypes_v2.py:36` and
  `compute_archetype_explainer.py:29,31`, both live. It feeds archetype clustering and the
  explainer.

The "v2 supersedes the v1 vector" note in the v2 docstring refers to the **archetype-clustering
vector only**, not the line-fit feature module. There is no deletion candidate in this pair.

### `fit_archetypes.py` (v1, SUPERSEDED) vs `fit_archetypes_v2.py` (live, DAG + Make)

- **v1 `fit_archetypes.py` is superseded and reachable by none of the six** (cleanup candidate, §5).
  Its own v2 counterpart says so explicitly: `fit_archetypes_v2.py:2`: "Archetype refit v2
  (supersedes fit_archetypes.py / archetypes_v1)."
- **v2 `fit_archetypes_v2.py` is live.** It is DAG task `write_archetypes`
  (`nhl_daily.py:589`, `fit_archetypes_v2 --write`, Monday-gated, single-thread BLAS) and Makefile
  target `archetypes-v2` (L135).
- Both write the same table `nhl_models.player_archetypes`, but with different `model_version`:
  v1 sets `archetypes_v1` (`fit_archetypes.py:194`), v2 sets `archetypes_v2`
  (`fit_archetypes_v2.py:323`). Because the live pipeline runs v2, the served `player_archetypes`
  carries `archetypes_v2`, confirmed downstream by `project_roster_forecast.py:496`
  (`WHERE … model_version = 'archetypes_v2'`) and by the explainer reading v2 artifacts.

### `archetypes_v1.joblib` (superseded) vs `archetypes_v2.joblib` (live)

- `archetypes_v1.joblib` is loaded/saved only by v1 `fit_archetypes.py`
  (`:53`, `:89` load, `:95` dump), which no live source invokes.
- `archetypes_v2.joblib` is loaded/saved by `fit_archetypes_v2.py` (`:51/:119/:126/:249/:252`) and
  consumed by `compute_archetype_explainer.py` (via `archetype_features_v2`), both live.
- Per Hard Rule 1: `archetypes_v1.joblib` is a *model artifact* (not ingested data), 15 KB at
  `models_ml/artifacts/archetypes_v1.joblib`, produced only by the superseded v1 script. That makes
  it a *potential* future Tier-2 cleanup candidate. This document records the fact and recommends no
  deletion; tiering is deferred to `CLEANUP_CANDIDATES.md`.

---

## 5. Reachability of the un-orchestrated scripts

Several `__main__` scripts are not named by any of the six sources *by module name*. Under the
critical invocation rule they cannot be called dead without confirming absence from all six, which
is true by module name here, but reachability through data dependencies changes the picture. They
split into two very different groups.

### Reaches a shipped surface, hand-run cadence (NOT dead)

These scripts are absent from both DAGs and every Makefile target, yet their outputs are in the
serving manifest and feed shipped frontend surfaces. They are **hand-run refresh steps, not dead
code.** The only genuine ambiguity is *how* they get refreshed on cadence, which static analysis
cannot determine.

- **Draft / pWAR cluster.** `fit_pwar_anchor.py` fits the box-score→real-WAR anchor artifact
  `pwar_anchor_v1.joblib`; `compute_pwar.py` applies it to write `player_pwar`
  (`serving_tables.yml`; also cited in `dbt/models/raw/sources.yml:186`); `fit_pick_value.py` writes
  `pick_value_curve`; `run_draft_theory.py` writes `draft_value_player` and `draft_value_summary`.
  These outputs are served and feed shipped surfaces: the `/draft/*` endpoints, and
  `mart_tradeable_assets` / the trade tools (`compute_futures_value` and `compute_trade_outcomes`
  both read `pick_value_curve` and `player_pwar`). **Classification: reaches a shipped surface,
  hand-run cadence. Not dead.**
- **`train_winprob.py`.** Produces `winprob_v1.joblib`, the artifact consumed by the live daily
  `score_winprob` job that writes `win_probability`. `H3` describes "2.4 win prob" as a training job
  but names only `train_xg`, so `train_winprob` is absent from the six by module. **Classification:
  feeds the live win-probability path via its artifact, hand-run cadence. Not dead.**

### Genuine cleanup candidates (report only; tiering deferred to `CLEANUP_CANDIDATES.md`)

These are reported as candidates here, not tiered. Their outputs are not served.

- **`fit_archetypes.py` (v1)**: superseded generation (§4). Candidate.
- **The playoff-model research line (11 + 2 scripts):** `analyze_combined_validation`,
  `analyze_goalie_clutch`, `analyze_goalie_clutch_impact`, `analyze_kitchen_sink`,
  `analyze_kitchen_sink_v2`, `analyze_noise_demo`, `analyze_playoff_components`,
  `analyze_playoff_experience`, `analyze_playoff_profile`, `analyze_series_features`,
  `analyze_series_model`, plus `build_playoff_weights.py` and `train_style_effect.py`. None is
  referenced by any of the six and none writes a served table (`build_playoff_weights.py` writes a
  local `playoff_weights.json`, inferred from filename and not confirmed by opening the file). This
  is the largest cleanup cluster, but it is investigation-only research, so verify against methodology
  docs before any Phase-E call.
- **One-shot calibration baked into config:** `measure_goalie_reliability.py` (its output is
  hand-copied into `config.GOALIE_GAR_CONFIG["RELIABILITY_K"]`, per `config.py:388`) and
  `tune_sequence_thresholds.py` (Phase 2.1 tuning; thresholds land in `dbt_project.yml` vars). Both
  are one-shot calibrations whose results are already frozen into config; candidates.

### Helper modules that are not dead (do not flag)

`bq.py`, `config.py`, `duck.py`, `textfmt.py`, `xg_features.py`, `xg_decompose.py`,
`winprob_features.py`, `linefit_features.py`, `archetype_features.py` (v1, via linefit_features),
`archetype_features_v2.py`, `build_verdict_payload.py`, `score_line.py`, and `score_team_fit.py` all
have at least one live importer (a backend service, an insight_engine template, or a DAG/Makefile-
invoked job).

---

## 6. Known documentation drift (flag for DOC_RECONCILIATION, not fixed here)

- **Stale DAG comment.** `dags/nhl_daily.py:587-588` still says the `write_archetypes` task "loads
  the committed, canonical GMM (archetypes_v1.joblib)", but the command it actually runs is
  `fit_archetypes_v2 --write`, which loads `archetypes_v2.joblib`
  (`fit_archetypes_v2.py:51 MODEL_PATH = ART_DIR / "archetypes_v2.joblib"`). The comment is stale;
  the executed code uses v2.
- **`models_ml/README.md` partial staleness.** The README (915 B) documents the layer contract
  (config as single source of constants, `artifacts/` gitignored except `.gitkeep`, one
  `train_*/score_*/compute_*` job per model, and a training-order line). Its "Rules" claim that
  "Every shipped model writes a versioned artifact here" is only partially true: most `compute_*`
  jobs write a BigQuery table with a `model_version` column but no joblib artifact. Only xg, winprob,
  linefit, archetypes, and the pWAR anchor emit `artifacts/*` files. Flagged for DOC_RECONCILIATION;
  not duplicated or edited here.
