# Phase 5 — Pre-registered validation (internal track only)

**Project:** System Effects · **Date:** 2026-07-11 · **Seed:** 20260711
**Status:** Phase 5 complete. Decision by the pre-registered rule: **INVESTIGATE**. Stopping for
the product owner's ruling per protocol.

5B was removed with the killed opponent style-matchup track. Thresholds, targets, cohort, metrics,
and the decision rule were fixed in the phase text **before any result was computed**; all
evaluation inputs are frozen copies under `data/parquet/frozen_eval/` (movers/stayers frames,
season-start-regime deployment, target split-half), read-only for the metrics. Reproduce:
`make phase5`.

---

## 0. Pre-registration as executed

- **Question:** do deployment-system terms predict movers beyond the Atlas rating?
- **Cohort:** Atlas `movers_eval` definition, all 15 pairs 2010-26 (**1,702 of 1,705** mover-
  instances; 3 dropped for a null season-start-regime deployment fingerprint — reported as a
  product). **6,138 stayers** as the population contrast.
- **Target:** mean of dest-season (S+1) and follow-up (S+2) 5v5 on-ice xG share where the player
  has **400+ prorated** 5v5 min in both (proration = `toi_min × 82 / season_scheduled_games`);
  players with only S+1 use S+1 alone — the **`s1_only` subgroup** (n=521; `both` n=1,181).
- **Predictors, nested and leakage-clean:**
  - **(i) incumbent** — Atlas variant RAPM alone, calibrated to the task: `target ~ q_S`
    (q = off+def, origin-season rating), coefficients refit per fold on train movers.
  - **(ii) + deployment** — `target ~ q_S + sys`, where `sys` = the Design B deployment-system
    contribution (deployment + type×deployment) evaluated at the **destination season-start
    regime's** deployment fingerprint (the coach behind the bench at game 1), with the player's
    **origin-season type** as the predicted role. The held-out fold's `sys` is recomputed from a
    Design B refit **excluding that fold's target seasons {S+1, S+2}** — so no evaluation outcome
    trains the system term. `q_S` is external/frozen Atlas RAPM.
- **Metrics:** MAE and Spearman, **leave-one-season-pair-out**; 1000-resample bootstrap CIs on
  (ii)−(i).
- **Decision rule (fixed):** SHIP if (ii) improves MAE over (i) by **≥3% and the CI excludes
  zero**; INVESTIGATE at 0–3% or CI spanning zero; KILL if no improvement.

---

## 1. Primary result (5A) — movers

| model | MAE | Spearman |
|---|---:|---:|
| (i) incumbent — RAPM only | **0.03227** | 0.3109 |
| (ii) + deployment-system | **0.03201** | 0.3250 |

- **MAE improvement: 0.81%** (95% CI **[0.15%, 1.50%]**).
- MAE difference (i−ii): +0.00026, 95% CI [+0.00005, +0.00048].
- Spearman: 0.311 → 0.325.

(Bootstrap percentiles are stable to ~±0.02 pp of BLAS float noise across reruns; the decision
and every substantive figure are invariant.)

**Decision (per the fixed rule): INVESTIGATE.** The improvement is positive and its CI excludes
zero, but the point estimate (0.81%) is below the 3% SHIP threshold.

---

## 2. Population contrast — stayers

| model | MAE (stayers, n=6,138) |
|---|---:|
| (i) incumbent | 0.02849 |
| (ii) + deployment | 0.02836 |

Stayers MAE improvement **0.49%** — the deployment term helps stayers about 60% as much as
movers (0.81%), i.e. movers benefit somewhat more, as the hypothesis predicts, but both effects
are small and neither would clear the bar.

---

## 3. Slices

| slice | n | MAE (i) | MAE (ii) | improvement |
|---|---:|---:|---:|---:|
| **pos = D** | 604 | 0.03039 | 0.02990 | **+1.62%** |
| pos = F | 1098 | 0.03330 | 0.03317 | +0.40% |
| type D0 (PP-QB) | 387 | 0.02920 | 0.02864 | **+1.91%** |
| type D1 (shutdown) | 217 | 0.03251 | 0.03214 | +1.15% |
| type F3 (top-PP scorer) | 239 | 0.02890 | 0.02859 | +1.08% |
| type F2 (mid-PP) | 305 | 0.03326 | 0.03306 | +0.59% |
| type F1 (mid-PK) | 242 | 0.03641 | 0.03632 | +0.24% |
| type F0 (bottom-6) | 312 | 0.03430 | 0.03433 | −0.08% |
| **TOI high** | 579 | 0.03131 | 0.03054 | **+2.48%** |
| TOI mid | 561 | 0.03025 | 0.03035 | −0.33% |
| TOI low | 562 | 0.03526 | 0.03517 | +0.25% |
| subgroup both (2-season target) | 1181 | 0.02960 | 0.02924 | +1.22% |
| subgroup s1_only | 521 | 0.03830 | 0.03827 | +0.08% |

