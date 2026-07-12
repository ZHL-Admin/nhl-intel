# System Effects — Findings

*One page. Full detail in `reports/phase{0..6}.md`; cross-project ledger in
`../PROGRAM-FINDINGS.md`.*

## What we built
A measurement of **what coaching systems do** to the players inside them and the opponents across
from them, on the frozen Deployment Atlas corpus (2010-11 → 2025-26, ~19,150 games), read-only.
We backfilled head coaches (+ officials + scratches) for 16,526 pre-2024 games from the NHL
right-rail, built a **regime ledger** (one row per team-coach span, raw + consolidated), a
per-regime **system-fingerprint** layer (deployment, style, PK), a 6-type **player pooling**
layer, and two effect tracks — **internal** (what a coach does to his own players) and
**opponent** (what a matchup does) — each validated predictively before any claim.

## What validated
- **Deployment is the coach-owned lever, in both windows.** Who plays and how they start
  (top-6 concentration, zone-start polarization) is the only thing that moves more than a placebo
  at coach changes — mid-season **and** across a summer (zone-pol ratio ~1.9, p=0.0005; summer
  install dose t=3.4, directional p=0.0005). Zone-start polarization persists while the coach
  persists (YoY r=0.70) and moves when he changes (0.31).
- **The portability machinery works.** A joint player-season model separates skill (RAPM) from
  system (deployment) with strong identifiability (58.5% of players are movers; every team-season
  anchored by ≥6 mover-players) and recovers a real out-of-fold system signal (CV R² ≈ 0.07 of the
  residual). It powers an internal, descriptive portability surface and a predicted-delta-by-
  destination accessor.
- **The schedule normalization is sound.** Team strength explains team-game xG share (R²=0.11) with
  era-stable coefficients; the strength-based opponent-schedule adjustment is a face-valid
  descriptive product.

## What fell short or died
- **Movers prediction — INVESTIGATE (not SHIP).** Adding deployment to the Atlas rating improves
  mover MAE by **+0.81%** (95% CI [0.15%, 1.50%], excludes zero) — below the pre-registered 3%
  bar. Real but immaterial (~1.3% of the target's 0.70 reliability ceiling).
- **Opponent style-matchup track — KILLED.** Style-matchup interactions add 0.00014 R² over
  strength (~60× smaller coefficients) and do not replicate across eras (r = −0.045).
- **Summer style install — null (positive but unconfirmed).** Even given a full offseason and camp,
  a new coach does not shift on-ice style beyond a continuing coach's, controlling roster
  continuity. The directional signal is **positive but too weak to confirm in sixteen years of
  transitions (p=0.08); never proven zero.**
- **The penalty kill — null in both windows.** Despite being a reliable, stable metric (split-half
  0.57–0.81) and a heavily-drilled phase, PK shot-location installs no more at coach changes than
  at placebo — mid-season or across a summer.

## The decisions (no editorializing)
- **5A movers:** improvement 0.81%, CI [0.15%, 1.50%], < 3% → **INVESTIGATE.**
- **Opponent style-matchup:** 0.00014 R² gain, cross-era r −0.045 → **KILLED**; strength-only
  schedule normalization survives as descriptive accounting (no predictive claim, no validation bar).
- **F12 scope (summer):** style fails both the directional and dose tests → **EXTEND** F12 to
  summers (observational). Deployment cleared both (calibration).
- **Nothing ships publicly.** The portability surface stays internal and descriptive under the
  amendment-4.1a materiality gate.

## Five most surprising findings
1. **A coach cannot measurably install a playing *style*** — not even over a summer. Style is a
   roster property; what a coach owns is *deployment*.
2. **The penalty kill is not coach-owned** at this resolution — a genuine null for the phase of
   play everyone assumes is the most coached.
3. **The new-coach result bump is real but unexplained** — deployment change mediates only ~4% of
   it (the "Jolt").
4. **Style matchups don't matter beyond strength** — who you play matters through their overall
   quality, not stylistic rock-paper-scissors; the interaction terms don't even survive an era split.
5. **The System Tax concentrates in defensemen and high-TOI players** — and the intuitive
   "system-dependence ratio" is a denominator trap (it flagged average-skill players like Kopitar);
   the honest metric is the absolute system contribution, which is small everywhere (≤ ~0.01
   xG-share pts).

## Upstream ledger — final state
- **UL-1** — `stg_games`/`stg_game_context` season mislabel (2015-16 block tagged 2024-25; dates
  correct, only the derived label): **flagged for a future gated production fix.** This project is
  immune (anchors on the frozen Atlas game universe by game_id).
- **UL-2** — `player_archetypes` staleness: **resolved** (self-healed; this project derives its own
  types regardless).
- **UL-3** — right-rail missing one coach for 2 of 16,526 games: negligible; HTML fallback exists.

## Open questions
- **The Jolt (next addendum).** The small new-coach on-ice result bump (F14) that deployment does
  not explain — is it **effort** (a bump that fades on an event-time curve), **reversion** (firing
  at a low ebb → regression), or **neither**? An **event-time study around the change date** is
  queued.
- **The D / high-TOI concentration thread.** The system signal concentrates in **defensemen and
  high-usage players** (5A slices; by construction in deployment). Carried as **pre-specified
  secondary subgroups** in the 2026-27 prospective registration to test out-of-sample replication.
