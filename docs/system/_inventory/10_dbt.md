# 10 — dbt Domain Inventory

READ-ONLY inventory of the dbt domain (`dbt/`). Authoritative lineage source:
`dbt/target/manifest.json` (parsed with `python json.load`, not by eyeballing
`ref()`/`source()`). Every dependency claim below is backed by a manifest
`depends_on.nodes` / `child_map` entry, a schema.yml line, or a quoted ripgrep hit.

## HARD RULES (govern this whole document)

1. **Data / ingested objects may NEVER be recommended for deletion.** This file
   reports facts and reference counts only; it makes no deletion calls. Any
   "0 consumers" note against a *model/source* is a reachability fact, not a
   delete recommendation, and never applies to raw/ingested data.
2. **Puck tracking is retained by owner decision.** `stg_ppt_tracking_frames`,
   `int_goal_release_frame`, `nhl.raw_ppt_replay`, and any ppt-derived object are
   RETAINED regardless of downstream count. They are never dead. (Both currently
   show 0 mart/backend consumers — that is expected and fine.)

## Counts (verified against manifest.json)

- Models: **67** — 23 staging, 20 intermediate, 24 mart (0 `raw` .sql models;
  `dbt/models/raw/` holds only `sources.yml`). `manifest['nodes']` = 283 total =
  67 models + 216 tests.
- Sources: **40** — 24 `nhl.raw_*`, 16 `nhl_models.*` (`manifest['sources']`).
- Macros (project-owned): **1** — `generate_schema_name` (all other 549 manifest
  macros are dbt/adapter internals, `package_name != 'nhl_intel'`).
- Seeds: **0** (no `dbt/seeds/` dir; no `.csv` under `dbt/`).
- The 5 NEW branch models are present and included:
  `int_segment_5v5_results`, `int_player_onice_game`, `mart_player_onice`,
  `mart_player_toi_matrix`, `mart_player_wowy`.

---

## 1. Models

Materialization is per-model `config.materialized` from the manifest. Note the
`dbt_project.yml` defaults: staging=view, **intermediate=view** (but many int
models override to `table`), mart=table. `pb`=partition_by field, `cl`=cluster_by.
"tests" = count of tests whose `depends_on` includes the model (from manifest).
Upstream/downstream are from `depends_on.nodes` / `child_map`.

### 1a. Staging (23) — schema `nhl_staging`, all materialized `view`

