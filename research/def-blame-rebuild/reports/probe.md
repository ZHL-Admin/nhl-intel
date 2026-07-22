# Defensive Blame · Possession-Level Rebuild — probe.md

**Outputs are a DESCRIPTIVE per-possession coverage-failure log and an ABSOLUTE blame rate over 5v5 goals-against, never a claim of certain fault on any single goal and never a full defensive rating. We measure change in a defender's own coverage state over time, not scheme or where he should have been (avoids F26). Banned as a single-goal verdict: bad defense, fault, out of position, mistake.**

From-scratch possession model (branch research/def-blame-rebuild, own venv, seed 20260714f). Blame is measured over the whole possession, in isolation per defender, ABSOLUTE (a goal may assign ~0 total blame). Read-only reuse: goal-tracking fused corpus + frames, def-scheme phase-0 primitives (validation only), Atlas stints/5v5. Nothing promoted.


## Link 0 · the 5v5 universe, the possession window, the coverage tracks

### The strength filter (fixed: even-strength 5v5 only)

| stage | goals |
|---|---|
| all tracked goals (reconstruction_ok) | 25,945 |
| **kept: 5v5, tracked, valid attack direction** | **22,773** |
| removed: not 5v5 (PP / PK / 4v4 / 3v3 / empty-net etc.) | 3,172 |
| of the 5v5 set, kept with exactly 5 defending & 5 attacking skaters tracked at the shot | 12,139 |

Strength breakdown of all tracked goals (the removed non-5v5 states):

| strength_state | goals |
|---|---|
| 5v5 | 22,774 |
| 5v4 | 868 |
| 4v5 | 758 |
| 3v3 | 530 |
| 4v4 | 400 |
| 5v6 | 154 |
| 6v5 | 136 |
| 1v0 | 101 |
| 0v1 | 87 |
| 4v3 | 46 |

The exact-5v5-at-shot occupancy gate keeps **12,139** goals of the 22,773 5v5 set. The dropped goals are those where tracking shows fewer or more than five skaters per side at the shot instant (momentary dropout, or phantom over-detection that would corrupt a defender's 'nearest attacker'). *Decision flag:* this gate favours clean geometry but may under-sample high-traffic net-front scrambles; reported here, not silently applied.

### The possession window

Per goal the window runs from the attacking team's last clean zone entry up to the shot release (`goal_frame = release_frame`). When no in-window entry exists (possession began before the tracked window — `entry_type = off_frame_start`), the window falls back to the final ≤12s of approach. Windows shorter than 0.6s are flagged (turnover chaos / no clean buildup).

| window source | goals |
|---|---|
| clean in-window zone entry | 8,030 |
| fallback final-approach window (no clean entry) | 14,743 |
| flagged short (< 0.6s) | 168 |

**Window length (seconds) distribution:**

| min | p10 | p25 | median | p75 | p90 | max |
|---|---|---|---|---|---|---|
| 0.0 | 2.0 | 3.4 | 7.8 | 9.1 | 9.8 | 12.0 |

### The coverage-track schema (10 Hz, geometry only — no labels, no blame)

One row per defending skater per frame of the window:

| column | meaning |
|---|---|
| `near_att_id` | identity of his nearest attacker that frame (reveals whether he manages one man or switches) |
| `dist_near_atk` | distance to that nearest attacker (ft) |
| `dist_puck` | distance to the puck (ft) |
| `dist_slot` | distance to the most dangerous ice (net-front / slot reference) |
| `dist_net` | his own distance to the defended net (ft) |
| `att_dist_net` | his nearest attacker's distance to the defended net (for goal-side) |
| `goal_side` | is he goal-side of his nearest attacker (nearer the defended net along the attack axis) |

Total: **4,278,720 defender-frames** over 12,139 goals.

### Fidelity (per-defender geometry vs def-scheme phase-0 primitive, 2025-26)

My per-defender nearest-attacker distance reproduces the independent phase-0 `dist_nearest_atk` exactly: **corr = 1.0000, mean abs diff = 0.000 ft** over 1,415,842 matched defender-frames. The coordinate frame and role assignment are correct.


---

## Link 1 · the coverage-failure events (absolute, per-defender, from scratch)

Blame accrues to a defender only when a coverage-failure event fires in HIS OWN track; a goal's total blame is the SUM of event severities (absolute, not forced to one). Three events, each isolating one failure mode; severities scale in [0,1] per event.

### Event definitions, fire rates, and calibration footage (frozen)

| event | what fires it | severity scales with | goals with >=1 fire |
|---|---|---|---|
| **E1 containment loss** | nearest, goal-side defender to the scorer/primary-passer for ≥1.0s, then that man's separation grew ≥ **14.3 ft** in the final 2.0s and he scored/assisted | how open the man got (to the p95 growth of 29.4 ft) × role (scorer 1.0, passer 0.6) | 4,581 |
| **E2 over-commitment** | nearest defender to the net-front early, then closed on the puck and vacated the net-front ≥ **3.6 ft**, goal from dangerous ice | how much he vacated (to p95 16.0 ft) × shot danger (release 2.2–35.2 ft from net) | 1,910 |
| **E3 failure to close** | nearest defender to the scorer through the final approach, never reduced the gap, scorer open ≥ **12.7 ft** at release | scorer openness at release (to p95 19.0 ft) | 526 |

Thresholds are the 80th percentile of each measure's own distribution (E1 over 23,381 managed defender-man pairs; E2 over 15,395 puck-pursuing net-front defenders; E3 over all goals' scorer-openness), frozen after this report. Guard: E1 and E3 are mutually exclusive per defender-goal (E1 needs a man held goal-side ≥1s; E3 needs he never held him).

