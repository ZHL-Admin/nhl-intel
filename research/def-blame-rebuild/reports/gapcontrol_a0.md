# Gap Control · Phase A0 — derived data-internal knobs (distributions + cuts only; nothing built)

Each knob labeled by geometry INDEPENDENT of the quantity being cut, then the cut is placed where the labeled distributions separate (Youden). Verdict CLEAN = trust the knob; SMEARED/WEAK = the condition is weak and must be reconsidered, not forced. No coupling on the full set, no gap, no profile.

## Knobs 1-4 (coupling conditions) — labeled-mode distributions + derived cut

| knob | pos n | neg n | pos med[IQR] | neg med[IQR] | AUC | derived cut | verdict |
|---|---|---|---|---|---|---|---|
| backward-posture: defender depth-velocity (ft/s); defending should be LOW | 1016215 | 315948 | -12.1 [-17.5,-5.1] | 4.6 [-0.8,9.6] | **0.111** | **-3.18** | CLEAN |
| lateral min-motion floor: |attacker lateral velocity| (ft/s); cutting should be HIGH | 1554839 | 1229785 | 6.6 [2.6,12.0] | 5.3 [2.0,10.5] | **0.549** | **6.79** | SMEARED/WEAK |
| separation-rate bound: d(distance)/dt (ft/s); BEATEN should be HIGH (separating) | 1580 | 31791 | 4.0 [0.4,8.0] | -0.6 [-2.0,0.2] | **0.796** | **1.69** | CLEAN |
| |Δlateral-velocity| (ft/s); DIFFERENT-man should be HIGH, same-man LOW | 2542510 | 156364 | 6.1 [2.6,11.3] | 3.1 [1.1,6.2] | **0.662** | **5.75** | MODERATE |

(pos/neg = the two independent-label modes; the cut is the derived §4.2 threshold. AUC≈0.5 ⇒ smeared.)

## Knob 5 — near-center / ambiguous D-side band

- 244 D (≥100 tracked frames); left-cluster 128 (med -4.4 ft), right-cluster 116 (med 3.9 ft). **Ambiguous band = |mean-lat| in [-1.1, 1.1] ft** (fraction of D in the dip: 0.102). |mean_lat| inside [-1.1, 1.1] = ambiguous → defer to handedness

## Knob 6 — thin-sample cutoff for the tracking-derived side

- within-D lateral SD 17.0 ft; half-band 1.1 ft → **frame cutoff ≈ 230**. below ~230 tracked frames a D's mean-lat SE exceeds half the ambiguous band → treat as thin, defer to handedness

## STOP — owner review of the derived knobs before Phase A coupling on the full set. Nothing built.
