# Phase 2 — The keystone: is pair chemistry persistent at all?

**Project:** Chemistry (`NIR/research/chemistry/`)
**Date:** 2026-07-12 · **Seed:** 20260712 · **polars** 1.42.1 · **scikit-learn** RidgeCV
**Status:** Phase 2 complete. Thresholds, strata, and verdict language were fixed before results
(§0, §4). The pre-registered rule lands in a configuration it does not enumerate; per the protocol
the **owner rules on survival**. Stopping after the exhibits.

Reproduce: `make phase2` (builds pair-half tables + strata, fits the null under both anchors, runs
both persistence tests with placebos, writes `reports/phase2_analysis.json`). Tests: `make test`.

---

## 0. Housekeeping confirmation (requested)

The System Effects durability commit **was made** — no new commit was needed:

- **SHA** `3ae4f52f7021ccd89c470ac5797cdc88ab8cf06a` — *"durability commit of completed system-effects
  artifacts; no content changes"*
- **51 files, +17,022 insertions**: all `research/system-effects/src/syseff/*` (context, design_a/b,
  jolt, opponent, phase3/4/5, player_types, portability, prospective, stability, summer,
  team_season, api), `research/system-effects/reports/{phase3,phase4,phase5,phase5-jolt-addendum,
  phase5-summer-addendum,phase6,FINDINGS,registration_2027,registration_jolt}.md`,
  `research/system-effects/tests/{test_jolt,test_phase3,test_phase4,test_phase5,test_summer}.py`,
  `research/PROGRAM-FINDINGS.md`, `research/deployment-atlas/reports/FINDINGS.md`, plus the staged
  production DBT (`dbt/models/mart/mart_syseff_*`, `dbt/seeds/syseff/*`, `dbt/tests/assert_syseff_*`,
  `dbt/models/staging/stg_syseff_game_coaches.sql`), `dags/nhl_daily.py`,
  `ingestion/backfill_coach_loader.py`, `docs/rebuild-reports/syseff-p7.md`.
- **Working tree carries no uncommitted System Effects artifacts** (verified: `git status` clean for
  `research/system-effects/`, `dbt/**/syseff*`, `ingestion/backfill_coach_loader.py`).

---

## 1. The additive-plus-curvature null (2.1) and its two anchors (2.1b)

Pair xG share during shared TOI is modeled from individual quality and context only: symmetrized
rapm_variant (`sum_off`, `sum_def`), talent-curvature (`product` and `squared-sum` of the two total
ratings), position-pair class, OZ start share, score-state mix, opponent strength, and season fixed
effects. Weighted Ridge (weights = shared TOI), **leave-one-season-out** CV, `RidgeCV` α selected
from {0.1,1,10,100} (α=100 both anchors). The **pair residual** (observed − predicted) is the
candidate chemistry quantity, carried TOI-weighted everywhere.

| anchor | pairs used | dropped (no rating) | LOSO CV wtd R² | key coefficients (direction) |
|---|---:|---:|---:|---|
| **same-season** (primary, conservative) | 90,315 | 212 | **0.506** | sum_off +.033, sum_def +.028, OZ +.013, opp −.007 ✓ |
| **prior-season + drift** (sensitivity, clean) | 67,289 | 23,238 | 0.219 | sum_off +.016, sum_def +.013, OZ +.017, opp −.003 ✓ |

Coefficients are directionally sane under both anchors (more individual quality → higher pair share;
more offensive-zone starts → higher; tougher opponent → lower). Curvature terms are small
(`product`, `squared-sum` ≈ 0), i.e. generic diminishing-returns between two high-quality players is
present but minor — and, importantly, it is **absorbed by the null**, so it cannot masquerade as
dyadic chemistry downstream.

**⚠ Deviation flagged — the 2.1b "age-drift adjustment."** The frozen Atlas inputs carry **no
birthdate/age** for any player (verified across rosters, player_context, boxscore, player_5v5, …).
The spec's "simple age-drift adjustment" is therefore realized as an **empirical league-wide drift
regression**: `rating_t ≈ a + b·rating_{t−1}` fit per component on all 10,982 consecutive-season
player-seasons (off: b=0.731, r=0.727; def: b=0.660, r=0.663). The slope (<1) *is* the pooled
aging + mean-reversion trend; the adjusted prior anchor = `a + b·rating_{t−1}` predicts current
ability from the past with no same-season contamination. Players without a prior season drop from
the sensitivity anchor and are counted (23,238 pair-seasons). True age-curve adjustment would require
a gated external fetch and is **not** performed.

