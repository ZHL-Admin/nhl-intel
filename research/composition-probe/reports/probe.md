# Composition probe — the last pre-registered swing at fit

**Project:** composition-probe (`NIR/research/composition-probe/`)
**Date:** 2026-07-13 · **Seed:** 20260713d · own `.venv` · polars 1.42 · scikit-learn
**The gate:** does *recipe* beat recipe — finer style composition / complementarity — holding
talent+style fixed, and repeat across an era split? Reuses the Chemistry trio corpus, the role-fit
two-way role axes, and the additive-plus-curvature null. Thresholds fixed before results. STOP at the
gate.

**Scope + one forced deviation.** The validated two-way style axes exist only for the primary window
**2015-16→2025-26** (role-fit `is_primary_scope`; pre-2015 axes are not validated — role-fit UL-P2).
So the analysis is scoped there and the spec's **2010-2017 vs 2018-2025** era split is adapted to
**2015-2019 vs 2020-2025**. The temporal-replication intent is preserved; the alternative (building
unvalidated pre-2015 style axes) would violate the "validated axes only" rule. Flagged, not worked
around.

---

## Step 1 — a fine STYLE vocabulary (16 archetypes)

Per forward-season (200+ 5v5 min), a style fingerprint from the validated role-fit two-way axes across
six functional families — **location/danger** (mean_dist, slot_share, xg_per_shot), **volume** (cf60,
xg60), **physicality** (hit60, hittaken60), **possession** (tk60, gv60), **discipline** (pentake60,
pendrawn60), **finish/play** (goals60, assists60) — plus handedness. K-means, **K=16** (finer than the
6–10 role types used before), on 4,944 forward-seasons; nothing invented. Interpretable archetypes,
e.g. A2 (high-volume/high-danger driver), A4 (slot shooter), A13 (volume finisher), A14
(playmaker/possession), A8 (net-front physical), A3/A10/A12 (perimeter/point).

**Stability.** The underlying axes are strongly stable (role-fit: retained ~0.79 across team changes).
The discrete *assignment* is stabler than chance but soft: **split-half 0.34, YoY 0.37 (both ≈ 5×
the 0.069 chance rate)** — boundary players flip archetype because style is continuous. The gate
therefore leans on the **continuous** complementarity/redundancy scores (built from the stable axes),
not the discrete label, for the causal test.

## Step 2 — recipes, and they recur

A **recipe** = the sorted multiset of the trio's three archetypes + two continuous descriptors from
the fine axes: **complementarity** (mean dispersion of the three members across the six functional
families — do they cover different jobs) and a **redundancy** score = volume+location dispersion
(low = two shooters stacked on the same ice). On 2,262 forward trios (100+ shared min): **560 distinct
recipes, median 3 trios each, 53% recurring ≥3 times** (top recipes appear 19–28 times). So recipes
**do recur across many different player sets** — unlike specific trios, exactly as the premise
requires. There is real recipe-level sample to test.

## Step 3 — the talent-and-style-matched contrast (the causal core)

Trio residual = observed 5v5 xG share − the additive-plus-curvature null (members' rapm_variant Σoff/
Σdef + curvature + OZ/score/opponent context + season). Two tests:

**(a) Regression — incremental CV R² of composition beyond controls:**

| model | CV R² (weighted, LOSO) |
|---|---:|
| talent + curvature + deployment + opponent controls | −0.008 |
| controls + **complementarity + redundancy** | −0.007 |
| **incremental composition R²** | **+0.0004 (0.04%)** |

The finer ingredients add **0.04%** — *below* Link 2's ~1.1% reference and far below the 3% ship bar.
Finer style buckets did **not** move it; they lowered it.

**(b) Matched balanced-vs-redundant contrast.** Within (talent tercile × season), the
top-complementarity third (753 "balanced" trios) minus the bottom third (767 "redundant") residual:
**+0.0002 xG-share points, 95% CI [−0.0037, +0.0042] — includes zero.** Holding talent and style
buckets fixed and varying only the arrangement, balanced recipes do **not** out-reside redundant ones.

## Step 4 — the repeat test (the gate that killed prior attempts)

- **Era split.** Complementarity coefficient fit on 2015-2019 = **−0.0009**, on 2020-2025 = **−0.0033**
  — "sign-consistent" only in the trivial sense that both are ≈ 0 and *negative*. There is no positive
  complementarity effect to replicate.
- **Within-season split-half** of the trio residual = **−0.148** (the same-season-anchor straddling
  artifact seen in Chemistry/Link 2) — a recipe's over-performance does not even repeat across halves
  of one season.

## VERDICT (pre-stated) → **HARD NULL**

Pre-stated: PASS needs ≥3% incremental R² AND era replication AND the matched CI excluding zero; HARD
NULL is "**~0 or negative** beyond controls — composition is talent-and-style in disguise." Realized:
incremental composition R² = **0.04% (≈0)**, the complementarity coefficient is **negative** in both
eras, and the matched balanced-minus-redundant contrast is **indistinguishable from zero**. This is the
**HARD NULL**. (It clears neither the 3% PASS bar nor sits in the 1–3% WEAK band; it is ~0.)

**Composition is talent-and-style in disguise.** Once the three members' individual quality and style
are fixed, *how they are arranged* — complementarity, redundancy, the specific recipe — adds nothing
to how the trio performs. **Fit is CLOSED as a predictable quantity.** The composition descriptors
survive only as **descriptive lineup-brainstorming context** (co-occurrence, not causation) — and
even that honestly: the recipe descriptors are stable enough to *describe* a line, but carry no
demonstrated causal lift.

### The whole fit line, closed
Fit has now been tested five ways, each a pre-registered swing, each clearing no usability bar:
**F17** pair residual (not persistent), **F18** unit over-performance (weak, sub-bar), **F19**
behavioral dependence (real pairwise, not a stable trait), **role-fit** roles (real & shippable
*descriptively*), and **now composition/recipe** (talent-and-style in disguise, hard null). The
durable product across the program is **descriptive**: stable two-way player role profiles and style
archetypes. **Predictive fit-beyond-parts does not exist at a buildable scale in public event data.**

**Recommendation.** Accept the hard null; do not open a composition-fit project. Ship the style
vocabulary + role profiles as descriptive lineup context only, labeled as co-occurrence not causation.
Any future fit work needs fundamentally richer inputs (tracking data for off-puck/passing — the Tier
-iii ceiling), not another arrangement of public-event features.

### Decisions & artifacts
- Era split adapted to 2015-2019 / 2020-2025 (validated style axes only 2015+; flagged above). Style
  vocabulary K=16 (target 12-20); complementarity/redundancy from the stable continuous axes, not the
  soft discrete labels. Denominators/magnitudes reported; matched contrast bootstrap 2,000×.
- `src/comppro/{config,styles,gate}.py`; `reports/{styles,gate}_analysis.json`;
  `data/parquet/archetypes.parquet` (gitignored). Reproduce: `make probe`. Reuses Chemistry trios +
  role-fit axes/units + the additive-plus-curvature null; frozen inputs untouched.

**STOP — owner review.** This was the last pre-registered swing at fit; the hard-null verdict is
accepted as written.
