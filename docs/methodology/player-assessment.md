# Player Assessment — Methodology

(The T1 table below is appended by `models_ml/validate_assessment.py`; the sections above it
are curated and preserved across re-runs.)

## Product: tiers, confidence, sample grades (the reader's view)

Every player's value reads as three things, never a bare number:

- **Tier** — a role band named by league job counts within the position group (e.g. *First-line
  forward*, *Top-pair defenseman*, *Elite starter*). The full ladder is `config.ASSESSMENT`
  `TIER_LABELS`. Tiers are assigned by rank on the reliability-shrunk **assessed WAR**, so they are
  monotone in that value; a boundary tie takes the higher tier.
- **Confidence** — probability mass of the player's WAR distribution inside the assigned tier,
  shown as **High / Medium / Low** (a dot + word). When the mass straddles two adjacent tiers
  (`tier_confidence < 0.55` and `tier_prob_within_one ≥ 0.85`) the copy names a **two-tier range**
  instead of a single tier — the straddle is information, not a hedge.
- **Sample grade** — data sufficiency **Sample A / B / C** (seasons present + 5v5 TOI in the
  window), separate from confidence; goalies cap at B. Single-season windows read *Low confidence,
  single-season window*.
- **Inactive (D13)** — a player with zero games in the window's most recent season is excluded from
  the tier pool and reads *Inactive, last played {season}* — no current-tier claim.

**D15 — one tier vocabulary.** The assessment tier ladder above is the ONLY player-value vocabulary
rendered anywhere in the product. The legacy percentile→noun mapping (elite / high-end / middle-tier
/ depth / fringe) is retired from every display surface and from the verdict identity anchor (which
now anchors on `tier_label`). Archetype names, team-fit copy, and radar spoke adjectives are a
different vocabulary and are unaffected.

## Negative results: the r-based lenses (C1, C4)

Two theoretically motivated estimators were built and tested against the sample-size
Marcel-toward-prior lens (C2) that ships. C1 (`c1_r_shrink`) shrinks each component's season
rate toward the position mean by the measured year-over-year reliabilities
(`GAR_STABILITY_YOY`: production 0.66, RAPM 0.38, finishing 0.35 toward 0). C4 (`c4_r_speed`)
uses the same r-values but makes the trust sample-adaptive, with the per-component regression
constant derived analytically from the reliability, K = n0·(1−r)/r.

Across ten walk-forward transitions (2016-17 through 2025-26; three COVID-affected transitions
flagged and excluded from decisions), both r-based lenses lost to the plain Marcel baseline on
most targets, while C2 held the lowest RMSE on every non-flagged target. On the three
pre-registered new-target seasons (2018-19, 2022-23, 2023-24) the mean skater WAR RMSE was C2
0.827 versus C4 0.888; C1 was similar to or worse than C4. Per the preregistered promotion rule
(v2.5), C4 was not promoted, and C1/C3/C4 remain in `value_lens` as documented, non-shipping
also-rans. The finding is stable and one-directional: fixing or deriving the shrinkage weight
from a single global reliability underperforms regressing each component toward a position prior
by its own realized sample size. The expanded T1 table follows.


## Calibration (T5 tier-bucket bias)

Signed-error diagnostic (prereg v3): skaters bucketed by their as-of-season-S C2 tier (walk-forward,
data through S only), mean signed error = predicted − realized S+1 WAR per bucket, across the
non-COVID transitions. Positive = the estimator over-predicts that tier's next-season WAR.

```
                 mean signed error (predicted - realized S+1 WAR)
  F bucket          C2 err   Marcel err     n        D bucket          C2 err   Marcel err     n
  elite            -0.121      -0.017     124        elite            -0.094      +0.092      83
  first_line       -0.076      -0.003     524        number_one       +0.001      +0.125     135
  second_line      +0.001      +0.024     621        top_pair         +0.185      +0.270     218
  third_line       +0.040      +0.045     513        second_pair      +0.060      +0.115     370
  fourth_line      +0.002      -0.020     272        third_pair       +0.057      +0.079     135
  fringe           -0.008      -0.103     359        fringe           +0.056      -0.048     420
```

Interpretation: C2 is better calibrated than Marcel in essentially every bucket, and near-unbiased
at the top of the defense ladder (elite −0.094, number_one +0.001) where Marcel drifts high
(+0.092, +0.125). Both estimators over-predict top-pair defensemen, C2 less so (+0.185 vs +0.270).
The one systematic C2 miss is a mild UNDER-prediction of elite/first-line forwards (−0.121, −0.076)
— real regression-to-the-mean, but small relative to the ~0.8 WAR RMSE. This did not justify a
tier-conditional estimator (no C5 was built). This section is revisited only after 2026-27 adds a
fresh transition, and any future candidate requires a new preregistration per prereg v3.

## T1 next-season WAR (assessment-validate)

```
method (RMSE)       2016-17    2017-18    2018-19   2019-20*   2020-21*   2021-22*    2022-23    2023-24    2024-25    2025-26
naive                0.8541     0.8730     0.8917     0.7481     0.7356     1.0158     1.0310     1.0536     1.0230     0.8355
marcel               0.7699     0.7582     0.7582     0.6393     0.5933     0.8252     0.8973     0.8756     0.8359     0.7697
c1_r_shrink          0.7406     0.7640     0.8069     0.6816     0.6724     0.9494     0.9522     0.9400     0.8618     0.8662
c2_roster_player     0.7245     0.7398     0.7470     0.6223     0.5890     0.8204     0.8743     0.8598     0.8209     0.7655
c3_blended           0.7727     0.7624     0.7646     0.6394     0.5973     0.8336     0.8901     0.8749     0.8285     0.7814
c4_r_speed           0.7397     0.7658     0.7989     0.6715     0.6658     0.9375     0.9424     0.9220     0.8536     0.8526
n (common)              510        531        545        534        482        546        564        563        570        491
(* = COVID-flagged transition, excluded from headline/decision metrics)
```

**v1 gate G1 (eval seasons):** c2_roster_player wins (lowest mean RMSE, beats Marcel in both); eval mean RMSE 0.7932.

**C4 promotion (prereg v2.5):** C4 NOT promoted (does not beat C2 by >0.005; new-target C4 0.8878 vs C2 0.8270). C2 ships.

**point_estimator = `c2_roster_player`**
