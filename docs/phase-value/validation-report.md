# Phase Value — Stage 5 validation report (REPORT-ONLY; no tiers written)

Model `phase_value_v1`. Criteria pre-registered in `config.PHASE_VALUE_CONFIG` before results: Tier A r ≥ 0.35, Tier B r ≥ 0.2 (else C) on year-over-year r; TOI floors [400, 200]. No number in Stages 1–4 was re-tuned to these results.

## 1. Reliability tiers — year-over-year r (the pre-registered crux)

### TOI ≥ 400 min
| component | mean YoY r | tier | per-pair r (n) |
|---|---|---|---|
| **deny** | +0.158 | **C** | 2021-22->2022-23 +0.25 (n=472); 2022-23->2023-24 +0.19 (n=461); 2023-24->2024-25 +0.13 (n=492); 2024-25->2025-26 +0.06 (n=498) |
| **suppress** | +0.219 | **B** | 2021-22->2022-23 +0.20 (n=523); 2022-23->2023-24 +0.23 (n=532); 2023-24->2024-25 +0.26 (n=526); 2024-25->2025-26 +0.18 (n=526) |
| **escape** | +0.206 | **B** | 2021-22->2022-23 +0.27 (n=523); 2022-23->2023-24 +0.30 (n=532); 2023-24->2024-25 +0.09 (n=526); 2024-25->2025-26 +0.17 (n=526) |
| **deny_rush** | +0.085 | **C** | 2021-22->2022-23 +0.04 (n=472); 2022-23->2023-24 +0.12 (n=461); 2023-24->2024-25 +0.04 (n=492); 2024-25->2025-26 +0.15 (n=498) |
| **pv_def_g60** | +0.246 | **B** | 2021-22->2022-23 +0.20 (n=472); 2022-23->2023-24 +0.25 (n=461); 2023-24->2024-25 +0.31 (n=488); 2024-25->2025-26 +0.23 (n=496) |

### TOI ≥ 200 min
| component | mean YoY r | tier | per-pair r (n) |
|---|---|---|---|
| **deny** | +0.158 | **C** | 2021-22->2022-23 +0.25 (n=472); 2022-23->2023-24 +0.19 (n=461); 2023-24->2024-25 +0.13 (n=492); 2024-25->2025-26 +0.06 (n=498) |
| **suppress** | +0.218 | **B** | 2021-22->2022-23 +0.20 (n=526); 2022-23->2023-24 +0.23 (n=535); 2023-24->2024-25 +0.26 (n=526); 2024-25->2025-26 +0.18 (n=526) |
| **escape** | +0.205 | **B** | 2021-22->2022-23 +0.27 (n=526); 2022-23->2023-24 +0.30 (n=535); 2023-24->2024-25 +0.09 (n=526); 2024-25->2025-26 +0.17 (n=526) |
| **deny_rush** | +0.085 | **C** | 2021-22->2022-23 +0.04 (n=472); 2022-23->2023-24 +0.12 (n=461); 2023-24->2024-25 +0.04 (n=492); 2024-25->2025-26 +0.15 (n=498) |
| **pv_def_g60** | +0.246 | **B** | 2021-22->2022-23 +0.20 (n=472); 2022-23->2023-24 +0.25 (n=461); 2023-24->2024-25 +0.31 (n=488); 2024-25->2025-26 +0.23 (n=496) |

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

## 4. Discrimination — between-player spread vs bootstrap sd (headline)
| component | sd(value) across players | mean bootstrap sd | ratio |
|---|---|---|---|
| deny | 1.6774 | 1.3867 | 1.21 |
| suppress | 0.2442 | 0.1862 | 1.31 |
| escape | 1.8191 | 1.3991 | 1.30 |
| deny_rush | 0.3076 | 0.2661 | 1.16 |
| pv_def_g60 | 0.0790 | 0.0570 | 1.39 |

Ratio near 1 = between-player signal barely exceeds resample noise (defence is the weakest signal); this is the empirical basis for the tiers above.

## 5. PV-D015 arena-bias diagnostic for `deny`
Deferred: the arena under-recording rate lives only inside the sprite-audit run (E3b), not a persisted table. Activating this pre-registered diagnostic needs the sprite audit to export its per-arena `established_full_window` share; flagged rather than approximated. deny team-season sample available: 889 players across 5 seasons.
## 6. PENDING (protocol not pinned verbatim in-repo — flagged, not invented)
- **Split-half reliability:** needs a within-season odd/even refit pass (extra fits); method not pinned verbatim. Awaiting owner confirmation of the split (odd/even game vs random-half) before running.
- **Team out-of-sample:** predict-team-season-from-held-out-seasons protocol not pinned verbatim.
- **Sensitivity grid:** `H_SENSITIVITY` = [20,40,60] is a STATE-VALUE horizon sweep (Stage 2); its propagation into the component fits is not pinned. Held for owner direction.
- **External A3Z agreement:** 'if run' in §7; not run this pass.

**Tiers are NOT written to `player_phase_value` in this run.** Rerun with `--write-tiers` only after owner review of this report.
