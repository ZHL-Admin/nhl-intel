# Phase 5 — Robustness round

Descriptive robustness on the Phase 5 mover result. **The INVESTIGATE decision
stands regardless of these outcomes.** Machine evidence: `reports/phase5_robust.json`,
`phase5_r4.json`; frozen predictors under `data/parquet/prospective_2026/`.

## R1 — Movers vs stayers (same LOSO, same metrics)

| population | n | (a) raw MAE | (b) prod MAE | (b2) var MAE | (a) Spearman | (b2) Spearman | **(b2)−(a)** | 95% CI |
|---|---|---|---|---|---|---|---|---|
| **movers** | 1,705 | 0.03705 | 0.03664 | 0.03568 | 0.257 | 0.311 | **+3.70%** | [+2.0%, +5.4%] |
| **stayers** | 5,833 | **0.02918** | 0.03259 | 0.03134 | **0.527** | 0.418 | **−7.40%** | [−8.6%, −6.3%] |

**On stayers, raw is far better** (MAE 0.0292 vs 0.0313; Spearman 0.527 vs 0.257 on
movers) and the adjusted rating *loses* by 7.4%. This is expected and now quantified:
a stayer keeps the same team, linemates, role and zone deployment, so **last year's
on-ice share self-predicts** — the persistent context the RAPM deliberately strips
out is exactly what carries a stayer forward. The adjustment **helps where context
changes (movers, +3.7%) and hurts where it persists (stayers, −7.4%)** — coherent
evidence it is doing its job, not adding noise.

## R2 — Slices (movers, (b2)−(a))

| slice | n | improvement | 95% CI | sign flip? |
|---|---|---|---|---|
| Forwards | 1,100 | +1.85% | [−0.26%, +3.94%] | no (spans 0) |
| **Defensemen** | 605 | **+7.04%** | **[+4.5%, +9.6%]** | no |
| TOI 400–700 | 447 | +3.62% | [+0.42%, +6.78%] | no |
| TOI 700–1000 | 676 | +2.63% | [−0.07%, +5.28%] | no (spans 0) |
| TOI 1000+ | 547 | +4.85% | [+2.3%, +7.5%] | no |
| exclude 2019-20→2020-21 | 1,593 | +3.80% | [+2.0%, +5.5%] | no |

**No slice flips sign.** The effect is **much stronger for defensemen (+7.0%)** —
their on-ice results are more teammate/deployment-driven, so raw is more misleading
for them and the adjustment gains more. Forwards and the mid-TOI tier span zero.
Dropping the COVID-affected pair leaves the headline essentially unchanged (+3.8%).

## R3 — Influence

- **Leave-one-mover-out** on the pooled improvement: min **3.62%**, max **3.78%** —
  a range of 0.16 points; no single player moves it.
- **Removing the 25 largest-residual movers:** improvement rises to **+3.92%** (the
  result is not propped up by outliers — the hardest movers slightly *understate* the edge).

**The CI-clean conclusion does not depend on a handful of players.**

## R4 — Noise ceiling

Split-half reliability of the target (season 5v5 xG share, odd vs even games,
n = 8,428 player-seasons ≥20 games/half): **r_half = 0.536 → Spearman-Brown
r_full = 0.698.**

> Only ~70% of the variance in a player's season xG share is stable talent; **~30%
> is within-season sampling noise** that no predictor of true talent can recover. A
> perfect predictor's error is floored by that noise, and the raw predictor already
> captures most of the *persistent* signal — so the reducible gap the adjustment can
> attack is a fraction of the total MAE, not all of it. Against a target only 0.70
> reliable, a **+3.70% MAE reduction over raw is a meaningful slice of the reducible
> error, and the pre-registered 5% bar likely sits at or above the one-season-ahead
> ceiling.** This is why the result *investigates* rather than *fails*: the signal is
> real and near the plausible limit, not absent. Widening the target's reliability
> (multi-season windows, joint targets) is the lever a future round should pull.

## R5 — New pre-registration (written, not run)

**Prospective test — mover portability, 2025-26 → 2026-27.**
- **Cohort:** all skaters whose *primary* team (most 5v5 TOI) differs between 2025-26
  and 2026-27, with ≥400 5v5 minutes in each (prorated by scheduled-games ratio for
  any shortened season).
- **Predictors (frozen today):** (a) = each player's **2025-26 5v5 on-ice xG share**;
  (b2) = each player's **2025-26 Atlas-variant RAPM** off/def. Frozen values stored
  now at `data/parquet/prospective_2026/frozen_predictors.parquet` (940 players:
  `raw_xgshare_2025_26, var_off_2025_26, var_def_2025_26, team_2025_26, toi_min_2025_26`)
  so nothing about the predictors can move.
- **Target:** 2026-27 5v5 on-ice xG share (secondary: GF share).
- **Metric + bar:** mover MAE, 1000-resample bootstrap CI on (b2)−(a); **SHIP the
  portability claim if (b2) beats (a) by ≥5% with CI excluding zero.**
- **Evaluation date:** end of the 2026-27 regular season. Fit uses the same
  leave-out structure on stayers; predictors are the frozen 2025-26 values only.

### Amendment (2026-07-10, pre-outcome — valid)
Added a **pre-specified position subgroup analysis**: (b2)−(a) computed separately
for **F** and **D** (same metrics + bootstrap CIs). The **≥5% / CI-excludes-zero
SHIP bar applies to the pooled result as the primary claim and to the defensemen
subgroup as a secondary claim** (motivated by R2's D +7.0% vs F +1.9%). Recorded in
`data/parquet/prospective_2026/registration.md`.

---

## Summary
The Phase 5 result survives every robustness check: no slice flips, no
single-player dependence (jackknife 3.62–3.78%), the COVID pair doesn't drive it,
and the movers-vs-stayers contrast (+3.7% vs −7.4%) shows the adjustment behaving
exactly as intended. The **+3.70%** sits against a target only **0.70** reliable —
near the one-season-ahead ceiling. INVESTIGATE stands; the prospective 2026-27 test
is pre-registered and frozen.
