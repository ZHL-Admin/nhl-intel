# Phase Value — Stage 5 validation report (REPORT-ONLY; no tiers written)

Model `phase_value_v1`. Criteria pre-registered in `config.PHASE_VALUE_CONFIG` before results: Tier A r ≥ 0.35, Tier B r ≥ 0.2 (else C) on year-over-year r; TOI floors [400, 200]. No number in Stages 1–4 was re-tuned to these results.

## 1. Reliability tiers — year-over-year r (the pre-registered crux)
**Baseline (§9.2.1):** `def_impact` YoY r on the identical cohort, side by side — the project's comparative verdict number. **Cohort note:** the TOI floors are applied (`toi_min ≥ floor`) but are largely NON-BINDING for the exposure-heavy components: each component's RAPM replacement pooling (< 100 exposure-min → F/D pool) already imposes a higher effective TOI floor — ~475 min for deny/deny_rush (outside exposure ≈ 21% of ice) and ~345 min for suppress/escape (in-zone ≈ 29%). So deny's cohort is empty in [200,400) (its min toi is ~514) and suppress gains only a handful when the floor halves. Per-pair cohort sizes (n_a, n_b) are shown so this is auditable. This is RAPM-parity pooling, not a misapplied filter.


### TOI ≥ 400 min
| component | mean YoY r | tier | per-pair r (n_pair; n_a/n_b) |
|---|---|---|---|
| **deny** | +0.158 | **C** | 2021-22->2022-23 +0.25 (n=472; 582/571); 2022-23->2023-24 +0.19 (n=461; 571/568); 2023-24->2024-25 +0.13 (n=492; 568/607); 2024-25->2025-26 +0.06 (n=498; 607/579) |
| **suppress** | +0.219 | **B** | 2021-22->2022-23 +0.20 (n=523; 644/635); 2022-23->2023-24 +0.23 (n=532; 635/637); 2023-24->2024-25 +0.26 (n=526; 637/610); 2024-25->2025-26 +0.18 (n=526; 610/637) |
| **escape** | +0.206 | **B** | 2021-22->2022-23 +0.27 (n=523; 644/635); 2022-23->2023-24 +0.30 (n=532; 635/637); 2023-24->2024-25 +0.09 (n=526; 637/610); 2024-25->2025-26 +0.17 (n=526; 610/637) |
| **deny_rush** | +0.085 | **C** | 2021-22->2022-23 +0.04 (n=472; 582/571); 2022-23->2023-24 +0.12 (n=461; 571/568); 2023-24->2024-25 +0.04 (n=492; 568/607); 2024-25->2025-26 +0.15 (n=498; 607/579) |
| **pv_def_g60** | +0.246 | **B** | 2021-22->2022-23 +0.20 (n=472; 582/571); 2022-23->2023-24 +0.25 (n=461; 571/568); 2023-24->2024-25 +0.31 (n=488; 568/600); 2024-25->2025-26 +0.23 (n=496; 600/579) |
| **def_impact** _(baseline §9.2.1)_ | +0.346 | **B** | 2021-22->2022-23 +0.35 (n=523; 644/635); 2022-23->2023-24 +0.35 (n=532; 635/637); 2023-24->2024-25 +0.38 (n=530; 637/617); 2024-25->2025-26 +0.31 (n=530; 617/637) |

