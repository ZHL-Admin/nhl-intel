# Phase 3 — Effects estimation, both tracks

**Project:** System Effects · **Date:** 2026-07-11 · **Seed:** 20260711
**Status:** Phase 3 complete. The two tracks return an asymmetric verdict that is exactly the
Phase-3-gate decision the spec anticipates — the INTERNAL/deployment track is alive and
persistent; the OPPONENT style-matchup track fails stability and is a kill candidate (its
strength-based schedule normalization survives). See **§7 For review**. Stopping per protocol.

Frozen-asset provenance: Atlas freeze `24acbab`; rebuild PR #1 merged (`8148462`). Reproduce:
`make primitives && make phase3` (all heavy primitives cached under `data/parquet/`; seeded).

---

## 0. Build-the-delta primitives (rule 7b) — and the one data gap

Phase 0/1 recorded that Atlas `player_context` and the coach fingerprints are materialized for
**2024-25 only**. Three cached primitives re-derive what Phase 3 needs for all 16 seasons from
the **frozen stints**, strength ICE-derived, quarantined stints excluded:

| primitive | grain | use |
|---|---|---|
| `pctx/` | (player, team, season) | 5v5 TOI, PP/PK sec, OZ/DZ starts → pooling + matching covariates |
| `depfull/` | (game, team, player) | 5v5 TOI + PP/PK + OZ/DZ starts, summable over any game set → Design A regime split |
| `onice/` | (game, team, player) | 5v5 on-ice xGF/xGA (all + score-close) → on-ice xG share over any game set |

**Reconciliation vs the one materialized Atlas season (2024-25):** the re-derivation matches
Atlas `player_context_2024-25` essentially exactly — `toi_5v5_min` and `oz_start_share` corr
**1.000** (mad ≤ 0.0001); `pp_frac`/`pk_frac` vs Atlas `pp_share_of_own`/`pk_share_of_own`
corr **0.9997** (mad ≤ 0.0014) once the man-advantage definition excludes pulled-goalie
(6v5/5v6) time. Guarded by `tests/test_phase3.py`.

**Data gap (recorded honestly).** **No birthdate/age exists in any frozen Atlas asset** (full
scan, §Artifacts). The spec's 3.2 "age band" matching covariate is therefore served by an
**experience proxy**: seasons since a player's first appearance in the frozen rosters
(`rookie ≤2`, `prime 3-6`, `vet 7+`). Documented as a proxy, not true age. This is the only
place Phase 3 could not honor a spec covariate exactly.

---

## 1. Pooling layer (3.1)

Phase 0 found production `player_archetypes` stale-backbone-derived and rebuild-divergent, so
(as recorded) Phase 3 derives its **own** types from frozen assets — an isolation choice, not a
staleness workaround. **Definition** (`player_types.py`): features per player-season with
**200+ 5v5 min** = variant RAPM `off_impact`, `def_impact`; `oz_start_share`; `pp_frac`;
`pk_frac`; per-game 5v5 TOI. Z-score over the pooled 10,961 player-seasons; **position-
stratified KMeans** (F and D have structurally different roles), `k` per position by silhouette
over a grid constrained so the total lands in the spec's [6,10] band; label each type by its
standardized centroid. **All 10,961 qualifying player-seasons are assigned** (0 unclustered).

**6 types (F k=4 sil 0.19 · D k=2 sil 0.21):**

| type | label | n | toi/gp | oz% | pp | pk | off | def |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| F | bottom-6 EV checker | 1739 | 10.5 | .50 | .04 | .03 | −.051 | +.013 |
| F | mid PK checker | 1723 | 10.9 | .39 | .03 | .13 | −.059 | +.043 |
| F | top-6 PP scorer | 1771 | 13.4 | .53 | .14 | .04 | **+.139** | +.053 |
| F | mid PP scorer (sheltered) | 1823 | 13.1 | .55 | .15 | .03 | +.023 | −.092 |
| D | top-pair PP-QB (offensive) | 1558 | 16.3 | .54 | .10 | .06 | +.061 | −.021 |
| D | bottom-pair PK (shutdown) | 2347 | 15.3 | .47 | .02 | .10 | −.044 | +.010 |

Defense splits cleanly in two by silhouette (offensive PP-QB vs shutdown PK); forwards into
four (two checking, two scoring). These are the interaction levels for Design B.

