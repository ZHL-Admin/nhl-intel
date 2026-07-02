# Data Pipeline

> **Cleanup applied (branch `cleanup/safe-removals`).** The five loose `dbt/` inspection
> scripts (`check_report_feed`, `check_xgf`, `query_metrics`, `verify_calculations`,
> `verify_hot_cold`) were **moved to `archive/dbt/`** (`0620488`). `dbt/profiles.yml` was
> **untracked** (`a3a2535`). The `sources.yml` description for `player_archetypes` was
> repointed from the deleted `fit_archetypes.py` to `fit_archetypes_v2.py`. The retired
> physical views `int_xg_rates` / `int_zone_entries` remain untouched (Tier 4); see the
> canonical-models note in section 4. See CLEANUP_CANDIDATES.md for status.

Polished reference for the NIR data pipeline, compiled from the read-only
inventories `docs/system/_inventory/10_dbt.md` (dbt lineage, parsed from
`dbt/target/manifest.json`) and `docs/system/_inventory/60_bq_objects.md`
(physical BigQuery objects vs. code producers). Every claim below is transcribed
from that already-gathered evidence, not re-investigated.

## Hard rules (in force for this whole document)

1. **This document only documents.** Data and ingested objects may never be
   recommended for deletion here. Any "0 consumers" note against a model or
   source is a reachability fact, not a delete recommendation, and never applies
   to raw or ingested data.
2. **Puck tracking is retained by owner decision.** `stg_ppt_tracking_frames`,
   `int_goal_release_frame`, and `nhl.raw_ppt_replay` (and any ppt-derived
   object) are RETAINED regardless of downstream count. Both puck-tracking
   models currently show 0 mart/backend consumers, which is expected and fine.

---

## 1. Overview: the layered flow

Data moves through five conceptual layers. Physical routing is enforced by dbt's
`generate_schema_name` macro plus the `+schema` settings in `dbt_project.yml`.

```
  raw ingestion            staging               intermediate            mart              consumers
  (nhl_raw, 24 feeds)  ->  (nhl_staging, stg_*)  (nhl_staging, int_*)  (nhl_mart, mart_*)  backend / report / ML
        |                        |                     |                     |
        |                        +---------------------+---------------------+
        |                                        dbt models
        |
        +--- ingestion/*.py, scripts/*.py, dags/*.py
                                              ^
                                              |  nhl_models.* seam (ML-written, read back)
                              models_ml/*.py (Python) writes nhl_models.* ----+
```

**Raw (`nhl_raw`, 24 ingested feeds).** BigQuery base tables written by the
ingestion layer (`ingestion/*.py`, `scripts/*.py`, `dags/nhl_daily.py`). dbt
declares 24 of these as `nhl.raw_*` sources. (The physical dataset holds 25
tables; `raw_backfill_failures` is an operational log table with an ingestion
producer but no dbt source declaration.)

**Staging (`nhl_staging`, `stg_*`).** 23 dbt models, all materialized as
`view`. They type, parse, and clean each raw feed one-to-one (with a few models
reading a second raw feed or an upstream `stg_` model). This is the cleaned
contract every downstream layer builds on.

**Intermediate (`nhl_staging`, `int_*`).** 20 dbt models that land in the same
`nhl_staging` dataset as staging (routing detail below). They compute the
feature-engineering middle layer: shot attempts with xG, shift segments,
on-ice event joins, score-state weighting, rink-bias multipliers, and the new
5v5-segment/on-ice lineage. The `dbt_project.yml` default for intermediate is
`view`, but many `int_` models override to `table`.

**Mart (`nhl_mart`, `mart_*`).** 24 dbt models, all materialized as `table`,
most partitioned by `game_date` (day) and clustered by `season` plus a team or
player id. Two hub marts, `mart_team_game_stats` and `mart_player_game_stats`,
fan out to most of the rest and are the heaviest-consumed objects in the system.

**Consumers.** Marts (and several `nhl_models.*` tables) are read by the FastAPI
backend, the daily report/Airflow pipeline, and the `models_ml` Python layer.
There is no separate GCP serving dataset. The serving layer is a local DuckDB
file, `data/serving/nhl_intel.duckdb` (714 MB on disk, declared in
`serving_tables.yml`), a rebuildable read-only copy of BigQuery produced by
`make export-serving` / `scripts/export_to_duckdb.py`. Nothing lives only in
DuckDB.