### Per-goal TOTAL blame distribution (the key property: blameless goals now assign ~0)

| quantile | total blame |
|---|---|
| p10 | 0.000 |
| p25 | 0.000 |
| median | 0.000 |
| p75 | 0.415 |
| p90 | 0.977 |
| p99 | 1.881 |
| max | 3.377 |

**7,140 of 12,139 goals (58.8%) assign ~zero total blame** — no defender's coverage measurably broke. This is the intended contrast with the old forced-unit model, where every goal distributed exactly 1.0 across five defenders (median max-share 0.20). Here blame concentrates only when a track actually shows a coverage state changing.

Event mix among fired goals: E1 containment loss is the most common, E3 failure-to-close the rarest — consistent with most 5v5 goals-against involving a man getting loose rather than a defender frozen.

### 12 worked example goals (geometry over time; STOP here for owner eyeball)

Each table samples the chosen defender's track every 0.5s from the window start to the shot. Descriptive geometry only — not a certain verdict on any one goal.


**Example 1 — E1 CONTAINMENT LOSS.** Defender **Charlie Coyle**, scorer **Josh Doan** (game 2025020152 / event 309), event severity 1.00.

| t-to-shot (s) | dist→scorer | dist→puck | dist→net-front | goal-side of scorer | nearest man |
|---|---|---|---|---|---|
| 10.0 | 23.9 | 51.4 | 8.4 | no | Alex Tuch |
| 9.5 | 27.4 | 55.5 | 9.6 | yes | Alex Tuch |
| 9.0 | 24.7 | 58.7 | 9.6 | yes | Alex Tuch |
| 8.5 | 19.4 | 62.2 | 8.6 | yes | Alex Tuch |
| 8.0 | 12.6 | 36.3 | 7.2 | yes | Alex Tuch |
| 7.5 | 7.6 | 8.8 | 6.2 | yes | Alex Tuch |
| 7.0 | 3.4 | 10.1 | 7.2 | yes | Josh Doan |
| 6.5 | 2.2 | 10.8 | 10.5 | yes | Josh Doan |
| 6.0 | 2.6 | 10.1 | 16.0 | yes | Josh Doan |
| 5.5 | 1.2 | 5.0 | 21.9 | yes | Josh Doan |
| 5.0 | 2.7 | 13.0 | 27.2 | yes | Josh Doan |
| 4.5 | 7.1 | 30.1 | 30.9 | no | Josh Doan |
| 4.0 | 12.4 | 42.2 | 31.9 | no | Josh Doan |
| 3.5 | 17.1 | 52.3 | 31.4 | no | Josh Doan |
| 3.0 | 23.6 | 63.9 | 33.4 | no | Alex Tuch |
| 2.5 | 29.9 | 51.5 | 38.9 | no | Alex Tuch |
| 2.0 | 37.3 | 41.1 | 43.9 | no | Alex Tuch |
| 1.5 | 39.8 | 38.3 | 45.2 | no | Alex Tuch |
| 1.0 | 39.7 | 46.3 | 41.0 | no | Ryan McLeod |
| 0.5 | 34.8 | 37.8 | 32.6 | no | Ryan McLeod |
| 0.0 | 29.9 | 32.5 | 23.8 | no | Ryan McLeod |

