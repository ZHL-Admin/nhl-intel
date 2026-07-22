# Stage 2 — Playmaking & buildup description

**Goal-Tracking program.** Reads the **Stage 0 API only** (fused_goals + goal_events); no frames, no Stage 1. `make stage2` reproduces from the Stage-0 cache.

> **LAW 1 · GOALS-ONLY.** Every tracked sequence ended in a goal; there is no tracked non-goal in this data. You may DESCRIBE and ATTRIBUTE what happened on goals and build goal-as-the-unit measurements. You may NEVER make a predictive or comparative 'what causes goals / what wins' claim from this data alone.

> **LAW 2 · FUSION.** Tracking is faithful on position (scorer within stick-reach 88% in validation) and weak on exact stick attribution in traffic (38%). Attribution NEVER comes from geometry alone: the recorded scorer/assisters from stg_play_by_play are the anchor; tracking supplies context around those labels. Cluster-level credit is acceptable; deflection micro-mechanics may remain fuzzy and are labeled as such.

> **AMENDMENT 2026-07-14:** carrier-dependent fields use **TRACKED** clips (a∧b); counts on all clips; "release" = **effective_release** (flight-start if the detector fired, else arrival).


## 2.1 Per-goal buildup descriptors

- Universe: **25,946 goals** (23,966 TRACKED). Per-column universe flagged below.

| descriptor | universe | definition |
|---|---|---|
| pass_count | all | reconstructed completed passes in the buildup |
| entry_type / entry_carrier | all | Stage 0 zone entry |
| time_in_zone | all | entry_to_goal (s) where an entry exists |
| pass_pattern | **tracked** | class of the LAST completed pass before effective_release |
| primary_carrier_id | **tracked** | most possession time in the final 8.0 s |
| separation_gain | **tracked** | nd_scorer_rel − nd_scorer **1.0 s** prior (see note) |

*Note (forced by the Stage-0 API):* the spec defines separation_gain against nd_scorer at **2.0 s** prior, but Stage 0 persisted only the 1.0 s value (`nd_scorer_1s`). With "reads the Stage 0 API only" binding, the **1.0 s window is used**; a 2.0 s version needs a Stage 0 field addendum. Median separation_gain = -3.50 ft (negative = the nearest defender closes as the shot arrives).

**pass_pattern assignment rates** (tracked; last completed pass before effective_release; priority behind_net_feed › cross_slot › point_to_net › low_to_high_to_net › rush_sequence › other):

| pattern | goals | share |
|---|---|---|
| other | 13,776 | 57.5% |
| cross_slot | 3,303 | 13.8% |
| (no pass before release) | 1,697 | 7.1% |
| point_to_net | 1,516 | 6.3% |
| rush_sequence | 1,487 | 6.2% |
| low_to_high_to_net | 1,154 | 4.8% |
| behind_net_feed | 1,033 | 4.3% |

**entry_type (all clips):** off_frame_start=15,217, carried=7,613, dumped=1,606, passed=1,088.

## 2.2 Player buildup signatures (shares with counts; gate ≥15 involved goals)

Two universes kept **separate**: **pbp** (scorer/assister; 735 players clear ≥15 pooled) and **carrier** (reconstructed primary carrier on a CLEAN clip; 103 players). Field medians (pbp gated): finisher=0.38, feeder=0.18, carrier=0.28, rush=0.35, royal_road=0.15, entry_driver=0.33, net_front=0.13.

Representative leaders (pbp, pooled, gated) — face validity check:

- **net-front:** Zach Hyman 49% (n=204); Nick Foligno 48% (n=90); Michael McLeod 47% (n=19); Corey Perry 47% (n=106); Cole Reinhardt 47% (n=17)
- **finisher:** Sam Colangelo 87% (n=15); Alex Nylander 75% (n=16); Dominik Kubalik 73% (n=15); Jeff Carter 73% (n=15); Marc Gatcomb 69% (n=16)
- **feeder:** Adam Wilsby 38% (n=21); Derek Ryan 37% (n=19); Denver Barkey 37% (n=19); Nate Schmidt 37% (n=71); Jordan Harris 35% (n=23)

## 2.3 Reliability gate (pre-stated: majority of fields split-half ≥0.30 AND placebo p<0.05)

Players with ≥30 involved goals pooled: **596**. **5/7 fields pass → GATE: PASS.** Per-season signatures are publishable subject to the ≥15-goal gate — buildup signatures are stable, persistent player traits (unlike the Stage-1 goalie mechanism mix).