### The `nhl_models.*` seam

`nhl_models` is where the Python ML layer (`models_ml/*.py`,
`MODELS_DATASET = "nhl_models"` in `models_ml/config.py`) writes its outputs.
The seam runs in both directions:

- **16 declared dbt sources** under the `nhl_models` source block are ML-written
  tables that dbt reads back in as inputs (for example `nhl_models.shot_xg`
  feeds eight int/mart models; `nhl_models.team_ratings` feeds
  `mart_team_game_stats`). Of these 16, eight have live dbt consumers and eight
  are declared with 0 dbt consumers so lineage docs reference them, while they
  are read directly by backend/models_ml Python rather than by any dbt model.
- **~28 more `nhl_models` tables** (the physical dataset holds 44 base tables)
  are not declared as dbt sources at all. They are pure ML products
  (`player_gar`, `player_overall`, `roster_forecast`, `trade_outcomes`,
  `deserved_standings`, and so on) written by `models_ml/*.py` and consumed
  directly by the backend and by other ML scripts.

So dbt both feeds the ML layer (marts as inputs) and consumes it back
(`nhl_models.*` sources), and the ML layer also produces many tables the backend
reads without dbt ever touching them.

### `generate_schema_name` routing

The one project-owned macro, `dbt/macros/generate_schema_name.sql`, uses custom
schema names as-is (no environment prefixing). `dbt_project.yml`'s `models:`
block sets the effective schema per layer via `+schema`:

| layer directive | `+schema` | resolved dataset |
|---|---|---|
| `staging` (`stg_*`) | `staging` | **`nhl_staging`** |
| `intermediate` (`int_*`) | `staging` | **`nhl_staging`** (int lands in the staging dataset) |
| `mart` (`mart_*`) | `mart` | **`nhl_mart`** |
| `raw` | `raw` | (no raw `.sql` models exist; `models/raw/` holds only `sources.yml`) |

So `stg_` and `int_` models both materialize into `nhl_staging`, and `mart_`
models into `nhl_mart`.

### Counts (verified against `manifest.json`)

- Models: **67** (23 staging, 20 intermediate, 24 mart; 0 raw `.sql` models).
- Sources: **40** (24 `nhl.raw_*`, 16 `nhl_models.*`).
- Project macros: **1** (`generate_schema_name`).
- Seeds: **0** (no `dbt/seeds/` directory, no `.csv` under `dbt/`).

---

## 2. Layer-by-layer reference

Materialization is per-model `config.materialized` from the manifest.
`pb` = `partition_by` field, `cl` = `cluster_by`. Upstream/downstream are from
`depends_on.nodes` / `child_map`. "src" prefixes a declared source input.

### 2a. Sources (40)

Defined in `dbt/models/raw/sources.yml` in two blocks: `nhl` and `nhl_models`.

**`nhl.raw_*` (24) — BigQuery ingested raw tables (dataset `nhl_raw`)**

| source | grain / purpose | consuming dbt model(s) |
|---|---|---|
| nhl.raw_boxscores | game boxscore team stats | stg_boxscores, stg_goalie_starts |
| nhl.raw_contracts | contract snapshots | stg_contracts |
| nhl.raw_contracts_rfa | RFA contract feed | stg_contracts_rfa |
| nhl.raw_draft_picks | future draft picks | stg_draft_picks |
| nhl.raw_draft_results | historical draft results | stg_draft_results |
| nhl.raw_edge_goalies | NHL Edge goalie aggregates | stg_edge_goalies |
| nhl.raw_edge_skaters | NHL Edge skater aggregates | stg_edge_skaters |
| nhl.raw_edge_teams | NHL Edge team aggregates | stg_edge_teams |
| nhl.raw_game_landing | pregame/postgame landing | stg_game_context |
| nhl.raw_game_right_rail | game right-rail context | stg_game_context |
| nhl.raw_games | schedule | stg_games |
| nhl.raw_glossary | reference/metadata | **0 consumers** (ingested data, retained) |
| nhl.raw_gm_tenures | GM tenures | stg_gm_tenures |
| nhl.raw_partner_odds | partner odds snapshots | stg_partner_odds |
| nhl.raw_play_by_play | play-by-play events | stg_play_by_play, stg_rosters |
| nhl.raw_player_bio | player bio | stg_player_bio |
| nhl.raw_player_draft_origin | player draft origin | stg_draft_results |
| nhl.raw_ppt_replay | puck-tracking replay | stg_ppt_tracking_frames (**PUCK TRACKING, RETAINED**) |
| nhl.raw_prospects | org prospect lists | stg_prospects |
| nhl.raw_rosters | live rosters | stg_roster_current |
| nhl.raw_shift_charts | shift charts | stg_shifts |
| nhl.raw_standings | league standings | stg_standings |
| nhl.raw_statsrest_faceoffs | faceoff zone splits | stg_statsrest_faceoffs |
| nhl.raw_trades | historical trades | stg_trades |

