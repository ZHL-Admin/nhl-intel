# Roster Builder — season-ahead player projection

A component-level projection of each player's next-season value, with **uncertainty calibrated from
backtest residuals**, used *only* by the Roster Builder's `roster-evaluate`. It replaces the shared
projection (`blended_war_rate` + one aging curve, with last season's *measurement* sd reused as
next-season uncertainty) for this tool. The offseason forecast, Trade Builder, and Contract Grader are
untouched and keep `blended_war_rate` — a documented, temporary divergence (promoting this model to the
shared layer is a future handoff). Built by `models_ml/project_roster_player.py`
(`make roster-player-projection`) into `nhl_models.roster_player_projection`.

## Why it exists

The [band diagnostic](roster-builder.md) showed the old uncertainty was built from within-season
measurement noise: it tracked roster composition (mostly the goalie's sd, ~1.8 WAR), and covered the
real outcome only **~52%** of the time at a nominal 1σ. This model fixes both the point estimate and —
more importantly — the uncertainty, and it reframes the tool around the **delta** (which has a genuinely
tight, honest band) rather than the absolute total (which is honestly wide because an 82-game season is
partly luck).

## The point estimate — a regularized component Marcel

Each skater component (`ev_offense, pp, ev_defense, pk, penalty, faceoff`) is projected as a
playing-time-weighted multi-year **rate**, regressed toward a position prior by a **per-component**
amount `k_c`, aged by a component-group age curve, then re-scaled by projected ice time. The
per-component regression is the core idea — components differ enormously in year-over-year reliability:

| component | YoY autocorr | fitted k_c | regression |
|---|---|---|---|
| ev_offense | 0.51 | 975 (min) | moderate |
| penalty | 0.58 | 68 | light |
| faceoff | 0.55 | 1 | ~none (stable, tiny) |
| pp | 0.33 | 160 | hard |
| ev_defense | **0.27** | **2700** | hardest |
| pk | 0.28 | 180 | hard |

Goalie components are near-noise year to year (autocorr 0.02–0.15; `ld_saves` −0.75), but the goalie
**WAR aggregate** persists (0.36), so goalies are projected at the **WAR level** with heavy regression
(`k = 70` games) toward the league-average goalie. This is what fixes the goalie band: goaltending
becomes a heavily-regressed projection with a calibrated ~0.75 sd, not a 1.8 raw-measurement sd.

Age curves are the within-player paired-delta method (mirroring `fit_aging_curves`), smoothed and shrunk
toward 0, grouped (pp ages like offense, pk like defense, penalty/faceoff barely age). Data span is only
5 GAR seasons (4 transitions), so everything is deliberately simple and regularized.

## The uncertainty — heteroscedastic, from backtest residuals

Per component, the residual variance on a **strict temporal holdout** (params fit on outcomes `< T`,
predict `T`) is modeled as `s0² + s1²/denom` (a measurement floor plus small-sample inflation), so
low–ice-time players get wider bands. Per-player WAR sd = component sds in quadrature, scaled by a global
λ=0.85 so **player-level 1σ coverage is 67%** (target ~68%). This *replaces* `war_sd = gar_sd/6`.

## Hybrid base + delta (Handoff 13)

The above projects a roster purely **bottom-up** (sum projected player WAR → absolute rating → points).
That throws away the single most accurate predictor of next-year team points — the team's own measured,
multi-year-regressed results — so the Roster Builder now anchors on it, exactly as the offseason tool
does. All on the goals/game rating scale:

```
projected_rating = R_bottomup(built) + w · ( R_current − R_bottomup(current actual) )
projected_points = rating_to_points(projected_rating)
```

- **R_current** — the **offseason forecast's projected rating** for the team's current transition,
  read from the `roster_forecast` serving row (`tools._forecast_current_rating`). It is the shared
  measured anchor **plus** the summer's move delta and chemistry — the ONE "current team" number, so an
  unedited roster reproduces the offseason forecast *exactly* (see roster-builder.md → *Cross-tool
  consistency*). If the row is missing, R_current falls back to the bare shared anchor with a
  `baseline_source` flag (never fabricated).
- **The shared measured anchor** — a **2-year recency-weighted, league-mean-regressed** measured
  `team_ratings` (`project_roster_forecast.predictive_base`, ONE definition used by BOTH tools). It
  predicts next-year strength far better than the latest single season (the offseason forecast now
  anchors on it too; the rank-delta backtest is within noise, points MAE unchanged at 4.50).
- **R_bottomup** — the existing absolute bottom-up rating, computed for both the built and the current
  actual roster with the *same* player projection, so projection bias cancels in their difference.
- **w** — the **minutes-weighted** retained-value share: the fraction of the actual roster's projected
  ice time still iced in the build. No changes → w=1; fully hypothetical → w→0.

The offset `R_current − R_bottomup(current actual)` carries the measured level + the summer's moves +
the coaching/system the parts-sum can't see. It **fades automatically** with roster turnover:

- **No changes (w=1):** `projected_rating = R_current` — identical to the offseason forecast's number,
  by construction (`points_delta = 0`).
- **Fully hypothetical (w=0):** `projected_rating = R_bottomup(built)` — pure bottom-up, correct since
  there's no measured team to anchor to.
- **In between:** the offset fades smoothly as the minutes turn over.

**The seam (documented, not hidden):** the base reflects *realized* value while the deltas adjust by
*projected* value — a minor inconsistency the w-fade mitigates, and the same seam the offseason tool
lives with. **Injured-player fix:** the deltas use player projections, so ice time is now projected
separately and **games-weighted** — a single injured/low-games season can't drag a returning player's
usage (and value) toward replacement (his rate already uses TOI-weighted healthy history).

### The two bands, under the hybrid

- **Delta band (the headline, tight).** `points_delta = projected_points(built) − rating_to_points(R_current)`.
  The unchanged players cancel **exactly** and the common season-ahead error cancels, so the band is the
  raw quadrature of **only the changed players'** calibrated sds, plus a small term from the offset fading
  as w drops — **no luck floor** (a talent comparison, not a realized-season bet). A single swap is **≈ ±1
  point**; a heavy rebuild widens it.
- **Absolute band (context, wide).** Strength uncertainty interpolated anchor↔bottom-up by w
  (`w·STRENGTH_ANCHOR + (1−w)·STRENGTH_BU`, points) in quadrature with the **luck floor 6.15**. Calibrated
  so a 1σ band covers **~68%** of real team-seasons. On points it stays ~±13 regardless of w — an 82-game
  season is mostly luck, so neither model can tighten the *absolute* number; the hybrid's win is the
  correct baseline and better de-lucked strength, not a narrower absolute band.

### Head-to-head (the gate — hybrid shipped)

| metric | hybrid | bottom-up |
|---|---|---|
| absolute points RMSE | **12.86** | 13.05 |
| absolute points corr | **0.413** | 0.375 |
| next-year **rating** corr (16-season) | **0.58** | 0.44 |
| delta corr (pooled, 2 transitions) | 0.12 | 0.12 |

The hybrid beats bottom-up on points RMSE (marginally — points are luck-saturated) and **clearly on
de-lucked strength**, and fixes the baseline to equal the team's measured level. The delta correlation
is **weak and noisy for both** (~0.12 pooled; per-season −0.17 and +0.40) — a correction to H12's reported
"0.40", which was one cherry-picked transition: the composition delta is a tiny signal two seasons can't
validate. The hybrid delta ≈ the bottom-up delta for retained rosters, so they tie there. Shipped because
it wins where the data is robust and is never worse.

## Calibration constants (`config.ROSTER_FORECAST`)

Bottom-up map: `LEAGUE_AVG_LINEUP_WAR = 11.28` · `WAR_TO_RATING = 0.03353` (average position-valid roster
≈ 91 pts). Hybrid: `ROSTER_BUILDER_BASE_W = [1.0, 0.5]` · `ROSTER_BUILDER_BASE_K = 1.0` ·
`ROSTER_BUILDER_STRENGTH_ANCHOR = 11.45` · `ROSTER_BUILDER_STRENGTH_BU = 11.34` · `SEASON_LUCK_FLOOR_PTS =
6.15` · `ROSTER_BUILDER_DELTA_OFFSET_W = 0.30`.

## Evaluation (strict temporal holdout, reported by the module)

**Out-of-sample RMSE — the model beats both baselines** (current naive "last season carried", and a
plain WAR-level Marcel):

| | model | Marcel | naive |
|---|---|---|---|
| skater WAR | **0.720** | 0.737 | 0.764 |
| goalie WAR | **0.853** | 0.884 | 0.936 |
| ev_offense | **2.206** | 2.219 | 2.564 |
| ev_defense | **2.842** | 2.862 | 3.854 |
| pp / pk / penalty | all beat both | | |

(`faceoff` ties the naive baseline; it contributes ~0.005 WAR — immaterial.)

**Delta validation (primary gate).** Predicted roster-change impact vs realized, 31 team-transitions:
correlation **0.40 vs the de-lucked measured-rating change**, 0.22 vs raw points. The predicted delta sd
(1.4 pts for a whole-roster turnover) is small and precise; the points-RMSE (17.4) is dominated by the
realized YoY team variance (sd 17.6) — stayer drift, goaltending swings, and luck the *composition* delta
deliberately excludes. The delta isolates the talent difference between two rosters; it does not try to
predict a full season.

**Monotonicity / sanity:** all pass — upgrading a slot never lowers points; a bigger talent gap orders a
bigger delta; removing a player never raises the team.

**Coverage calibration:** absolute band **~68%** at 1σ (was 52%); player WAR sd **67%**. The delta band is
the changed players' calibrated projection sd (verified at the player level); it is a precision interval
on a talent comparison, not a realized-season coverage claim.

## Limitations

- 4 transitions of GAR — the model is simple by necessity; it will sharpen as seasons accumulate.
- The absolute number remains a soft season-ahead projection (MAE ~10.5 pts, ~5 of it irreducible luck).
  Lead with the delta.
- A player projected on a club other than his own carries extra role/translation uncertainty not in the
  same-team backtest; this is not added to the band (documented).
- Temporary divergence: a player projects slightly differently here than in the offseason/trade/contract
  tools, which keep `blended_war_rate`.