| field | players | split-half r | placebo p | passes |
|---|---|---|---|---|
| net_front_share | 596 | 0.76 | 0.000 | **Y** |
| finisher_share | 596 | 0.70 | 0.000 | **Y** |
| entry_driver_share | 596 | 0.56 | 0.000 | **Y** |
| carrier_share | 596 | 0.53 | 0.000 | **Y** |
| rush_share | 596 | 0.37 | 0.000 | **Y** |
| royal_road_share | 596 | 0.24 | 0.000 | · |
| feeder_share | 596 | 0.16 | 0.000 | · |

*The two failing fields — royal_road_share (0.24) and feeder_share (0.16) — are not stable per-player traits: creating cross-slot goals and feeding a specific scorer are situation/linemate-driven, not individual signatures. Report them descriptively, not as identity claims.*

**Role-axis sanity matrix** (no bar; pooled pbp signatures vs role-fit two-way role axes; face validity):

| signature | role axis | r | n |
|---|---|---|---|
| finisher_share | goals60 | +0.74 | 1,517 |
| net_front_share | slot_share | +0.72 | 1,517 |
| finisher_share | xg60 | +0.71 | 1,517 |
| net_front_share | tip_share | +0.65 | 1,517 |
| finisher_share | slot_share | +0.64 | 1,517 |
| carrier_share | cf60 | +0.22 | 1,517 |
| feeder_share | assists60 | +0.12 | 1,517 |

All signs are face-valid (finishers score & shoot from the slot; net-front players tip & shoot the slot; carriers drive shot volume). No contradictory sign flagged.

## 2.4 Exhibits (pbp, pooled, gated ≥15)


**Top-10 rush-share scorers:**

| # | player | rush_share | count | involved |
|---|---|---|---|---|
| 1 | Cole Koepke | 62% | 23 | 37 |
| 2 | Brett Howden | 61% | 64 | 105 |
| 3 | Teddy Blueger | 61% | 45 | 74 |
| 4 | Joel Armia | 59% | 49 | 83 |
| 5 | Barclay Goodrow | 56% | 22 | 39 |
| 6 | Jake Evans | 56% | 56 | 100 |
| 7 | Morgan Barron | 56% | 33 | 59 |
| 8 | Scott Laughton | 55% | 50 | 91 |
| 9 | Miles Wood | 55% | 28 | 51 |
| 10 | John Beecher | 53% | 16 | 30 |

**Top-10 entry-driver playmakers:**

| # | player | entry_driver_share | count | involved |
|---|---|---|---|---|
| 1 | Connor Bedard | 75% | 40 | 203 |
| 2 | Patrik Laine | 75% | 6 | 47 |
| 3 | Yakov Trenin | 73% | 8 | 59 |
| 4 | Filip Chytil | 71% | 5 | 36 |
| 5 | Michael Eyssimont | 71% | 10 | 54 |
| 6 | Sam Carrick | 71% | 12 | 52 |
| 7 | Pierre Engvall | 69% | 9 | 43 |
| 8 | Miles Wood | 69% | 11 | 51 |
| 9 | Michael Carcone | 68% | 21 | 81 |
| 10 | Colin Blackwell | 67% | 8 | 46 |

**Top-10 royal-road creators:**

| # | player | royal_road_share | count | involved |
|---|---|---|---|---|
| 1 | Patrik Laine | 39% | 15 | 47 |
| 2 | Radko Gudas | 34% | 14 | 47 |
| 3 | Adam Klapka | 32% | 9 | 31 |
| 4 | Erik Gustafsson | 31% | 14 | 51 |
| 5 | Carson Soucy | 31% | 9 | 36 |
| 6 | Alexander Nikishin | 30% | 10 | 35 |
| 7 | Mike Reilly | 30% | 9 | 38 |
| 8 | Egor Zamula | 30% | 9 | 39 |
| 9 | Ty Emberson | 29% | 10 | 36 |
| 10 | Matthew Schaefer | 28% | 15 | 59 |

**Worked goal chain (example; owner to name the goal at the gate):**

**2023020097-119** (2023-24) — scorer Nick Bjugstad, assists (Lawson Crouse, Michael Carcone); entry=off_frame_start; release_source=arrival.

| frame | event | detail |
|---|---|---|
| — | ENTRY | off_frame_start |
| 27–28 | pass | Lawson Crouse → Nick Bjugstad (-7,19)→(-8,18) |
| 45–47 | pass | Lawson Crouse → Michael Carcone (-23,17)→(-25,21) |
| 67–75 | pass | Lawson Crouse → Nick Bjugstad (-66,14)→(-78,0) |
| 76 | RELEASE | puck @(-80,-0) |
| 79 | ARRIVAL | puck @(-90,-2) |

## Reproducibility

- `make stage2` = descriptors → signatures → reliability → tests → report, from the Stage-0 cache. Seed 20260714. Ratio metrics ship with absolute counts.

**STOP for owner review.**
