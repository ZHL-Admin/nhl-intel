# Behavioral Scheme Detection v3 — five detectors, per-detector nulls, phase-sequence switches (§7: DESCRIPTIVE only)

**SETTLED (tightened, owner-ruled 2026-07-18):** a play is settled only once ALL 10 skaters are inside the offensive blue line (depth≤66ft); the window STARTS when the last skater enters and holds to the goal (≤5-frame excursions tolerated), then puck dwell≥25 + cycle-back≥12ft are re-checked on that trimmed window. Entry/rush frames where players are still streaming in are dropped.

Segments scored: **7,143** over 3,628 settled plays. Firing is NULL-CALIBRATED against each detector's OWN pooled null (identity-shuffle for man/zone, puck/time-shuffle for the configurational three): the fire threshold is the p95 of the pooled null — DATA-DERIVED, not a hand-set score. A segment's behavior is the firing detector with the largest null-normalized excess; CONFIDENT = one clear winner, AMBIGUOUS = ≥2 comparable, NO-CLEAR = none beats its null. **GOALS-ONLY CAVEAT: behavior FREQUENCIES are failure-conditioned (e.g. swarm may over-appear); per-segment detection is descriptive.**

**GUARDRAIL: descriptive, confidence-flagged, human-checkable. NEVER an automated blame input.**

## Per-segment outcome distribution

- man: 10 (0%)
- zone: 114 (2%)
- five_tight: 229 (3%)
- swarm: 167 (2%)
- box1: 283 (4%)
- AMBIGUOUS: 10 (0%)
- NO-CLEAR: 6,330 (89%)

## Per-detector — real-vs-null margin (over enabling segments) and confident-fire rate

mean-real = mean detector score where enabling; null p50 / p95 = pooled-null median / fire threshold; fire = confident-fire count (this detector won the segment).

| detector | enabling segs | mean-real | null p50 | null p95 (thresh) | mean-real − thresh | confident-fire |
|---|---|---|---|---|---|---|
| man | 5,254 | 0.002 | 0.000 | 0.000 | +0.002 | 10 |
| zone | 5,254 | 0.019 | 0.000 | 0.250 | -0.231 | 114 |
| five_tight | 2,874 | 0.200 | 0.059 | 0.727 | -0.528 | 229 |
| swarm | 3,830 | 0.009 | 0.000 | 0.040 | -0.031 | 167 |
| box1 | 5,840 | 0.216 | 0.191 | 0.409 | -0.193 | 283 |

## SWITCH patterns — common HIGH→LOW behavior sequences (does 'man/box high → five-tight/swarm low' emerge?)

Plays with a confident HIGH behavior AND a confident LOW behavior: **49**.

- HIGH:box1 → LOW:box1 — 14
- HIGH:box1 → LOW:five_tight — 10
- HIGH:box1 → LOW:swarm — 7
- HIGH:box1 → LOW:zone — 7
- HIGH:zone → LOW:box1 — 4
- HIGH:zone → LOW:swarm — 4
- HIGH:zone → LOW:five_tight — 3

## Example plays (8–10) for owner TAPE review — phase sequence + per-detector excess-over-null (×null-spread)

- **2023020519-311**: LOW:swarm{swarm:2.88} → HIGH:box1{box1:0.13} → LOW:box1{box1:0.41}
- **2023020611-670**: LOW:zone{zone:1.0} → HIGH:box1{box1:0.17}
- **2023020644-345**: LOW:box1{box1:0.02} → HIGH:zone{zone:0.33}
- **2023020377-842**: LOW:five_tight{five_tight:0.21} → HIGH:box1{box1:0.02} → LOW:NO-CLEAR
- **2023021139-627**: LOW:swarm{swarm:6.89} → HIGH:NO-CLEAR → LOW:box1{box1:0.03}
- **2023021234-461**: LOW:five_tight{five_tight:0.08} → HIGH:NO-CLEAR
- **2023021180-972**: HIGH:NO-CLEAR → LOW:zone{zone:0.33,five_tight:0.05}
- **2023021201-968**: LOW:NO-CLEAR → HIGH:box1{box1:0.88}
- **2023021306-287**: LOW:NO-CLEAR → HIGH:NO-CLEAR → LOW:five_tight{five_tight:0.14} → HIGH:NO-CLEAR
- **2023021256-717**: LOW:swarm{swarm:1.02}

