# RCET §5(a) REFINE v2 — BLUE-LINE-aligned + puck-route-bucketed gate (different-alignment hypothesis)

Genuinely different test: re-align on the PUCK CROSSING THE DEFENSIVE BLUE LINE (t=0 at entry, real seconds forward toward the net / backward into the NZ; 3s NZ approach captured), bucket by the puck's ROUTE, keep the clean-anchor filter. Same pre-registered bar; COHERENCE required (TIGHT at ≥2 checkpoints, not a single instant). **STOP at the gate — no deviation, no diagnosis.**

Checkpoints: NZ(-1.0s), blueline(0.0s), in+1.0s, in+2.0s (0 = blue line). Speed split up-rate median = 24.5 ft/s; east-west split lateral-range median = 14.0 ft. Cells tested only at N ≥ 200.

## Bucket Ns (clean-anchor)

- LANE=left: **645** goals
- LANE=middle: **475** goals
- LANE=right: **682** goals
- SPEED=fast: **900** goals
- SPEED=slow: **900** goals
- ROUTE=straight: **901** goals
- ROUTE=eastwest: **901** goals
- ALL(bl,clean): **1,802** goals

## Gate per bucket — placebo ratio (real/scrambled IQR) at each checkpoint; COHERENT = TIGHT at ≥2

| bucket | role | axis | ratio NZ-1.0 | ratio BL 0 | ratio +1.0 | ratio +2.0 | #TIGHT | COHERENT |
|---|---|---|---|---|---|---|---|---|
| LANE=left | strong | rel_lateral | 1.07 | 0.88 | 0.72 | 0.59 | 1 | no |
| LANE=left | strong | rel_depth | 0.89 | 0.56 | 0.44 | 0.58 | 3 | **YES** |
| LANE=left | strong | separation | 0.77 | 0.64 | 0.61 | 0.66 | 0 | no |
| LANE=left | weak | rel_lateral | 1.11 | 0.93 | 0.8 | 0.83 | 0 | no |
| LANE=left | weak | rel_depth | 1.06 | 0.82 | 0.73 | 0.77 | 2 | **YES** |
| LANE=left | weak | separation | 0.97 | 0.86 | 0.8 | 0.8 | 0 | no |
| LANE=middle | strong | rel_lateral | 1.07 | 0.97 | 0.73 | 0.55 | 0 | no |
| LANE=middle | strong | rel_depth | 0.75 | 0.49 | 0.37 | 0.44 | 3 | **YES** |
| LANE=middle | strong | separation | 0.66 | 0.47 | 0.42 | 0.61 | 2 | **YES** |
| LANE=middle | weak | rel_lateral | 1.14 | 0.78 | 0.73 | 0.77 | 0 | no |
| LANE=middle | weak | rel_depth | 0.93 | 0.68 | 0.62 | 0.58 | 2 | **YES** |
| LANE=middle | weak | separation | 0.76 | 0.61 | 0.75 | 0.96 | 0 | no |
| LANE=right | strong | rel_lateral | 1.07 | 0.88 | 0.64 | 0.72 | 1 | no |
| LANE=right | strong | rel_depth | 0.86 | 0.53 | 0.44 | 0.55 | 3 | **YES** |
| LANE=right | strong | separation | 0.73 | 0.72 | 0.66 | 0.63 | 0 | no |
| LANE=right | weak | rel_lateral | 1.06 | 0.86 | 0.79 | 0.78 | 0 | no |
| LANE=right | weak | rel_depth | 1.08 | 0.88 | 0.78 | 0.73 | 1 | no |
| LANE=right | weak | separation | 0.95 | 0.87 | 0.78 | 0.79 | 0 | no |
| SPEED=fast | strong | rel_lateral | 1.05 | 0.88 | 0.66 | 0.64 | 1 | no |
| SPEED=fast | strong | rel_depth | 0.9 | 0.53 | 0.39 | 0.55 | 3 | **YES** |
| SPEED=fast | strong | separation | 0.75 | 0.68 | 0.64 | 0.65 | 0 | no |
| SPEED=fast | weak | rel_lateral | 1.09 | 0.93 | 0.77 | 0.78 | 0 | no |
| SPEED=fast | weak | rel_depth | 1.1 | 0.88 | 0.74 | 0.75 | 2 | **YES** |
| SPEED=fast | weak | separation | 0.91 | 0.88 | 0.84 | 0.75 | 0 | no |
| SPEED=slow | strong | rel_lateral | 1.13 | 0.84 | 0.72 | 0.64 | 1 | no |
| SPEED=slow | strong | rel_depth | 0.79 | 0.5 | 0.38 | 0.52 | 3 | **YES** |
| SPEED=slow | strong | separation | 0.74 | 0.56 | 0.54 | 0.62 | 1 | no |
| SPEED=slow | weak | rel_lateral | 1.07 | 0.87 | 0.81 | 0.86 | 0 | no |
| SPEED=slow | weak | rel_depth | 1.01 | 0.81 | 0.77 | 0.73 | 1 | no |
| SPEED=slow | weak | separation | 0.9 | 0.86 | 0.82 | 0.86 | 0 | no |
| ROUTE=straight | strong | rel_lateral | 1.14 | 0.89 | 0.6 | 0.56 | 0 | no |
| ROUTE=straight | strong | rel_depth | 0.92 | 0.6 | 0.37 | 0.4 | 3 | **YES** |
| ROUTE=straight | strong | separation | 0.74 | 0.66 | 0.57 | 0.63 | 0 | no |
| ROUTE=straight | weak | rel_lateral | 1.1 | 0.92 | 0.76 | 0.58 | 0 | no |
| ROUTE=straight | weak | rel_depth | 1.05 | 0.85 | 0.7 | 0.61 | 2 | **YES** |
| ROUTE=straight | weak | separation | 0.91 | 0.89 | 0.87 | 0.71 | 1 | no |
| ROUTE=eastwest | strong | rel_lateral | 1.05 | 0.86 | 0.77 | 0.75 | 0 | no |
| ROUTE=eastwest | strong | rel_depth | 0.79 | 0.45 | 0.41 | 0.62 | 3 | **YES** |
| ROUTE=eastwest | strong | separation | 0.72 | 0.57 | 0.6 | 0.65 | 0 | no |
| ROUTE=eastwest | weak | rel_lateral | 1.06 | 0.89 | 0.83 | 0.82 | 0 | no |
| ROUTE=eastwest | weak | rel_depth | 1.04 | 0.77 | 0.73 | 0.86 | 1 | no |
| ROUTE=eastwest | weak | separation | 0.87 | 0.89 | 0.84 | 0.84 | 0 | no |
| ALL(bl,clean) | strong | rel_lateral | 1.07 | 0.87 | 0.68 | 0.64 | 2 | **YES** |
| ALL(bl,clean) | strong | rel_depth | 0.84 | 0.53 | 0.42 | 0.52 | 3 | **YES** |
| ALL(bl,clean) | strong | separation | 0.75 | 0.63 | 0.59 | 0.63 | 0 | no |
| ALL(bl,clean) | weak | rel_lateral | 1.05 | 0.89 | 0.8 | 0.8 | 0 | no |
| ALL(bl,clean) | weak | rel_depth | 1.06 | 0.82 | 0.73 | 0.73 | 2 | **YES** |
| ALL(bl,clean) | weak | separation | 0.91 | 0.9 | 0.86 | 0.81 | 0 | no |