---

## 2. Split-half persistence (2.2)

Within each pair-season at the 100-minute tier, the pair's shared games are split odd/even (by game
rank within the pair-season), and each half's residual is `share_half − pred_pair-season`. The null
prediction is the **pair-season** quantity; it is **not** re-predicted per half — score-state mix is
endogenous (post-outcome), so per-half re-prediction would leak realized performance into the
baseline. TOI-weighted split-half correlation, Spearman-Brown corrected, against a shuffled-half
placebo (N=500, seed 20260712).

| cut | **same anchor** residual SB | **prior anchor** residual SB | raw-share SB (measurement) | placebo |
|---|---:|---:|---:|---:|
| **overall (≥100 min, n≈60k/48k)** | **−0.217** | **+0.304** | +0.470 / +0.478 | ≈0.000 |
| tier 100 (100–200 min) | −0.185 | +0.235 | +0.359 | ≈0 |
| tier 200 (≥200 min) | −0.254 | +0.345 | +0.531 | ≈0 |
| D-D | −0.376 | +0.281 | +0.471 | ≈0 |
| D-F | −0.181 | +0.297 | +0.458 | ≈0 |
| F-F | −0.272 | +0.327 | +0.494 | ≈0 |
| high-diversity stratum | −0.263 | +0.274 | +0.441 | ≈0 |
| low-diversity (locked) stratum | −0.192 | +0.311 | +0.478 | ≈0 |

**Reading — the primary-anchor split-half is the 2.1b contamination made visible, not a bug.**
- The **raw pair xG-share is reliably measured** (SB ≈ 0.47 overall, 0.53 at ≥200 min): a pair's
  performance repeats across game-halves. But that reliability is dominated by **individual quality**
  (good pairs post high share in both halves), which is a season constant and therefore cannot move
  a within-pair across-half correlation.
- Removing quality is where the anchors split. Under the **prior (clean) anchor**, the quality-
  removed residual still carries reliable pair-level signal: **SB = 0.304, which clears the 0.30
  bar** (0.35 at ≥200 min). Under the **same-season (contaminated) anchor**, the same computation is
  **negative** (−0.217): same-season RAPM has already absorbed the pair's own shared-minutes
  performance, so subtracting a same-season-based prediction straddles the season mean and drives the
  residual split-half below zero. This is precisely 2.1b's warning ("biasing residuals toward zero
  exactly where locking is worst") — dropping the endogenous score-state term barely moves it
  (−0.09 → −0.04), confirming the driver is the *anchor*, not the score-state control.

So: there is a modest, reliably-measured pair residual **when quality is removed with an
uncontaminated anchor** (SB ≈ 0.30). The pre-registered primary anchor cannot see it.

---

## 3. Year-over-year persistence (2.3)

Same-pair residual correlation across consecutive seasons (both years ≥100 shared minutes), weighted
by the smaller year's shared TOI, against a **shuffled-pair placebo matched on destination team and
position class** (within-cell permutation, 2000 perms, seed 20260712).

| cut | **same anchor** r (p) | **prior anchor** r (p) |
|---|---:|---:|
| **overall** | **0.051 (p=0.0005)** ✓ | **0.041 (p=0.0375)** ✓ |
| D-D | 0.087 (p=0.007) ✓ | 0.077 (p=0.109) ✗ |
| D-F | 0.040 (p=0.000) ✓ | 0.032 (p=0.161) ✗ |
| F-F | 0.083 (p=0.000) ✓ | 0.063 (p=0.052) ✗ |
| high-diversity stratum | 0.034 (p=0.051) ✗ | 0.011 (p=0.855) ✗ |
| mid-diversity stratum | 0.043 (p=0.0005) ✓ | 0.020 (p=0.567) ✗ |
| low-diversity (locked) stratum | 0.065 (p=0.0005) ✓ | 0.065 (p=0.001) ✓ |