---

## 2. INTERNAL track, Design A — coach-change experiments (3.2)

Reframed per the Phase 2 finding (**deployment is the validated treatment**; on-ice shot-style
behaved like placebo). For all **49 Cohort C changes**, each skater with **100+ 5v5 min under
both** the old and new coach (**868 treated players**) gets within-player old→new deltas,
differenced against **matched controls** (8,100 one-regime player-seasons; same season,
position, experience band, TOI tier within 3 min/gp, prior RAPM within 0.15) split at a
within-season midpoint (2nd-half − 1st-half) — a difference-in-differences that removes natural
within-season drift.

### The causal chain: coach change → deployment change → result change

**DiD (treated old→new minus matched-control 1st→2nd half):**

| axis | mean treated Δ | mean DiD | sd | t | n |
|---|---:|---:|---:|---:|---:|
| 5v5 TOI/gp (min) | −0.318 | +0.097 | 3.42 | 0.83 | 868 |
| **OZ-start share** | −0.007 | **−0.0076** | 0.092 | **−2.43** | 868 |
| PP-frac | −0.009 | −0.0011 | 0.034 | −0.98 | 868 |
| PK-frac | −0.007 | −0.0015 | 0.033 | −1.32 | 868 |
| top-unit membership | −0.013 | +0.015 | 0.54 | 0.84 | 868 |
| on-ice xG share (all) | +0.001 | +0.0029 | 0.064 | 1.32 | 868 |
| **on-ice xG share (close)** | +0.002 | **+0.0042** | 0.072 | **1.73** | 868 |

The **treatment end of the chain is real**: a coach change moves players' **OZ-start share**
significantly more than controls (t=−2.43) — deployment is where coaching bites, consistent
with Phase 2. The **result end is small**: a marginal +0.004 on-ice xG-share DiD bump
(t=1.73), the familiar new-coach/mean-reversion nudge.

### Mediation — the link is weak

Regressing each treated player's score-close on-ice xG-share delta on the deployment deltas:
**deployment carries only R² = 0.04** of the within-player result-delta variance (largest
standardized β is OZ-share, +0.013). So the small result bump is **not** meaningfully mediated
by the measured deployment change. Coherent with Phase 2's thin one-season headroom.

### Split by measured deployment-fingerprint shift ("did deployment actually move?")

Median-split of the 49 changes on combined z(|Δtop6|)+z(|Δzone-pol|):

| group | n changes | n players | mean result Δ (close) | mean \|result Δ\| |
|---|---:|---:|---:|---:|
| high deployment shift | 25 | 438 | +0.0010 | 0.0566 |
| low deployment shift | 24 | 430 | +0.0021 | 0.0519 |

Players whose coach reshuffled deployment a lot show **the same** result change as those whose
coach barely moved it — reinforcing the R²=0.04 mediation: the result nudge is not driven by
the deployment reshuffle.

### Watch-list style trio (descriptive, **UNVALIDATED** — Phase 2 §4)

Mean team-level |Δ| across the 49 changes: `forecheck_share_for` 0.0105 · `pace` 3.91 ·
`loc_outer_against` 0.0259. Reported per spec, clearly labeled: these behaved like placebo in
Phase 2 and carry no coaching-effect claim here.

---

## 3. INTERNAL track, Design B — joint model on player-seasons (3.3)

**Outcome:** season 5v5 on-ice xG share per **(player, season, team)** from
`player_season_team_onice` (a traded player is two rows — extra leverage separating player
quality from team system). 200+ min → **11,395 rows, 2,052 players, 494 team-seasons.**

**Terms.** Own variant RAPM enters as a **frozen OFFSET, not refit** — a one-time OLS calibrates
quality `q = off+def` into xG-share units (intercept 0.494, slope 0.236); it alone explains
**57.1%** of xG-share variance; the system model then fits the **residual**, so system/
interaction terms cannot absorb player identity. Own-team **deployment** vector (the validated
axes) = the **system** term; own-team **style** vector included but **descriptive-context**
(Phase 2 §4 caveat); **opponent-schedule-average style** as controls; **type×deployment**
interactions (primary), **type×style** (secondary, caveated); **season** effects.

**Estimator:** Ridge (L2 = the hierarchical shrinkage), **α by GroupKFold(5) grouped on
team-season** so no team-season leaks across folds. CV picks **α=300** (confirmed against a grid
to 10,000).