## TAPE — FIVE-TIGHT confident fires (the one detector clearing chance; game-event, phase, excess×null-spread)

- 2023021234-461 [LOW] excess=0.08
- 2023021306-287 [LOW] excess=0.14
- 2023020441-307 [LOW] excess=0.03
- 2023020812-145 [LOW] excess=0.31
- 2023021181-165 [LOW] excess=0.03
- 2023020888-178 [LOW] excess=0.41
- 2023021242-113 [HIGH] excess=0.41
- 2023021088-599 [HIGH] excess=0.41
- 2023021019-124 [LOW] excess=0.41
- 2023021159-211 [LOW] excess=0.41
- 2023020641-1028 [LOW] excess=0.41
- 2023021288-679 [LOW] excess=0.01

(total five-tight confident fires: 229)


## TAPE — 'STRUCTURED HIGH → COLLAPSE LOW' switch plays (box1 HIGH → five_tight/swarm LOW) for owner eyes

- 2023020519-311: LOW:swarm → HIGH:box1 → LOW:box1
- 2023020377-842: LOW:five_tight → HIGH:box1
- 2023021237-1032: LOW:swarm → HIGH:box1 → LOW:box1
- 2023020823-540: HIGH:box1 → LOW:five_tight
- 2023020697-591: LOW:five_tight → HIGH:box1
- 2024020478-886: LOW:swarm → HIGH:box1
- 2024020127-619: LOW:swarm → HIGH:box1
- 2024020597-256: HIGH:box1 → LOW:swarm
- 2024021110-380: LOW:five_tight → HIGH:box1
- 2024020842-210: LOW:five_tight → HIGH:box1
- 2024020178-165: LOW:five_tight → HIGH:box1
- 2024020536-895: LOW:five_tight → HIGH:box1
- 2025021083-1091: LOW:swarm → HIGH:box1
- 2025020084-864: LOW:swarm → HIGH:box1
- 2025020769-429: LOW:five_tight → HIGH:box1
- 2025020188-667: HIGH:box1 → LOW:five_tight
- 2025020640-604: LOW:five_tight → HIGH:box1

(total box→collapse switch plays: 17)


## TAPE — NO-CLEAR plays (settled, but NO segment beat any detector's null) for owner eyes

- 2023021007-621: LOW:NO-CLEAR → HIGH:NO-CLEAR
- 2023021168-595: LOW:NO-CLEAR
- 2023020450-98: LOW:NO-CLEAR
- 2023021025-619: LOW:NO-CLEAR → HIGH:NO-CLEAR → LOW:NO-CLEAR
- 2023021143-947: LOW:NO-CLEAR → HIGH:NO-CLEAR
- 2023020593-920: LOW:NO-CLEAR → HIGH:NO-CLEAR
- 2023021222-594: LOW:NO-CLEAR → HIGH:NO-CLEAR
- 2023020729-546: HIGH:NO-CLEAR → LOW:NO-CLEAR → HIGH:NO-CLEAR
- 2023020897-58: HIGH:NO-CLEAR → LOW:NO-CLEAR
- 2023021043-917: LOW:NO-CLEAR
- 2023021253-160: LOW:NO-CLEAR → HIGH:NO-CLEAR → LOW:NO-CLEAR
- 2023021312-489: LOW:NO-CLEAR → HIGH:NO-CLEAR
- 2023021209-376: LOW:NO-CLEAR
- 2023020425-1058: LOW:NO-CLEAR → HIGH:NO-CLEAR
- 2023020948-969: LOW:NO-CLEAR

(total all-NO-CLEAR settled plays: 2,899 of 3,628)


## STOP — behavioral scheme read for owner tape review. No aggregation past the gate, no grade, no blame.