**`nhl_models.*` (16) — external, written by `models_ml` Python, consumed by dbt**

| source | consuming dbt model(s) |
|---|---|
| nhl_models.shot_xg | int_event_leverage, int_goalie_shots, int_line_seasons, int_segment_5v5_results, int_shot_attempts, int_shot_attempts_all, int_shot_score_adj, mart_team_identity |
| nhl_models.team_ratings | mart_team_game_stats |
| nhl_models.win_probability | int_event_leverage |
| nhl_models.player_pwar | int_draft_player_value |
| nhl_models.contract_player_map | mart_player_contracts |
| nhl_models.rfa_player_map | mart_player_contracts |
| nhl_models.futures_value | mart_tradeable_assets |
| nhl_models.player_contract_value | mart_tradeable_assets |
| nhl_models.deserved_standings | **0 dbt consumers** (read by backend/models_ml) |
| nhl_models.player_archetypes | **0 dbt consumers** (consumed outside dbt) |
| nhl_models.player_composite | **0 dbt consumers** (consumed outside dbt) |
| nhl_models.player_impact | **0 dbt consumers** (consumed outside dbt) |
| nhl_models.roster_forecast | **0 dbt consumers** (consumed outside dbt) |
| nhl_models.roster_moves | **0 dbt consumers** (consumed outside dbt) |
| nhl_models.streak_cards | **0 dbt consumers** (consumed outside dbt) |
| nhl_models.style_map | **0 dbt consumers** (consumed outside dbt) |

The 8 `nhl_models.*` sources with 0 dbt consumers are declared so dbt lineage
docs reference them; they are read directly by backend/models_ml (Python). All
are ML-produced data, never a deletion candidate.

### 2b. Staging (23) — schema `nhl_staging`, all materialized `view`

