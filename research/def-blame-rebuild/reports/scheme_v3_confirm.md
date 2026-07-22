# Behavioral Scheme Detection v3 §8 — read-only confirm (phase segmentation + enabling-situation exposure)

Settled goals: **8,047**. Hysteresis phases (HIGH≥25 / LOW<15, hold between), min segment 1.0s. **No detectors fired — enabling-situation exposure only.**

## Phase segmentation

- total segments: **19,369** · segments/goal: mean 2.4, median 2, p90 3
- HIGH 48% / LOW 52% of segments · segment length (s): median 3.1, p25 2.0, p75 4.8

## Enabling-situation exposure per detector (fraction of segments that CONTAIN the required situation)

| detector | enabling situation | % of segments | viable? |
|---|---|---|---|
| MAN | ≥1 attacker moves ≥15ft | **85%** | yes |
| MAN (≥3 shadows) | ≥3 attackers move ≥15ft | **64%** | yes |
| ZONE | ≥1 attacker moves ≥15ft (same as man) | **85%** | yes |
| FIVE-TIGHT | low-corner puck (depth<15 & |lat|≥15) | **50%** | yes |
| SWARM | LOW-phase (puck low) | **52%** | yes |
| BOX+1 | sustained ≥1s seg, 5 defenders | **67%** | yes |

## Read
- A detector whose enabling situation is rare (<~10% of segments) is largely dead on arrival — it can only fire on the few segments that contain its situation. This sizes viability BEFORE building. MAN's ≥3-simultaneous-shadow requirement (issue #4) is the tightest enabling gate; watch it.

## STOP — read-only confirm. No detectors, no nulls, no scores.
