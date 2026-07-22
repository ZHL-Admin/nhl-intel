# Stage 4 — TEAM goal-STYLE enrichment (descriptive; nothing promoted)

**LAW 1 · GOALS-ONLY. Every tracked sequence ended in a goal; there is no tracked non-goal in this data. You may DESCRIBE and ATTRIBUTE what happened on goals and build goal-as-the-unit measurements. You may NEVER make a predictive or comparative 'what causes goals / what wins' claim from this data alone.**

**LAW 2 · FUSION. Tracking is faithful on position (scorer within stick-reach 88% in validation) and weak on exact stick attribution in traffic (38%). Attribution NEVER comes from geometry alone: the recorded scorer/assisters from stg_play_by_play are the anchor; tracking supplies context around those labels. Cluster-level credit is acceptable; deflection micro-mechanics may remain fuzzy and are labeled as such.**

Team-season profiles aggregate the Stage 2 per-goal buildup descriptors. FOR = how a team scores; AGAINST = how it is scored on. Shares carry absolute goal counts. Deterministic (seed 20260714). 2025-26 latest game_date 2026-06-11 and ~230-355 GF/team → **complete season (not partial)**. (Utah team_id changed to 68 in 2025-26.)

## Metric definitions

- **rush_share** — goal off the rush (rush_flag)
- **carried_share** — zone entry carried in
- **dumped_share** — entry dumped in
- **cross_slot_share** — buildup pass pattern = cross-slot/royal-road
- **netfront_share** — scorer released ≤8 ft from net (net-front reliance)
- **multipass_share** — ≥3 passes in the buildup
- **direct_share** — 0 passes (direct/off-rebound)
- **mean_time_in_zone** — mean seconds in zone before the goal (buildup speed; lower=faster)

## Gate — FOR side: stability (split-half, bar 0.40) AND distinctiveness (excess ≥1.5)

| metric | n team-seasons | split-half r | placebo p | excess (spread/noise) | STABLE | DISTINCT | BOTH |
|---|---|---|---|---|---|---|---|
| rush_share | 96 | **0.206** | 0.0225 | **1.28** | n | n | — |
| carried_share | 96 | **0.281** | 0.001 | **1.64** | n | Y | distinct-only |
| dumped_share | 96 | **0.09** | 0.1905 | **1.23** | n | n | — |
| cross_slot_share | 96 | **0.324** | 0.001 | **1.82** | n | Y | distinct-only |
| netfront_share | 96 | **0.278** | 0.006 | **1.73** | n | Y | distinct-only |
| multipass_share | 96 | **0.638** | 0.0 | **4.63** | Y | Y | **YES** |
| direct_share | 96 | **0.522** | 0.0 | **3.86** | Y | Y | **YES** |
| mean_time_in_zone | 96 | **0.259** | 0.004 | **3.9** | n | Y | distinct-only |

## Gate — AGAINST side: stability (split-half, bar 0.40) AND distinctiveness (excess ≥1.5)

| metric | n team-seasons | split-half r | placebo p | excess (spread/noise) | STABLE | DISTINCT | BOTH |
|---|---|---|---|---|---|---|---|
| rush_share | 96 | **0.02** | 0.437 | **1.12** | n | n | — |
| carried_share | 96 | **0.026** | 0.3965 | **1.03** | n | n | — |
| dumped_share | 96 | **0.127** | 0.11 | **1.11** | n | n | — |
| cross_slot_share | 96 | **0.222** | 0.0135 | **1.77** | n | Y | distinct-only |
| netfront_share | 96 | **0.284** | 0.004 | **1.57** | n | Y | distinct-only |
| multipass_share | 96 | **0.666** | 0.0 | **4.42** | Y | Y | **YES** |
| direct_share | 96 | **0.654** | 0.0 | **3.66** | Y | Y | **YES** |
| mean_time_in_zone | 96 | **0.262** | 0.0055 | **4.08** | n | Y | distinct-only |

## System Effects fingerprint agreement (goals-only style vs movement-based style, overlapping seasons)

Descriptive agreement only — does NOT reopen matchup/style-install (F12/F15).

- rush_share~rush_share_for: r=-0.015 (n=96)
- netfront_share~loc_inner_against: r=-0.035 (n=96)
- direct_share~point_shot_share_for: r=-0.137 (n=96)

**Interpretation:** the overlapping concepts show ~zero correlation (|r|<0.15) — the goals-only event-sequence style and the movement-based System Effects fingerprint capture DIFFERENT facets of team identity (goals-only rush/net-front vs all-shot movement/location; and SE has no pass-count analog, which is where goals-only is most distinctive). They do NOT agree on team identity for these concepts; the goals-only pass-count signature is a NEW, independent style axis, not a re-derivation of SE.

## League style map — FOR side, stable+distinct metrics (2025-26)

| team | GF | multipass_share | direct_share |
|---|---|---|---|
| COL | 345 | 0.739 | 0.017 |
| MTL | 331 | 0.716 | 0.012 |
| BOS | 284 | 0.704 | 0.014 |
| NYI | 232 | 0.694 | 0.022 |
| BUF | 330 | 0.694 | 0.039 |
| DAL | 290 | 0.690 | 0.010 |
| UTA | 290 | 0.686 | 0.038 |
| ANA | 312 | 0.686 | 0.013 |
| NSH | 245 | 0.682 | 0.037 |
| PIT | 308 | 0.675 | 0.029 |
| NYR | 237 | 0.675 | 0.021 |
| EDM | 305 | 0.669 | 0.016 |
| WPG | 232 | 0.668 | 0.017 |
| VGK | 342 | 0.667 | 0.023 |
| CAR | 355 | 0.665 | 0.028 |
| PHI | 265 | 0.664 | 0.023 |
| CBJ | 246 | 0.663 | 0.024 |
| MIN | 308 | 0.662 | 0.032 |
| WSH | 263 | 0.658 | 0.030 |
| SEA | 228 | 0.654 | 0.048 |
| NJD | 229 | 0.651 | 0.039 |
| OTT | 283 | 0.650 | 0.025 |
| FLA | 253 | 0.648 | 0.028 |
| SJS | 258 | 0.647 | 0.035 |
| LAK | 231 | 0.645 | 0.039 |
| CHI | 212 | 0.632 | 0.019 |
| DET | 247 | 0.632 | 0.020 |
| CGY | 212 | 0.627 | 0.024 |
| TBL | 304 | 0.625 | 0.043 |
| STL | 240 | 0.617 | 0.062 |
| VAN | 221 | 0.615 | 0.063 |
| TOR | 255 | 0.600 | 0.047 |

## Three worked team profiles (FOR, 2025-26)

- **COL** (345 GF): rush_share 0.33, carried_share 0.32, dumped_share 0.05, cross_slot_share 0.14, netfront_share 0.44, multipass_share 0.74, direct_share 0.02, mean_time_in_zone 3.84, time_in_zone 3.8s
- **TOR** (255 GF): rush_share 0.41, carried_share 0.35, dumped_share 0.08, cross_slot_share 0.10, netfront_share 0.47, multipass_share 0.60, direct_share 0.05, mean_time_in_zone 3.22, time_in_zone 3.2s
- **DAL** (290 GF): rush_share 0.30, carried_share 0.25, dumped_share 0.05, cross_slot_share 0.11, netfront_share 0.56, multipass_share 0.69, direct_share 0.01, mean_time_in_zone 3.52, time_in_zone 3.5s

## STOP — owner review. Nothing promoted. Unlocks the F4 team-style visual if the gate holds.