| model | src (upstream) | grain (one row per) | purpose | downstream | tests |
|---|---|---|---|---|---|
| stg_boxscores | src nhl.raw_boxscores | game (team-level) | cleaned boxscore team stats per game | int_goalie_shots, int_rink_bias, int_score_state_weights, int_segment_5v5_results, int_segment_context, int_shot_score_adj, int_shot_sequence, mart_player_game_stats, mart_player_situational, mart_team_faceoffs, mart_team_game_stats, mart_team_identity_inputs, mart_team_stats_situational, mart_team_zone_time, stg_games | 10 |
| stg_contracts | src nhl.raw_contracts | player×contract-snapshot | typed/parsed dated contract snapshot ($→INT64, term/remaining years) | mart_player_contracts | 5 |
| stg_contracts_rfa | src nhl.raw_contracts_rfa | RFA row | typed RFA contract feed | mart_player_contracts | 0 |
| stg_draft_picks | src nhl.raw_draft_picks | owner_team×draft_year×round | future draft picks as tradeable assets (Trade P5) | — | 4 |
| stg_draft_results | src nhl.raw_draft_results, nhl.raw_player_draft_origin | draft_year×overall_pick | historical draft results universe (Draft Value tool) | int_draft_player_value | 6 |
| stg_edge_goalies | src nhl.raw_edge_goalies | goalie×season | NHL Edge goalie season aggregates | mart_goalie_season | 2 |
| stg_edge_skaters | src nhl.raw_edge_skaters | player×season×game_type | NHL Edge skater season aggregates (pivoted) | mart_edge_player_profile | 2 |
| stg_edge_teams | src nhl.raw_edge_teams | team×season | NHL Edge team danger-bucket shares | mart_edge_team_profile | 2 |
| stg_game_context | src nhl.raw_game_landing, nhl.raw_game_right_rail | game | pregame/postgame context (scratches, coaches, series) | — | 2 |
| stg_games | src nhl.raw_games, stg_boxscores | game | schedule spine enriched with played-game detail | stg_roster_current | 6 |
| stg_gm_tenures | src nhl.raw_gm_tenures | gm×team×start_date | curated GM tenures (trade-outcome attribution SoT) | — | 4 |
| stg_goalie_starts | src nhl.raw_boxscores | goalie start | goalie starts derived from boxscores | mart_goalie_season | 0 |
| stg_partner_odds | src nhl.raw_partner_odds | odds snapshot | de-vigged implied win prob — INTERNAL CALIBRATION ONLY (no API/UI by design) | — | 0 |
| stg_play_by_play | src nhl.raw_play_by_play | event | PBP events unnested, one row/event | int_assists, int_goalie_shots, int_on_ice_events, int_rink_bias, int_score_state_weights, int_segment_context, int_shot_attempts, int_shot_attempts_all, int_shot_score_adj, int_shot_sequence, int_zone_entry_proxy, mart_player_game_score, mart_player_game_stats, mart_team_faceoffs, mart_team_game_stats, mart_team_identity, mart_team_zone_time | 8 |
| stg_player_bio | src nhl.raw_player_bio | player | player bio | — | 0 |
| stg_ppt_tracking_frames | src nhl.raw_ppt_replay | game×event×frame×entity | **PUCK TRACKING — RETAINED** ppt-replay goal frames | int_goal_release_frame | 2 |
| stg_prospects | src nhl.raw_prospects | prospect | typed org prospect lists (Trade P5) | — | 5 |
| stg_roster_current | src nhl.raw_rosters, stg_games | player | live team-roster membership (current affiliation) | int_player_current_team | 3 |
| stg_rosters | src nhl.raw_play_by_play | player×game | game-derived roster (one row/player/game) | int_player_current_team, int_shift_segments, mart_player_contracts, mart_player_game_stats, mart_player_situational, mart_player_zone_deployment, mart_tradeable_assets, stg_trades | 8 |
| stg_shifts | src nhl.raw_shift_charts | player×shift×game | one row/shift/player (goal-annotation rows excluded) | int_shift_segments, mart_edge_player_profile, mart_player_game_stats, mart_team_identity | 3 |
| stg_standings | src nhl.raw_standings | team×date | league standings as of a date | — | 2 |
| stg_statsrest_faceoffs | src nhl.raw_statsrest_faceoffs | player×season | season per-player faceoff zone splits | mart_player_faceoff_zones | 2 |
| stg_trades | src nhl.raw_trades, stg_rosters | trade×asset | typed historical trades w/ resolved_player_id (Handoff 5 D) | — | 5 |

### 1b. Intermediate (20) — schema `nhl_staging`

