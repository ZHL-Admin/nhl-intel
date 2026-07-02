# Phase 0 findings — on-ice reconstruction, WOWY, RAPM, rankings

Discovery output for the on-ice / WOWY / RAPM / rankings implementation brief. Every
later phase cites these facts instead of guessing. Written 2026-07-01 against branch
`finalization`.

> **Headline: the brief reads as greenfield, but the repository is not.** The shift feed,
> the stint keystone, on-ice event attribution, and a full RAPM model already exist under
> different names and, in the RAPM case, exceed the brief's v1. This document maps the
> brief's assumed names to what is really there, and records what is genuinely missing.
> The build that follows reuses the existing backbone rather than forking it.

---

## 0.1 The shift feed — already ingested

The brief's "one new external input" (`api.nhle.com/stats/rest/en/shiftcharts`) is
**already ingested** into `nhl_raw.raw_shift_charts` (declared in
`dbt/models/raw/sources.yml`, one row per game, shift array serialized as JSON in `data`).

- **Shift-vs-marker discriminator (confirmed, in-repo):** `stg_shifts.sql` documents it
  empirically — `typeCode 517` = real shifts; `typeCode 505` = goal annotations (null
  duration, excluded). This is the exact discriminator the brief's Phase 0 asked us to find.
- **Absolute game time:** `(period - 1) * 1200 + mm*60 + ss`, computed in `stg_shifts`
  (`shift_start_seconds`, `shift_end_seconds`) and reused identically in
  `int_shift_segments`, `int_on_ice_events`, `int_segment_context`. Matches brief D5.
- **OT handling:** the existing formula already covers OT slots (period 4 = 3600s, etc.),
  i.e. it is *not* regulation-only. v1 analytical marts filter to 5v5 via strength state,
  not by truncating periods.

**Implication:** Brief Phases 1 (ingestion) and 2 (staging) are **done**. No `raw_shifts`
table, no `fetch_shift_charts` client, no `ingest_shifts` DAG task needs to be created —
they exist in equivalent form.

## 0.2 Fixture game / probe

Not re-run. The feed is already ingested for the full backfill window and the empirical
discriminator is already baked into `stg_shifts`, so a fresh probe would only re-confirm
what the staging model documents. If a fixture is needed for a future ingestion test,
`models_ml/train_rapm.py` and the existing models already exercise the feed end-to-end
across seasons `2021-22`..`2025-26`.

## 0.3 game_id type

`game_id` is stored/consumed as **INT64** throughout staging and mart (e.g.
`cast(... as int64)` in `stg_shifts`; `substr(cast(game_id as string), 5, 2)` game-type
filters in `mart_team_game_stats`). New models match this — no string game_ids.

---

## 0.4 Column inventory (role → real column)

Confirmed by reading each model. New models refer to these exact names.

### `stg_play_by_play` (staging)
| role | column |
|---|---|
| event id | `event_id` |
| event type | `type_desc_key` (`'goal'`, `'faceoff'`, `'shot-on-goal'`, `'missed-shot'`, `'blocked-shot'`, `'hit'`, `'giveaway'`, `'takeaway'`, `'penalty'`, …) |
| period | `period_number` (+ `period_type`, `'SO'` for shootout) |
| in-period time | `time_in_period` (`mm:ss` string) |
| coordinates | `x_coord`, `y_coord` |
| zone | `zone_code` (`'O'`/`'N'`/`'D'`, **relative to `event_owner_team_id`**) |
| strength | `situation_code` (`'1551'` = 5v5; digits = away goalie / away skaters / home skaters / home goalie) |
| event-owner team | `event_owner_team_id` (the **attacking/shooting** team, incl. for blocked shots) |
| ordering | `sort_order` |

### `int_shot_attempts` (intermediate) — the xG basis, **5v5 only** (`situation_code='1551'`)
| role | column |
|---|---|
| shooting/attacking team | `event_owner_team_id` |
| expected goals value | `xg_value` (`coalesce(nhl_models.shot_xg.xg, 0.0)`; blocked & empty-net = 0 by design) |
| goal flag | `is_goal` |
| shot-on-goal flag | `is_on_net` |
| block flag | `is_blocked` (`type_desc_key = 'blocked-shot'`) |
| Corsi universe | `type_desc_key in ('shot-on-goal','goal','missed-shot','blocked-shot')` |

`int_shot_attempts_all` is the all-situations sibling (no `1551` filter, excludes `SO`).

### xG source: `nhl_models.shot_xg` (dbt **source**, written by `models_ml/score_xg.py`)
One row per `(game_id, event_id)`; columns `xg`, `base_rate`, `model_version`. Unblocked,
non-empty-net, non-shootout only. **This is the only xG source. Do not build a new xG model.**

### `int_shift_segments` (intermediate) — **this IS the brief's `int_stints`**
Grain: one row per `(game_id, segment_index, player_id)`.
`game_id, season, segment_index, segment_start_seconds, segment_end_seconds,
segment_duration, player_id, team_id, position_code, is_goalie, team_skater_count,
team_goalie_count`. Boundary-union interval algorithm (brief D6/D7), `segment_duration > 0`
(brief D16), `>6 skaters/side` overlap noise excluded.