**Reading — the YoY signal is real but tiny, and it lives where it cannot be identified.**
- Overall YoY same-pair correlation exceeds its matched placebo under **both** anchors (p=0.0005
  same; p=0.0375 prior). But the effect is **very small** — r ≈ 0.04–0.05, i.e. a pair's
  quality-removed residual explains ≈ 0.2–0.3% of its next-season residual.
- The persistence **concentrates in locked pairs and evaporates in diverse pairs.** Under the clean
  prior anchor the entire overall signal is carried by the **low-diversity (locked) stratum**
  (r=0.065, p=0.001); the **high-diversity stratum shows nothing** (r=0.011, p=0.855) and mid is null
  (p=0.567). The same ordering holds under the same anchor (high-div weakest, p=0.051; D-D — the most
  locked class — strongest, r=0.087). Whatever persists is a property of *pairings that rarely
  break up* — exactly where "the pair" and "the players/deployment" are collinear (Phase 1 O3: a
  defenseman pours a median 48%, p90 78%, of his D-partner minutes into one partner) and where a
  persistent pair residual is **not identifiable** from persistent individual/usage structure the
  anchor did not fully remove.

---

## 4. Verdict (2.4) — stated per the rule, no editorializing

Pre-registered bars (fixed in §0 before results): split-half SB ≥ **0.30** at the 100-minute tier
**AND** YoY same-pair correlation exceeds its matched placebo at permutation **p < 0.05**, **on the
primary (same-season) anchor, full population**.

**Primary anchor, full population:**
- split-half SB (≥100-min tier) = **−0.217** → **does NOT clear 0.30**.
- YoY p = **0.0005** → **clears p < 0.05**.

The enumerated 2.4 outcomes are PASS (both bars), "only split-half passes → within-era", "both fail
→ die", and the one-shot rescue. The realized configuration is **split-half fails while YoY passes** —
which 2.4 does not enumerate. No branch that continues the predictive arm is satisfied: PASS requires
the split-half bar (not met); "split-half only" requires the split-half bar (not met); the **rescue
clause is NOT triggered** — the high-diversity stratum fails both bars under both anchors (split-half
−0.263 same / +0.274 prior; YoY p=0.051 same / 0.855 prior). "Both fail → die" is the only remaining
branch, but YoY did not fail, so the state is not literally "both fail."

**Machine outcome:** `UNDEFINED_BY_2.4 → OWNER RULES`. The primary-anchor split-half is additionally
confounded by the 2.1b anchor contamination documented in §2 (raw-share SB +0.47; clean prior-anchor
residual SB +0.30). Per the STOP, the owner rules on survival. A recommendation is offered in §6,
kept separate from this verdict statement.

---

## 5. Descriptive exhibits (2.5) — presented regardless of verdict

**Largest 2024-25 pair residuals (≥200 shared min), grouped-bootstrap 95% CI over shared games
(N=1000, seed 20260712).** Absolute effect (residual in xG-share points) primary. Names are not in
the frozen inputs; only 2024-25 top-20 players are labelled, the rest by `player_id`.

*Top positive (all D-F):*
| pair | pos | shared min | xG share | residual | 95% CI |
|---|---|---:|---:|---:|---|
| 8481553 + 8482142 | D-F | 252 | 0.622 | **+0.159** | [+0.070, +0.241] |
| 8475171 + 8478904 | D-F | 229 | 0.607 | +0.145 | [+0.048, +0.247] |
| 8478483 + 8481122 | D-F | 234 | 0.553 | +0.137 | [+0.048, +0.222] |
| 8478038 + **Martin Necas** | D-F | 251 | 0.672 | +0.132 | [+0.083, +0.188] |

*Bottom negative (all D-F):*
| pair | pos | shared min | xG share | residual | 95% CI |
|---|---|---:|---:|---:|---|
| 8476880 + 8477845 | D-F | 336 | 0.419 | **−0.130** | [−0.195, −0.055] |
| 8476923 + 8479944 | D-F | 290 | 0.410 | −0.125 | [−0.209, −0.035] |
| 8473507 + 8483464 | D-F | 204 | 0.432 | −0.115 | [−0.203, −0.020] |

Single-season pair residuals **can be large and have CIs that exclude zero** (±0.13–0.16 xG-share
points). The persistence tests (§2–§3) are what establish whether such a number **repeats** — and it
largely does not once quality is removed with a clean anchor, except weakly in locked pairs.