| model | mat | pb / cl | upstream | grain / purpose | downstream | tests |
|---|---|---|---|---|---|---|
| int_assists | view | — | stg_play_by_play | assist per goal (1st/2nd) | mart_player_game_stats | 7 |
| int_draft_player_value | table | — | src nhl_models.player_pwar, stg_draft_results | realized career value per drafted pick | — | 5 |
| int_event_leverage | table | cl: season,shooter_id | src nhl_models.shot_xg, src nhl_models.win_probability, int_shot_sequence | per-shot leverage/WPA weight | — | 0 |
| int_goal_release_frame | view | — | stg_ppt_tracking_frames | **PUCK TRACKING — RETAINED** goal release/arrival frame per game×event×entity | — | 2 |
| int_goalie_shots | table | — | src nhl_models.shot_xg, stg_play_by_play, stg_boxscores | unblocked shot faced by goalie w/ xG+danger | mart_goalie_game_stats | 3 |
| int_line_seasons | table | cl: season,team_id | src nhl_models.shot_xg, int_segment_context, int_shift_segments, int_on_ice_events, int_shot_sequence | qualifying F3 trio / D2 pair season w/ 5v5 results | — | 6 |
| int_on_ice_events | table | — | stg_play_by_play, int_shift_segments | event joined to its shift segment w/ on-ice arrays | int_line_seasons, int_segment_5v5_results | 2 |
| int_player_current_team | view | — | stg_rosters, stg_roster_current | current-team resolution per player | — | 3 |
| int_player_onice_game **[NEW]** | table | — | int_segment_5v5_results, int_shift_segments | per game×player 5v5 on/off-ice results | mart_player_game_stats, mart_player_onice, mart_player_relative | 3 |
| int_rink_bias | table | — | stg_play_by_play, stg_boxscores | scorer-bias multipliers per arena×season | mart_player_game_stats, mart_team_game_stats | 3 |
| int_score_state_weights | table | — | int_segment_context, stg_play_by_play, stg_boxscores | league 5v5 shot-rate by score state → weights | int_shot_score_adj | 2 |
| int_segment_5v5_results **[NEW]** | table | — | src nhl_models.shot_xg, int_segment_context, stg_boxscores, int_on_ice_events | per-5v5-segment for/against xG+Corsi+goals | int_player_onice_game, mart_player_toi_matrix, mart_player_wowy | 5 |
| int_segment_context | table | — | int_shift_segments, stg_boxscores, stg_play_by_play | per game×segment strength/score/zone context | int_line_seasons, int_score_state_weights, int_segment_5v5_results | 2 |
| int_shift_segments | table | — | stg_shifts, stg_rosters | maximal unchanged-on-ice interval per game×segment×player | int_line_seasons, int_on_ice_events, int_player_onice_game, int_segment_context, mart_player_toi_matrix, mart_player_wowy | 3 |
| int_shot_attempts | view | — | src nhl_models.shot_xg, stg_play_by_play | 5v5 shot attempts w/ high-danger flag | int_shot_types, mart_team_game_stats, mart_team_stats_situational | 8 |
| int_shot_attempts_all | view | — | src nhl_models.shot_xg, stg_play_by_play | all-strength shot attempts w/ per-situation xG | mart_player_game_stats, mart_player_situational | 1 |
| int_shot_score_adj | table | — | src nhl_models.shot_xg, stg_play_by_play, stg_boxscores, int_score_state_weights | per game×team score-adj 5v5 Corsi/xG | mart_team_game_stats | 2 |
| int_shot_sequence | table | pb: game_date(day) / cl: season,team_id | stg_play_by_play, stg_boxscores | sequence-mined shot (rebound/rush/forecheck…) per unblocked attempt | int_event_leverage, int_line_seasons, mart_player_game_stats, mart_team_identity, mart_team_identity_inputs | 7 |
| int_shot_types | view | — | int_shot_attempts | 5v5 shot w/ normalized shot type | — | 9 |
| int_zone_entry_proxy | view | — | stg_play_by_play | proxy zone entries from zone-code transitions | mart_player_zone_deployment, mart_team_game_stats | 4 |

### 1c. Mart (24) — schema `nhl_mart`, all materialized `table`

