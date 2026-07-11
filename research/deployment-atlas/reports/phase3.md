# Phase 3 — xG: audit, validate, adopt

**Path: ADOPT `nhl_models.shot_xg` (xg_v1).** It passes coverage (99.99%) and
quality (AUC ≥ 0.72 including a fully leakage-clean refit and the true holdout),
with sane calibration. No v0 built (rule 7b).

Evidence: `reports/phase3_analysis.json`, `reports/xg_refit_leakage_clean.json`,
`reports/figures/xg_calibration.png`.

---

## 3.1 Audit of `score_xg.py` / `shot_xg`

**Model:** LightGBM binary classifier, one row per unblocked non-EN non-SO shot;
per-shot additive decomposition. Artifact `xg_v1` (2026-06-15).

**Features** (`xg_features.py`), grouped:
- **location:** `distance`, `angle` — pure geometry, normalized to the `|x|=89` goal line (`distance=√((89−|x|)²+y²)`, `angle=atan2(|y|, 89−|x|)`).
- **shot_type:** wrist/slap/snap/backhand/tip-in/deflected/wrap-around/other.
- **strength:** 5v5/PP/SH/other — **derived from `situation_code`** (see contamination).
- **sequence:** rebound, rush, forecheck, cross-ice, time-since-faceoff, time-since-turnover.
- **game_state:** period, shooter-is-home, score_diff (running pre-shot pbp score, clipped ±3).

**Training window (precise — matters for Phase 5 leakage):**
- **train: 2010-11 … 2023-24** (inclusive; ~1.14M–1.6M shots)
- **val (tuned, early-stop): 2024-25**
- **holdout (reported only): 2025-26**

**Exclusions (verified empirically against pbp):**
- **Shootout: 0 SO rows in `shot_xg`** ✓ (`period_type != 'SO'`).
- **Empty net: imperfect.** shot_xg excludes EN via `situation_code`, but **1,867
  scored rows have `goalieInNetId` null** (a pulled goalie per pbp details) —
  0.1% of shots where situationCode disagrees with `goalieInNetId`. The Atlas uses
  the ice for EN exclusion, so these fall into the reclassified set (§3.4).

**Coordinate normalization:** shots mirrored to a single attacking net at `|x|=89`;
distance + absolute angle from goal centre. Pure geometry — no on-ice dependence.

