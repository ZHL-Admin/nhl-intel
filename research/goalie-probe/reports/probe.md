# Goalie-probe — reports/probe.md

**Project:** `NIR/research/goalie-probe/` · read-only over production and prior research · own venv · `make g1` reproduces from cache · seed **20260714b**.

> **THE DENOMINATOR IS THE POINT.** Every save-performance figure here is computed over **shots faced** (SOG + goals), never over goals allowed. Stage 1's error — characterizing a goalie from the composition of goals alone — is structurally avoided: the shot spine *is* the denominator. Tracking enrichment (Stage 0) is goals-only and would only DESCRIBE goals; G1 does not use it.


## Step 0 — inventory & fixed decisions

| input | source | note |
|---|---|---|
| shot spine | `stg_play_by_play` (SOG+goals) | full span **2010-11..2025-26** (1,269,140 shots); G1 runs on the tracking window 2023-24, 2024-25, 2025-26 |
| per-shot xG | `deployment-atlas/shot_xg.parquet` | joined on (game_id,event_id); **91.0%** of spine shots have xG |
| strength (ice) | Atlas `stints.parquet` | interval join; fallback situationCode |
| handedness | `stg_player_bio.shoots` | (used in G2 only) |
| tracking enrichment | goal-tracking Stage 0 `fused_goals` | goals-only; **not used in G1** (no denominator) |

