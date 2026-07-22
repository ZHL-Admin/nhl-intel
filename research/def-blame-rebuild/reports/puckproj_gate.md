# Puck-Path Projector — §5 SHARPNESS GATE (mode-based, held-out-tuned, controlled nulls)

Library 22,773 5v5 goals. Knobs TUNED by held-out predictive skill (leave-one-goal-out): motion-window **0.2s**, radius **8 ft**, heading-tol **±30°**, look-ahead **0.5s** (best mean log-lik -0.862). Distinct-goal collapse + mode/entropy per §0e.

**LOCKED BAR (per decision-state): top-2 modes ≥60% AND conditioned entropy ≤0.7× same-zone-marginal AND held-out skill beats BOTH nulls. Funnel guard: near_net EXCLUDED from any 'works' claim.**

## blue_line_entry

**Dominant continuations (share of matched distinct goals):** OUT/back **76%** · HIGH/point **19%** · SLOT-high **2%**
- top-2 modes = **95%** (bar ≥60%) · matched goals 1,532
- entropy: conditioned **0.73** vs same-zone-marginal 0.47 → ratio **1.55** (bar ≤0.70)
- held-out skill (log-lik of the TRUE continuation): conditioned **-0.53** vs position-only -0.55 vs zone-marginal -0.62 → beats both: **True**
- **CLEARS LOCKED BAR: no**

## right_point

**Dominant continuations (share of matched distinct goals):** HIGH/point **58%** · OUT/back **23%** · NET-FRONT **9%** · SLOT-high **6%** · R-wall **2%**
- top-2 modes = **81%** (bar ≥60%) · matched goals 2,658
- entropy: conditioned **1.2** vs same-zone-marginal 0.94 → ratio **1.28** (bar ≤0.70)
- held-out skill (log-lik of the TRUE continuation): conditioned **-0.76** vs position-only -0.94 vs zone-marginal -1.05 → beats both: **True**
- **CLEARS LOCKED BAR: no**

## half_wall_to_net

**Dominant continuations (share of matched distinct goals):** R-wall **37%** · HIGH/point **18%** · NET-FRONT **14%** · OUT/back **14%** · SLOT-high **8%**
- top-2 modes = **55%** (bar ≥60%) · matched goals 4,324
- entropy: conditioned **1.72** vs same-zone-marginal 1.46 → ratio **1.18** (bar ≤0.70)
- held-out skill (log-lik of the TRUE continuation): conditioned **-1.24** vs position-only -1.48 vs zone-marginal -1.53 → beats both: **True**
- **CLEARS LOCKED BAR: no**

## below_goal_line

**Dominant continuations (share of matched distinct goals):** OUT/back **63%** · BEHIND-net **29%** · NET-FRONT **6%**
- top-2 modes = **92%** (bar ≥60%) · matched goals 3,251
- entropy: conditioned **0.92** vs same-zone-marginal 0.94 → ratio **0.98** (bar ≤0.70)
- held-out skill (log-lik of the TRUE continuation): conditioned **-0.86** vs position-only -0.99 vs zone-marginal -1.17 → beats both: **True**
- **CLEARS LOCKED BAR: no**

## near_net_slot  [FUNNEL — excluded from the claim]

**Dominant continuations (share of matched distinct goals):** OUT/back **65%** · NET-FRONT **24%** · BEHIND-net **8%**
- top-2 modes = **89%** (bar ≥60%) · matched goals 8,931
- entropy: conditioned **0.97** vs same-zone-marginal 1.4 → ratio **0.69** (bar ≤0.70)
- held-out skill (log-lik of the TRUE continuation): conditioned **-1.2** vs position-only -1.36 vs zone-marginal -1.45 → beats both: **True**
- **CLEARS LOCKED BAR: YES**

## Verdict (funnel-guarded — the 4 non-funnel decision states must pass on their own)

- Non-funnel decision states clearing the locked bar: **NONE** of ['blue_line_entry', 'right_point', 'half_wall_to_net', 'below_goal_line'].
- near_net (funnel, excluded): CLEARS=True — expected/boring, not counted.
- → at the interesting non-funnel decision states the projection is MUSH by the locked bar; the likely path is NOT well-posed there and the defensive read rests on sand. Honest negative.

## STOP — sharpness gate for owner review. No defense-read, no grading.