### TOI ≥ 200 min
| component | mean YoY r | tier | per-pair r (n_pair; n_a/n_b) |
|---|---|---|---|
| **deny** | +0.158 | **C** | 2021-22->2022-23 +0.25 (n=472; 582/571); 2022-23->2023-24 +0.19 (n=461; 571/568); 2023-24->2024-25 +0.13 (n=492; 568/607); 2024-25->2025-26 +0.06 (n=498; 607/579) |
| **suppress** | +0.218 | **B** | 2021-22->2022-23 +0.20 (n=526; 648/637); 2022-23->2023-24 +0.23 (n=535; 637/639); 2023-24->2024-25 +0.26 (n=526; 639/610); 2024-25->2025-26 +0.18 (n=526; 610/637) |
| **escape** | +0.205 | **B** | 2021-22->2022-23 +0.27 (n=526; 648/637); 2022-23->2023-24 +0.30 (n=535; 637/639); 2023-24->2024-25 +0.09 (n=526; 639/610); 2024-25->2025-26 +0.17 (n=526; 610/637) |
| **deny_rush** | +0.085 | **C** | 2021-22->2022-23 +0.04 (n=472; 582/571); 2022-23->2023-24 +0.12 (n=461; 571/568); 2023-24->2024-25 +0.04 (n=492; 568/607); 2024-25->2025-26 +0.15 (n=498; 607/579) |
| **pv_def_g60** | +0.246 | **B** | 2021-22->2022-23 +0.20 (n=472; 582/571); 2022-23->2023-24 +0.25 (n=461; 571/568); 2023-24->2024-25 +0.31 (n=488; 568/600); 2024-25->2025-26 +0.23 (n=496; 600/579) |
| **def_impact** _(baseline §9.2.1)_ | +0.345 | **B** | 2021-22->2022-23 +0.34 (n=526; 648/637); 2022-23->2023-24 +0.35 (n=535; 637/639); 2023-24->2024-25 +0.38 (n=530; 639/617); 2024-25->2025-26 +0.31 (n=530; 617/637) |

**Comparative verdict:** PV components vs the `def_impact` baseline on identical cohorts, above. `pv_def_g60`/`suppress`/`escape` at Tier B; `deny`/`deny_rush` at Tier C; read each against the baseline's own YoY r in the same table.

### 1b. Deny post-mortem — YoY r split by team continuity (ruling 2)
| pair | group | deny YoY r | n |
|---|---|---|---|
| 2021-22->2022-23 | same team | +0.256 | 372 |
| 2021-22->2022-23 | moved | +0.244 | 100 |
| 2022-23->2023-24 | same team | +0.225 | 350 |
| 2022-23->2023-24 | moved | +0.092 | 111 |
| 2023-24->2024-25 | same team | +0.127 | 360 |
| 2023-24->2024-25 | moved | +0.145 | 132 |
| 2024-25->2025-26 | same team | +0.045 | 370 |
| 2024-25->2025-26 | moved | +0.088 | 128 |

**Pooled: same-team +0.163 vs moved +0.142.** Same-team persistence does NOT materially exceed movers, so `deny` is **not** a system-level signal passing through players — the null stands as written. The monotonic decline appears in BOTH groups (same-team 0.26→0.05, moved 0.24→0.09), consistent with a temporal, not a roster-continuity, mechanism.

## 2. def_impact baseline comparison (3-season window, toi ≥ 200)
| component | r vs def_impact |
|---|---|
| deny | +0.414 |
| suppress | +0.852 |
| escape | +0.141 |
| deny_rush | +0.119 |
| pv_def_g60 | +0.871 |