**Example 2 — E1 CONTAINMENT LOSS.** Defender **Connor Dewar**, scorer **Marcus Johansson** (game 2025020332 / event 299), event severity 1.00.

| t-to-shot (s) | dist→scorer | dist→puck | dist→net-front | goal-side of scorer | nearest man |
|---|---|---|---|---|---|
| 9.6 | 24.6 | 20.7 | 44.0 | yes | Matt Boldy |
| 9.1 | 17.1 | 14.9 | 36.5 | yes | Marcus Johansson |
| 8.6 | 9.3 | 14.4 | 29.4 | yes | Marcus Johansson |
| 8.1 | 1.4 | 23.1 | 27.0 | no | Marcus Johansson |
| 7.6 | 2.4 | 17.4 | 24.6 | no | Marcus Johansson |
| 7.1 | 2.1 | 44.2 | 22.5 | no | Marcus Johansson |
| 6.6 | 2.3 | 42.0 | 21.3 | yes | Marcus Johansson |
| 6.1 | 3.2 | 34.6 | 21.9 | yes | Marcus Johansson |
| 5.6 | 4.2 | 36.2 | 22.6 | yes | Marcus Johansson |
| 5.1 | 4.6 | 39.6 | 24.6 | yes | Marcus Johansson |
| 4.6 | 6.6 | 34.3 | 29.7 | yes | Marcus Johansson |
| 4.1 | 10.7 | 22.0 | 35.2 | yes | Marcus Johansson |
| 3.6 | 13.4 | 26.0 | 39.2 | yes | Marcus Johansson |
| 3.1 | 16.6 | 27.0 | 38.5 | yes | Marcus Johansson |
| 2.6 | 18.9 | 28.2 | 35.6 | yes | Joel Eriksson Ek |
| 2.1 | 22.8 | 21.4 | 34.4 | yes | Joel Eriksson Ek |
| 1.6 | 29.5 | 15.9 | 38.6 | yes | Jonas Brodin |
| 1.1 | 39.8 | 7.9 | 44.7 | no | Jonas Brodin |
| 0.6 | 48.0 | 35.9 | 48.6 | no | Jonas Brodin |
| 0.1 | 49.7 | 50.8 | 47.6 | no | Jonas Brodin |
| 0.0 | 49.8 | 55.5 | 47.0 | no | Jonas Brodin |

**Example 3 — E1 CONTAINMENT LOSS.** Defender **Luke Evangelista**, scorer **Brady Tkachuk** (game 2025020798 / event 697), event severity 1.00.

