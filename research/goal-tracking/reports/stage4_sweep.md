# Stage 4 sweep — FULL offensive-style axis space, two-bar gate (descriptive; nothing promoted)

**LAW 1 · GOALS-ONLY. Every tracked sequence ended in a goal; there is no tracked non-goal in this data. You may DESCRIBE and ATTRIBUTE what happened on goals and build goal-as-the-unit measurements. You may NEVER make a predictive or comparative 'what causes goals / what wins' claim from this data alone.**

Gate: STABILITY split-half ≥0.40 AND DISTINCTIVENESS excess ≥1.5 — an axis is a real team-style identity ONLY if it clears BOTH. Full goal corpus (~270 GF/team-season); seed 20260714.

**faceoff-origin now COMPUTED** by combining the goal corpus with pbp faceoffs (not in the tracking json but in stg_play_by_play, per owner): goal within 10 s of the scoring team winning an o-zone faceoff (zone_code relative to winner). League share ~5.7% — rare, so a thin per-team sample (~16 goals/team-season).

## Gate by dimension (FOR side)

| dim | axis | mean | n_ts | split-half r | placebo p | excess | STABLE | DISTINCT | BOTH |
|---|---|---|---|---|---|---|---|---|---|
| ORIGIN | sustained_share | 0.641 | 96 | **0.206** | 0.021 | **1.28** | n | n | — |
| ORIGIN | rebound_share | 0.156 | 96 | **0.132** | 0.0975 | **1.13** | n | n | — |
| ORIGIN | faceoff_origin | 0.057 | 96 | **-0.131** | 0.898 | **1.05** | n | n | — |
| ENTRY | carried_entry | 0.299 | 96 | **0.281** | 0.003 | **1.64** | n | Y | — |
| ENTRY | dumped_entry | 0.063 | 96 | **0.09** | 0.18 | **1.23** | n | n | — |
| ENTRY | passed_entry | 0.042 | 96 | **-0.006** | 0.5165 | **0.98** | n | n | — |
| SHAPE | multipass | 0.613 | 96 | **0.638** | 0.0 | **4.63** | Y | Y | **YES** |
| SHAPE | direct | 0.043 | 96 | **0.522** | 0.0 | **3.86** | Y | Y | **YES** |
| SHAPE | point_involve | 0.12 | 96 | **0.18** | 0.046 | **1.54** | n | Y | — |
| SHAPE | east_west | 0.637 | 96 | **0.099** | 0.163 | **1.32** | n | n | — |
| FINISH | netfront_finish | 0.469 | 96 | **0.278** | 0.005 | **1.73** | n | Y | — |
| FINISH | slot_finish | 0.479 | 96 | **0.246** | 0.011 | **1.48** | n | n | — |
| FINISH | point_finish | 0.017 | 96 | **0.04** | 0.346 | **1.08** | n | n | — |
| FINISH | cross_slot | 0.15 | 96 | **0.324** | 0.002 | **1.82** | n | Y | — |
| FINISH | scorer_hhi | 0.076 | 96 | **0.596** | None | **2.74** | Y | Y | **YES** |
| TEMPO | buildup_speed | 3.296 | 96 | **0.259** | 0.0075 | **3.9** | n | Y | — |
| TEMPO | shot_quickness | 2.926 | 96 | **0.225** | 0.0135 | **3.54** | n | Y | — |

## Phase-3 (def-blame) axes — CARRIED from teamoffense (tracked-5v5, ~120 GF/team-season; thinner, flagged)

| axis | split-half r | excess | BOTH |
|---|---|---|---|
| turnover_created (ORIGIN) | 0.225 | 1.88 | — |
| forecheck_turnover (ORIGIN) | 0.178 | 1.32 | — |
| nz_turnover (ORIGIN) | 0.319 | 1.76 | — |
| oddman_rush (ORIGIN) | 0.086 | 0.98 | — |
| breakaway_rush (ORIGIN) | 0.251 | 1.26 | — |
| inside_lev_exploit (SHAPE) | 0.207 | 2.07 | — |
| blown_switch_exploit (FINISH) | 0.26 | 2.24 | — |

## Synthesis — axes clearing BOTH bars = the real team-offensive-identity dimensions

- **BOTH-bar axes: ['multipass', 'direct', 'scorer_hhi']**
- stable-but-uniform (F30-style): none
- distinctive-but-noisy (thin sample / game-to-game noise): ['carried_entry', 'point_involve', 'netfront_finish', 'cross_slot', 'buildup_speed', 'shot_quickness']

## Three worked team profiles (FOR, 2025-26)

- **COL** (345 GF): multipass 0.74, direct 0.02, netfront_finish 0.44, point_involve 0.15, rebound_share 0.17, buildup_speed 3.84
- **VAN** (221 GF): multipass 0.62, direct 0.06, netfront_finish 0.47, point_involve 0.10, rebound_share 0.15, buildup_speed 3.36
- **DAL** (290 GF): multipass 0.69, direct 0.01, netfront_finish 0.56, point_involve 0.11, rebound_share 0.20, buildup_speed 3.52

## STOP — owner review. Feeds F4 team-style visual. Nothing promoted.
