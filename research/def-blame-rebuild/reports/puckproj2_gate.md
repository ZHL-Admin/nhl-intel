# Puck-Path Projector RE-POSE — DESTINATION (shot-origin) sharpness gate

Target = where the play RESOLVES = shot-origin region (goals-only → the scoring shot; §6 limit: 'reset/cleared' plays aren't in the corpus). Knobs TUNED by held-out DESTINATION skill (leave-one-goal-out): window **0.3s**, radius **8ft**, heading **±30°**, time-to-shot cap **H=2s** (best mean log-lik -1.532).

**PRE-REGISTERED BAR (locked): top-2 destinations ≥60% AND conditioned entropy ≤0.7× same-zone-marginal destination entropy AND held-out destination-skill beats BOTH nulls. Funnel: near_net excluded.**

## Global shot-origin marginal (all goals): NET-FRONT 50% · SLOT-high 14% · BEHIND-net 10% · HIGH/point 9% · OUT/back 5% · L-wall 4% · R-wall 4%

## blue_line_entry

**Resolves to (share of matched distinct goals):** SLOT-high **35%** · NET-FRONT **21%** · HIGH/point **21%** · R-wall **8%** · L-wall **7%** · OUT/back **6%**
- top-2 destinations = **56%** (bar ≥60%) · matched goals 543
- entropy: conditioned **1.68** vs same-zone-marginal 1.68 → ratio **1.0** (bar ≤0.70) · zone-marginal top destination: NET-FRONT 39%
- held-out destination-skill: conditioned **-1.66** vs position-only -1.73 vs zone-marginal -1.75 → beats both: **True**
- **CLEARS PRE-REGISTERED BAR: no**

## right_point

**Resolves to (share of matched distinct goals):** NET-FRONT **42%** · SLOT-high **23%** · HIGH/point **16%** · R-wall **9%** · OUT/back **2%** · BEHIND-net **2%**
- top-2 destinations = **65%** (bar ≥60%) · matched goals 1,334
- entropy: conditioned **1.61** vs same-zone-marginal 1.63 → ratio **0.99** (bar ≤0.70) · zone-marginal top destination: NET-FRONT 46%
- held-out destination-skill: conditioned **-1.52** vs position-only -1.65 vs zone-marginal -1.66 → beats both: **True**
- **CLEARS PRE-REGISTERED BAR: no**

## half_wall_to_net

**Resolves to (share of matched distinct goals):** NET-FRONT **51%** · R-wall **16%** · SLOT-high **14%** · HIGH/point **8%** · BEHIND-net **5%** · L-corner **2%**
- top-2 destinations = **67%** (bar ≥60%) · matched goals 2,724
- entropy: conditioned **1.5** vs same-zone-marginal 1.58 → ratio **0.95** (bar ≤0.70) · zone-marginal top destination: NET-FRONT 50%
- held-out destination-skill: conditioned **-1.67** vs position-only -1.73 vs zone-marginal -1.74 → beats both: **True**
- **CLEARS PRE-REGISTERED BAR: no**

## below_goal_line

**Resolves to (share of matched distinct goals):** NET-FRONT **52%** · BEHIND-net **46%**
- top-2 destinations = **98%** (bar ≥60%) · matched goals 2,521
- entropy: conditioned **0.81** vs same-zone-marginal 1.07 → ratio **0.75** (bar ≤0.70) · zone-marginal top destination: NET-FRONT 47%
- held-out destination-skill: conditioned **-1.3** vs position-only -1.36 vs zone-marginal -1.39 → beats both: **True**
- **CLEARS PRE-REGISTERED BAR: no**

## near_net_slot  [FUNNEL — excluded]

**Resolves to (share of matched distinct goals):** NET-FRONT **79%** · BEHIND-net **17%** · SLOT-high **3%**
- top-2 destinations = **96%** (bar ≥60%) · matched goals 7,637
- entropy: conditioned **0.67** vs same-zone-marginal 0.88 → ratio **0.77** (bar ≤0.70) · zone-marginal top destination: NET-FRONT 75%
- held-out destination-skill: conditioned **-0.72** vs position-only -0.78 vs zone-marginal -0.83 → beats both: **True**
- **CLEARS PRE-REGISTERED BAR: no**

## Verdict (funnel-guarded)

- Non-funnel decision states clearing the bar: **NONE** of ['blue_line_entry', 'right_point', 'half_wall_to_net', 'below_goal_line'].
- Zone-marginal lopsidedness (is the destination zone-DETERMINED?): blue_line_entry → NET-FRONT 39% · right_point → NET-FRONT 46% · half_wall_to_net → NET-FRONT 50% · below_goal_line → NET-FRONT 47%

## STOP — destination sharpness gate for owner review. No defense-read, no grading.