| t-to-shot (s) | dist→scorer | dist→puck | dist→net-front | goal-side of scorer | nearest man |
|---|---|---|---|---|---|
| 8.7 | 9.7 | — | 8.3 | yes | Brady Tkachuk |
| 8.2 | 9.1 | — | 8.4 | yes | Brady Tkachuk |
| 7.7 | 8.9 | — | 8.4 | yes | Brady Tkachuk |
| 7.2 | 8.4 | — | 8.6 | yes | Brady Tkachuk |
| 6.7 | 7.0 | 45.1 | 9.8 | yes | Brady Tkachuk |
| 6.2 | 7.7 | 44.2 | 13.2 | no | Brady Tkachuk |
| 5.7 | 12.5 | 41.6 | 17.5 | no | Brady Tkachuk |
| 5.2 | 20.9 | 41.8 | 21.8 | no | Brady Tkachuk |
| 4.7 | 28.9 | 46.9 | 26.1 | no | Artem Zub |
| 4.2 | 35.9 | 50.3 | 29.9 | no | Artem Zub |
| 3.7 | 36.3 | 46.2 | 30.1 | no | Artem Zub |
| 3.2 | 33.3 | 41.5 | 29.1 | no | Artem Zub |
| 2.7 | 32.0 | 38.4 | 29.6 | no | Dylan Cozens |
| 2.2 | 32.7 | 37.4 | 29.6 | no | Dylan Cozens |
| 1.7 | 35.1 | 21.2 | 31.1 | no | Dylan Cozens |
| 1.2 | 36.8 | 20.7 | 33.2 | no | Dylan Cozens |
| 0.7 | 38.9 | 14.4 | 37.5 | no | Artem Zub |
| 0.2 | 39.1 | 33.3 | 38.5 | no | Artem Zub |
| 0.0 | 38.5 | 42.6 | 37.7 | no | Artem Zub |

**Example 4 — E2 OVER-COMMITMENT.** Defender **Charlie Coyle**, scorer **Josh Doan** (game 2025020152 / event 309), event severity 1.00.

| t-to-shot (s) | dist→scorer | dist→puck | dist→net-front | goal-side of scorer | nearest man |
|---|---|---|---|---|---|
| 10.0 | 23.9 | 51.4 | 8.4 | no | Alex Tuch |
| 9.5 | 27.4 | 55.5 | 9.6 | yes | Alex Tuch |
| 9.0 | 24.7 | 58.7 | 9.6 | yes | Alex Tuch |
| 8.5 | 19.4 | 62.2 | 8.6 | yes | Alex Tuch |
| 8.0 | 12.6 | 36.3 | 7.2 | yes | Alex Tuch |
| 7.5 | 7.6 | 8.8 | 6.2 | yes | Alex Tuch |
| 7.0 | 3.4 | 10.1 | 7.2 | yes | Josh Doan |
| 6.5 | 2.2 | 10.8 | 10.5 | yes | Josh Doan |
| 6.0 | 2.6 | 10.1 | 16.0 | yes | Josh Doan |
| 5.5 | 1.2 | 5.0 | 21.9 | yes | Josh Doan |
| 5.0 | 2.7 | 13.0 | 27.2 | yes | Josh Doan |
| 4.5 | 7.1 | 30.1 | 30.9 | no | Josh Doan |
| 4.0 | 12.4 | 42.2 | 31.9 | no | Josh Doan |
| 3.5 | 17.1 | 52.3 | 31.4 | no | Josh Doan |
| 3.0 | 23.6 | 63.9 | 33.4 | no | Alex Tuch |
| 2.5 | 29.9 | 51.5 | 38.9 | no | Alex Tuch |
| 2.0 | 37.3 | 41.1 | 43.9 | no | Alex Tuch |
| 1.5 | 39.8 | 38.3 | 45.2 | no | Alex Tuch |
| 1.0 | 39.7 | 46.3 | 41.0 | no | Ryan McLeod |
| 0.5 | 34.8 | 37.8 | 32.6 | no | Ryan McLeod |
| 0.0 | 29.9 | 32.5 | 23.8 | no | Ryan McLeod |

