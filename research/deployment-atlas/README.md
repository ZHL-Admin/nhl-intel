# Deployment Atlas

Research pipeline that reconstructs NHL on-ice presence from shift charts + play-by-play
and produces context-corrected player ratings and coach deployment fingerprints.
Isolated research repo under `NIR/research/deployment-atlas`; removable by deleting the
folder (production is read-only except the two explicitly-gated shift ingestions).

- **Scope:** regular seasons 2010-11 → 2025-26 (primary modeling 2015-16+).
- **Reports:** `reports/phase0.md` … `phase5.md`, `reports/FINDINGS.md`, `reports/upstream-ledger.md`.
- **Reproduce:** `make all` (rebuild tables from cache), `make report` (rebuild figures), `make test`.
- **Query:** `src/atlas/api.py` — `rapm_table`, `player_context`, `team_fingerprint`, `shared_toi`.

## Table schema freeze (Phase 6.1 — frozen 2026-07-10)

For each table: grain, key columns, and **adopt** (reused production asset) vs
**derive** (built in the research layer). All Parquet under `data/parquet/`.

### `shifts` — `shifts.parquet`
Grain: one row per shift (player, game). `game_id, season_start_year, season_label,
is_primary_scope, player_id, team_id, period, shift_number, shift_start_seconds,
shift_end_seconds, duration_seconds`.
**Derive:** reuses `stg_shifts`'s transformation (517-filter, `(period-1)*1200`) but
reads `raw_shift_charts` directly, **hardened** (SAFE_CAST) and **exact-dup-removed**.
Includes the 563 HTML-backfilled games.

### `events` — `events.parquet`
Grain: one row per pbp event. `game_id, …, event_id, sort_order, period_number,
period_type, time_in_period_s, event_second, situation_code, home_team_defending_side,
type_code, type_desc_key, x_coord, y_coord, zone_code, shot_type, shooting_player_id,
scoring_player_id, goalie_in_net_id, assist1/2_player_id, event_owner_team_id,
home_score, away_score, source`.
**Adopt:** `stg_play_by_play`, plus 2 gap-fetched games (`source='api:gap_fetch'`).

### `stints` — `stints.parquet`
Grain: one row per stint (personnel + score constant). `game_id, season_label, stint_id,
start_seconds, end_seconds, duration_seconds, home_skater_ids[], away_skater_ids[],
home_goalie_id, away_goalie_id, strength_state, home_score, away_score, score_state,
start_type, is_playoffs, is_quarantined, home/away_corsi/fenwick/sog/goals, home/away_xg`.
**Derive:** boundary-union of shift starts/ends **+ goal seconds** (Amendment A), from the
clean corpus (production `int_shift_segments` was stale + dup-contaminated).

### `player_season_rates` — `player_5v5.parquet`
Grain: (player, season). `player_id, season_label, toi_s, toi_min, xgf, xga, cf, ca, gf,
ga, xgf_per60, xga_per60, xg_share, cf_per60, ca_per60, gf_per60, ga_per60`. Min 200 min.
**Derive:** from `stints` (xG from adopted `shot_xg`), strength from the ice.

### `rapm` — `rapm_variant.parquet` (+ production `nhl_models.player_impact`)
Grain: (player, season). `player_id, off_impact, def_impact, toi_min, alpha, prior_weight,
season`. **Per rating column:** `off_impact` / `def_impact` = **Atlas variant** (research-
derived on clean stints; the adopted internal rating). Production `player_impact`
(`off/def/pp/pk` + SDs) is **adopted-but-held** — audited sound in design but built on the
stale segment backbone; available in BigQuery, not the Atlas rating of record.

### `context_metrics` — `player_context_{season}.parquet`
Grain: (player, season), min 200 5v5 min. `player_id, toi_5v5_s/min, oz_starts, dz_starts,
oz_start_share, pp_s, pk_s, pp_share_of_own, pk_share_of_own, qoc, qot, strictness`.
**Derive:** QoC/QoT = shared-TOI-weighted mean opponent/teammate prior-season **Atlas variant** rating.

### `fingerprints` — `coach_fingerprints_{season}.parquet`
Grain: (team, season). `team_id, top6_fwd_toi_share, home_away_strictness,
zone_start_polarization, close_game_shortening`.
**Derive.** ⚠️ `home_away_strictness` failed last-change validation (Phase 5.6) —
descriptive only; the other three validated (bench shortening positive for all 32 teams).

### `with_matrix` / `against_matrix` — query-derived via `api.shared_toi`
Grain: (season, player_id_a, player_id_b, relation, toi_seconds), `relation ∈ {with, against}`.
**Derive** on demand from `stints` (not materialized — the full pairwise matrix is
multi-million-row; the production WOWY marts were stale + teammates-only).

### `movers_eval` — `movers_eval.parquet`
Grain: one row per held-out mover. `player_id, pair, actual_xg_share, pred_raw,
pred_variant, err_raw, err_variant`. **Derive** (Phase 5 leave-one-pair-out).