**Result:** on the residual (i.e. *beyond* player quality), the system + interaction + schedule
model recovers **out-of-fold CV R² ≈ 0.073–0.076** (positive in all five folds, ~0.047–0.097).
The small run-to-run wiggle is KMeans label nondeterminism (BLAS threading) nudging a few
borderline type assignments; the substantive result — a modest but real out-of-sample system
signal — is stable.

**Shrunk system estimates** (deployment, xG-share units): `top6_fwd_toi_share` **+0.0031**,
`zone_start_polarization` **−0.0011**. Largest type×deployment interactions:
`F(mid-PK checker)×zone_pol −0.0027`, `F(mid-PP scorer)×zone_pol +0.0024`,
`D(shutdown)×top6 +0.0021`, `D(PP-QB)×top6 +0.0013` — i.e. deployment concentration helps
some types and hurts others, as expected, but all effects are small under heavy shrinkage.

**Identifiability / anchoring.** Player and system separate through **movement**: **1,201 of
2,052 players (58.5%) appear on ≥2 distinct teams**. Every team-season is anchored by a median
of **18 mover-players** (min **6**), against a median roster of 23 — so no system estimate rests
on a closed, non-moving roster. Identifiability is well-supported.

---

## 4. OPPONENT track — style matchups + schedule bias (3.4)

**Model.** Team-game 5v5 xG share (score-close) ~ both teams' **strength** (TOI-weighted roster
variant-RAPM: own & opponent off/def) + **style-interaction** terms (own ATTACK {pace, rush,
cycle, point-shot} × opponent DEFENSE {inner/outer/point-against}). Ridge, fit on **33,052
regular-season team-games, 2010-11 … 2023-24**; 2024-25 held out.

**Style matchups add almost nothing beyond strength:**

| model | R² |
|---|---:|
| strength only | 0.1118 |
| + style main effects | 0.1118 |
| + all style interactions | 0.1120 |

**Interaction R² gain = 0.00014** (0.014 pp). Coefficient magnitudes: mean |strength coef|
**0.0225** vs mean |interaction coef| **0.00038** — strength effects are **~60× larger**.
Strength coefs are sensible and symmetric (own off/def +0.022/+0.023; opp off/def
−0.022/−0.023) — the model is well-calibrated; it is the *style* interactions that are
negligible.

**Delta vs production `train_style_effect.py` (audited).** That model predicts **playoff SERIES
win probability** (logistic, ~16 series/season, end-of-RS rating + same-season fingerprint,
shrink-to-validate). This track is a different object: **continuous per-GAME 5v5 xG share over
the full regular season**, producing (a) per-matchup style effects and (b) a **per-player
schedule-bias correction** — neither of which production produces. No duplication.

**Schedule-bias exhibit (2024-25).** For each team-game, the expected xG-share shift from the
**specific** opponent vs a **league-average** opponent (opponent strength + style), aggregated to
each player TOI-weighted over their games. Magnitude is small — mean **|bias| = 0.003**
xG-share points, p90 **0.0065** — because style matchups are minor and this is mostly opponent-
strength exposure. Face-valid at the extremes:

| most flattered (easy schedule) | Δ | | most punished (hard schedule) | Δ |
|---|---:|---|---|---:|
| Spencer Stastney (NSH) | +.019 | | Nikolai Kovalenko (SJS) | −.016 |
| Ryan Lindgren (COL) | +.018 | | Hampus Lindholm (BOS) | −.016 |
| Erik Johnson (COL) | +.016 | | Nikita Nesterenko (ANA) | −.015 |
| Kyle Burroughs (LAK) | +.014 | | Elmer Söderblom (DET) | −.015 |
| Charlie Coyle (COL) | +.014 | | Jacob Bernard-Docker (BUF) | −.015 |
| Brock Nelson (COL) | +.014 | | Jeremy Lauzon (NSH) | −.014 |

The flattered list is dominated by 2025-deadline acquisitions to Colorado (Lindgren, Coyle,
Nelson, Colton) — partial-season players whose games skewed to a favorable opponent set — which
reads correctly.

---

## 5. Stability tests (3.5)

### (a) System effects persist while the coach persists

YoY correlation of the deployment fingerprint across consecutive team-seasons, **continuing
regime (same coach) vs coach change**:

| axis | continuing (n=310) | coach change (n=148) | verdict |
|---|---:|---:|---|
| **zone_start_polarization** | **r = 0.699** | r = 0.313 | ✅ persists within regime, moves at change (mean \|Δ\| 0.019 → 0.026) |
| top6_fwd_toi_share | r = 0.248 | r = 0.402 | ⚠ does **not** show the pattern — noisier YoY, flagged |

`zone_start_polarization` behaves exactly as a real coaching signal should — the same axis that
won the Phase 2 discontinuity test most decisively (ratio 1.92). `top6_fwd_toi_share` (the
weaker Phase 2 axis, ratio 1.27) does **not** persist within regimes better than across changes;
it is flagged as the less stable of the two system axes.

### (b) Interaction-term stability across eras (2010-17 vs 2017-26)

| interactions | cross-era corr | verdict |
|---|---:|---|
| Design B type×deployment (12) | **+0.563** | moderately stable (some sign flips; carried) |
| Opponent style-matchup (12) | **−0.045** | **does not replicate — flagged UNSTABLE** |

The opponent **strength** terms are rock-stable across eras (own off 0.0227→0.0213, own def
0.0248→0.0226, etc.). It is only the **style-matchup interactions** that fail to replicate —
consistent with their ~0 R² gain in §4. The internal type×deployment interactions replicate at
r=0.56.

---

## 6. Assumptions in the spec vs. reality

- ⚠ **Age band (3.2)** — no age/birthdate in any frozen Atlas asset; served by an **experience
  proxy** (seasons since first roster appearance). Only spec covariate not honored exactly.
- ℹ **Pooling count** — silhouette alone favors 5 types (F=3,D=2); constrained to the spec's
  [6,10] band → 6. Defense genuinely wants only k=2 by silhouette; noted.
- ℹ **Player names** for the schedule-bias exhibit came from a **season-independent global**
  `stg_rosters` map (read-only), deliberately keyed by `player_id` not `season` to sidestep the
  UL-1 season mislabel; team abbreviations are canonical NHL API constants (reference, not
  derived). No new upstream defect found in Phase 3; `upstream-ledger.md` unchanged (UL-1..3).

---

## 7. For review — the Phase 3 gate decision

The spec puts the fork here: *both tracks proceed to validation, or one dies early on stability
grounds.* The evidence draws that line cleanly:

1. **INTERNAL / deployment track — ALIVE.** Deployment is a real, **persistent** system signal:
   OZ-start share moves at coach changes (Design A DiD t=−2.43); `zone_start_polarization`
   persists within regimes (YoY r=0.70) and moves at changes (0.31); Design B recovers a modest
   but genuinely out-of-fold system signal (CV R²=0.073) with strong identifiability (58.5%
   movers). **Recommend: proceed to Phase 4/5 validation.** Caveat forward: the *result* effect
   is small and only ~4% mediated by measured deployment — the validation targets must be sized
   to that thin headroom (as the preamble already warns).

2. **OPPONENT style-matchup track — KILL CANDIDATE.** Style-matchup interactions add 0.00014 R²,
   are ~60× smaller than strength, and **fail cross-era replication (r=−0.045)**. They should
   **not** proceed. **But** the track's *strength-based* machinery is sound and stable (strength
   R²=0.11, era-stable coefs), and its **schedule-bias normalization** is a face-valid,
   novel-vs-production deliverable. **Recommend: kill the style-interaction claim; keep the
   opponent-strength schedule normalization** as the surviving opponent-track product, to be
   validated on its own terms.

3. **`top6_fwd_toi_share`** is the weaker of the two deployment axes at every test (Phase 2
   ratio 1.27; no YoY persistence pattern). Recommend anchoring portability primarily on
   `zone_start_polarization` and carrying top-6 concentration with a stability caveat.

Nothing here is promoted to production (Phase 7 only). **Stopping for review.**

---

### Artifacts
`data/parquet/pctx|onice|depfull/*` (16 seasons each) · `player_types.parquet` (10,961) ·
`team_season_fp.parquet` (494) · `reports/phase3_analysis.json` (combined) +
`phase3_{designA,designB,opponent,stability}.json` · `data/cache/warehouse/player_names.csv`
(read-only, global) · tests `tests/test_phase3.py` (4 pass; 8 total).
Repro: `make primitives && make phase3`.