| model | pb / cl | upstream | grain / purpose | downstream (dbt) | tests |
|---|---|---|---|---|---|
| mart_daily_report_feed | pb game_date(day) / cl season,team_id | mart_team_game_stats, mart_team_rolling, mart_player_game_stats | denormalized daily-report feed per game×team | — | 3 |
| mart_edge_player_profile | cl season_id,player_id | stg_edge_skaters, stg_shifts | player-season Edge profile | mart_team_identity | 2 |
| mart_edge_team_profile | cl season_id,team_id | stg_edge_teams | team-season Edge danger shares | — | 2 |
| mart_goalie_game_stats | pb game_date(day) / cl season,goalie_id | int_goalie_shots | per goalie×game GSAx | mart_goalie_season | 2 |
| mart_goalie_season | cl season,goalie_id | mart_goalie_game_stats, stg_goalie_starts, stg_edge_goalies | goalie-season GSAx + rolling + Edge | — | 2 |
| mart_player_contracts | — | src nhl_models.contract_player_map, src nhl_models.rfa_player_map, stg_contracts, stg_rosters, mart_team_game_stats, stg_contracts_rfa | matched player×contract-snapshot | mart_tradeable_assets | 6 |
| mart_player_faceoff_zones | cl season_id,player_id | stg_statsrest_faceoffs | player-season faceoff by zone | — | 2 |
| mart_player_game_score | cl season,player_id | mart_player_game_stats, stg_play_by_play | single-game "game score" per player×game | — | 0 |
| mart_player_game_stats | pb game_date(day) / cl season,player_id | stg_rosters, int_shot_attempts_all, int_assists, stg_play_by_play, int_rink_bias, stg_boxscores, int_shot_sequence, mart_team_game_stats, int_player_onice_game, stg_shifts | player×game advanced stats (hub mart) | mart_daily_report_feed, mart_player_game_score, mart_player_relative, mart_player_shooting_luck | 6 |
| mart_player_onice **[NEW]** | cl season,team_id | int_player_onice_game | season 5v5 on/off-ice per season×player×team | mart_player_wowy | 4 |
| mart_player_relative | pb game_date(day) / cl season,player_id | mart_player_game_stats, int_player_onice_game | player×game relative (on-off) metrics | — | 0 |
| mart_player_shooting_luck | pb game_date(day) / cl season,player_id | mart_player_game_stats | player×game shooting-luck (xG vs actual) | — | 0 |
| mart_player_situational | pb game_date(day) / cl season,player_id | stg_rosters, stg_boxscores, int_shot_attempts_all | player×game situational (strength splits) | — | 0 |
| mart_player_toi_matrix **[NEW]** | cl season,team_id | int_segment_5v5_results, int_shift_segments | pairwise shared 5v5 TOI per season×team×playerA<playerB | — | 6 |
| mart_player_wowy **[NEW]** | cl season,team_id | int_segment_5v5_results, int_shift_segments, mart_player_onice | WOWY per season×team×focal→partner | — | 6 |
| mart_player_zone_deployment | pb game_date(day) / cl season,player_id | stg_rosters, mart_team_zone_time, int_zone_entry_proxy | player×game zone deployment | — | 0 |
| mart_team_faceoffs | pb game_date(day) / cl season,team_id | stg_boxscores, stg_play_by_play | team×game faceoff results | — | 0 |
| mart_team_game_stats | pb game_date(day) / cl season,team_id | src nhl_models.team_ratings, stg_boxscores, int_shot_attempts, int_zone_entry_proxy, stg_play_by_play, int_rink_bias, mart_team_identity_inputs, int_shot_score_adj | team×game advanced stats (hub mart) | mart_daily_report_feed, mart_player_contracts, mart_player_game_stats, mart_team_identity, mart_team_rolling | 4 |
| mart_team_identity | cl season,team_id | src nhl_models.shot_xg, mart_team_game_stats, mart_team_identity_inputs, int_shot_sequence, stg_play_by_play, stg_shifts, mart_edge_player_profile | team-season identity/style profile | — | 0 |
| mart_team_identity_inputs | pb game_date(day) / cl season,team_id | int_shot_sequence, stg_boxscores | team×game inputs feeding identity | mart_team_game_stats, mart_team_identity | 0 |
| mart_team_rolling | pb game_date(day) / cl season,team_id | mart_team_game_stats | rolling 5-game team averages per team×game | mart_daily_report_feed | 4 |
| mart_team_stats_situational | pb game_date(day) / cl season,team_id | stg_boxscores, int_shot_attempts | team×game situational splits | — | 0 |
| mart_team_zone_time | pb game_date(day) / cl season,team_id | stg_boxscores, stg_play_by_play | team×game zone-time | mart_player_zone_deployment | 0 |
| mart_tradeable_assets | — | src nhl_models.player_contract_value, src nhl_models.futures_value, stg_rosters, mart_player_contracts | unified tradeable-asset layer (player/prospect/pick) per asset_id | — | 5 |

Note: 5v5-segment lineage (`int_segment_5v5_results`) is the same `nhl_models.shot_xg`
pull as `models_ml/train_rapm.py` per `int_segment_5v5_results` schema.yml description.

---

## 2. Sources (40)

Defined in `dbt/models/raw/sources.yml` (two source blocks: `nhl`, `nhl_models`).
Consumers from `child_map`.

### 2a. `nhl.raw_*` (24) — BigQuery ingested raw tables (dataset `nhl.raw`)

