# Roster Builder

An interactive roster sandbox. Start from a team's current roster laid out as a depth chart, freely
swap in any player in the league, and read a points-led projection live — graded lines, component and
positional breakdowns, and an honest band. It is a *what-if projection* tool, distinct from the
offseason forecast (which evaluates the moves a team actually made) and the Trade Builder (cap-aware
movements between teams). No cap or salary anywhere — explicitly out of scope.

**Current-roster baseline.** The pre-loaded roster (`_team_current_members`) is the team's real current
roster: every player on the published active roster **plus** signed non-roster/AHL players still under a
contract covering the upcoming season. It deliberately drops the "phantom" latest-game UFAs that
`dim_current_roster` keeps on a club via its game fallback (an unsigned/retired veteran resolves to his
last team) — those players are no longer on the team. This is the **same current-roster rule the
offseason forecast uses**, so the two tools open from the same roster.

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
| `LEAGUE_AVG_LINEUP_WAR` | **12.09** | league-mean projected *deployment-valid* iced-lineup WAR, so an average roster maps to `rating_abs ≈ 0` (≈ 91.5 league-average points) |
| `WAR_TO_RATING` | **0.03540** | goals/game of team rating per 1 WAR of centered lineup value |

The lineup is iced **position- and deployment-aware** (see *Effective position* and *Line assignment*
below): forwards are seated by a soft-penalty assignment over the positions they *actually* play,
defensemen by handedness side (≤3 each, left-shot → LD, right-shot → RD), with surplus and short
positions flex-filling the rest (a 5th center overflows to a wing; a 5th lefty plays his off side).
This is what a real depth chart does — you cannot ice seven centers — and `LEAGUE_AVG_LINEUP_WAR` is
calibrated on this **exact same rule** (`calibrate_roster_builder.py` shares
`project_roster_forecast.assign_forward_sides` with the live tool; a pure top-by-WAR lineup overstates
the iceable total).

`WAR_TO_RATING` is roughly **half** the offseason move-scale `GOALS_PER_WIN / GAMES_PER_SEASON`
(6/82 = 0.073). Summed lineup WAR maps to team goal-differential at a **compressed** rate — shared
ice time, opponent-adjusted regression in the measured rating, and a replacement baseline that does
not stack linearly all mean nineteen players' worth of above-replacement value does not convert
one-for-one into team goal difference. We fit the slope against the **measured** (de-lucked) rating so
the rating→points step stays the separate, already-validated map and the two calibrations do not
contaminate each other. Forcing the naive 6/82 overstates the spread and inflates the points error.

---

## Effective position: what a player actually plays

The NHL roster feed lists a *nominal* position that is often not where a player lines up — J.T.
Compher is listed at LW but has taken center-level faceoff volume for years, and dozens of listed
"centers" are really wingers who rarely take a draw. Icing off the listed position mis-seats those
players and hides real centers from center slots. So a nightly precompute,
`nhl_models.player_effective_position` (`models_ml/precompute_serving.build_player_effective_position`),
derives the position each forward *actually* plays from **faceoff volume** — the cleanest deployment
signal, since a center takes draws every shift and a winger almost never.

For each player it sums `stg_statsrest_faceoffs` over the last `EFFECTIVE_POSITION.FO_WINDOW_SEASONS`
(**2**) seasons (regular season + playoffs, GP-weighted) and classifies forwards by faceoffs-per-game:

| condition (games ≥ `FO_MIN_GP` = 10) | effective position | locked |
|---|---|---|
| `fo_per_gp ≥ FO_CENTER_PER_GP` (**7**) | `C` | yes |
| `fo_per_gp ≤ FO_WINGER_PER_GP` (**2.5**) | winger — listed side if L/R, else by handedness (L-shot → L, R-shot → R) | yes |
| otherwise / thin sample / rookie | `F_FLEX` (fills any forward slot) | no |
| no faceoff rows at all | *absent* → the builder falls back to the listed position | — |

Defensemen and goalies pass through unchanged (`effective = listed`, locked). Thresholds live in
`config.EFFECTIVE_POSITION` and are validated on the disagreement list: Compher and thirteen other
two-way centers listed on the wing flip to `C`; established wingers (Kucherov, Marchand, Rantanen,
Nylander) stay wingers; real centers stay `C`. **Fail loud, never fabricate** — a player with no
faceoff evidence keeps his listed position, never a guess. The same map also feeds `roster_suggest`
(a wing-listed center is offered for `C` slots; an `F_FLEX` matches any forward slot) and the
offseason forecast's displayed lineup (Compher appears at `C` there too).

## Line assignment: stick at C unless a wing is required

Given the pool's effective positions, forwards are seated by solving an **assignment problem** over
(forward, forward-slot) rather than a greedy column fill (`assign_forward_sides`, shared by the tool
and its calibration, `scipy.optimize.linear_sum_assignment`):