Plot for LANE=left: `reports/rcet_bl_LANE_left.png`

Plot for LANE=middle: `reports/rcet_bl_LANE_middle.png`

Plot for LANE=right: `reports/rcet_bl_LANE_right.png`

Plot for SPEED=fast: `reports/rcet_bl_SPEED_fast.png`

Plot for SPEED=slow: `reports/rcet_bl_SPEED_slow.png`

Plot for ROUTE=straight: `reports/rcet_bl_ROUTE_straight.png`

Plot for ROUTE=eastwest: `reports/rcet_bl_ROUTE_eastwest.png`

Plot for ALL(bl,clean): `reports/rcet_bl_ALLbl_clean.png`

## Verdict

- **15 COHERENT cell(s)** clear the bar at ≥2 checkpoints: [('LANE=left', 'strong', 'rel_depth'), ('LANE=left', 'weak', 'rel_depth'), ('LANE=middle', 'strong', 'rel_depth'), ('LANE=middle', 'strong', 'separation'), ('LANE=middle', 'weak', 'rel_depth'), ('LANE=right', 'strong', 'rel_depth'), ('SPEED=fast', 'strong', 'rel_depth'), ('SPEED=fast', 'weak', 'rel_depth'), ('SPEED=slow', 'strong', 'rel_depth'), ('ROUTE=straight', 'strong', 'rel_depth'), ('ROUTE=straight', 'weak', 'rel_depth'), ('ROUTE=eastwest', 'strong', 'rel_depth'), ('ALL(bl,clean)', 'strong', 'rel_lateral'), ('ALL(bl,clean)', 'strong', 'rel_depth'), ('ALL(bl,clean)', 'weak', 'rel_depth')]. Blue-line alignment + route bucketing recovered a real within-route pattern — the prior smear was MISALIGNMENT. Report which route, proceed within it (still no deviation until owner approves).

## STOP — owner review of the blue-line-aligned refined gate. Nothing past it.
