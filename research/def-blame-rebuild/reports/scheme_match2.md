# Assignment-Free Scheme Matcher (v2) — Hungarian shape-match, no roster roles (§7: DESCRIPTIVE only)

5v5 22,773 → D-zone-entire-buildup 11,224 → SETTLED 8,047 → matched **5,528**. Match = optimal 5→5 assignment (defenders↔predicted zones), NO roster roles. Absolute NO-FIT floor = **14 ft/defender** (re-grounded on the assignment-free scale; NOT a percentile).

**Permutation-invariance CODE check (§6): max mismatch change when defenders are relabeled (over 30 goals) = 5.68e-14 ft** → assignment-free confirmed (0 by Hungarian construction; this proves the implementation carries no hidden order).

**GUARDRAIL: descriptive, confidence-flagged, human-checkable. NEVER an automated blame input.**

## Confidence breakdown (THE key result)

- **CONFIDENT: 1,078** (20%)
- **AMBIGUOUS: 1,464** (26%)
- **NO-FIT: 2,986** (54%)

- per-defender fit distribution (ft): p10 11.3 · median **14.3** · p90 20.9 (floor 14)
- median discriminating-frame fraction: 50%

## HEAD-TO-HEAD vs F37 (the decisive comparison)

- F37 (role-fixed): CONFIDENT **0.3%**, role-flip 64% (the wall was role assignment).
- v2 (assignment-free): CONFIDENT **20%**, role-flip N/A (no roles).
- → confident rate ROSE materially → the F37 wall WAS the role-assignment artifact; assignment-free formation-matching recovers scheme signal. Coaches' shape-first view is right.

## Best-fit scheme among CONFIDENT goals (context; tape-check needed)

- fiveTight: 547
- swarm: 396
- zone: 80
- box1: 43
- man: 12

## Example goals (6–8) for owner TAPE review

- 2025020699-348 — **CONFIDENT** · best-fit **swarm** · fit 9.0 ft/def · margin 0.94 (null-p90 0.88) · disc 87% · 100fr
- 2025020986-251 — **CONFIDENT** · best-fit **swarm** · fit 9.0 ft/def · margin 0.79 (null-p90 0.31) · disc 75% · 101fr
- 2025020032-207 — **CONFIDENT** · best-fit **swarm** · fit 7.9 ft/def · margin 0.72 (null-p90 0.50) · disc 6% · 90fr
- 2025020654-1204 — **CONFIDENT** · best-fit **swarm** · fit 9.6 ft/def · margin 0.70 (null-p90 0.36) · disc 84% · 94fr
- 2025020705-154 — **AMBIGUOUS** · best-fit **swarm** · fit 13.1 ft/def · margin 0.00 (null-p90 0.17) · disc 24% · 89fr
- 2025020879-247 — **AMBIGUOUS** · best-fit **fiveTight** · fit 12.2 ft/def · margin 0.00 (null-p90 0.20) · disc 28% · 95fr
- 2023020470-668 — **NO-FIT** · best-fit **man** · fit 82.9 ft/def · margin 0.07 (null-p90 0.08) · disc 36% · 81fr
- 2023021139-1060 — **NO-FIT** · best-fit **man** · fit 71.8 ft/def · margin 0.05 (null-p90 0.04) · disc 9% · 82fr

## STOP — assignment-free scheme read for owner review. No aggregation, no grade, no blame.