The deployment signal is concentrated in **defensemen** (D0 +1.91%, D +1.62%), **high-TOI
players** (+2.48%), and the **less-noisy 2-season-target subgroup** (+1.22%); it is ~zero for
bottom-six forwards and mid-TOI. No slice reaches 3%. The high-TOI slice is the closest to
material and the natural place any follow-up (per an INVESTIGATE ruling) would look.

---

## 4. Influence (robustness)

| test | improvement % |
|---|---:|
| base | 0.808 |
| jackknife (leave-one-mover-out) | min 0.778 · max 0.842 · sd 0.009 |
| top-25 (ii)-residual removal (n=1,677) | 0.876 |

The improvement is **not driven by outliers**: leave-one-out barely moves it (sd 0.009 pp), and
removing the 25 worst-fit movers slightly *raises* it (0.88%). The effect is small but stable.

---

## 5. Noise-ceiling accounting (5C)

Target split-half reliability (odd/even games within the target seasons), Spearman-Brown adjusted
to full length: **r = 0.698** (raw half r = 0.536) — the expected ~0.70 for one-season 5v5 xG
share, confirming the target as evaluated is only ~70% reliable, so predictable variance is
capped there.

Against that ceiling:

| model | R² vs target | R² as share of reliability ceiling |
|---|---:|---:|
| (i) incumbent | 0.105 | 15.1% |
| (ii) + deployment | 0.114 | 16.3% |

The deployment term adds **0.009 R²** — about **1.3% of the reliability ceiling**. The signal is
real but sits in a thin band: even a perfect model could explain ~0.70 of the variance, RAPM
alone reaches ~0.11, and deployment moves that by a sliver.

---

## 6. The 10 worst misses (context)

Signed (ii) residual = pred − target:

| player | destination | type | target | pred (ii) | residual | subgroup |
|---|---|---|---:|---:|---:|---|
| Mike Brown | EDM 2012-13 | F1 | 0.316 | 0.487 | +0.171 | s1_only |
| Zack Kassian | ARI 2022-23 | F1 | 0.336 | 0.481 | +0.145 | s1_only |
| Dylan Cozens | OTT 2025-26 | F0 | 0.606 | 0.474 | −0.132 | s1_only |
| Jay McClement | TOR 2012-13 | F2 | 0.369 | 0.495 | +0.126 | both |
| Eric Belanger | EDM 2011-12 | F3 | 0.378 | 0.503 | +0.125 | both |
| Cody Hodgson | NSH 2015-16 | F0 | 0.606 | 0.481 | −0.125 | s1_only |
| Taylor Pyatt | PIT 2013-14 | F1 | 0.368 | 0.492 | +0.123 | s1_only |
| Valeri Nichushkin | COL 2019-20 | F1 | 0.611 | 0.488 | −0.123 | both |
| Luke Schenn | WPG 2025-26 | D0 | 0.379 | 0.500 | +0.121 | s1_only |
| Carter Verhaeghe | FLA 2020-21 | F1 | 0.606 | 0.490 | −0.116 | both |

The misses are dominated by **single-season (`s1_only`) targets** (noisier by construction) and
by genuine role/production surprises no deployment model captures: bottom-six checkers landing in
tough on-ice roles on weak teams (Brown, Kassian, Pyatt), and breakouts the rating under-rated
(Nichushkin COL 2019-20, Verhaeghe FLA 2020-21). These are regression-to-mean and
opportunity-change stories, not deployment-system failures.

---

## 7. Decision (no editorializing)

Per the pre-registered rule, on the primary movers metric:
**improvement 0.81%, 95% CI [0.13%, 1.50%] → within [0, 3%] → INVESTIGATE.**

Supporting facts for the product owner's ruling: the effect is directionally correct
(CI excludes zero; movers > stayers; stable under influence), concentrated in defensemen and
high-TOI players, and sits at ~1.3% of the target's reliability ceiling. It does not reach the
SHIP bar and is not zero/negative. **Stopping for the product owner to rule.**

---

### Artifacts
`data/parquet/frozen_eval/{movers_eval_frame,stayers_eval_frame,season_start_regime_deploy,
target_splithalf}.parquet` (frozen before metrics) · `reports/phase5_analysis.json` · tests
`tests/test_phase5.py` (4 new; 17 total). Repro: `make phase5`.