**Long-tenure "famous" pairs (most cumulative shared TOI, ≥3 seasons together), pooled TOI-weighted
residual:**
| pair (player_ids) | seasons together | total shared min | pooled residual |
|---|---:|---:|---:|
| 8470638 + 8473419 | 13 | 9,443 | **+0.004** |
| 8471685 + 8474563 | 16 | 7,879 | +0.004 |
| 8467875 + 8467876 | 8 | 7,349 | −0.012 |
| 8470600 + 8474716 | 9 | 7,293 | +0.003 |
| 8471214 + 8473563 | 13 | 7,281 | +0.001 |
| 8470606 + 8471685 | 12 | 7,086 | +0.007 |

The most-established pairs in the league — up to **16 seasons together** — pool to a residual of
**essentially zero** (|pooled| ≤ 0.012 xG-share points). Pairs that stay together do so because the
*players* are good (the null captures it), not because a durable pair residual accrues. This is the
face-valid sanity read of §3's near-null.

---

## 6. Recommendation to the owner (separate from the §4 verdict)

The evidence, taken together, points **against** launching a general chemistry predictive arm:

1. The **rescue clause is the decisive test** — it exists precisely to find chemistry where it is
   *identifiable* (diverse pairs). It **fails**: high-diversity pairs show no YoY persistence under
   either anchor (p=0.051 same, 0.855 prior) and their split-half is below bar (−0.26 same, +0.27
   prior). The one place dyadic chemistry could be cleanly identified is the one place it is absent.
2. The persistence that *does* clear bars is **tiny** (YoY r≈0.04–0.09) and **concentrated in locked
   pairs** (low-diversity, D-D), i.e. where a pair residual is not separable from persistent
   individual/usage structure — the Phase 1 O3 identifiability trap.
3. Long-tenure pairs pool to **~0** residual; the exhibits' large single-season residuals do not
   persist.
4. The only reading under which a bar clears cleanly is the **prior-anchor overall** (split-half
   0.30, YoY p=0.037) — but that YoY is **entirely locked-pair-driven** and the prior anchor
   under-removes within-season individual quality change, so it is lenient, not confirmatory.

**Recommended ruling:** treat this as the **null / both-fail path in substance** — the identifiable
(diverse-pair) chemistry signal is absent, so Phases 3–5 (the predictive arm) should **not** proceed
as specified; **Phase 6 packages the corpus and this null finding.** If the owner wishes to pursue
the marginal locked-pair signal, it requires a **new pre-registration** acknowledging that locked-pair
effects are, by construction, not identifiable from individual quality — and would be descriptive
only. This is a recommendation; the ruling is the owner's.

---

## 7. Decisions & deviations recorded

- **Age-drift substitution** (§1): no birthdates in frozen inputs → empirical league-wide drift
  regression stands in for the 2.1b "age-drift adjustment." Flagged; a true age curve needs a gate.
- **Split-half baseline** (§2): the null is applied at pair-season grain (constant per pair) to each
  half; it is *not* re-predicted with endogenous half-context (score-state), which would flip the
  correlation by construction. The same-anchor negative is the 2.1b contamination, evidenced by the
  clean prior anchor (+0.30) and raw-share reliability (+0.47).
- **Verdict configuration** (§4): 2.4 does not enumerate "split-half fails, YoY passes"; the rescue
  fails; machine outcome `UNDEFINED_BY_2.4 → OWNER RULES`.
- **Player names** (§5): no player_id→name map in frozen inputs (only 2024-25 top-20). Exhibits use
  player_id with top-20 labels; full name resolution deferred to the production dim (not fetched).
- **`run(seasons=…)`** limits only which season half-tables feed split-half; the null fit, strata,
  and YoY always use the full 16-season corpus. The reported run uses all seasons everywhere.

### Artifacts
`src/chem/nullmodel.py` · `src/chem/phase2.py` · `reports/phase2.md` · `reports/phase2_analysis.json`
· `data/parquet/pair_halves/*` (gitignored). Frozen Atlas / System-Effects inputs untouched.

**STOP** — the owner rules on survival (§4 verdict; §6 recommendation).