**Contamination-inheritance determination (the Phase 2 question):**
- ✅ **No inheritance of the stale/dup-contaminated segment backbone.** `int_shot_sequence`
  (shot_xg's basis) references **no** `int_shift_segments` / `int_segment_context` /
  `int_on_ice_events` (grep-verified). No feature derives from segments or on-ice state.
- ⚠️ **`strength` and `is_empty_net` derive from `situationCode`** — so shot_xg
  inherits situationCode's ~4%-of-event-seconds timing lag in those two inputs.
  Immaterial to geometry; handled by the Atlas re-classifying strength to the ice (§3.4).

### Coverage — scored rows vs Atlas xG-eligible attempts

Atlas xG-eligible = reg-season unblocked (SOG/goal/missed), non-SO, goalie in net, has coords.

| season | eligible | scored | coverage | | season | eligible | scored | coverage |
|---|---|---|---|---|---|---|---|---|
| 2010-11 | 103,281 | 103,264 | 99.98% | | 2018-19 | 109,581 | 109,580 | 100.0% |
| 2011-12 | 101,292 | 101,291 | 100.0% | | 2019-20 | 92,593 | 92,559 | 99.96% |
| 2012-13 | 58,211 | 58,211 | 100.0% | | 2020-21 | 70,888 | 70,888 | 100.0% |
| 2013-14 | 102,278 | 102,277 | 100.0% | | 2021-22 | 112,561 | 112,561 | 100.0% |
| 2014-15 | 101,662 | 101,661 | 100.0% | | 2022-23 | 113,353 | 113,351 | 100.0% |
| 2015-16 | 101,090 | 101,089 | 100.0% | | 2023-24 | 114,059 | 113,971 | 99.92% |
| 2016-17 | 102,891 | 102,890 | 100.0% | | 2024-25 | 111,304 | 111,228 | 99.93% |
| 2017-18 | 111,723 | 111,723 | 100.0% | | 2025-26 | 111,099 | 111,099 | 100.0% |

- **Overall 99.99%** (223 of 1,617,866 uncovered — the EN-classification boundary).
- **Backfilled 563 games: 100.0%** (47,754 eligible all scored) — shot_xg did not
  inherit the shift gap (pbp existed for those games).
- **2024-26: 99.97%.** `shot_xg` is current, not stale (unlike the segment backbone).

## 3.2 Validation (AUC + calibration, 2022-23 → 2025-26)

Production AUC — **but 2022-23/2023-24 are in the training window**, 2024-25 is
tuned-on, only 2025-26 is a true holdout:

| season | production AUC | in-sample? |
|---|---|---|
| 2022-23 | 0.7514 | **train (in-sample)** |
| 2023-24 | 0.7561 | **train (in-sample)** |
| 2024-25 | 0.7451 | val (tuned) |
| 2025-26 | **0.7328** | **holdout (clean)** |

**Leakage-clean refit** (`xg_refit.py`, same pipeline, train ≤ 2020-21, early-stop
2021-22, so all of 2022-25 is out-of-sample):

| season | leakage-clean AUC |
|---|---|
| 2022-23 | 0.7468 |
| 2023-24 | 0.7454 |
| 2024-25 | 0.7362 |
| 2025-26 | **0.7251** |

Production is only ~0.01 optimistic vs the clean refit — minimal overfit. **Every
number ≥ 0.72**, including the fully out-of-sample 2025-26. Calibration
(`reports/figures/xg_calibration.png`, 10 quantile bins, 2022-25) is sane:
per-season mean xG ≈ actual goal rate; mild over-prediction only in the top bin
(0.214 pred vs 0.180 actual). **Meets the AUC ≥ 0.72 + sane-calibration bar → ADOPT.**

## 3.3 xG v0 — not built

Coverage and quality both pass; per rule 7b no fallback model was built.

## 3.4 Stint xG, strength reclassification, per-player rates

- **Stint xGF/xGA filled** from `shot_xg` (attributed via the `(start, end]`
  convention). 105,708 total xG attributed across reg-season stints.
- **Strength reclassification: 8,624 shots (0.53%)** change 5v5 status when using
  **shift-derived (ice) strength** instead of `situationCode` — 3,288 the ice calls
  5v5 that situationCode doesn't, 5,336 the reverse. Per the standing ruling,
  **strength for all Atlas uses comes from the ice**, never situationCode, regardless
  of what shot_xg used internally. (0.53% on shots vs ~4% of event-seconds — shots
  are rare at strength transitions.)
- **Per-player 5v5 on-ice rates:** `player_5v5.parquet` — TOI, xGF/60, xGA/60,
  xG-share, CF/60, CA/60, GF/60, GA/60 per (player, season); **10,959 player-seasons**
  meet the 200-minute minimum. 5v5 = 5 skaters + goalie each side from the ice,
  excluding the 753 quarantined stints.

### 3-game reconciliation
The 3 games in the shifts corpus lacking BigQuery pbp are **`2013021108`,
`2023020651`, `2024020147`**. The two Phase-1-fetched games (`2023020651`,
`2024020147`) **have their events present in the Atlas events table** ✓ (gap-fetch
worked). The **third game is `2013021108`** — a 2013-14 game whose pbp is absent
from `raw_play_by_play` (pre-2015, outside Phase 1.2's 2015+ missing-pbp check).
All 3 lack stints (no home/away meta) — 0.016% of games; **documented and added to
the upstream-fixes ledger** (fetch `2013021108` pbp; build stints for the 2 fetched
games from their cached pbp). Not fixed now.

## Top 20 skaters — 2024-25, 5v5 xGF/60 (min 500 min)

| # | player | TOI (min) | xGF/60 | xGA/60 | xG% | CF/60 | GF/60 |
|---|---|---|---|---|---|---|---|
| 1 | Connor McDavid | 1152 | 3.71 | 2.39 | .608 | 72.3 | 3.54 |
| 2 | Zach Hyman | 1079 | 3.60 | 2.33 | .607 | 71.5 | 3.39 |
| 3 | Leon Draisaitl | 1180 | 3.59 | 2.40 | .599 | 71.6 | 3.30 |
| 4 | Nathan MacKinnon | 1349 | 3.52 | 2.50 | .585 | 73.6 | 3.07 |
| 5 | Mattias Ekholm | 1170 | 3.41 | 2.33 | .594 | 71.0 | 2.82 |
| 6 | Matthew Tkachuk | 715 | 3.35 | 2.42 | .580 | 71.0 | 3.19 |
| 7 | Evan Bouchard | 1523 | 3.33 | 2.37 | .584 | 71.2 | 2.80 |
| 8 | Sebastian Aho | 1075 | 3.33 | 2.46 | .575 | 74.7 | 2.85 |
| 9 | Shayne Gostisbehere | 994 | 3.28 | 2.25 | .593 | 71.8 | 2.65 |
| 10 | Barrett Hayton | 1028 | 3.27 | 2.32 | .585 | 70.3 | 2.28 |
| 11 | Artturi Lehkonen | 1098 | 3.25 | 2.54 | .561 | 68.0 | 3.50 |
| 12 | Connor McMichael | 1113 | 3.21 | 2.76 | .537 | 62.4 | 3.56 |
| 13 | Seth Jarvis | 957 | 3.21 | 2.09 | .605 | 71.8 | 2.63 |
| 14 | Sean Monahan | 743 | 3.19 | 2.53 | .558 | 69.2 | 4.28 |
| 15 | Martin Necas | 1112 | 3.18 | 2.55 | .555 | 69.6 | 2.97 |
| 16 | Anthony Cirelli | 1136 | 3.17 | 2.14 | .596 | 66.1 | 3.12 |
| 17 | Sidney Crosby | 1273 | 3.16 | 2.91 | .520 | 66.8 | 3.44 |
| 18 | Jackson Blake | 914 | 3.14 | 2.00 | .612 | 70.6 | 2.49 |
| 19 | Cale Makar | 1456 | 3.14 | 2.40 | .567 | 68.9 | 3.01 |
| 20 | Auston Matthews | 954 | 3.14 | 2.55 | .552 | 63.1 | 3.21 |

Face-valid: elite drivers on top, with the Oilers / Avalanche / Hurricanes clusters
exactly where expected.

---

## Summary

- **ADOPT `shot_xg`** — coverage 99.99% (100% on backfilled games), AUC ≥ 0.72
  production and leakage-clean, sane calibration. No v0.
- **Training window:** train ≤ 2023-24, val 2024-25, holdout 2025-26 (recorded for
  Phase 5 leakage accounting).
- **Contamination:** no segment/on-ice inheritance; `strength`+`is_empty_net` use
  `situationCode` — Atlas re-classifies strength to the ice (8,624 shots, 0.53%).
- **3-game reconciliation:** third game `2013021108` (pre-2015, missing BQ pbp) →
  upstream ledger.

**Phase 3 complete. Stopping per the preamble; awaiting Phase 4 (rule-7b-revised).**