| model | src (upstream) | grain (one row per) | purpose | downstream |
|---|---|---|---|---|
| stg_boxscores | src nhl.raw_boxscores | game (team-level) | cleaned boxscore team stats per game | int_goalie_shots, int_rink_bias, int_score_state_weights, int_segment_5v5_results, int_segment_context, int_shot_score_adj, int_shot_sequence, mart_player_game_stats, mart_player_situational, mart_team_faceoffs, mart_team_game_stats, mart_team_identity_inputs, mart_team_stats_situational, mart_team_zone_time, stg_games |
| stg_contracts | src nhl.raw_contracts | player x contract-snapshot | typed/parsed dated contract snapshot ($ to INT64, term/remaining years) | mart_player_contracts |
| stg_contracts_rfa | src nhl.raw_contracts_rfa | RFA row | typed RFA contract feed | mart_player_contracts |
| stg_draft_picks | src nhl.raw_draft_picks | owner_team x draft_year x round | future draft picks as tradeable assets (Trade P5) | (none) |
| stg_draft_results | src nhl.raw_draft_results, nhl.raw_player_draft_origin | draft_year x overall_pick | historical draft results universe (Draft Value tool) | int_draft_player_value |
| stg_edge_goalies | src nhl.raw_edge_goalies | goalie x season | NHL Edge goalie season aggregates | mart_goalie_season |
| stg_edge_skaters | src nhl.raw_edge_skaters | player x season x game_type | NHL Edge skater season aggregates (pivoted) | mart_edge_player_profile |
| stg_edge_teams | src nhl.raw_edge_teams | team x season | NHL Edge team danger-bucket shares | mart_edge_team_profile |
| stg_game_context | src nhl.raw_game_landing, nhl.raw_game_right_rail | game | pregame/postgame context (scratches, coaches, series) | (none) |
| stg_games | src nhl.raw_games, stg_boxscores | game | schedule spine enriched with played-game detail | stg_roster_current |
| stg_gm_tenures | src nhl.raw_gm_tenures | gm x team x start_date | curated GM tenures (trade-outcome attribution source of truth) | (none) |
| stg_goalie_starts | src nhl.raw_boxscores | goalie start | goalie starts derived from boxscores | mart_goalie_season |
| stg_partner_odds | src nhl.raw_partner_odds | odds snapshot | de-vigged implied win prob (INTERNAL CALIBRATION ONLY, no API/UI by design) | (none) |
| stg_play_by_play | src nhl.raw_play_by_play | event | PBP events unnested, one row per event | int_assists, int_goalie_shots, int_on_ice_events, int_rink_bias, int_score_state_weights, int_segment_context, int_shot_attempts, int_shot_attempts_all, int_shot_score_adj, int_shot_sequence, int_zone_entry_proxy, mart_player_game_score, mart_player_game_stats, mart_team_faceoffs, mart_team_game_stats, mart_team_identity, mart_team_zone_time |
| stg_player_bio | src nhl.raw_player_bio | player | player bio | (none) |
| stg_ppt_tracking_frames | src nhl.raw_ppt_replay | game x event x frame x entity | **PUCK TRACKING, RETAINED** ppt-replay goal frames | int_goal_release_frame |
| stg_prospects | src nhl.raw_prospects | prospect | typed org prospect lists (Trade P5) | (none) |
| stg_roster_current | src nhl.raw_rosters, stg_games | player | live team-roster membership (current affiliation) | int_player_current_team |
| stg_rosters | src nhl.raw_play_by_play | player x game | game-derived roster (one row per player per game) | int_player_current_team, int_shift_segments, mart_player_contracts, mart_player_game_stats, mart_player_situational, mart_player_zone_deployment, mart_tradeable_assets, stg_trades |
| stg_shifts | src nhl.raw_shift_charts | player x shift x game | one row per shift per player (goal-annotation rows excluded) | int_shift_segments, mart_edge_player_profile, mart_player_game_stats, mart_team_identity |
| stg_standings | src nhl.raw_standings | team x date | league standings as of a date | (none) |
| stg_statsrest_faceoffs | src nhl.raw_statsrest_faceoffs | player x season | season per-player faceoff zone splits | mart_player_faceoff_zones |
| stg_trades | src nhl.raw_trades, stg_rosters | trade x asset | typed historical trades with resolved_player_id (Handoff 5 D) | (none) |

All staging models are `view`; none are partitioned or clustered.

### 2c. Intermediate (20) — schema `nhl_staging`