```
value(player, slot) = projected_war − off_position_penalty(player, slot)          # maximize the total
```

The penalties (WAR units, `config.ROSTER_FORECAST`, tune-friendly) bias placement toward natural
positions:

| situation | penalty |
|---|---|
| a **locked** C at a wing, or a **locked** winger at C | `OFF_POSITION_PENALTY_CW` = **0.35** |
| a winger on his off side (L on RW, R on LW) | `WING_SIDE_PENALTY` = **0.05** |
| an `F_FLEX` forward anywhere | 0 |

**The penalty shapes the assignment only.** It decides *who sits where* — so a center sticks at C
unless the pool genuinely needs him on a wing (a 5th locked center overflows to a wing, paying the
penalty), and a winger prefers his side. It is **never** subtracted from `lineup_value` or the team
WAR total: a player's value does not shrink because he is off his natural spot; the optimizer simply
avoids it. `LEAGUE_AVG_LINEUP_WAR` and `WAR_TO_RATING` are calibrated on the *raw* iced WAR this
assignment produces. Output is deterministic (forwards pre-sorted by `(−projected_war, player_id)`, so
equal-value ties resolve stably); a pool under twelve forwards leaves replacement holes, never a
dropped slot. Defense-pair assignment (handedness) and the goalie tandem are unchanged.

## Deployment-aware line seeding: reproduce observed units, don't WAR-stack

A pure best-C + best-LW + best-RW build is not how a team actually deploys. Edmonton splits Connor
McDavid and Leon Draisaitl across two 5v5 lines (they reunite only on the power play), yet a WAR-greedy
builder stacks them on line 1. So **before** the assignment, the builder *seeds* observed units
(`project_roster_forecast.seed_and_assign_forwards` / `seed_and_assign_defense`):

- **Candidate units** are the team's `int_line_seasons` forward trios and defense pairs for the base
  season — loaded by the **same** `project_roster_forecast.load_seed_units` the offseason forecast uses,
  so both tools seed from the identical units and ice the identical lineup from the same roster. A unit
  qualifies only when its **full member set is present and unplaced** in the pool and it clears the
  shared-5v5 floor (`LINE_SEED_MIN_5V5_MINUTES = 100`).
- Units are accepted greedily in descending shared minutes, skipping any that conflict with an
  already-placed player. Accepted units are ranked into line/pair order by combined projected WAR
  (best unit = line 1). Within a trio the C slot goes to the member with the highest faceoffs/game;
  wings take their effective side (handedness as tiebreak). Within a pair the left-shot takes LD.
- Everyone left — **all arrivals and edited-in players, who by construction never played with the
  group** — flows through the Phase 1 assignment for the remaining slots.

This needs no special gating: trade Draisaitl away and his units dissolve automatically because the
member-set check fails; his linemates fall to the assignment. It reproduces the McDavid/Draisaitl 5v5
split because the observed data contains it (their dominant trios are *separate*; their shared-line
minutes fall below the floor). **Power-play units are out of scope** — the seeding is 5v5 deployment
only. The live re-evaluate path stays fast: seeding + assignment are `O(small)` with no per-edit model
scoring, and the observed-unit lookup is cached per team.

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

### Cross-tool consistency — identical by construction

For a team's current roster with **no edits**, the Roster Builder reproduces the offseason forecast's
projected points **exactly** (within integer rounding), with `points_delta = 0`. This is not a
coincidence to be measured — it is guaranteed by construction: the unedited baseline anchors on
**R_current**, the offseason forecast's own projected rating for the team's current transition (read
from the `roster_forecast` serving row; `tools._forecast_current_rating`). The hybrid
`projected_rating = R_bottomup(built) + w·(R_current − R_bottomup(current actual))` collapses to
`R_current` at `w = 1` (nothing changed), so `baseline_points = rating_to_points(R_current)` = the
forecast's number. Both tools also share ONE **measured anchor** — the 2-year regressed
`predictive_base` (§ *A single measured anchor* / `project_roster_forecast.predictive_base`) — and ONE
current-roster membership, so nothing upstream can make them disagree.

A hard gate enforces it: `make baseline-consistency`
(`scripts/validate_baseline_consistency.py`) fails if any of the 32 teams' unedited baseline drifts more
than ±1 point from the forecast or has a non-zero `points_delta`. If the `roster_forecast` row is
missing for a team, `baseline_source` flips to `measured_anchor` (the shared `predictive_base`) and a
log line records it — never a fabricated number.

Edits then delta off this shared baseline exactly as before (the retained-value share `w` fades
`R_current` toward the pure bottom-up rating as the roster turns over). **NOTE:** the two tools still
project individual *players* differently (component model vs the shared `blended_war_rate`) — that
per-player divergence is documented in `roster-projection.md` and is out of scope here; it does not
affect the shared *team* baseline, which is one number.

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