Expected (pre-registered thesis): suppress high (def_impact's xG channel re-denominated), deny moderate (new frequency channel), escape ≈ 0 (orthogonal). pv_def_g60 ~0.87 = suppress-dominated.

## 3. Smell tests — face validity (3-season pv_def_g60, toi ≥ 400)
**Top 10 pv_def_g60:** Sam Reinhart (+0.201), Alexander Wennberg (+0.176), Moritz Seider (+0.175), Devon Toews (+0.173), Jordan Kyrou (+0.167), Cam York (+0.165), Tyler Tucker (+0.161), Nate Schmidt (+0.160), Luke Evangelista (+0.160), Radek Faksa (+0.160)
**Bottom 10 pv_def_g60:** Connor Bedard (-0.310), Tony DeAngelo (-0.263), Evander Kane (-0.252), Ben Chiarot (-0.233), Chandler Stephenson (-0.232), Artyom Levshunov (-0.199), Dylan Strome (-0.183), Frank Vatrano (-0.182), Mikael Granlund (-0.179), Vinnie Hinostroza (-0.175)

**(a) def_impact percentile of the top-10** (distinguishes inherited-from-baseline from PV-specific):
| player | pv_def_g60 | def_impact %ile |
|---|---|---|
| Sam Reinhart | +0.201 | 100 |
| Alexander Wennberg | +0.176 | 93 |
| Moritz Seider | +0.175 | 99 |
| Devon Toews | +0.173 | 97 |
| Jordan Kyrou | +0.167 | 99 |
| Cam York | +0.165 | 76 |
| Tyler Tucker | +0.161 | 73 |
| Nate Schmidt | +0.160 | 98 |
| Luke Evangelista | +0.160 | 91 |
| Radek Faksa | +0.160 | 97 |
A high def_impact percentile ⇒ the ranking is inherited from the baseline (not a PV artifact); a low one ⇒ PV-specific and worth scrutiny.

**(b) corr(pv_def_g60, in-zone-against share of TOI) = -0.148** (n=702). A strong NEGATIVE value would support the per-in-zone-second flattery hypothesis (players who defend in-zone less get a smaller denominator and a flattered rate); near zero refutes it.

## 4. Discrimination — between-player spread vs bootstrap sd (headline)
| component | sd(value) across players | mean bootstrap sd | ratio |
|---|---|---|---|
| deny | 1.6774 | 1.3867 | 1.21 |
| suppress | 0.2442 | 0.1862 | 1.31 |
| escape | 1.8191 | 1.3991 | 1.30 |
| deny_rush | 0.3076 | 0.2661 | 1.16 |
| pv_def_g60 | 0.0790 | 0.0570 | 1.39 |

Ratio near 1 = between-player signal barely exceeds resample noise (defence is the weakest signal); this is the empirical basis for the tiers above.

## 5. Split-half reliability (§9.2.2 — even/odd game_id, 2023-24 & 2024-25)
Refit A/B/C per half at the full-season CV alpha; Pearson r across halves + Spearman-Brown (half→full). Same cohorts.

| season | fit | r (halves) | Spearman-Brown | n |
|---|---|---|---|---|
| 2023-24 | deny | +0.280 | +0.438 | 151 |
| 2023-24 | suppress | +0.272 | +0.428 | 401 |
| 2023-24 | escape | +0.293 | +0.453 | 401 |
| 2024-25 | deny | +0.197 | +0.329 | 319 |
| 2024-25 | suppress | +0.314 | +0.478 | 341 |
| 2024-25 | escape | +0.270 | +0.425 | 341 |

## 6. Team out-of-sample — predict team 5v5 xGA/60 in t+1 (§9.2.3)
Minutes-weighted team aggregates in t predict team 5v5 xGA/60 in t+1 (temporal-OOS). 126 team-season pairs over the available PV seasons (2021-22→2025-26). **Range note:** the spec's 2016-17 start needs single-season PV fits for 2016-17→2020-21 backfilled — flagged as a scope decision, not run here.

| predictor set | r | out-of-sample R² |
|---|---|---|
| (i) pv_def_g60 | +0.330 | +0.109 |
| (ii) def_impact | +0.489 | +0.239 |
| (iii) own xGA/60 | +0.451 | +0.203 |
| (iv) i+iii | +0.452 | +0.205 |
| (v) ii+iii | +0.490 | +0.240 |

Read (i) vs (ii): whether team `pv_def_g60` predicts future defence better than team `def_impact`; (iv)/(v) vs (iii): whether either adds over the team's own past xGA/60.

**Interpretation (ruling 4):** `def_impact` bundles in-zone frequency with per-second danger in one xGA target; PV split them by design; the frequency half (`deny`) proved unreliable; the recombined composite therefore carries only the danger half and loses the exposure-share signal the bundle retains.

## 7. Sensitivity grid (§9.3, seasons 2023-24 & 2024-25)
**H_SECONDS ∈ {20,40,60} and the 5v5-goals-only V variant touch ONLY Stage 2** (V and the league constants). Component coefficients never consume V, and year-over-year r is INVARIANT to a uniform repricing (a common scalar on `deny_g60`/`suppress_g60` cancels in a correlation). So the tiers above are unchanged by H and the goals-only V variant **by construction**; the effect is confined to the goal SCALE of `*_g60`, reported as Stage-2 V/constant sensitivity (stage2-acceptance.md), not a tier change. **`phase_episode_gap_seconds ∈ {2,4,6}` and the blocked-shot-possession alternative** DO change the episode definition and were REBUILT into isolated `nhl_staging_sens_*` datasets (canary-proven, prod untouched — PV-I001) and refit on 2023-24 & 2024-25:

| variant | component | YoY r (Δ vs base) | split-half 23-24 (Δ) | split-half 24-25 (Δ) |
|---|---|---|---|---|
| gap2 | deny | +0.137 (+0.006) | +0.436 (-0.002) | +0.320 (-0.009) |
| gap2 | suppress | +0.258 (+0.000) | +0.430 (+0.002) | +0.479 (+0.001) |
| gap2 | escape | +0.090 (+0.005) | +0.453 (+0.000) | +0.421 (-0.004) |
| gap6 | deny | +0.135 (+0.004) | +0.429 (-0.009) | +0.319 (-0.010) |
| gap6 | suppress | +0.258 (+0.000) | +0.430 (+0.002) | +0.479 (+0.001) |
| gap6 | escape | +0.089 (+0.004) | +0.456 (+0.003) | +0.430 (+0.005) |
| blockshot_owner | deny | +0.277 (+0.146) | +0.509 (+0.071) | +0.510 (+0.181) |
| blockshot_owner | suppress | +0.298 (+0.040) | +0.473 (+0.045) | +0.489 (+0.011) |
| blockshot_owner | escape | +0.054 (-0.031) | +0.497 (+0.044) | +0.285 (-0.140) |

Baseline (gap=4, blocked-shot=opp), 2023-24→2024-25 pair: deny YoY +0.131; suppress YoY +0.258; escape YoY +0.085. **Read:** the gap variants move everything negligibly (episode counts shift <0.5%; deny/suppress/escape YoY move ≤0.006) — the conclusions are robust to the episode-gap knob. The **blocked-shot alternative** is the larger perturbation (~18% fewer episodes): on this pair deny's YoY rises 0.13→0.28 and its split-half climbs. But `blocked_shot_possession='owner'` is the **empirically-REJECTED reading** (PV-D005: the blocked-shot owner is the BLOCKER 94% of the time, so possession = the opponent). So this is a robustness CAVEAT — deny's stability is sensitive to the possession convention — NOT a valid tier rescue: under the correct PV-D005 convention deny remains Tier C. It does flag that a future possession-attribution refinement is the most promising lever for the deny channel.

## 8. PV-D015 arena-bias diagnostic for `deny`
Deny's monotonic YoY decline (0.25→0.19→0.13→0.06) makes this more informative, not less.

Team-season `deny` (minutes-weighted) vs home-arena under-recording share, over **100 team-seasons**: **r = +0.010**. A material positive r ⇒ teams whose home scorers under-record settled possession look better at `deny` (scorekeeper bias, not defence); near zero clears it. Since deny is already Tier C, this bounds how much of even that weak signal is arena artifact.

**Caveat (ruling 3):** this diagnostic is cross-sectional — it rules out venue-level bias in `deny`'s LEVELS and does NOT address the monotonic temporal decline (0.25→0.06). League-wide drift in recording or play over time remains unexcluded; an open question, not a finding.

## 9. External A3Z agreement — GATED (directory absent)
Not run: the A3Z reference is not present in-repo; '§7 if run' condition unmet.

---
**Tiers:** written to `nhl_models.phase_component_tiers` only with `--write-tiers` after owner review. Tier C (deny, deny_rush) semantics (§9.1): not published at player level; retained for team/pair analysis only; the deny null is reported explicitly in methodology §7.