| model | mat | pb / cl | upstream | grain / purpose | downstream |
|---|---|---|---|---|---|
| int_assists | view | — | stg_play_by_play | assist per goal (1st/2nd) | mart_player_game_stats |
| int_draft_player_value | table | — | src nhl_models.player_pwar, stg_draft_results | realized career value per drafted pick | (none) |
| int_event_leverage | table | cl: season, shooter_id | src nhl_models.shot_xg, src nhl_models.win_probability, int_shot_sequence | per-shot leverage/WPA weight | (none) |
| int_goal_release_frame | view | — | stg_ppt_tracking_frames | **PUCK TRACKING, RETAINED** goal release/arrival frame per game x event x entity | (none) |
| int_goalie_shots | table | — | src nhl_models.shot_xg, stg_play_by_play, stg_boxscores | unblocked shot faced by goalie with xG + danger | mart_goalie_game_stats |
| int_line_seasons | table | cl: season, team_id | src nhl_models.shot_xg, int_segment_context, int_shift_segments, int_on_ice_events, int_shot_sequence | qualifying F3 trio / D2 pair season with 5v5 results | (none) |
| int_on_ice_events | table | — | stg_play_by_play, int_shift_segments | event joined to its shift segment with on-ice arrays | int_line_seasons, int_segment_5v5_results |
| int_player_current_team | view | — | stg_rosters, stg_roster_current | current-team resolution per player | (none) |
| int_player_onice_game **[NEW]** | table | — | int_segment_5v5_results, int_shift_segments | per game x player 5v5 on/off-ice results | mart_player_game_stats, mart_player_onice, mart_player_relative |
| int_rink_bias | table | — | stg_play_by_play, stg_boxscores | scorer-bias multipliers per arena x season | mart_player_game_stats, mart_team_game_stats |
| int_score_state_weights | table | — | int_segment_context, stg_play_by_play, stg_boxscores | league 5v5 shot-rate by score state to weights | int_shot_score_adj |
| int_segment_5v5_results **[NEW]** | table | — | src nhl_models.shot_xg, int_segment_context, stg_boxscores, int_on_ice_events | per-5v5-segment for/against xG + Corsi + goals | int_player_onice_game, mart_player_toi_matrix, mart_player_wowy |
| int_segment_context | table | — | int_shift_segments, stg_boxscores, stg_play_by_play | per game x segment strength/score/zone context | int_line_seasons, int_score_state_weights, int_segment_5v5_results |
| int_shift_segments | table | — | stg_shifts, stg_rosters | maximal unchanged-on-ice interval per game x segment x player | int_line_seasons, int_on_ice_events, int_player_onice_game, int_segment_context, mart_player_toi_matrix, mart_player_wowy |
| int_shot_attempts | view | — | src nhl_models.shot_xg, stg_play_by_play | 5v5 shot attempts with high-danger flag | int_shot_types, mart_team_game_stats, mart_team_stats_situational |
| int_shot_attempts_all | view | — | src nhl_models.shot_xg, stg_play_by_play | all-strength shot attempts with per-situation xG | mart_player_game_stats, mart_player_situational |
| int_shot_score_adj | table | — | src nhl_models.shot_xg, stg_play_by_play, stg_boxscores, int_score_state_weights | per game x team score-adj 5v5 Corsi/xG | mart_team_game_stats |
| int_shot_sequence | table | pb: game_date(day) / cl: season, team_id | stg_play_by_play, stg_boxscores | sequence-mined shot (rebound/rush/forecheck) per unblocked attempt | int_event_leverage, int_line_seasons, mart_player_game_stats, mart_team_identity, mart_team_identity_inputs |
| int_shot_types | view | — | int_shot_attempts | 5v5 shot with normalized shot type | (none) |
| int_zone_entry_proxy | view | — | stg_play_by_play | proxy zone entries from zone-code transitions | mart_player_zone_deployment, mart_team_game_stats |

Note: the `int_segment_5v5_results` 5v5-segment lineage uses the same
`nhl_models.shot_xg` pull as `models_ml/train_rapm.py` (per its schema.yml
description).

### 2d. Mart (24) — schema `nhl_mart`, all materialized `table`

Downstream shown here is dbt-internal only; the great majority of marts are read
outside dbt by the backend, report pipeline, and `models_ml` (see the
reachability appendix in section 5).

