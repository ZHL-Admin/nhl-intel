# Phase 1 — The scheme-norm, with goals-only bias mitigation

**Defensive Scheme & Role** (`NIR/research/def-scheme/`). Read-only; `make phase1` reproduces. Seed 20260714c. Universe: 5v5 (n_def=5), real NHL team-seasons (≥20 GA; exhibition rosters excluded).

> **LAW 1 · GOALS-ONLY. The tracking corpus contains only goal buildups; there is no tracked non-goal. This project INFERS team scheme and player role from goal geometry and measures deviation from the team's own norm. It never claims 'this positioning caused the goal' nor compares against non-goal plays it does not have. The scheme-norm is a norm ON GOALS.**

> **LAW 2 · NO FAULT LANGUAGE. 'out of position', 'blame', 'fault', 'mistake', 'responsible' never appear. The only permitted claim is DEVIATION FROM THE TEAM'S OWN STRUCTURAL NORM — a descriptive geometric fact, never a verdict of error. Scheme vs individual error cannot be separated per-goal; only aggregate deviation tendency is claimed.**


## 1.1 Coverage-signature representation

For each team-season, the typical **five-defender shape as a function of the PUCK situation**, as **distributions** (mean + spread), not single points — spread is itself part of the signature (tight = disciplined, wide = variable). Six interpretable geometry features per situation:

| feature | meaning |
|---|---|
| `depth` | mean distance of the 5 defenders to the defended net (deep vs stepped-up) |
| `spread` | mean distance to the defenders' centroid (compactness; low = tight box) |
| `netfront` | count of defenders within 15 ft of the net (collapse / net-front load) |
| `marking` | mean distance to the nearest attacker (low = tight man, high = zone/sag) |
| `highest` | distance to net of the highest defender (how far the top of the structure steps up) |
| `strong_frac` | fraction of defenders on the puck's strong side (puck-side loading) |

**Situation grid (the PUCK's location):** coarse = ['dzone_high', 'dzone_low', 'neutral', 'ozone']; fine = ['dzone_high_mid', 'dzone_high_wide', 'dzone_low_mid', 'dzone_low_wide', 'neutral', 'ozone']. 

*Design note (flagged for review):* a raw left/right "side" is symmetric and not a distinct scheme situation, so the spec's "strong/weak side" is operationalized as the puck's **lateral band** (mid/slot vs wide/boards) after folding out left-right symmetry. The coarse grid drops it; the fine grid adds it in the defensive zone.

**League-baseline shape by situation** (the norm ON GOALS every team is read against):

| situation | depth | spread | netfront | marking | highest | strong_frac |
|---|---|---|---|---|---|---|
| dzone_high | 47.7 | 20.3 | 0.56 | 13.6 | 71.6 | 0.66 |
| dzone_low | 27.6 | 18.2 | 1.54 | 14.0 | 48.3 | 0.59 |
| neutral | 92.9 | 24.6 | 0.09 | 15.7 | 121.1 | 0.63 |
| ozone | 133.7 | 27.3 | 0.01 | 16.2 | 162.6 | 0.66 |

## 1.2 Goals-only bias mitigation (Law 1)

The norm learned from a team's OWN goals-against is biased toward broken coverage. Two mitigations:

- **(a) League baseline → deviation.** Each situation's shape is pooled across the whole league's goals-against; every team-season is then read as a **deviation from league structure** (`dev_*` / z-scored `z_*` in the signature), not an absolute. The broken-coverage bias common to all teams cancels in the deviation.
- **(b) Independent-view agreement + offensive-goals cross-view.** The same frames are, from the scoring team's side, their OFFENSIVE goals; pooling every team's offensive goals reproduces the identical league defensive baseline (consistency by construction). The genuinely independent check of a team's *own* signature is a split-half of its goals-against, reported below.

**Residual bias that cannot be removed (stated honestly):** every view here is still drawn from GOALS ONLY. There is no tracked non-goal, so the *absolute* coverage shape is a shape-on-goals, and the selection toward sequences that ended in goals is shared by team, league, and offensive-goals views alike. Only **relative** (deviation-from-league) claims are made; no view recovers the team's coverage on non-scoring possessions, which this data does not contain.

**Signal check (feeds the keystone).** The *absolute* geometry is highly reproducible across independent goal-halves — it is driven by the situation, common to all teams:

| feature | absolute split-half r |
|---|---|
| depth | 1.00 |
| spread | 0.96 |
| netfront | 0.99 |
| marking | 0.83 |
| highest | 0.99 |
| strong_frac | 0.59 |

But the **team-specific deviation** — the part that would distinguish one team's scheme from another — reproduces only weakly at single-team-season granularity: **standardized split-half median r = 0.13**. The gross shape is stable; the team fingerprint on top of it is faint per season.

## 1.3 Per-situation sample counts & resolvable granularity

**How many goals-against populate each situation bucket, per team-season** (a goal populates a bucket with ≥5 frames there; min-sample gate = 15 GA to characterize a cell — a thin cell gets **no norm, not a guess**):

| grid | situation | min GA | median GA | team-seasons below gate |
|---|---|---|---|---|
| coarse | dzone_high | 116 | 161 | 0 |
| coarse | dzone_low | 148 | 180 | 0 |
| coarse | neutral | 76 | 101 | 0 |
| coarse | ozone | 50 | 71 | 0 |
| fine | dzone_high_mid | 59 | 73 | 0 |
| fine | dzone_high_wide | 114 | 156 | 0 |
| fine | dzone_low_mid | 146 | 178 | 0 |
| fine | dzone_low_wide | 129 | 167 | 0 |
| fine | neutral | 76 | 101 | 0 |
| fine | ozone | 50 | 71 | 0 |

- **coarse grid** (4 situations): **95/95 team-seasons** populate ALL cells above the 15-GA gate (median 4 cells covered).

- **fine grid** (6 situations): **95/95 team-seasons** populate ALL cells above the 15-GA gate (median 6 cells covered).

### Resolvable granularity — the honest bound for the keystone

**Sample size is NOT the binding constraint at this granularity.** Every team-season fully populates both the 4-cell coarse and the 6-cell fine puck-situation grids (min 50 GA/cell). A team defensive norm is therefore *resolvable at the situation level the fine grid describes.*

**The binding constraint is signal, not sample.** Even with ample counts, the team-specific deviation reproduces at only ~0.13 within a single season. So the keystone (Phase 2) should be judged **at the granularity the data supports — the 6-cell puck-situation grid — and with within-COACH pooling** (multiple seasons of one bench) to lift the team signal, rather than expecting a sharp per-single-season fingerprint. Going finer than 6 cells is unnecessary for samples but would not help the signal; going to per-single-season sharp schemes is where the data is thin — not in counts, but in reproducible team deviation.

## STOP — Phase 1 for owner review (before the Phase 2 keystone)

Coverage signatures built (deviation-from-league, standardized); samples ample to the 6-cell grid; the team-deviation signal is faint per season and is the keystone's real test. No scheme is named or claimed in Phase 1.