**Fixed decisions (before results):**
- **SPINE = unblocked shots ON GOAL = SOG (saves) + goals (scored).** Missed (wide) and blocked are excluded — they are not shots the goalie faced on net. This is the shots-faced denominator.
- **Dropped buckets (flagged, not fabricated):** *rush-vs-in-zone* — pbp carries no zone-entry sequence, so it is not inferable without fabrication (Stage 0's `rush_flag` exists only on goals via tracking, has no save denominator, so it cannot be used here). *one-timer* — not carried by pbp. Both are dropped rather than invented.
- **Kept buckets** (all computable on saves too): `shot_type`, `danger` (xG), `region` (location), `rebound` (derived from the spine: an on-goal shot ≤3 s after a prior on-goal shot by the same team).
- Save-quality = **GSAx/100 shots** = 100·(xGA−GA)/shots, centered on the **league bucket** residual (the Atlas xG model, trained on all Fenwick, under-predicts goals on the on-goal-only subset — league baselines are negative; centering by bucket removes this, making the metric calibration-robust). EB shrinkage toward league by bucket, prior **k=200** pseudo-shots; 90% CIs.

## G1.1 — the shot spine

- **247,350 shots faced** = 221,823 saves + 25,527 goals, over **154 goalies**, 2023-24, 2024-25, 2025-26. Overall save% **0.8968**, mean xG 0.0726.
- **Shots-faced per goalie-season:** median 704, p10 20, p90 1640, max 2225; 226/328 goalie-seasons clear 200 shots.

## G1.2 — buckets (rates with absolute counts)

- **shot_type:** wrist n=124,611 sv=0.913; snap n=51,375 sv=0.876; slap n=26,412 sv=0.920; deflection n=22,794 sv=0.853; backhand n=18,789 sv=0.880; other n=3,369 sv=0.814.
- **danger tier (xG):** low n=113,476 sv=0.966; mid n=79,561 sv=0.855; high n=32,135 sv=0.776.
- **region (distance):** outer_slot n=102,420 sv=0.906; inner_slot n=77,228 sv=0.819; point n=67,465 sv=0.975.
- **rebound:** rebound n=18,051 sv=0.825; non-rebound n=229,299 sv=0.902.

## G1.3 — save-quality by bucket (GSAx/100, EB-shrunk, gated ≥50 shots)

| dimension | bucket | league GSAx/100 | goalies (≥50) | goalie GSAx/100 spread |
|---|---|---|---|---|
| overall | all | -2.77 | 120 | [-3.09, 1.60] |
| shot_bucket | backhand | -1.60 | 79 | [-3.46, 2.21] |
| shot_bucket | deflection | -3.10 | 83 | [-3.30, 3.13] |
| shot_bucket | other | -0.94 | 22 | [-2.05, 2.03] |
| shot_bucket | slap | -3.29 | 83 | [-2.05, 1.73] |
| shot_bucket | snap | -4.23 | 94 | [-2.93, 3.14] |
| shot_bucket | wrist | -2.22 | 108 | [-3.01, 1.46] |
| danger | high | -1.76 | 88 | [-4.31, 4.21] |
| danger | low | -0.94 | 109 | [-1.89, 1.12] |
| danger | mid | -5.79 | 101 | [-3.71, 2.43] |
| region | inner_slot | -3.43 | 100 | [-5.11, 3.00] |
| region | outer_slot | -3.75 | 106 | [-2.73, 2.01] |
| region | point | -0.53 | 98 | [-1.54, 1.04] |
| rebound | non_rebound | -3.21 | 119 | [-3.47, 1.72] |
| rebound | rebound | 3.15 | 80 | [-3.73, 3.77] |

## G1.4 — THE STABILITY GATE (pre-stated: split-half ≥0.30 AND YoY placebo p<0.05)

**Overall (all-shot) GSAx benchmark:** split-half r=**0.44** (p=0.000), YoY r=**0.27** (p=0.002). Goalies genuinely differ in overall stopping (modestly reliable, as in public work). Each bucket is judged against this benchmark.

| dimension | bucket | goalies | split-half r | YoY r | YoY p | PASS | beats overall (0.44)? |
|---|---|---|---|---|---|---|---|
| danger | low | 87 | 0.37 | 0.02 | 0.388 | · | no |
| rebound | non_rebound | 95 | 0.34 | 0.21 | 0.011 | **Y** | no |
| region | inner_slot | 79 | 0.33 | 0.19 | 0.013 | **Y** | no |
| danger | high | 64 | 0.32 | 0.11 | 0.137 | · | no |
| danger | mid | 83 | 0.21 | 0.06 | 0.246 | · | no |
| region | outer_slot | 84 | 0.18 | 0.09 | 0.151 | · | no |
| shot_bucket | slap | 56 | 0.12 | 0.08 | 0.237 | · | no |
| shot_bucket | deflection | 48 | 0.11 | 0.12 | 0.128 | · | no |
| shot_bucket | snap | 71 | 0.10 | 0.05 | 0.271 | · | no |
| shot_bucket | backhand | 41 | 0.09 | 0.19 | 0.063 | · | no |
| shot_bucket | wrist | 88 | 0.05 | -0.00 | 0.478 | · | no |
| rebound | rebound | 36 | 0.04 | 0.18 | 0.081 | · | no |
| region | point | 78 | 0.04 | 0.09 | 0.152 | · | no |

## VERDICT G1

- **No shot-type bucket is stable *beyond* overall GSAx** (overall split-half 0.44; the best bucket is low at 0.37 — below overall). 0 buckets exceed the overall benchmark.
- The 2 buckets that clear the pre-stated bar (**non-rebound**, **inner-slot**) are the overall-stopping signal in disguise: non-rebound shots are ~93% of all shots (≈ overall), and inner-slot is the danger core that dominates overall GSAx. Neither is a distinct specialty.
- **Shot_type specialties (wrist/snap/slap/backhand/deflection) do not persist** (split-half 0.05–0.13); danger-tier and rebound-shot save-quality do not clear both halves of the gate.

### ➡ FINDING (F-number for the owner): **goalies differ in overall stopping, not in identifiable shot-type specialties.** The denominator delivers the clean result Stage 1 could not: a real, modestly-reliable overall save-quality signal, and a null on shot-type specialization.

### Overall GSAx/100 leaders & laggards (pooled 2023-26, ≥50 shots, EB-shrunk)

| | goalie | shots faced | save% | GSAx/100 (EB) | 90% CI |
|---|---|---|---|---|---|
| leader | Dylan Garand | 114 | 0.921 | +1.60 | [+0.24,+2.97] |
| leader | Anthony Stolarz | 2,620 | 0.912 | +1.45 | [+0.67,+2.23] |
| leader | Jacob Fowler | 452 | 0.903 | +1.25 | [-0.18,+2.68] |
| leader | Jet Greaves | 2,287 | 0.910 | +1.23 | [+0.43,+2.04] |
| leader | Connor Hellebuyck | 5,755 | 0.908 | +1.22 | [+0.67,+1.77] |
| leader | Laurent Brossoit | 651 | 0.920 | +1.17 | [-0.02,+2.37] |
| leader | Logan Thompson | 4,586 | 0.909 | +1.09 | [+0.47,+1.71] |
| leader | Igor Shesterkin | 5,430 | 0.909 | +1.05 | [+0.47,+1.62] |
| laggard | Magnus Chrona | 269 | 0.855 | -2.28 | [-3.73,-0.82] |
| laggard | Felix Sandstrom | 96 | 0.823 | -2.30 | [-3.71,-0.90] |
| laggard | Ivan Fedotov | 695 | 0.872 | -2.57 | [-3.73,-1.40] |
| laggard | Aleksei Kolosov | 466 | 0.861 | -2.62 | [-3.96,-1.28] |
| laggard | Mads Sogaard | 261 | 0.828 | -3.09 | [-4.51,-1.67] |

---

# LINK G2 — goalie behavioral habits from tracking (goals + fusion)

> **Framing (fixed):** *rebound-control* is the one axis with a real **save denominator** (from the pbp spine, over saves), so it is foregrounded and given the full stability test. The tracking axes (depth, lateral-recovery, east-west coverage) are **goals-only**; they are reported as positioning **habits**, never as save-skill claims without a denominator.

## G2.1/G2.2 — axes and the stability gate (split-half ≥0.30 AND YoY placebo p<0.05)

| axis | source | goalies | split-half r | YoY r | YoY p | PASS |
|---|---|---|---|---|---|---|
| **rebound_control** | pbp spine / SAVES | 97 | 0.21 | 0.13 | 0.059 | · |
| lateral_recovery | tracking / goals-only | 77 | 0.41 | 0.14 | 0.050 | **Y** |
| ew_coverage | tracking / goals-only | 82 | 0.28 | 0.11 | 0.064 | · |
| unset_rate | tracking / goals-only | 77 | 0.17 | 0.08 | 0.183 | · |
| depth | tracking / goals-only | 77 | 0.08 | -0.02 | 0.585 | · |

- **Rebound-control (denominator-backed) does NOT clear the gate** (split-half 0.21, YoY p=0.059): it is cleanly measurable over saves but only weakly persistent — the axis with the honest denominator is not a strong stable trait.
- **Lateral-recovery (continuous UNSET) is the one axis that clears the gate** (split-half **0.41, p=0.000** — decisive; YoY p=0.050 — a **razor-thin, underpowered pass** with only two season-pairs). The verdict rests on the strong split-half; the YoY only marginally corroborates. It **confirms and strengthens the Stage-1 UNSET r=0.34**, but is **goals-only** — a persistent positioning *habit* (how set / how much he is moving laterally when beaten), not a save-skill claim.
- The binary `unset_rate`, `ew_coverage`, and `depth` do not clear the gate; the continuous lateral-recovery is better-behaved than its binarized UNSET form.

## G2.3 — do the axes relate to save performance (G1 overall GSAx)? (descriptive, no causal claim)

- **Lateral-recovery vs overall GSAx: r = -0.13** (n=77). Only a weak descriptive tie — and it is **goals-only**, so this is not causal (it is the goalie's lateral speed *on the goals he allowed*, confounded with being scored on). The one stable habit barely tracks results.
- **Rebound-control vs overall GSAx: r = 0.01** (n=97). Essentially zero; and the axis is not stable anyway. Rebound-generation-after-saves neither persists as a trait nor relates to overall save quality here.

---

# PROBE VERDICT

**What the denominator (G1) established that Stage 1 could not:**
- Goalies genuinely differ in **overall stopping** — GSAx over shots faced is real and modestly reliable (split-half 0.44, YoY 0.27). *(F22)*
- **No shot-type save specialty persists** beyond overall stopping — wrist/snap/slap/backhand/deflection, danger tiers, region, and rebound-shot save-quality all fail to beat the overall benchmark. Goalies are not identifiable shot-type specialists. *(F22)*

**What the tracking fusion (G2) added — and its limits:**
- **One stable behavioral habit: lateral-recovery / how-set** (split-half 0.41, decisive; YoY only marginal), confirming Stage 1's lone UNSET signal. But it is **goals-only** — a describable positioning *style*, not a denominator-backed skill, and it barely relates to save results (r=−0.13). *(proposed F23)*
- **The one denominator-backed behavioral axis, rebound-control, is NOT a stable trait** (split-half 0.21) and does not relate to GSAx. The hoped-for honest behavioral skill does not materialize. *(proposed F24)*

**What stays goals-only-limited vs what the fusion genuinely unlocked:**
- *Goals-only-limited:* every tracking positioning axis (depth, lateral-recovery, east-west coverage). They describe how a goalie was positioned **on goals against**; with no tracked saves, none can become a save-skill rate. Causality is off the table.
- *Genuinely unlocked:* the fusion **confirmed** lateral-recovery as a persistent habit (beyond a single Stage-1 metric) and lets us **describe** goal anatomy — but the goalie **skill** question is answered by the **denominator** (G1 overall save-quality), not by tracking.

### How to build the F2 goalie visual (given F21, F22, and G2)

- **Build F2 on overall GSAx-over-shots-faced, with 90% CIs** — the one real, reliable, denominator-backed goalie skill. Rank/round leaders and laggards from this (Hellebuyck, Shesterkin, Stolarz, Thompson lead; face-valid).
- **Retire the Stage-1 mechanism-mix framing (F21):** it is goals-only and unstable (single seasons are noise). Do not show a 'shot-type specialty' breakdown (F22): those specialties do not exist.
- **Optionally** annotate a goalie's **lateral-recovery/how-set habit as a descriptive STYLE tag** (labeled goals-only, not a skill, weak tie to results). Do NOT show rebound-control as a skill.

**Recommendation:** this warrants a **descriptive product** — a goalie overall save-quality card (GSAx/shots-faced + CIs, with an optional goals-only style tag) — **not** a 'goalie specialties' project, because the specialties are null. The fusion's value here was **confirmation and description**, not a new skill dimension. Nothing promoted; findings hold their F-numbers.

## STOP — probe complete, gate for owner review.