| model | pb / cl | upstream | grain / purpose | downstream (dbt) |
|---|---|---|---|---|
| mart_daily_report_feed | pb game_date(day) / cl season, team_id | mart_team_game_stats, mart_team_rolling, mart_player_game_stats | denormalized daily-report feed per game x team | (none) |
| mart_edge_player_profile | cl season_id, player_id | stg_edge_skaters, stg_shifts | player-season Edge profile | mart_team_identity |
| mart_edge_team_profile | cl season_id, team_id | stg_edge_teams | team-season Edge danger shares | (none) |
| mart_goalie_game_stats | pb game_date(day) / cl season, goalie_id | int_goalie_shots | per goalie x game GSAx | mart_goalie_season |
| mart_goalie_season | cl season, goalie_id | mart_goalie_game_stats, stg_goalie_starts, stg_edge_goalies | goalie-season GSAx + rolling + Edge | (none) |
| mart_player_contracts | — | src nhl_models.contract_player_map, src nhl_models.rfa_player_map, stg_contracts, stg_rosters, mart_team_game_stats, stg_contracts_rfa | matched player x contract-snapshot | mart_tradeable_assets |
| mart_player_faceoff_zones | cl season_id, player_id | stg_statsrest_faceoffs | player-season faceoff by zone | (none) |
| mart_player_game_score | cl season, player_id | mart_player_game_stats, stg_play_by_play | single-game "game score" per player x game | (none) |
| mart_player_game_stats | pb game_date(day) / cl season, player_id | stg_rosters, int_shot_attempts_all, int_assists, stg_play_by_play, int_rink_bias, stg_boxscores, int_shot_sequence, mart_team_game_stats, int_player_onice_game, stg_shifts | player x game advanced stats (hub mart) | mart_daily_report_feed, mart_player_game_score, mart_player_relative, mart_player_shooting_luck |
| mart_player_onice **[NEW]** | cl season, team_id | int_player_onice_game | season 5v5 on/off-ice per season x player x team | mart_player_wowy |
| mart_player_relative | pb game_date(day) / cl season, player_id | mart_player_game_stats, int_player_onice_game | player x game relative (on-off) metrics | (none) |
| mart_player_shooting_luck | pb game_date(day) / cl season, player_id | mart_player_game_stats | player x game shooting-luck (xG vs actual) | (none) |
| mart_player_situational | pb game_date(day) / cl season, player_id | stg_rosters, stg_boxscores, int_shot_attempts_all | player x game situational (strength splits) | (none) |
| mart_player_toi_matrix **[NEW]** | cl season, team_id | int_segment_5v5_results, int_shift_segments | pairwise shared 5v5 TOI per season x team x playerA<playerB | (none) |
| mart_player_wowy **[NEW]** | cl season, team_id | int_segment_5v5_results, int_shift_segments, mart_player_onice | WOWY per season x team x focal to partner | (none) |
| mart_player_zone_deployment | pb game_date(day) / cl season, player_id | stg_rosters, mart_team_zone_time, int_zone_entry_proxy | player x game zone deployment | (none) |
| mart_team_faceoffs | pb game_date(day) / cl season, team_id | stg_boxscores, stg_play_by_play | team x game faceoff results | (none) |
| mart_team_game_stats | pb game_date(day) / cl season, team_id | src nhl_models.team_ratings, stg_boxscores, int_shot_attempts, int_zone_entry_proxy, stg_play_by_play, int_rink_bias, mart_team_identity_inputs, int_shot_score_adj | team x game advanced stats (hub mart) | mart_daily_report_feed, mart_player_contracts, mart_player_game_stats, mart_team_identity, mart_team_rolling |
| mart_team_identity | cl season, team_id | src nhl_models.shot_xg, mart_team_game_stats, mart_team_identity_inputs, int_shot_sequence, stg_play_by_play, stg_shifts, mart_edge_player_profile | team-season identity/style profile | (none) |
| mart_team_identity_inputs | pb game_date(day) / cl season, team_id | int_shot_sequence, stg_boxscores | team x game inputs feeding identity | mart_team_game_stats, mart_team_identity |
| mart_team_rolling | pb game_date(day) / cl season, team_id | mart_team_game_stats | rolling 5-game team averages per team x game | mart_daily_report_feed |
| mart_team_stats_situational | pb game_date(day) / cl season, team_id | stg_boxscores, int_shot_attempts | team x game situational splits | (none) |
| mart_team_zone_time | pb game_date(day) / cl season, team_id | stg_boxscores, stg_play_by_play | team x game zone-time | mart_player_zone_deployment |
| mart_tradeable_assets | — | src nhl_models.player_contract_value, src nhl_models.futures_value, stg_rosters, mart_player_contracts | unified tradeable-asset layer (player/prospect/pick) per asset_id | (none) |

---

## 3. WOWY / on-ice feature (materialized and validated, Phase 6.1)

Five models form a coherent WOWY / on-ice / 5v5-segment feature. As of Phase 6.1
(branch `feature/phase6-impact-context`) they are **materialized in BigQuery and
validated** (`dbt run --select int_segment_5v5_results+`, PASS=10; 31 dbt tests
PASS). Two of them (`int_segment_5v5_results` and `int_player_onice_game`) are
wired **upstream** of the live hub marts: `int_player_onice_game` feeds
`mart_player_game_stats` (replacing the former team-proxy `on_ice_xgf_pct` with a
real per-player value that now varies within a team-game) and `mart_player_relative`
(additive columns only). Not yet served — Phase 6.4 adds them to `serving_tables.yml`.

Lineage:

```
int_shift_segments ─┐
int_segment_context ┤
stg_boxscores ──────┤
int_on_ice_events ──┤
nhl_models.shot_xg ─┴─> int_segment_5v5_results ─┬─> int_player_onice_game ─┬─> mart_player_game_stats (LIVE)
                                                 │                          ├─> mart_player_relative   (LIVE)
                                                 │                          └─> mart_player_onice ──┐
                                                 ├─> mart_player_toi_matrix                          │
                                                 └─> mart_player_wowy <──────────────────────────────┘
```