| source | consuming dbt model(s) |
|---|---|
| nhl.raw_boxscores | stg_boxscores, stg_goalie_starts |
| nhl.raw_contracts | stg_contracts |
| nhl.raw_contracts_rfa | stg_contracts_rfa |
| nhl.raw_draft_picks | stg_draft_picks |
| nhl.raw_draft_results | stg_draft_results |
| nhl.raw_edge_goalies | stg_edge_goalies |
| nhl.raw_edge_skaters | stg_edge_skaters |
| nhl.raw_edge_teams | stg_edge_teams |
| nhl.raw_game_landing | stg_game_context |
| nhl.raw_game_right_rail | stg_game_context |
| nhl.raw_games | stg_games |
| nhl.raw_glossary | **0 consumers** (reference/metadata; ingested data — retained) |
| nhl.raw_gm_tenures | stg_gm_tenures |
| nhl.raw_partner_odds | stg_partner_odds |
| nhl.raw_play_by_play | stg_play_by_play, stg_rosters |
| nhl.raw_player_bio | stg_player_bio |
| nhl.raw_player_draft_origin | stg_draft_results |
| nhl.raw_ppt_replay | stg_ppt_tracking_frames — **PUCK TRACKING, RETAINED** |
| nhl.raw_prospects | stg_prospects |
| nhl.raw_rosters | stg_roster_current |
| nhl.raw_shift_charts | stg_shifts |
| nhl.raw_standings | stg_standings |
| nhl.raw_statsrest_faceoffs | stg_statsrest_faceoffs |
| nhl.raw_trades | stg_trades |

### 2b. `nhl_models.*` (16) — EXTERNAL: written by `models_ml` Python, consumed by dbt

All 16 are marked "external — written by models_ml Python, consumed by dbt".
Consumers from `child_map`:

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
| nhl_models.deserved_standings | **0 dbt consumers** (external ML output; consumed by backend/models_ml, not dbt) |
| nhl_models.player_archetypes | **0 dbt consumers** (external; consumed outside dbt) |
| nhl_models.player_composite | **0 dbt consumers** (external; consumed outside dbt) |
| nhl_models.player_impact | **0 dbt consumers** (external; consumed outside dbt) |
| nhl_models.roster_forecast | **0 dbt consumers** (external; consumed outside dbt) |
| nhl_models.roster_moves | **0 dbt consumers** (external; consumed outside dbt) |
| nhl_models.streak_cards | **0 dbt consumers** (external; consumed outside dbt) |
| nhl_models.style_map | **0 dbt consumers** (external; consumed outside dbt) |

The 8 `nhl_models.*` sources with 0 dbt consumers are declared so dbt lineage docs
reference them, but they are read directly by backend/models_ml (Python), not by any
dbt model. They are ML-produced data — retained, never a deletion candidate.

---

## 3. Macros & Seeds

- **Seeds: none.** No `dbt/seeds/` directory and no `.csv` under `dbt/`.
- **Macros: 1 project macro** — `dbt/macros/generate_schema_name.sql`
  (`generate_schema_name`, `package_name='nhl_intel'`). All other manifest macros
  are dbt/adapter internals.

**`generate_schema_name` routing (verbatim from the macro):** custom schema names
are used as-is (no env prefixing). The `dbt_project.yml` `models:` block sets the
effective schema per layer via `+schema`:
- `staging` → `+schema: staging` → **`nhl_staging`**
- `intermediate` → `+schema: staging` → **`nhl_staging`** (int models land in the
  staging dataset)
- `mart` → `+schema: mart` → **`nhl_mart`**
- `raw` → `+schema: raw` (no raw .sql models exist)

So `stg_`/`int_` models materialize into the `nhl_staging` dataset and `mart_`
models into `nhl_mart`, exactly matching the prompt's stated routing rule.

---

## 4. Non-obvious loose dbt-dir scripts (5)

All five are standalone ad-hoc BigQuery inspection scripts (each opens its own
`bigquery.Client(project='nhl-intel-498216')` using the SA keyfile). None is
imported, called, or referenced by any code, Makefile, or config.

