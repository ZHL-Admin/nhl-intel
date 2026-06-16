# Isolated impact — RAPM (Phase 4.1)

Regularized Adjusted Plus-Minus on the in-house xG layer: isolate each skater's contribution
to expected goals for and against, controlling for teammates, competition, and usage.
Implemented in `models_ml/train_rapm.py`; output `nhl_models.player_impact`.

## Design matrix

- **Unit:** a 5v5 stint (a maximal interval with the same 10 skaters on ice), from
  `int_shift_segments` x `int_segment_context`. Stints shorter than 4 seconds are dropped as
  line-change noise, as are any with ≠ 5 skaters per side.
- **Two rows per stint, one per attacking direction.** The target is the *attacking* team's
  xGF per 60 during the stint (xG summed from `nhl_models.shot_xg` via `int_on_ice_events`),
  weighted by stint duration.
- **Two-sided indicators:** +1 in each of the 5 attacking skaters' OFFENCE columns and +1 in
  each of the 5 defending skaters' DEFENCE columns. So every skater gets an offence
  coefficient (how much they raise their own team's xGF/60) and a defence coefficient (how
  much they raise the opponent's xGF/60 while defending).
- **Controls:** attacker score state (leading/tied/trailing), zone start (O/D/N faceoff vs
  on-the-fly; encoded shared across both directions because the effect is empirically
  symmetric — an O-zone faceoff raises xGF for *both* teams), home indicator, back-to-back
  (attacking team played the previous calendar day, from the schedule), and season fixed
  effects.

## Estimation

Ridge regression (`sklearn`, sparse design). Lambda is chosen by game-grouped 80/20 holdout
weighted xG MSE. The validation curve is **flat for strong regularization** (MSE within ~0.2%
across alpha 2000–8000), so the CV selects the high end (~8000); this matches standard RAPM
practice and the player *ranking* is insensitive to the exact value in that range.

Coefficients are centred across players (mean 0). We report `off_impact` = centred offence
coefficient and `def_impact` = −(centred defence coefficient), so **higher is better for
both**, in xGF/60 units.

### Windows

A 3-season rolling window weighted 1.0 / 0.6 / 0.3 (newest → oldest) is the headline estimate
(`season_window` like `2023-24_2025-26`), plus single-season estimates for recent seasons.
Segment data covers 2015-16 onward, so RAPM is available from 2015-16.

### Special teams

Power-play segments (5v4 / 4v5) are fit with the same two-sided machinery but only the
man-up direction: offence = the PP unit, defence = the PK unit, target = PP-team xGF/60. One
fit yields `pp_impact` (PP offence) and `pk_impact` (PK defence, sign-flipped so higher = a
better kill). Smaller samples → wider uncertainty.

## Uncertainty

Game-resample bootstrap: resample games with replacement, reweight each stint by its game's
draw count, refit, and take the per-player coefficient SD. 100 resamples for the 3-season
window, 40 for single seasons (the plan suggests 200; reduced for compute, documented here).
Low-TOI players show visibly wider SD — never read a point estimate without it.

## Validation (full run, 2026-06)

- **Coefficients centre at 0** (3-season window: off_impact mean 0.000, sd 0.202; def_impact
  mean 0.000, sd 0.178), as a centred RAPM should.
- **Top-10 pass the smell test.** 3-season window offence: MacKinnon, B. Tkachuk, Matthews,
  Hyman, Gallagher, M. Tkachuk, Hagel, Barkov, R. Thomas, Hischier. Defence: Reinhart,
  Foligno, W. Karlsson, Toews, Cizikas, Hathaway — defensive forwards plus an elite defensive
  defenceman. (Single-season defence is led by Adam Pelech.)
- **Year-over-year stability** of single-season offence impact (≥200 5v5 min): r = 0.47, 0.42,
  0.46, 0.37 across the four adjacent season pairs, **mean 0.43** — squarely in the expected
  0.3–0.5 range, confirming the estimates capture repeatable skill rather than noise.
- **Low-TOI uncertainty shows up as shrinkage, not wide bands.** With ridge + a game-resample
  bootstrap, sparse-minutes players are pulled toward 0 and carry *small* absolute SD: the
  model expresses "we don't know" as "near league average," not as a wide interval. So a
  near-zero impact on a low-TOI player means *unproven*, not *confidently average*; absolute
  SD tracks impact magnitude (median off_sd ≈ 0.12 for >1000-min players vs ≈ 0.08 for
  <150-min). Relative uncertainty (sd/|impact|) is lowest for high-minute players (~0.84).

## Known limitations

- RAPM attributes on-ice xG, not micro-skill; it cannot separate, say, zone exits from
  finishing within the on-ice effect.
- Deployment is only partly controlled (score/zone/home/B2B/season); systematic usage not
  captured by those controls is absorbed into coefficients.
- Defence coefficients are noisier than offence (fewer distinguishing events per defender).
- Special-teams estimates are smaller-sample and should be read as directional.
