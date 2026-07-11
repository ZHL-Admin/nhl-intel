# Plan: unify the "current team" number across the offseason forecast and the Roster Builder

Goal: one measured-anchor definition + one "current team" projection, so an **unedited**
`roster-evaluate` reproduces the offseason forecast's projected points for that team's current
transition (within integer rounding), with `points_delta = 0` and a ~0 delta band. Edits then delta off
that shared baseline. Per-player WAR divergence (component model vs `blended_war_rate`) stays OUT OF
SCOPE.

## Phase 0 — what the code does today (confirmed by reading)

### Offseason forecast anchor + composition
- `project_roster_forecast.load_team_ratings(bq, season)` returns, per team, the **last** `team_ratings`
  row of `season` (`ROW_NUMBER() ... ORDER BY game_date DESC` → the single **end-of-season** measured
  rating). `_run_all` passes `rc["rating"]` into `forecast_team` as `base_rating`.
- `forecast_team` → `project_rating(base_rating, net_delta, chem)` =
  `base_rating + net_delta_war*GOALS_PER_WIN/GAMES + chemistry_adj`. `projected_points =
  rating_to_points(projected_rating)`. So the offseason "current team" number =
  **single end-of-season rating + move delta + chemistry**, written to `roster_forecast` (columns
  `transition`, `base_rating`, `projected_rating`, `projected_points`, ...).

### Roster Builder baseline (today)
- `roster_evaluate` (backend/services/tools.py): `base_rating` = `absolute_rating(base_iced)` =
  **R_bottomup(current actual roster)**. `r_measured` = `_team_predictive_base(team, base_season)` =
  a **2-year recency-weighted, league-mean-regressed** measured rating (`ROSTER_BUILDER_BASE_W=[1.0,0.5]`,
  `BASE_K=1.0`). `offset = r_measured - base_rating`; `w` = minutes-weighted retained value share;
  `projected_rating = built_R_bu + w*offset`; `points_delta = SLOPE*(projected_rating - r_measured)`;
  `baseline_points = rating_to_points(r_measured)`; `baseline_rating = r_measured`.
  Unedited → w=1 → projected = r_measured, delta 0. **But r_measured ≠ the offseason's projected rating**
  (no move delta, different anchor), so the two tools disagree by ≈ the move delta.
- Absolute band: `sqrt(strength_sd^2 + SEASON_LUCK_FLOOR_PTS^2)`, `strength_sd = w*ANCHOR +
  (1-w)*BU`, `ANCHOR = ROSTER_BUILDER_STRENGTH_ANCHOR=11.45` (fit as the 68th pctile of
  |predictive_base points − actual| in `project_roster_player.head_to_head`). Delta band: raw quadrature
  of changed players' sds + `ROSTER_BUILDER_DELTA_OFFSET_W*(1-w)*|offset|*SLOPE`, no luck floor.

### The duplicated anchor
- `models_ml/project_roster_player.predictive_base(series, target_yr)` and
  `backend/services/tools._team_predictive_base(team, base_season)` are the SAME 2-year regressed blend
  (`BASE_W`/`BASE_K`), one reading a passed series, one querying `team_ratings` live. → extract one
  shared pure function `predictive_base(hist_desc, cfg)` and call it from both.

### Membership
- Already unified (prior fix): both tools resolve the current roster via
  `project_roster_forecast.offseason_updated_membership` (Roster Builder's `_team_current_members` calls
  it). So R_bottomup(current) is computed on the SAME roster in both → no membership skew.

### Reading the forecast row at serving time
- `nhl_models.roster_forecast` is a DuckDB serving table (`services.offseason` already reads it).
  `roster_evaluate` can look up `WHERE team_id = @t AND transition = '{base}->{next}'` and take
  `projected_rating` as **R_current**. Fallback: recompute via the pure `forecast_team` path; if neither
  is available, fall back to the current `predictive_base` anchor with an explicit `baseline_source` flag
  + a log line (never fabricate).

### Gates / tests today
- `head_to_head` (project_roster_player.py) is THE gate for the hybrid anchor + `sigma_anchor`.
- `validate_roster_forecast.py` (`make roster-forecast-validate`) reports Spearman rank-delta corr
  (~0.60) + MAE (~6.7 positions) + points calibration.
- Cross-tool consistency (docs cite mean gap −0.6 pts, MAE 7.8) is currently prose in
  roster-builder.md, not a gate.
- Pure-core unit tests: `tests/test_roster_forecast.py` (synthetic PlayerProj, hermetic).

## Plan

### Phase 1 — one shared anchor
- Add pure `predictive_base(hist_desc: list[float], cfg)` to `project_roster_forecast.py` (pure core).
  Reimplement `project_roster_player.predictive_base` and `tools._team_predictive_base` as thin callers.
- Switch the offseason `base_rating` from `load_team_ratings` (single end-of-season) to
  `predictive_base` over the team's `team_ratings` history (seasons ≤ base). Keep `load_team_ratings`
  for the base COMPONENTS (play_5v5/finishing/…), only the scalar anchor changes.
- Re-run `make roster-forecast-validate`; report before/after Spearman corr + MAE. **STOP + report** if
  it degrades materially. Do NOT refit `rating_to_points`.

### Phase 2 — seed the Roster Builder from the forecast
- `roster_evaluate`: `R_current` = the team's `roster_forecast.projected_rating` for the current
  transition (row lookup; else recompute via `forecast_team`; else `predictive_base` + flag).
  `offset = R_current - base_rating` (base_rating = R_bottomup(current actual), unchanged).
  `projected_rating = built_R_bu + w*offset`; `baseline_rating = R_current`;
  `baseline_points = rating_to_points(R_current)`; `points_delta = SLOPE*(projected − R_current)`
  (unedited → 0). Update `schemas.py` docstrings.
- Recalibrate `ROSTER_BUILDER_STRENGTH_ANCHOR` for R_current (68th pctile of |R_current points −
  actual| on the 63 team-seasons) via the `head_to_head`/`calibrate_absolute` machinery. Keep the delta
  band unchanged (raw quadrature + offset-fade, no luck floor). Target ~68% one-sigma coverage.
- Preserve invariants: replacement-level unfilled slots, no_track_record wide band, on_new_team
  band-only, monotonicity. Re-run the sanity checks.

### Phase 3 — gate, tests, docs, report
- Hard gate: all 32 teams, unedited roster-evaluate points == forecast points within ±1 and
  points_delta == 0. Wire into a make target alongside the existing gates.
- Unit-test the shared anchor, the R_current hybrid composition, and the fallback path.
- Docs: roster-builder.md (baselines identical by construction + the gate), roster-projection.md
  (R_measured → R_current, keep the realized-vs-projected seam + the per-player divergence limitation),
  offseason-forecast.md (Roster Builder seeds from this tool), config comments for changed constants.
- Run report in `models_ml/artifacts/reports/`: anchor before/after backtest, recalibrated band +
  coverage, 32-team before/after gap table, monotonicity.

## Risks / stop conditions
- Phase 1 anchor switch degrades the rank-delta backtest → STOP, report options (keep single-season for
  the offseason and instead unify onto IT, or a blended anchor).
- Membership date skew between the batch (roster_forecast) and live serving → both now use
  `offseason_updated_membership`; the batch row and live recompute must use the same `base_season`.
- If `roster_forecast` has no row for a team (e.g. quiet/negligible), the recompute/fallback path must
  still hit the gate (points_delta 0 vs the forecast's own projected points).
