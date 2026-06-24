# Goalie leverage-clutch — pre-registration (committed before looking at outcomes)

**Question.** Is a goalie's *leverage-weighted* GSAx a repeatable skill — i.e. do some goalies
systematically save more (or fewer) goals above expected when the game is on the line, beyond what
their overall GSAx already says? And if so, does it improve playoff-series prediction?

This document fixes the design, metrics, and decision thresholds **before** any correlation is
computed, so the result cannot be reverse-engineered to be positive (discipline: rarity is a
sample-size problem, not a talent signal).

## Data
- One row per shot on a goalie: `int_shot_sequence` (time, is_goal, empty-net) ⋈ `shot_xg` (xg)
  ⋈ goalie of record for the defending team that game (`mart_goalie_game_stats`, max shots faced)
  ⋈ `win_probability.leverage` at the shot's time (nearest 10 s).
- Seasons 2015-16 → 2025-26 (win-probability coverage). Empty-net shots excluded.
- `gsax_per_shot = xg − is_goal` (goals saved above expected; positive = save above expected).
- **Leverage buckets:** league-wide terciles of `leverage` (fixed thresholds across all shots).
  High = top tercile, Low = bottom tercile.

## Metric
`clutch_delta(goalie, season) = mean(gsax | high-leverage) − mean(gsax | low-leverage)`.
Positive ⇒ the goalie raises his game when it matters. Minimum sample to qualify: **≥ 800 total
shots and ≥ 150 high-leverage shots** in the goalie-season (else excluded as underpowered).

## Pre-registered repeatability tests + thresholds
1. **Within-season split-half reliability.** Randomly split each goalie-season's shots 50/50,
   compute `clutch_delta` on each half, Pearson r across goalie-seasons, Spearman-Brown corrected.
   **Pass: SB-corrected r ≥ 0.20.**
2. **Year-over-year persistence.** Correlate a goalie's `clutch_delta` in season N vs N+1.
   **Pass: r ≥ 0.15.**
3. **Permutation null.** Within each goalie-season, shuffle the high/low leverage labels across that
   goalie's shots (preserving counts), recompute `clutch_delta`; build the null distribution of the
   cross-goalie SD of `clutch_delta` (1000 shuffles). **Pass: observed cross-goalie SD > null p95.**

## Decision rule (committed)
- Declare goalie leverage-clutch a **real repeatable skill** only if **all three pass**.
- **Only then** test impact: add the projected starter's `clutch_delta` to the 225-series playoff
  model; keep it in the bracket only if it improves LOSO log-loss by ≥ 0.0005 with a bootstrap
  coefficient CI excluding zero.
- If any test fails → declare it noise, report the error bars, add nothing to the bracket.

## Prior
The existing skater `player_clutch` model shows clutch is ~chance-level (≈9% of players p<0.05) and
persists year-over-year at r ≈ 0.11. Goalies face fewer high-leverage shots and are noisier, so the
prior is that this comes back null. Pre-registering anyway so the test is honest either way.
