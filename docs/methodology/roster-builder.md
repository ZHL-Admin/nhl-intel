# Roster Builder

An interactive roster sandbox. Start from a team's current roster laid out as a depth chart, freely
swap in any player in the league, and read a points-led projection live — graded lines, component and
positional breakdowns, and an honest band. It is a *what-if projection* tool, distinct from the
offseason forecast (which evaluates the moves a team actually made) and the Trade Builder (cap-aware
movements between teams). No cap or salary anywhere — explicitly out of scope.

It reuses the offseason forecast engine end to end: every player projects to the same WAR he does in
the offseason tool and the contract grader (`project_skater_war` / `project_goalie_war` →
`blended_war_rate` + aging), lineups are built with `build_lineup` (an unfilled slot is a
replacement-level hole, never dropped), lines are graded cold-start with the Lineup Lab's
`score_line`, the chemistry nudge is the same bounded `chemistry_adjustment`, the band is
`forecast_band` + `inflate_arrival_bands`, and points come from the shared `rating_to_points` map.
The **only** new model code is the absolute-rating helper and one calibrated constant.

---

## The one new piece: an absolute rating

The offseason forecast computes a team's projected rating as

```
projected_rating = base_rating + net_delta_war · (GOALS_PER_WIN / GAMES_PER_SEASON) + chemistry_adj
```

It can do that because it **trusts the team's measured power rating** (`team_ratings`) for the
returning core and only adjusts for the moves. The Roster Builder has no trustworthy base — the user
may have rebuilt the roster from scratch — so it derives the rating from the roster's *own* projected
value (`models_ml/project_roster_forecast.absolute_rating`):

```
rating_abs       = (total_iced_lineup_WAR − LEAGUE_AVG_LINEUP_WAR) · WAR_TO_RATING + chemistry_adj
projected_points = rating_to_points(rating_abs)          # the shared Handoff-10 map, clamped [0, 164]
```

`total_iced_lineup_WAR` is `lineup_value` over the 12 forwards / 6 defensemen / 1 starting goalie
(`N_GOALIE = 1` — the backup dresses but the value model counts one goalie's WAR). The two constants
live once in `config.ROSTER_FORECAST` and are calibrated by `models_ml/calibrate_roster_builder.py`:

| constant | value | meaning |
|---|---|---|
| `LEAGUE_AVG_LINEUP_WAR` | **12.53** | league-mean projected *position-valid* iced-lineup WAR, so an average roster maps to `rating_abs ≈ 0` (≈ 91.5 league-average points) |
| `WAR_TO_RATING` | **0.03174** | goals/game of team rating per 1 WAR of centered lineup value |

The lineup is iced **position-aware** — forwards fill their natural C/L/R column (≤4 each), defensemen
their handedness side (≤3 each, left-shot → LD, right-shot → RD), with surplus and short positions
flex-filling the rest (a center covers a thin wing slot; a 5th lefty plays his off side). This is what
a real depth chart does — you cannot ice seven centers — and `LEAGUE_AVG_LINEUP_WAR` is calibrated on
this same basis (a pure top-by-WAR lineup overstates the iceable total by ~0.85 WAR).

`WAR_TO_RATING` is roughly **half** the offseason move-scale `GOALS_PER_WIN / GAMES_PER_SEASON`
(6/82 = 0.073). Summed lineup WAR maps to team goal-differential at a **compressed** rate — shared
ice time, opponent-adjusted regression in the measured rating, and a replacement baseline that does
not stack linearly all mean nineteen players' worth of above-replacement value does not convert
one-for-one into team goal difference. We fit the slope against the **measured** (de-lucked) rating so
the rating→points step stays the separate, already-validated map and the two calibrations do not
contaminate each other. Forcing the naive 6/82 overstates the spread and inflates the points error.

---

## Projection, not measurement — read this before trusting the number

**This is a forward projection with a band, not a measured power rating.** That distinction is the
whole reason the tool is delta-led, and it is grounded in the calibration
(`calibrate_roster_builder.py`, 63 team-seasons over the two completed forward transitions
2023-24→2024-25 and 2024-25→2025-26 opening rosters):

- **The value system reconciles.** A team's *realized* roster WAR tracks its measured power rating at
  **corr ≈ 0.82** — summing player value reproduces team strength. The engine is sound; lineup
  construction, the scale, and the league-average centering are right.
- **The season-ahead projection is genuinely uncertain.** Projecting a roster a full season forward
  (prior-season player value + aging) tracks the measured rating at only **corr ≈ 0.44**. The entire
  drop from 0.82 to 0.44 is the per-player *projection* step, not roster construction (realized WAR on
  *opening* rosters still correlates 0.82). This is ordinary preseason-projection difficulty, made
  harder by there being only a few seasons of single-season WAR history to blend.
- **Points error decomposed.** Projected vs *actual* standings points is **MAE ≈ 10.5**. Of that,
  **~5.2 points is irreducible in-season luck** — even the *measured* end-of-season rating predicts
  actual points only to MAE 5.2 (corr 0.90). The projection's own error against de-lucked strength is
  **MAE ≈ 7.9**.

So the **absolute projected-points number is a soft, season-ahead estimate** and is presented as
secondary, with a band wide enough to be honest. The **headline is the delta vs the team's real
roster** (`points_delta`), because that rides on *relative* player value — shared players cancel and
only the swapped value matters — which is the engine's core competency and far more trustworthy than
the summed absolute level. This mirrors how the offseason tool leads with its move-delta anchored on a
measured base.

### Cross-tool consistency

For a team's current roster with no changes, the Roster Builder's pure-projection baseline agrees with
the offseason tool's measured-rating-anchored projection with **no systematic bias**: mean gap
**−0.6 points**, MAE 7.8, sd 10.0 across 32 teams. The per-team spread is exactly the expected
projection-vs-measured difference — a team whose measured rating exceeds its roster's projected talent
(e.g. on the back of hot goaltending or finishing) reads lower here, because a forward projection will
not assume that outperformance repeats. That offset is a feature of the distinction, not a
miscalibration.

---

## What it returns

Per the built roster (`POST /tools/roster-evaluate`): the iced lineup grouped by line / pair / goalie
(each player with projected WAR + band, age, last-season WAR, and `on_new_team` / `no_track_record`
flags); per-line fit grades from `score_line`; `projected_points` with its band; `rating_abs`
(secondary); **`points_delta` vs the team's real roster (the headline)**; the component breakdown
(5v5 play / finishing / special teams / goaltending, an additive partition of the roster's realized
WAR on a shared scale); positional values (forward / defense / goaltending projected WAR); the
chemistry adjustment; and a negligible/empty flag. A player placed on a club other than his own has
his band widened by `inflate_arrival_bands` (role/translation uncertainty) while his projection is
left unchanged.

## Limitations

- The absolute points number is a season-ahead projection (MAE ≈ 10.5 vs actual, ~5 of which is
  irreducible luck). Lead with the delta; treat the absolute level as banded guidance, not a forecast
  that beats the field.
- Single-season WAR history exists only from 2021-22, so the projection blends few windows; it will
  sharpen as more seasons land. Calibration is therefore on two forward transitions (63 team-seasons)
  — wider than a single season, but still a small sample to re-confirm as data accumulates.
- A young player with no prior WAR window projects to replacement level with a deliberately wide band
  (`no_track_record`), so a roster heavy on unproven talent reads conservatively — by design, never a
  fabricated value.
- No cap or salary modeling of any kind.