**Example 5 — E2 OVER-COMMITMENT.** Defender **Connor Dewar**, scorer **Marcus Johansson** (game 2025020332 / event 299), event severity 0.97.

| t-to-shot (s) | dist→scorer | dist→puck | dist→net-front | goal-side of scorer | nearest man |
|---|---|---|---|---|---|
| 9.6 | 24.6 | 20.7 | 44.0 | yes | Matt Boldy |
| 9.1 | 17.1 | 14.9 | 36.5 | yes | Marcus Johansson |
| 8.6 | 9.3 | 14.4 | 29.4 | yes | Marcus Johansson |
| 8.1 | 1.4 | 23.1 | 27.0 | no | Marcus Johansson |
| 7.6 | 2.4 | 17.4 | 24.6 | no | Marcus Johansson |
| 7.1 | 2.1 | 44.2 | 22.5 | no | Marcus Johansson |
| 6.6 | 2.3 | 42.0 | 21.3 | yes | Marcus Johansson |
| 6.1 | 3.2 | 34.6 | 21.9 | yes | Marcus Johansson |
| 5.6 | 4.2 | 36.2 | 22.6 | yes | Marcus Johansson |
| 5.1 | 4.6 | 39.6 | 24.6 | yes | Marcus Johansson |
| 4.6 | 6.6 | 34.3 | 29.7 | yes | Marcus Johansson |
| 4.1 | 10.7 | 22.0 | 35.2 | yes | Marcus Johansson |
| 3.6 | 13.4 | 26.0 | 39.2 | yes | Marcus Johansson |
| 3.1 | 16.6 | 27.0 | 38.5 | yes | Marcus Johansson |
| 2.6 | 18.9 | 28.2 | 35.6 | yes | Joel Eriksson Ek |
| 2.1 | 22.8 | 21.4 | 34.4 | yes | Joel Eriksson Ek |
| 1.6 | 29.5 | 15.9 | 38.6 | yes | Jonas Brodin |
| 1.1 | 39.8 | 7.9 | 44.7 | no | Jonas Brodin |
| 0.6 | 48.0 | 35.9 | 48.6 | no | Jonas Brodin |
| 0.1 | 49.7 | 50.8 | 47.6 | no | Jonas Brodin |
| 0.0 | 49.8 | 55.5 | 47.0 | no | Jonas Brodin |

**Example 6 — E3 FAILURE TO CLOSE.** Defender **Matthew Robertson**, scorer **Conor Garland** (game 2025021086 / event 154), event severity 1.00.

| t-to-shot (s) | dist→scorer | dist→puck | dist→net-front | goal-side of scorer | nearest man |
|---|---|---|---|---|---|
| 11.0 | 47.6 | 50.5 | 2.9 | yes | Sean Monahan |
| 10.5 | 50.0 | 56.2 | 2.5 | yes | Sean Monahan |
| 10.0 | 50.7 | 54.3 | 3.7 | yes | Sean Monahan |
| 9.5 | 47.6 | 55.8 | 4.5 | yes | Sean Monahan |
| 9.0 | 43.8 | 48.1 | 5.4 | yes | Sean Monahan |
| 8.5 | 39.4 | 36.6 | 6.7 | yes | Sean Monahan |
| 8.0 | 34.8 | 32.2 | 6.8 | yes | Sean Monahan |
| 7.5 | 31.5 | 32.3 | 5.1 | yes | Sean Monahan |
| 7.0 | 29.7 | 35.7 | 5.2 | yes | Sean Monahan |
| 6.5 | 29.6 | 37.8 | 5.6 | yes | Sean Monahan |
| 6.0 | 30.3 | 40.0 | 6.7 | yes | Sean Monahan |
| 5.5 | 31.9 | 40.8 | 7.1 | yes | Sean Monahan |
| 5.0 | 30.8 | 49.8 | 7.8 | yes | Sean Monahan |
| 4.5 | 30.7 | 60.1 | 8.8 | yes | Sean Monahan |
| 4.0 | 30.4 | 57.6 | 9.4 | yes | Sean Monahan |
| 3.5 | 28.9 | 57.9 | 8.9 | yes | Sean Monahan |
| 3.0 | 25.4 | 31.5 | 8.7 | yes | Conor Garland |
| 2.5 | 21.6 | 20.7 | 7.9 | yes | Conor Garland |
| 2.0 | 17.1 | 15.2 | 8.2 | yes | Conor Garland |
| 1.5 | 9.5 | 8.5 | 13.1 | yes | Conor Garland |
| 1.0 | 7.6 | 10.4 | 17.9 | yes | Conor Garland |
| 0.5 | 13.3 | 23.0 | 19.5 | yes | Conor Garland |
| 0.0 | 24.2 | 17.8 | 17.8 | yes | Sean Monahan |