| model | layer / target | grain | rows (Phase 6.1) | status |
|---|---|---|---|---|
| int_segment_5v5_results | intermediate / `nhl_staging` (table) | game × 5v5 segment | 5.1M | materialized ✓ |
| int_player_onice_game | intermediate / `nhl_staging` (table) | game × player (5v5) | 714.6k | materialized ✓ |
| mart_player_onice | mart / `nhl_mart` (table) | season × player × team | 15.7k | materialized ✓ |
| mart_player_toi_matrix | mart / `nhl_mart` (table) | season × team × pair (a<b) | 208.3k | materialized ✓ |
| mart_player_wowy | mart / `nhl_mart` (table) | season × team × focal × partner | 416.6k | materialized ✓ |

**Validation (Phase 6.1):** `assert_toi_matrix_symmetric` and
`assert_onice_game_toi_reconciles` PASS (the latter checks `int_player_onice_game.
toi_5v5_sec` against an independent shift-derived 5v5 recompute; NHL boxscores are
team-grain with no per-player strength TOI, so shift-derived time is the truth-source,
per `docs/PHASE6_FINDINGS.md`). Payoff spot-check recorded: the Seider/Edvinsson
2024-25 → 2025-26 with/without splits are internally consistent (directional fields
mirror) and show the pair's shared TOI rising 463 → 724 min with a rising together
xGF% (52.4% → 58.2%). Serving is Phase 6.4.

---

## 4. Physical drift (from `60_bq_objects.md`)

A metadata-only pass (INFORMATION_SCHEMA only, 0 bytes scanned) cross-referenced
every physical BigQuery object against its code producer. Physical totals: 25
raw + 42 staging + 2 staging_staging + 21 mart + 44 models = **134 objects**,
of which 130 have a producer. Drift appears in both directions.

### 4a. Tier-4 physical orphans (no code producer, investigate, do not drop)

Four physical objects have no producing dbt model, ML script, or ingestion path.
All are **Tier 4: investigate, do not drop.** The likely cause in each case is a
removed or misconfigured source file whose already-materialized BigQuery object
was left behind (dbt does not drop the physical relation when a model's `.sql`
is deleted). None may be dropped by documentation.

| orphan object | type | evidence | interpretation |
|---|---|---|---|
| `nhl_staging.int_xg_rates` | VIEW | no `int_xg_rates.sql` source file; absent from manifest model nodes; only stale `dbt/target/compiled|run` artifacts reference it | former dbt model, source `.sql` removed, physical VIEW persists |
| `nhl_staging.int_zone_entries` | VIEW | no source file; absent from manifest (distinct from the live `int_zone_entry_proxy`, not a rename alias); only stale target artifacts | former dbt model, source removed, physical VIEW left behind |
| `nhl_staging_staging.stg_boxscores` | VIEW | entire `nhl_staging_staging` dataset is unexpected; zero references in `.py`/`.yml`/`.sql`; serving config targets single `nhl_staging` | residue of a past dbt custom-schema concatenation (`nhl_staging` + `_staging`), orphaned when `generate_schema_name` fixed the naming |
| `nhl_staging_staging.stg_games` | VIEW | same as above (only these two views live in that dataset) | frozen copy under the old naming scheme |

For all four, the recommended follow-up is investigation only; the relevant
source artifact (the schema-name macro) is already fixed, and no BigQuery object
is dropped by this pass.

#### Canonical models (do not reference the ghosts)

To stop future work from pointing at the retired objects above, the canonical
live models are:

- **Expected goals:** produced by the ML layer as `nhl_models.shot_xg`
  (`models_ml/score_xg.py`) and consumed per shot via **`int_shot_attempts`** /
  `int_shot_attempts_all`. There is **no** `int_xg_rates` dbt model. The physical
  `nhl_staging.int_xg_rates` VIEW is a non-producing orphan and **must not be
  referenced by new code, models, or docs.**
- **Zone logic:** **`int_zone_entry_proxy`** (the honest proxy derived from
  zone-code transitions in `stg_play_by_play`). There is **no** `int_zone_entries`
  dbt model; it was superseded by `int_zone_entry_proxy`. The physical
  `nhl_staging.int_zone_entries` VIEW is a non-producing orphan and **must not be
  referenced by new work.** See DOC_RECONCILIATION.md §0a.

### 4b. Reverse drift — RESOLVED (Phase 6.1)

