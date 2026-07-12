# Jolt addendum — pre-registration (event-time, observational)

**Registered & frozen:** 2026-07-11 · **Seed:** 20260711 · **Status:** ratified by product owner;
thresholds fixed BEFORE results. All evaluation inputs frozen to `data/parquet/frozen_eval_jolt/`
before any metric. Observational (coach changes are not randomized); labeled as such.

## Question
Design A found a small new-coach on-ice result bump (**+0.004 score-close 5v5 xG-share DiD,
t=1.73**) that measured deployment change does NOT mediate (F14). Is it **effort** (a bump that
fades on an event-time curve), **reversion** (teams fire coaches at a low ebb → mean regression),
or **neither**?

## Cohort
The 49 Cohort C mid-season changes (validated, frozen). Event time τ = games relative to the new
coach's first game (τ=0; first new game = τ=+1). Regular season, ice-derived strength,
quarantine/playoff exclusions (standing rules).

## Outcome
Team 5v5 **score-close** on-ice xG share, aggregated into event-time bins:
`pre [-20..-11], [-10..-1]` (old coach) · `post [+1..+10], [+11..+20], [+21..+40]` (new coach).

## Baseline & placebo
- **Baseline** = the team's prior-season (S−1) 5v5 score-close xG share (fallback: change-season
  overall). A pre-change **trough** = pre-change level significantly below baseline.
- **Matched-trough placebo** = no-change (one-regime) team-seasons, at their own deepest trailing-
  10-game xG-share trough (pseudo-τ0 after the trough), restricted to troughs whose pre-window
  `[-10..-1]` level falls within the real changes' pre-window range. Measures the natural
  post-trough recovery WITHOUT a coach change, in the same bins.

## Discriminating signatures (pre-committed)
| hypothesis | pre-change | post-change **excess over matched-trough placebo** | fade slope over τ=+1..+40 |
|---|---|---|---|
| **Reversion** | significant trough | CI includes 0 (recovery matches placebo) | ≈ 0 |
| **Effort** | trough present | initial (τ=+1..+10) excess > 0, CI excludes 0 | significantly negative |
| **Neither** | no significant trough | no excess | flat 0 |

## Decision rule (fixed)
- **REVERSION** if pre-change trough is significant (CI below baseline) AND post-change excess-over-
  placebo CI includes zero across post bins.
- **EFFORT** if the τ=+1..+10 excess CI excludes zero AND the fade slope over τ=+1..+40 is
  significantly negative.
- **NEITHER** if no significant trough and no excess.
- **MIXED** otherwise, reported without editorializing.

## Robustness (inside the phase)
Matched-trough placebo stated; 2000-perm placebo on the excess (seed 20260711); leave-one-change-
out influence; era split (2010-17 vs 2018-26); xG-share split-half reliability as the noise
ceiling. No threshold moves after results.

## Deliverable
`reports/phase5-jolt-addendum.md`; finding logged to `research/PROGRAM-FINDINGS.md`. STOP for the
product owner's ruling.