**Example 7 — E3 FAILURE TO CLOSE.** Defender **Alex Vlasic**, scorer **Dylan Guenther** (game 2025021010 / event 374), event severity 1.00.

| t-to-shot (s) | dist→scorer | dist→puck | dist→net-front | goal-side of scorer | nearest man |
|---|---|---|---|---|---|
| 11.2 | 13.3 | 13.3 | 16.0 | no | Clayton Keller |
| 10.7 | 9.3 | 6.8 | 13.5 | yes | Clayton Keller |
| 10.2 | 10.3 | 7.2 | 12.7 | yes | Clayton Keller |
| 9.7 | 12.8 | 5.5 | 13.3 | yes | Clayton Keller |
| 9.2 | 18.6 | 5.8 | 15.6 | yes | Clayton Keller |
| 8.7 | 23.0 | 5.1 | 20.3 | yes | Clayton Keller |
| 8.2 | 27.2 | 3.7 | 27.2 | no | Clayton Keller |
| 7.7 | 34.8 | 4.5 | 37.6 | no | Clayton Keller |
| 7.2 | 41.3 | 5.1 | 47.4 | no | Nick Schmaltz |
| 6.7 | 41.6 | 2.6 | 54.9 | no | Clayton Keller |
| 6.2 | 39.9 | 2.2 | 60.9 | no | Nick Schmaltz |
| 5.7 | 33.8 | 1.8 | 63.3 | no | Nick Schmaltz |
| 5.2 | 25.8 | 8.8 | 64.4 | no | Nick Schmaltz |
| 4.7 | 17.4 | 11.5 | 61.7 | no | Nick Schmaltz |
| 4.2 | 15.0 | 13.5 | 55.1 | no | Nick Schmaltz |
| 3.7 | 14.9 | 13.2 | 45.9 | no | Clayton Keller |
| 3.2 | 15.6 | 13.2 | 35.2 | no | Clayton Keller |
| 2.7 | 13.8 | 16.5 | 23.8 | no | Dylan Guenther |
| 2.2 | 11.0 | 10.6 | 11.9 | no | Dylan Guenther |
| 1.7 | 8.3 | 6.7 | 4.0 | no | Dylan Guenther |
| 1.2 | 8.0 | 9.5 | 13.0 | no | Dylan Guenther |
| 0.7 | 11.7 | 14.1 | 20.2 | yes | Dylan Guenther |
| 0.2 | 21.2 | 15.0 | 22.8 | yes | John Marino |
| 0.0 | 25.3 | 14.9 | 23.2 | yes | John Marino |

**Example 8 — NO COVERAGE BROKE (~0 blame; defender stayed tight).** Defender **Luke Hughes**, scorer **Tanner Pearson** (game 2025020711 / event 112), event severity 0.00.

