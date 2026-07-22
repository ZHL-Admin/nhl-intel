# Def-breakdown — culprit-rate CONTEXT-ADJUSTMENT probe

**descriptive: what happened on goals-against, not a defensive rating.** Extends the def-breakdown probe (branch research/def-culprit-adj; folder-isolated in def-breakdown, reusing the approved Link-1 shares). Tests whether F27's failure (raw culprit rate split-half ~0, backwards eye-test) was CONTEXT CONTAMINATION. Seed 20260714e. Nothing promoted.

> **Scoping note (flagged):** player_context (QoC/QoT) exists only for 2024-25, so ADJ-2 deployment covariates (OZ-start share, PK share, trailing share, 5v5 TOI) are computed from stints for all three seasons; opponent quality is handled by ADJ-3 (scorer RAPM), so QoC is not double-counted.
> **ADJ-1 note:** on this metric each goal's one unit is distributed entirely within the player's own on-ice team, so within-team share is a monotone rescaling of RAW — team quality was never a rate-inflating confound. Reported for completeness.


## Link 1 — the adjusted rates & how little they move

Usage barely predicts culprit rate (ADJ-2 betas: OZ-start +0.002, PK +0.007, TOI ~0), and **no adjustment widens the spread** — every version stays a razor-thin band, like RAW:

| version | 2025-26 spread (max−min) |
|---|---|
| RAW (F27) | 0.062 |
| ADJ-1 within-team | 0.062 |
| ADJ-2 usage | 0.056 |
| ADJ-3 opponent | 0.065 |
| ADJ-4 xGA-relative | 0.058 |
| ADJ-COMBINED | 0.061 |

(For reference the RAW defensemen-only band was 0.034; combined D+F here ~0.06. Context strips do not create separation — the variance is not context, it is noise.)

## Link 2 — the stability gate (both positions, all versions)

| position | version | n | split-half r | placebo p |
|---|---|---|---|---|
| D | RAW (F27) | 415 | +0.01 | 0.381 |
| D | ADJ-1 within-team | 415 | +0.01 | 0.376 |
| D | ADJ-2 usage | 415 | +0.02 | 0.392 |
| D | ADJ-3 opponent | 415 | +0.00 | 0.484 |
| D | ADJ-4 xGA-relative | 415 | +0.01 | 0.411 |
| D | ADJ-COMBINED | 415 | +0.00 | 0.481 |
| F | RAW (F27) | 543 | +0.05 | 0.120 |
| F | ADJ-1 within-team | 543 | +0.05 | 0.113 |
| F | ADJ-2 usage | 543 | +0.04 | 0.164 |
| F | ADJ-3 opponent | 543 | +0.04 | 0.172 |
| F | ADJ-4 xGA-relative | 543 | +0.05 | 0.119 |
| F | ADJ-COMBINED | 543 | +0.03 | 0.261 |

**Reference:** bar = 0.30; offensive signature (F25) 0.41–0.76. **Every version, both positions, sits at split-half ~0** — no adjustment reaches the bar. As predicted, residualizing on a season-constant (ADJ-2/4/combined) cannot create within-season split-half signal, and ADJ-3's reweighting does not either.

## Link 2 — the EYE TEST (does any adjustment un-scramble the sort?)

The decisive check: the fullest context strip, ADJ-COMBINED (usage + opponent), 2025-26. If removing all context still leaves known-strong defenders at the top (most-culpable), context was not the hidden cause.


**ADJ-COMBINED — highest 10 defensemen (2025-26):** Jakob Chychrun, Ryan Lindgren, Henri Jokiharju, Tom Willander, Ryker Evans, Carson Soucy, Owen Power, Brock Faber, Matt Grzelcyk, Artyom Levshunov

**ADJ-COMBINED — lowest 10 defensemen:** Travis Sanheim, Sean Walker, Noah Hanifin, Denton Mateychuk, Oliver Ekman-Larsson, Erik Karlsson, Shakir Mukhamadullin, Simon Benoit, Vladislav Gavrikov, Braden Schneider

**ADJ-COMBINED — highest 10 forwards (2025-26):** Conor Garland, Evgeni Malkin, Artemi Panarin, Trevor Zegras, Brandon Hagel, Mitch Marner, Jesper Bratt, Nick Cousins, Nick Suzuki, Jared McCann

**ADJ-COMBINED — lowest 10 forwards:** David Pastrnak, Mark Stone, Jonathan Huberdeau, Patrick Kane, Cole Perfetti, Paul Cotter, Mika Zibanejad, Robert Thomas, Mavrik Bourque, Cody Glass

## Face-validity — culprit rate vs on-ice xGA/60 (per version)

| position | version | corr with on-ice xGA/60 |
|---|---|---|
| D | RAW (F27) | +0.04 |
| D | ADJ-1 within-team | +0.04 |
| D | ADJ-2 usage | +0.08 |
| D | ADJ-3 opponent | +0.04 |
| D | ADJ-4 xGA-relative | -0.00 |
| D | ADJ-COMBINED | +0.08 |
| F | RAW (F27) | +0.04 |
| F | ADJ-1 within-team | +0.04 |
| F | ADJ-2 usage | +0.01 |
| F | ADJ-3 opponent | +0.04 |
| F | ADJ-4 xGA-relative | +0.00 |
| F | ADJ-COMBINED | +0.01 |

## VERDICT — HARD NULL

**Context contamination was NOT the hidden cause.** Removing team quality (ADJ-1, degenerate), deployment (ADJ-2), opponent quality (ADJ-3), and unit results (ADJ-4), alone and combined, for both positions: (i) leaves the spread a razor-thin band (~0.06, unchanged), (ii) leaves split-half at ~0 for every version — none clears the 0.30 bar or beats placebo, and (iii) does not un-scramble the eye test. Usage barely predicts the rate (betas ~0), so there was little context to remove.

**Individual defensive attribution is not recoverable from goals-only geometry, even context-adjusted.** This closes the thread with evidence: the raw metric's failure (F27) was not hidden signal masked by context — it is noise. The per-goal assignment is descriptively sane, but no per-player defensive rate — raw or adjusted — is a stable, sensibly-sorting individual signal. The catalog entry stays DESCRIPTIVE (goal-anatomy only); no version graduates to 'signal'. *(reinforces F27; proposed as its context-adjusted confirmation.)* Nothing promoted.

## STOP — owner rules.