### `int_segment_context` (intermediate) — per-segment situation
Grain: one row per `(game_id, segment_index)`.
`home_team_id, away_team_id, home_skaters, away_skaters, home_goalies, away_goalies,
strength_state ('5v5','5v4','4v5','EN',…; home perspective), home_score, away_score,
home_score_state ('leading'/'tied'/'trailing'), is_zone_start, zone_start_code`.

### `int_on_ice_events` (intermediate) — **this IS the brief's `int_stint_events` attribution**
Grain: one row per `(game_id, event_id)`. `type_desc_key, event_owner_team_id, event_seconds,
segment_index, on_ice_for[] (owner-team skaters), on_ice_against[] (opponent skaters)`.
Events attribute to segment `(start, end]` so stoppage events credit the line that was playing.

### `stg_boxscores` (staging)
`game_id, season (STRING), game_date (DATE), home_team_id, away_team_id, home_team_score,
away_team_score`. **Used for game_date + home/away resolution** (new segment/context models
carry `season` but not `game_date`).

### `stg_rosters` (staging)
`game_id, game_date, season, player_id, team_id, first_name, last_name, position_code`
(`'C'/'L'/'R'/'D'/'G'`). Player→position and player→name map.

### `mart_player_game_stats` (mart) — proxy confirmed
`on_ice_xgf_pct` is literally the **team proxy**: `m.team_xgf_pct as on_ice_xgf_pct`
(with the comment "On-ice xGF% proxy: use team xGF% as approximation … True on-ice xGF%
requires shift-by-shift tracking not available in this model"). That claim is now stale —
the shift-by-shift tracking exists. Every other column is preserved by the Phase-4 edit.
Real per-game denominator is `estimated_toi_5v5_minutes` (all-situations shift TOI, kept
under the legacy name `toi_5v5`).

### `mart_player_relative` (mart) — misleading definition confirmed
Computes **player − team-average** (`ixg_per60_rel`, `primary_points_per60_rel`,
`on_ice_xgf_pct_rel`), grain `(game_id, player_id)`, partitioned by `game_date`. This is
not on-ice-minus-off-ice. See §0.7 for the breaking-change constraint.

---

## 0.5 situationCode digit order

`situation_code = '1551'` is used repository-wide as the 5v5 filter (`int_shot_attempts`,
`int_zone_entry_proxy`, `int_shot_sequence`). Digits are **away-goalie / away-skaters /
home-skaters / home-goalie**. Consistent with the brief's cross-check role — but note
**strength for the analytical marts comes from shift-derived counts** (`int_segment_context.
strength_state`), not `situation_code`, which is what the brief wanted (shift counts
authoritative). The two agree at 5v5.

---

## 0.6 RAPM already exists — and exceeds brief v1

`models_ml/train_rapm.py` implements the brief's Phase 5 in full, on the exact stack
(`int_shift_segments × int_segment_context × int_on_ice_events × nhl_models.shot_xg`):

| brief spec | existing implementation |
|---|---|
| two rows per stint, one per attacking direction | `expand_rows()` |
| two-sided player features (off column + def column) | `build_design(two_sided=True)` |
| ridge, `rapm_def = -coef(def)` | `player_impacts()` centres & negates def |
| alpha by game-grouped CV | `cv_alpha()` (grid `[250..8000]`) |
| bootstrap uncertainty | `bootstrap_sd()` — game-resample, reports **SD** |
| controls: zone start, score state, home | present, **plus** back-to-back + season FE |
| ≥200 5v5-min qualification | `toi_min >= 200` in `report()` |
| single-season v1; multi-year as D21 extension | ships **both**: 3-season weighted window + singles, **plus** PP/PK special-teams impacts |

Output table: **`nhl_models.player_impact`** (dbt source), grain `(player_id,
season_window)`, columns `off_impact, def_impact, off_sd, def_sd, pp_impact, pp_sd,
pk_impact, pk_sd, toi_min, alpha, model_version`. Methodology at
`docs/methodology/isolated-impact.md`.

**Differences from the brief's `mart_player_rapm` spec** (intentional, keep the existing one):
- key is `season_window` (a single season *or* `"2023-24_2025-26"`), not `season`.
- uncertainty is **SD** (`off_sd`/`def_sd`), not 2.5/97.5 CI percentiles. A CI is
  `impact ± 1.96·sd` if a downstream needs bounds.
- naming is `off_impact`/`def_impact` (goals-per-60, higher=better), not
  `rapm_off`/`rapm_def`/`rapm_total`.

`player_impact` is **load-bearing**: consumed by `compute_composite`, `compute_gar`,
`compute_player_radar`, `compute_deployment_efficiency`, `build_verdict_payload`,
`archetype_features`. **Do not build a duplicate `mart_player_rapm`.** The rankings work
(brief Phase 6) should read `player_impact`, translating `off_impact+def_impact` →
`rapm_total` and `sd` → CI at read time.

Also already present: `models_ml/compute_composite.py` (→ `nhl_models.player_composite`,
per-player value stack), `compute_gar`, `compute_player_radar` — i.e. a transparent
multi-component player-value layer already exists, which overlaps brief Phase 6's intent.

## 0.6b Line/pair chemistry already partially exists

`int_line_seasons` computes, per season/team, every F3 trio and D2 pair that shared
≥ `var('line_min_5v5_minutes')` of 5v5 ice, with on-ice `xgf_pct`, `xgf_per60`,
`xgf_per60_against` and the shot-sequence mix — feeding `train_linefit.py` / `score_line.py`
(Lineup Lab). This is *line-constrained* (exact trios/pairs), **not** arbitrary-pair WOWY,
so the brief's `mart_player_wowy` / `mart_player_toi_matrix` remain genuinely missing, but
they share the same segment backbone.

---

## 0.7 Done vs. missing vs. conflicting

| brief phase / artifact | status | action |
|---|---|---|
| P1 shift ingestion (`raw_shifts`, client, DAG) | **DONE** as `raw_shift_charts` + `stg_shifts` | none |
| P2 `stg_shifts` | **DONE** | none |
| P3 `int_stints` / `int_stint_events` | **DONE** as `int_shift_segments` / `int_on_ice_events` (+ `int_segment_context`) | none |
| P4 `int_player_onice_game` | **MISSING** | build |
| P4 `mart_player_onice` | **MISSING** | build |
| P4 `mart_player_toi_matrix` | **MISSING** | build |
| P4 `mart_player_wowy` | **MISSING** | build |
| P4 fix `mart_player_game_stats.on_ice_xgf_pct` | proxy confirmed | fix **additively** (keep column name, add off/rel) |
| P4 redefine `mart_player_relative` | **CONFLICT** (see below) | additive columns only in this pass |
| P5 RAPM (`mart_player_rapm`, modeling job, weekly DAG) | **DONE & exceeds** as `nhl_models.player_impact` + `train_rapm.py` | reuse; no duplicate |
| P6 rankings/entanglement/carry/partner-adj | **MISSING** (composite/GAR partially overlap) | out of this pass's chosen scope; buildable on `toi_matrix`/`wowy`/`player_impact` |
| P7 backend API | deferred by user | not touched |
| P8 frontend | deferred by user | not touched |

### Conflict: `mart_player_relative` is a breaking change into deferred backend
The brief's Phase 4 says to **rename** `mart_player_relative`'s columns to `rel_xgf_pct` /
`rel_cf_pct` and drop the player-minus-team-average columns. But `mart_player_relative` is
consumed by **`backend/routers/teams.py`, `backend/routers/players.py`,
`backend/services/bigquery.py`** (and documented in `backend/API_EXPANSION_SUMMARY.md`).
The user scoped this pass to **stop before the backend/frontend**. Renaming/removing columns
now would break the API without the deferred consumer fix.

**Decision for this pass (additive, non-breaking):** keep the existing
player-minus-team-average columns in `mart_player_relative`, and **add** true
`rel_xgf_pct` / `rel_cf_pct` (on-ice minus off-ice, from `mart_player_onice`). The hard
rename + consumer migration is left for the Phase 7 backend pass, where the API layer is
updated in the same change. This is flagged so it is not lost.

---

## 0.8 Conventions / decisions applied by the build

- **Game-type filter:** analytical 5v5 marts include regular season + playoffs
  (`substr(cast(game_id as string),5,2) in ('02','03')`), matching `train_rapm.py`, so the
  on-ice/WOWY numbers and RAPM share the same universe. (`mart_team_game_stats` additionally
  keeps `'01'` preseason; the new marts exclude it to avoid preseason noise in xGF%.)
- **Strength:** 5v5 = `int_segment_context.strength_state = '5v5'` (shift-derived, brief D1/D2).
- **Corsi / xG attribution:** reuse the team-model convention — `event_owner_team_id` is the
  attacking team for all four attempt types; CF/CA/GF/GA counted from `type_desc_key`, xGF/xGA
  summed from `shot_xg` (identical to `train_rapm.py`'s pull), so player on-ice numbers
  reconcile with `mart_team_game_stats`.
- **Pair TOI threshold:** WOWY `small_sample = toi_together_sec < 3000` (50 min, brief D17).
- **New-model naming:** `int_segment_5v5_results` (segment fact), `int_player_onice_game`,
  `mart_player_onice`, `mart_player_toi_matrix`, `mart_player_wowy`. Season-grain marts
  cluster by `season, team_id` (no `game_date` partition); game-grain intermediate is not
  partitioned (intermediate).
- **Env note:** dbt 1.11 + `secrets/nhl-intel-sa.json` are present, so models are validated
  with `dbt parse`/`compile`; full `dbt run`/`dbt test` against BigQuery (which incurs cost)
  is left for the user to execute — the acceptance-gate runs from the brief require live data.