Ripgrep across the repo (`--include=*.py,*.yml,*.toml,*.sh,Makefile,*.md`,
excluding the file's own definition) found inbound references ONLY from the
inventory doc `docs/system/_inventory/00_manifest.md` (a file listing, not a
caller). Quoted, the only hits per script are of the form:
`docs/system/_inventory/00_manifest.md:54:**dbt/check_report_feed.py/** (1)` and
`docs/system/_inventory/00_manifest.md:56:- \`dbt/check_report_feed.py\``.

| script | purpose (from docstring/body) | functional inbound refs |
|---|---|---|
| dbt/check_report_feed.py | "Check mart_daily_report_feed data and schema." — prints INFORMATION_SCHEMA columns | **zero** (only 00_manifest.md listing) |
| dbt/check_xgf.py | "Check if xgf_pct exists in mart_team_game_stats." — schema probe | **zero** (only 00_manifest.md listing) |
| dbt/query_metrics.py | ad-hoc SELECT of team CF%/HDCF metrics from mart_team_game_stats | **zero** (only 00_manifest.md listing) |
| dbt/verify_calculations.py | manual verification of CF%/HDCF for a specific game (2025030314, CAR) | **zero** (only 00_manifest.md listing) |
| dbt/verify_hot_cold.py | verifies hot_cold_flag trend logic on mart_player_game_stats | **zero** (only 00_manifest.md listing) |

These are source-code utility scripts (not data). They are dead/orphaned by
reference count — recorded here as fact for Phase C; no deletion call is made here.

---

## 5. `dbt/profiles.yml` git status — RULE NOT SATISFIED (finding)

The prompt expected `dbt/profiles.yml` to be untracked (gitignored) and the rule
"profiles.yml must never be committed" to be satisfied. **The actual state
contradicts this:**

- `git ls-files --error-unmatch dbt/profiles.yml` → **exit 0** (file IS tracked).
- `git log --oneline -1 -- dbt/profiles.yml` → `b347016 Finalization: offseason
  forecast ...` (it was committed on this branch).
- `.gitignore` line 39 is `profiles.yml` and line 57 is `!dbt/profiles.yml.example`,
  but there is **no** negation forcing `dbt/profiles.yml` to be tracked — the file
  overrides the ignore only because it was already committed (`git check-ignore`
  returns exit 1 for it since tracked files bypass ignore).
- The tracked `dbt/profiles.yml` **differs** from the template and contains real
  keyfile paths:
  `line 9: keyfile: /Users/codytownsend/Desktop/nhl/NIR/secrets/nhl-intel-sa.json`
  and `line 19: keyfile: /opt/airflow/secrets/nhl-intel-sa.json`. (No secret
  material inline — the SA JSON itself lives outside the repo — but local absolute
  paths and connection config are leaked.)

**Recorded finding:** the project rule "profiles.yml must never be committed" is
currently **VIOLATED** — `dbt/profiles.yml` is tracked and committed. Remediation
(not performed here, out of read-only scope): `git rm --cached dbt/profiles.yml`.

- `dbt/profiles.yml.example` IS tracked (exit 0) and is the correct committed
  template. That part is fine.

---

## 6. Reference-count appendix (marts) — for Phase C reachability

For each of the 24 marts: dbt downstream consumer count (`child_map`, tests
excluded) + ripgrep raw-line counts of the mart name in `backend/` and `models_ml/`
(marts are consumed outside dbt). Grep = `grep -rn "<mart>" backend/ | wc -l` (and
same for `models_ml/`); these are raw line counts (a proxy, includes comments/
repeats), not unique-file counts.

| mart | dbt downstream | backend refs | models_ml refs | note |
|---|---|---|---|---|
| mart_team_game_stats | 5 | 26 | 37 | hub — heavily consumed everywhere |
| mart_player_game_stats | 4 | 20 | 25 | hub — heavily consumed everywhere |
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
| mart_daily_report_feed | 0 | 0 | 0 | **no dbt/backend/models_ml refs found — needs external check** (Airflow/report generator may read it directly; see check_report_feed.py which probes it) |
| mart_player_onice **[NEW]** | 1 | 0 | 0 | internal only (feeds mart_player_wowy) |
| mart_player_toi_matrix **[NEW]** | 0 | 0 | 0 | **no consumers found** — new model, not yet wired to backend/models_ml (unknown — needs product-surface confirmation) |
| mart_player_wowy **[NEW]** | 0 | 0 | 0 | **no consumers found** — new model, not yet wired to backend/models_ml (unknown — needs product-surface confirmation) |

Reachability caveats (labelled uncertainty, not guesses):
- `mart_daily_report_feed`: 0 refs in dbt/backend/models_ml grep, but the report
  pipeline likely reads it outside those dirs (its own inspector `check_report_feed.py`
  targets it). **unknown — needs a scan of the report/Airflow layer** before any
  reachability conclusion.
- `mart_player_toi_matrix`, `mart_player_wowy`, `mart_player_onice` are the NEW
  branch marts; low/zero external refs is consistent with being freshly added.
  **unknown — needs confirmation of the intended consuming surface.** These are
  models producing data; not deletion candidates regardless.

Grep counts are raw `wc -l` line counts (may over- or under-count true usage);
treat as a relative signal, not an exact unique-consumer count.
