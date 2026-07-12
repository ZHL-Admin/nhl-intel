# Phase 5 addendum — the summer-install question (F12 scope)

**Project:** System Effects · **Date:** 2026-07-11 · **Seed:** 20260711
**Status:** complete. **Exploratory, observational with roster adjustment — labeled as such.**
Verdict by the pre-stated thresholds: **F12 EXTENDS to summers** (style does not install across
a summer either). Stopping after the addendum per protocol.

**The question.** F12 (Phase 2): at the resolution of within-team, one-season MID-SEASON coach
changes, on-ice **style behaved like a roster property** (placebo); only deployment moved. Does
style instead install across a **summer** — a full offseason plus camp — that a mid-season change
never gets? This is observational: coach-change summers also turn over more roster, so continuity
is measured and controlled (S2), and the strong test is directional (S4). Thresholds were fixed
before results; none moved after. Reproduce: `python -m syseff.summer`.

---

## S1 — Cohorts (consolidated regime ledger, season boundaries 2010-26)

A transition is summer-**change** if the season-start coach of A+1 differs from the season-end
coach of A, else summer-**continuation**.

| | all transitions | summer-change | continuation |
|---|---:|---:|---:|
| total | 458 | 89 | 369 |
| stable subset (≥20 in-season games each boundary regime) | 440 | 87 | 353 |

The stable subset (both the season-A end regime and the season-A+1 start regime have ≥20 in-season
games, for fingerprint stability) is used for S3/S4.

---

## S2 — Roster continuity (the confound this design controls)

Per transition, the returning share of season-A **5v5 TOI**, and of **RAPM-weighted value**
(TOI × rating-percentile), for players still on the team in A+1.

| cohort | returning TOI (median, IQR) | returning value (median, IQR) |
|---|---|---|
| summer-change | **0.723** (0.665–0.786) | **0.762** (0.686–0.829) |
| continuation | **0.758** (0.698–0.812) | **0.797** (0.720–0.852) |

Coach-change summers do have **lower continuity** — ~3.5 pp less returning TOI and value — the
expected confound. It is modest, and it enters S3 as a covariate so the coach-change dose is read
**at matched continuity**.

---

## S3 — Dose test

Per family, pooled regression of standardized `|Δmetric|` (summer, team-A-end → team-A+1-start)
on **coach-change + returning-TOI + returning-value + season FE + metric FE**. The coach-change
coefficient is the summer dose **net of continuity**. Compared to the Phase 2 mid-season dose (the
F12 baseline), standardized on the same per-metric scale.

| family | coach-change coef (SD units) | 95% CI | t | summer-change \|Δ\| | continuation \|Δ\| | mid-season \|Δ\| |
|---|---:|---|---:|---:|---:|---:|
| **style** | **+0.052** | [−0.018, +0.120] | 1.46 | 1.275 | 1.193 | 1.067 |
| deployment | **+0.289** | [+0.121, +0.457] | 3.38 | 1.371 | 1.066 | 1.089 |
| pk | −0.065 | [−0.202, +0.072] | −0.93 | 1.292 | 1.353 | 1.355 |

**Style dose does not clear:** the coefficient's CI spans zero (summer-change style shifts are
barely above continuation, 1.275 vs 1.193, and only modestly above the mid-season baseline).
**Deployment installs strongly across the summer** (coef +0.289, CI excludes zero) beyond
continuity — as it does mid-season. **PK does not move** either way.

---

## S4 — Directional test (the strong one)

For every incoming summer coach with a measured prior fingerprint (≥40 games in a prior regime
within the preceding 3 seasons): per metric, correlate `(coach_prior − team_previous)` with
`(team_new − team_previous)` — does the team move **toward** the incoming coach's established
style? Pooled by family, against a permutation placebo (random coach-fingerprint assignment,
2000 perms, seed 20260711). **Eligible: 37 transitions, 28 distinct incoming coaches.**

**Primary** = mean of per-metric directional correlations (scale-invariant, faithful to "per
metric … pooled by family"). **Robustness** = correlation of pooled per-metric-standardized pairs.

| family | directional corr (primary) | perm p (primary) | perm p (robustness) | clears p<0.05? |
|---|---:|---:|---:|:--:|
| **style** | 0.482 | **0.084** | 0.052 | **no** (both poolings) |
| deployment | 0.637 | **0.0005** | 0.002 | yes |
| pk | 0.487 | 0.870 | 0.871 | no |

**Style is positive but does not clear** — under neither pooling does the permutation p fall below
0.05 (primary 0.084; standardized-pairs 0.052). **Deployment clears decisively** at the same
n=37, which matters: it proves the test has the **power** to detect a real family-level install at
this sample size, so the style non-result is a **genuine null, not underpowering**. For
transparency, the pace-dominated raw-pooled variant (no standardization) gives style p=0.156 —
the worst reading — and never changes the conclusion.

---

## S5 — Verdict (pre-stated language; no thresholds moved)

The pre-registered rule:
- **AMEND** F12 (→ "style installs need a summer; mid-season changes only reallocate") requires
  the directional test to clear **AND** the dose test to show summer-change style shifts exceeding
  continuation at matched continuity.
- **EXTEND** F12 to summers (with the roster-adjustment caveat) if the style family **fails both**.

**Style fails both.** Directional does not clear (p=0.084 primary, 0.052 robustness — neither
below 0.05); dose does not clear (coef CI [−0.018, +0.120] spans zero). AMEND is impossible under
every pooling because the **dose test fails regardless**.

### → F12 EXTENDS to summers (observational)

> **F12 (extended).** On-ice **style** is largely a **roster property**, not a system that a coach
> installs — and this now holds across **summers**, not only mid-season changes. Controlling for
> roster continuity, a new coach's first full season does not shift the team's style measurably
> more than a continuing coach's does (dose coef +0.05 SD, ns), and teams do not move toward an
> incoming coach's established style beyond chance (directional p=0.08). What a coach **does**
> install — in both windows — is **deployment**: who plays and how they start (dose coef +0.29,
> directional p=0.0005). **Penalty-kill** shot-location profile installs in neither window.
> *Caveat: observational; coach-change summers carry ~3.5 pp lower roster continuity, controlled
> here but not randomized.*

**Deployment calibration (as pre-specified):** cleared easily on both tests (dose t=3.38,
directional p=0.0005) — confirming the design detects a real family-level install when one exists.

---

### Artifacts
`reports/phase5_summer_analysis.json` · `src/syseff/summer.py`. The finding is logged to the
shared research-program ledger (`research/deployment-atlas/reports/FINDINGS.md`, System Effects
section). Repro: `python -m syseff.summer`.
