# NHL Research Program — Findings Ledger

The shared, **growing** cross-project findings ledger. Completed-project reports under each
`research/<project>/reports/` are **frozen** and do not grow; new findings and cross-project
threads are recorded here instead.

Projects:
- **Deployment Atlas** (`research/deployment-atlas/`) — frozen. Findings in its own
  `reports/FINDINGS.md`; summarized threads carried forward here.
- **System Effects** (`research/system-effects/`) — findings below (F-series).

---

# System Effects — Findings (follow-on project, answers "The System Tax")

A follow-on research project (`research/system-effects/`, reads the frozen Atlas parquet
read-only) that measures what coaching **systems** do to the players inside them and the
opponents across from them. It ingested a right-rail coach backfill (2010-11 → 2023-24, 16,526
games + officials + scratches), built a per-(team, regime) system-fingerprint layer, and ran two
tracks with pre-registered validation. Numbered findings (F-series) below; full detail in
`research/system-effects/reports/phase{0..5}.md`.

## What the discontinuity/validation tests established
- **F12 — style is a roster property, deployment is the system.** At within-team coach changes,
  only **deployment** (top-6 forward concentration, zone-start polarization) shifts more than a
  placebo (zone-pol ~1.9×, p=0.0005); on-ice **style** (rush/cycle/forecheck/point-shot shares,
  shot-location, pace) is statistically indistinguishable from placebo. **Extended (Phase 5
  addendum):** the style null holds across **summers** too — controlling for roster continuity, a
  new coach's first full season does not shift style beyond a continuing coach's, and teams do not
  move toward an incoming coach's established style beyond chance (dose +0.05 SD ns; directional
  p=0.08). Deployment installs in **both** windows (summer dose t=3.4, directional p=0.0005) —
  which also proves the test had power, so the style null is real, not underpowering. Penalty-kill
  shot-location installs in neither window. The summer style directional is **positive but
  unconfirmed** — too weak to confirm in sixteen years of transitions, never proven zero.
  *Observational for the summer extension.*
- **F13 — deployment persists with the coach.** Zone-start polarization has YoY correlation 0.70
  within a continuing regime and 0.31 across a coach change — it persists while the coach persists
  and moves when he changes. (Top-6 concentration does **not** show this pattern and carries a
  stability caveat everywhere.)
- **F14 — thin mediation.** A coach change's on-ice **result** effect is small (+0.004 score-close
  on-ice xG-share DiD, t=1.73) and only **~4%** of the within-player result change is mediated by
  the measured deployment change (R²=0.04). Deployment is what coaching demonstrably moves; the
  result payoff of that move is barely detectable at one-season resolution.
- **F15 — style matchups don't matter beyond strength.** In a team-game 5v5 xG-share model,
  style-matchup interactions add **0.00014 R²** over team strength (coefficients ~60× smaller) and
  **do not replicate across eras** (cross-era r = −0.045). The opponent style-matchup track was
  **killed**; only a strength-based schedule normalization survives as descriptive accounting.
- **F16 — the Jolt is reversion (not effort).** The small new-coach on-ice result bump (F14) that
  deployment does not explain is **mean regression**: teams fire coaches at a genuine on-ice trough
  (~1.3 pp below prior-season baseline, CI excludes 0), and the new coach's recovery to baseline is
  **flat, sustained through +40 games (no fade), and statistically indistinguishable** from what a
  matched-trough non-firing team recovers (excess +0.004, CI [−0.011, +0.020]). Effort (a fading
  honeymoon) is rejected; "neither" is rejected (the trough is real). Era-stable, not outlier-driven.
  *Observational.* (Event-time addendum; the registered "deepest-trough" placebo had a
  regression-to-minimum bias, corrected to a matched-depth control — disclosed, no threshold moved.)

## The System Tax — answered
The Atlas open question ("how much of a player's on-ice result is the system vs the player?") now
has a number and a caveat. A joint player-season model (RAPM as frozen offset; team deployment +
type×deployment as the system term; grouped CV) recovers **CV R² ≈ 0.07 of the residual** beyond
player quality — a real, out-of-fold system signal, but small. Absolute per-player system
contributions are **≤ ~0.01 xG-share points** (p95 0.008). So the System Tax is **real but thin**:
the system a player is in explains single-digit percent of what his rating doesn't, concentrated in
**deployment** (not style), and mostly for **defensemen and high-usage players**.

## The decision (pre-registered, INVESTIGATE — matches the Atlas mover verdict)
Do deployment-system terms predict movers beyond the Atlas rating? On the Atlas mover cohort, a
leakage-clean nested test (RAPM vs RAPM+deployment, LOSO-pair-out, sys refit clean per fold)
improves MAE by **+0.81%** (95% CI [0.15%, 1.50%], excludes zero) — **below the 3% ship bar →
INVESTIGATE.** The signal is directionally correct (movers > stayers 0.81 vs 0.49%), stable under
influence, and concentrated in **defensemen (+1.62%) and high-TOI players (+2.48%)**, but sits at
~1.3% of the target's reliability ceiling (split-half 0.70). **Nothing ships publicly.** The
portability surface stays **internal and descriptive** under a materiality gate (label a player
system-dependent only where the absolute system contribution's CI excludes zero **and** |sys| ≥
0.004); the defensemen / high-TOI slices are **pre-specified secondary subgroups** for a future
prospective registration, not claims now.

## Upstream ledger additions (System Effects)
- **UL-1 — `stg_games`/`stg_game_context` season mislabel:** a 2015-16 block tagged `2024-25`
  (game dates correct, only the derived season label corrupt). System Effects immunizes by
  anchoring on the frozen Atlas game universe + game_id joins. Flagged for a future gated
  production fix.
- **UL-3 — right-rail missing one coach for 2 of 16,526 backfilled games** (source omission);
  negligible, HTML-roster fallback available if ever needed.

## Open questions (System Effects → next)
- **The Jolt — RESOLVED → F16 (reversion).** The event-time addendum ruled it mean regression, not
  effort (see F16). Closed.
- **The D / high-TOI concentration thread.** The system signal — retrospectively (5A slices) and by
  construction (deployment) — concentrates in **defensemen and high-usage players**. The 2026-27
  prospective registration carries these as **pre-specified secondary subgroups** to test whether
  the concentration replicates out of sample.