| t-to-shot (s) | dist→scorer | dist→puck | dist→net-front | goal-side of scorer | nearest man |
|---|---|---|---|---|---|
| 5.3 | 39.5 | 12.8 | 44.0 | yes | Danil Zhilkin |
| 4.8 | 43.2 | 18.0 | 37.8 | yes | Danil Zhilkin |
| 4.3 | 44.4 | 19.3 | 31.5 | yes | Danil Zhilkin |
| 3.8 | 39.3 | 27.8 | 23.5 | yes | Danil Zhilkin |
| 3.3 | 32.0 | 35.4 | 16.7 | yes | Danil Zhilkin |
| 2.8 | 21.3 | 38.3 | 10.5 | yes | Danil Zhilkin |
| 2.3 | 10.6 | 30.7 | 7.8 | yes | Tanner Pearson |
| 1.8 | 3.6 | 28.7 | 9.1 | yes | Tanner Pearson |
| 1.3 | 2.2 | 28.4 | 6.5 | no | Tanner Pearson |
| 0.8 | 1.8 | 23.9 | 3.4 | no | Tanner Pearson |
| 0.3 | 0.8 | 9.1 | 5.0 | no | Tanner Pearson |
| 0.0 | 0.8 | 5.3 | 5.1 | no | Tanner Pearson |

**Example 9 — NO COVERAGE BROKE (~0 blame; defender stayed tight).** Defender **Louis Crevier**, scorer **Dakota Joshua** (game 2025020520 / event 1017), event severity 0.00.

| t-to-shot (s) | dist→scorer | dist→puck | dist→net-front | goal-side of scorer | nearest man |
|---|---|---|---|---|---|
| 2.3 | 7.6 | 34.9 | 52.2 | yes | Dakota Joshua |
| 1.8 | 6.8 | 34.6 | 44.9 | yes | Dakota Joshua |
| 1.3 | 5.5 | 37.1 | 36.4 | yes | Dakota Joshua |
| 0.8 | 4.6 | 24.2 | 29.0 | yes | Dakota Joshua |
| 0.3 | 2.7 | 9.9 | 19.6 | yes | Dakota Joshua |
| 0.0 | 0.9 | 4.5 | 13.5 | no | Dakota Joshua |

**Example 10 — NO COVERAGE BROKE (~0 blame; defender stayed tight).** Defender **Jack Quinn**, scorer **Ryan Hartman** (game 2025020754 / event 381), event severity 0.00.

| t-to-shot (s) | dist→scorer | dist→puck | dist→net-front | goal-side of scorer | nearest man |
|---|---|---|---|---|---|
| 8.0 | 14.7 | 10.8 | 52.9 | yes | Ryan Hartman |
| 7.5 | 13.8 | 13.0 | 47.9 | yes | Ryan Hartman |
| 7.0 | 10.5 | 11.1 | 44.5 | yes | Ryan Hartman |
| 6.5 | 6.0 | 8.5 | 42.9 | yes | Ryan Hartman |
| 6.0 | 1.5 | 16.6 | 43.2 | no | Ryan Hartman |
| 5.5 | 4.7 | 28.1 | 41.3 | no | Ryan Hartman |
| 5.0 | 10.0 | 28.3 | 37.1 | no | Ryan Hartman |
| 4.5 | 18.5 | 27.8 | 33.7 | no | Ryan Hartman |
| 4.0 | 26.4 | 27.5 | 33.1 | no | Quinn Hughes |
| 3.5 | 31.5 | 26.5 | 32.4 | no | Quinn Hughes |
| 3.0 | 33.8 | 26.9 | 28.9 | no | Mats Zuccarello |
| 2.5 | 34.4 | 32.6 | 23.9 | no | Mats Zuccarello |
| 2.0 | 30.0 | 34.1 | 18.0 | no | Mats Zuccarello |
| 1.5 | 23.5 | 32.9 | 13.4 | no | Mats Zuccarello |
| 1.0 | 15.6 | 32.8 | 8.1 | no | Mats Zuccarello |
| 0.5 | 6.9 | 32.2 | 3.7 | no | Ryan Hartman |
| 0.0 | 0.9 | 3.3 | 6.1 | no | Ryan Hartman |