The five new-branch models were previously declared-but-unmaterialized. As of
Phase 6.1 they are **materialized in BigQuery and validated** (section 3), so the
reverse-drift gap is closed. They still need to be added to the nightly
`dbt build` selection and to `serving_tables.yml` (Phase 6.4) to reach the app.

### 4c. Retained (never flagged)

`raw_ppt_replay`, `stg_ppt_tracking_frames`, and `int_goal_release_frame` all
have producers and are additionally marked RETAINED by owner decision. They are
never flagged as orphans for removal, even where unreferenced downstream.

---

## 5. Reachability appendix (marts consumed outside dbt)

Marts are read mostly by the backend, report pipeline, and `models_ml`, so
dbt-internal downstream counts understate their true use. The counts below are
raw `grep -rn "<mart>" | wc -l` line counts against `backend/` and `models_ml/`
(a relative signal including comments/repeats, not exact unique-consumer counts).

| mart | dbt downstream | backend refs | models_ml refs | note |
|---|---|---|---|---|
| mart_team_game_stats | 5 | 26 | 37 | hub, heavily consumed everywhere |
| mart_player_game_stats | 4 | 20 | 25 | hub, heavily consumed everywhere |
| mart_player_contracts | 1 | 7 | 6 | reachable |
| mart_tradeable_assets | 0 | 6 | 2 | reachable via backend/models_ml |
| mart_player_zone_deployment | 0 | 6 | 0 | reachable via backend |
| mart_player_relative | 0 | 5 | 0 | reachable via backend |
| mart_goalie_season | 0 | 4 | 3 | reachable |
| mart_player_situational | 0 | 4 | 0 | reachable via backend |
| mart_goalie_game_stats | 1 | 2 | 11 | reachable |
| mart_team_identity | 0 | 3 | 8 | reachable |
| mart_team_faceoffs | 0 | 3 | 0 | reachable via backend |
| mart_team_stats_situational | 0 | 3 | 0 | reachable via backend |
| mart_team_zone_time | 1 | 3 | 0 | reachable |
| mart_player_shooting_luck | 0 | 3 | 1 | reachable |
| mart_player_game_score | 0 | 2 | 2 | reachable |
| mart_edge_player_profile | 1 | 2 | 4 | reachable |
| mart_team_rolling | 1 | 2 | 0 | reachable |
| mart_edge_team_profile | 0 | 1 | 0 | reachable via backend |
| mart_player_faceoff_zones | 0 | 0 | 1 | reachable via models_ml only |
| mart_team_identity_inputs | 2 | 0 | 1 | internal + models_ml |
| mart_daily_report_feed | 0 | 0 | 0 | no dbt/backend/models_ml grep refs; report/Airflow layer likely reads it directly (its own inspector `dbt/check_report_feed.py` probes it) |
| mart_player_onice **[NEW]** | 1 | 0 | 0 | internal only (feeds mart_player_wowy); new, not yet wired externally |
| mart_player_toi_matrix **[NEW]** | 0 | 0 | 0 | new, not yet wired to a product surface |
| mart_player_wowy **[NEW]** | 0 | 0 | 0 | new, not yet wired to a product surface |

Caveats: `mart_daily_report_feed`'s 0 grep count reflects the report/Airflow
pipeline reading it outside the scanned dirs, not disuse. The three new marts'
low external counts are consistent with being freshly added. All of these
produce data and are not deletion candidates.

---

## Appendix: ad-hoc scripts and a config finding (from `10_dbt.md`)

- **Loose `dbt/` inspection scripts (5).** `check_report_feed.py`, `check_xgf.py`,
  `query_metrics.py`, `verify_calculations.py`, `verify_hot_cold.py` are
  standalone ad-hoc BigQuery probes, each opening its own client. None is
  imported or called by any code, Makefile, or config (only listed in
  `00_manifest.md`). These are source-code utilities (not data), recorded as
  orphaned by reference count; no deletion call is made here.
- **`dbt/profiles.yml` is tracked (rule violation, recorded finding).** The
  project rule "profiles.yml must never be committed" is currently violated:
  `dbt/profiles.yml` is tracked and was committed on this branch, and it contains
  real local keyfile paths (no inline secret material). The correct template
  `dbt/profiles.yml.example` is also tracked. Remediation
  (`git rm --cached dbt/profiles.yml`) is out of this document's read-only scope.
