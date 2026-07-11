# Phase 2 addendum — the offense/defense asymmetry question (exploratory)

**Project:** System Effects · **Date:** 2026-07-11 · **Seed:** 20260711
**Status:** exploratory; runs independently of Phase 3. Same thresholds as Phase 2
(coaching-sensitive ⟺ ratio > 1.25 **and** permutation p < 0.05); this addendum can add to
the watch-list or promote a metric only via those thresholds — it cannot relax them.

Method: 49 Cohort C changes vs 424 placebo splits (random midpoint splits of one-regime
team-seasons, seed 20260711), permutation p over 2000 perms. All metrics are the frozen,
score-close Phase 2 primitives; the new PK metric (§A2) is built the same way.

---

## A1 — Family-level discontinuity test

Each style metric's per-unit |Δ| is standardized by **that metric's placebo-median |Δ|**;
a family's pooled shift for a unit is the mean of its metrics' standardized |Δ|. Real vs
placebo is then compared at the family level. Deployment is the **calibration reference** —
it should (and does) dominate.

**Offensive family** (7): rush/cycle/forecheck/point-shot shares-for + PP location-for (inner/outer/point).
**Defensive family** (8): shot-location-against (inner/outer/point) + rush-share-against + cycle-share-against + **PK location-against (inner/outer/point)** (§A2).
**Deployment family** (2, calibration): top-6 forward TOI share + zone-start polarization.

| family | metrics | pooled real (mean) | pooled placebo (mean) | **ratio** | perm p | coaching-sensitive |
|---|---:|---:|---:|---:|---:|:--:|
| **deployment** (ref) | 2 | 2.102 | 1.312 | **1.60** | **0.0005** | ✅ |
| offensive | 7 | 1.268 | 1.181 | 1.074 | 0.079 | – |
| defensive | 8 | 1.279 | 1.206 | 1.060 | 0.139 | – |

Deployment moves ~1.6× more at real coach changes than at placebos (p=0.0005) — the test is
calibrated. **Neither style family clears the bar.** Offensive (1.074, p=0.079) is marginally
*higher* and closer to significance than defensive (1.060, p=0.139) — the reverse of the
common "defense is the more coachable half" intuition.

---

## A2 — New metric: PK shot-location-against profile

Inner/outer/point shares of unblocked attempts conceded **while shorthanded** (strength
ice-derived: a man-advantage shot for one side = a PK-against event for its opponent).
Built as a summable primitive (`fingerprints.build_pk`, `data/parquet/pk/`).

**Discontinuity (individual):**

| PK metric | median \|Δ\| real | median \|Δ\| placebo | ratio | perm p | sensitive |
|---|---:|---:|---:|---:|:--:|
| pk_loc_inner_against | 0.0347 | 0.0332 | 0.994 | 0.500 | – |
| pk_loc_outer_against | 0.0347 | 0.0359 | 1.055 | 0.322 | – |
| pk_loc_point_against | 0.0243 | 0.0258 | 0.939 | 0.680 | – |

**Split-half reliability** (odd/even, 184 regimes ≥40 games): inner **0.565**, outer
**0.717**, point **0.807** — all above 0.5. The metrics are reliable, so the null result is
**not** a reliability artifact: the PK location profile is a stable team property that simply
does **not** shift at coach changes more than at random midseason splits.

---

## A3 — Verdict

Defensive identity does **not** move more than offensive identity at coach changes — the two
style families are statistically indistinguishable from placebo, with the offensive family if
anything marginally stronger (offensive 1.07, p=0.079; defensive 1.06, p=0.139), overturning
the intuition that the defensive half is the more coach-owned one. The **penalty kill
specifically is not coach-owned** at this resolution: despite being a reliable, stable metric
(split-half r 0.57–0.81), its shot-location-against profile shifts no more at real coach
changes than at placebo splits (ratios 0.94–1.06, p 0.32–0.68) — a genuinely surprising null
for a phase of play coaches drill heavily, and one this exploratory test is built to catch
rather than assume. **None of this changes the Phase 2 ruling.** Deployment remains the only
validated coaching-sensitive family (1.60, p=0.0005); nothing here clears the ratio > 1.25 and
p < 0.05 bar, so nothing promotes to the validated set. The single item earning a **watch-list**
note is the **offensive family** (p=0.079) — the closest to significance and a candidate to
re-test if Phase 3's movers track adds statistical power. Phase 3 should still anchor
portability on deployment; offensive and defensive on-ice style, including the PK, stay
descriptive context under the Phase 2 §4 caveat.

Artifacts: `data/parquet/pk/*` · `reports/phase2_addendum_analysis.json`.