**Example 11 — NO COVERAGE BROKE (~0 blame; defender stayed tight).** Defender **Alexander Petrovic**, scorer **Jack McBain** (game 2025020390 / event 554), event severity 0.00.

| t-to-shot (s) | dist→scorer | dist→puck | dist→net-front | goal-side of scorer | nearest man |
|---|---|---|---|---|---|
| 8.9 | 31.4 | 49.9 | 126.3 | yes | Lawson Crouse |
| 8.4 | 33.5 | 53.6 | 119.4 | yes | Lawson Crouse |
| 7.9 | 32.9 | 53.1 | 110.4 | yes | Lawson Crouse |
| 7.4 | 31.3 | 49.0 | 100.3 | yes | Lawson Crouse |
| 6.9 | 29.4 | 43.2 | 89.4 | yes | Lawson Crouse |
| 6.4 | 28.3 | 38.3 | 77.3 | yes | Jack McBain |
| 5.9 | 26.8 | 31.9 | 64.8 | yes | Jack McBain |
| 5.4 | 25.8 | 23.9 | 52.7 | yes | Jack McBain |
| 4.9 | 26.5 | 20.5 | 39.2 | yes | John Marino |
| 4.4 | 25.9 | 15.2 | 26.8 | yes | John Marino |
| 3.9 | 24.6 | 6.3 | 17.1 | yes | John Marino |
| 3.4 | 22.3 | 16.8 | 12.6 | yes | John Marino |
| 2.9 | 15.6 | 20.5 | 10.2 | yes | John Marino |
| 2.4 | 9.0 | 22.9 | 8.8 | yes | John Marino |
| 1.9 | 3.6 | 18.6 | 7.2 | yes | Jack McBain |
| 1.4 | 2.5 | 15.6 | 5.5 | yes | Jack McBain |
| 0.9 | 2.4 | 5.1 | 4.0 | yes | Jack McBain |
| 0.4 | 2.0 | 3.7 | 3.4 | no | Jack McBain |
| 0.0 | 0.9 | 5.7 | 4.9 | no | Jack McBain |

**Example 12 — NO COVERAGE BROKE (~0 blame; defender stayed tight).** Defender **Frank Nazar**, scorer **Teddy Blueger** (game 2025020985 / event 153), event severity 0.00.

| t-to-shot (s) | dist→scorer | dist→puck | dist→net-front | goal-side of scorer | nearest man |
|---|---|---|---|---|---|
| 5.3 | 9.1 | 17.5 | 56.8 | yes | Teddy Blueger |
| 4.8 | 8.2 | 18.0 | 48.4 | yes | Teddy Blueger |
| 4.3 | 8.3 | 19.6 | 40.5 | yes | Teddy Blueger |
| 3.8 | 4.8 | 21.6 | 34.1 | yes | Teddy Blueger |
| 3.3 | 4.9 | 28.1 | 26.5 | no | Teddy Blueger |
| 2.8 | 6.1 | 36.4 | 18.0 | no | Teddy Blueger |
| 2.3 | 4.4 | 29.8 | 10.2 | no | Teddy Blueger |
| 1.8 | 3.8 | 20.3 | 3.8 | no | Teddy Blueger |
| 1.3 | 5.0 | 13.1 | 2.9 | no | Teddy Blueger |
| 0.8 | 2.4 | 10.7 | 0.8 | no | Teddy Blueger |
| 0.3 | 1.7 | 1.3 | 2.7 | yes | Teddy Blueger |
| 0.0 | 0.9 | 5.4 | 3.1 | yes | Teddy Blueger |

## STOP — owner eyeball validation of the assignment before any aggregation (Link 2).
