# PROACTIVE defensive-action fingerprint probe (D-only; scope-then-gate; nothing promoted)

Tests CHOSEN defensive actions (proactive), unlike F32 (forced reactions, unstable). Goals-only (LAW 1). Bar: split-half ≥0.40 (F25 offensive ref 0.41-0.76). min 40 on-ice goals-against.

## Link 1 — SCOPE of the NEW detectors (rate + phantom; scoped before trusting)

Corpus 22678 goals.
- **SHOT-BLOCK**: ~0.185/goal (4192 events). Phantom: goal-side filter (pl_depth<p_depth) drops 41% of fast-puck touches (defender merely near a fast puck, not between it and the net)
- **BOARD-PIN**: ~0.035/goal (785 events). Phantom: requires slow (pspeed<5) near-boards (|lat|>35) coupling sustained >=5 frames — a pin, not a fly-by
- **LANE-DISRUPTION**: ~0.132/goal (2986 events). Phantom: mid-flight speed (12-40) + heading change (dir_cos<0.3) at the defender = a redirect, not a clean reception; but NOISY — overlaps deflections/bounces, needs pre-state pass check (deferred)
- SHOT-BLOCK scopes CLEAN (goal-side filter is a real phantom discriminator). BOARD-PIN scopes usable (slow near-boards sustained). LANE-DISRUPTION is NOISY (overlaps bounces/deflections; the pre-state pass check to separate disruption from bounce is DEFERRED — not built, per the scope-first discipline).

## Link 2/3 — action MIX stability (split-half odd/even games + YoY, vs placebo)

| proactive action | def | n | split-half r | placebo p | YoY r | STABLE (≥0.40) |
|---|---|---|---|---|---|---|
| puck_challenge — closest he chooses to attack the puck (aggression) | | 227 | **-0.024** | 0.6485 | 0.034 | no |
| stepup_depth — how high up-ice he engages | | 227 | **0.033** | 0.3115 | 0.132 | no |
| netfront_frac — net-front anchor (chosen position) | | 227 | **0.033** | 0.3095 | 0.259 | no |
| man_stability — man-marking (tracks a man) vs zone/roving | | 227 | **0.043** | 0.273 | 0.097 | no |
| takeaway — genuine puck-win/coupling (chosen puck-attack) | | 227 | **0.098** | 0.06 | 0.036 | no |
| shot_block — shot-block (goal-side fast-puck intercept) | | 227 | **0.005** | 0.474 | -0.085 | no |

**Stable proactive actions (split-half ≥0.40): NONE.**

## Link 4 — role/system control (for stable actions: does it survive WITHIN team?)

- (no stable action to role-control)

## Link 5 — verdict

- **No proactive defensive action is stable** even though chosen — a DEEPER finding than F32: defense is illegible even in its chosen actions on goals-only data. The reactive-vs-chosen distinction does NOT rescue defensive fingerprinting. Defensive individual signal stays out of reach.

## STOP — owner review after scoping + stability (before any predictive test). Nothing promoted.
