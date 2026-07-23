# Phase Value (phase_value_v1) — build spec

> **Provenance note (read first).** The original phase-value handoff document was NOT committed at
> Stage 0 and is not present anywhere on disk (only the unrelated `docs/HANDOFF-1..4-*.md` exist). This
> file is assembled from the spec sections the owner has **quoted verbatim** during stage reviews, plus
> the constants pinned in `models_ml/config.PHASE_VALUE_CONFIG`, so the pre-registered protocols are
> citable in-repo. Sections quoted verbatim are marked as such. If the full handoff is recovered it
> should REPLACE this file verbatim. Anything not quoted here lives in `docs/methodology/phase-value.md`
> and `docs/phase-value/DECISIONS.md`.

## §7.1 — Component targets and weights (two-sided stint design)
Each component is the RAPM two-sided ridge (attacker = `off`, defender = `deff`) reused by import, with
per-fit target/weight:

| fit | target (per 60 of exposure) | weight | exposure floor |
|---|---|---|---|
| `deny` | `episode_starts_nonfo / outside_exposure_sec × 3600` | `outside_exposure_sec` | `≥ MIN_EXPOSURE_SECONDS` |
| `suppress` | `xg_inzone / inzone_sec × 3600` | `inzone_sec` | `≥ MIN_EXPOSURE_SECONDS` |
| `escape` | `favorable_ends / inzone_sec × 3600` | `inzone_sec` | `≥ MIN_EXPOSURE_SECONDS` |
| `deny_rush` (diagnostic) | `episode_starts_rush / outside_exposure_sec × 3600` | `outside_exposure_sec` | `≥ MIN_EXPOSURE_SECONDS` |

## §7.2 — Publication sign
Components are defence-side, higher = better; the defence coefficient is sign-flipped at publication so
higher = better. *(Ratified deviation PV-D017: the blanket flip assumes suppression targets; `escape` is
a production target, so honouring §7.2's intent requires `+def_c`, not `−def_c`.)*

## §8.1 — Goals accounting (owner-quoted, verbatim)
> deny_g60 = a * (s_out/60) * C_seq * cal; suppress_g60 = b * (s_in/60) * cal; escape published as rate
> only; pv_def_g60 = deny + suppress; composite sd from within-resample composites, not quadrature.

(a = `deny` coef, b = `suppress` coef, cal = `xg_calibration`, C_seq = `c_seq_xg_nonfo`, s_out/s_in =
`s_out_min_per_60`/`s_in_min_per_60`; all from `nhl_models.phase_league_constants`.)

## §9.1 — Reliability tiers (thresholds from config; Tier C semantics owner-quoted verbatim)
Tiers on **year-over-year r**: Tier A `r ≥ RELIABILITY_TIER_A` (0.35), Tier B `r ≥ RELIABILITY_TIER_B`
(0.20), else Tier C. Evaluated per component at each `VALIDATION_MIN_TOI` floor (`[400, 200]`).
Tier C, verbatim:
> not published at player level; retained for team/pair analysis only; the methodology doc reports the
> null result explicitly.

## §9.2.1 — Baseline (owner-quoted, verbatim)
> Baseline: identical computation on player_impact.def_impact singles for the identical cohort (no refit
> needed; the table exists). Report PV components and baseline side by side.

## §9.2.2 — Split-half reliability (owner-quoted, verbatim)
> within seasons 2023-24 and 2024-25, split games by even/odd game_id, refit A/B/C per half (no
> bootstrap), correlate player coefficients across halves (same cohorts).

> **ERRATA (owner-confirmed).** §9.2.3's "from 2016-17 onward" contradicts §7.2, whose single-season
> windows begin **2021-22**. This is an owner authorship inconsistency, not a build error. The accepted
> range is **2021-22 as run** (four YoY pairs / 126 team-season pairs); extending team-OOS back to
> 2016-17 would require backfilling single-season PV fits for 2016-17→2020-21 (flagged, not run).

## §9.2.3 — Team out-of-sample (owner-quoted, verbatim)
> for season pairs (t, t+1) from 2016-17 onward: predict team 5v5 on-ice xGA/60 in t+1 from (i)
> minutes-weighted team aggregate of pv_def_g60 in t, (ii) minutes-weighted def_impact aggregate in t,
> (iii) the team's own xGA/60 in t, and (iv) combinations (i)+(iii) and (ii)+(iii). Report r and
> out-of-sample R^2 per predictor set.

## §9.3 — Sensitivity grid (owner-quoted, verbatim)
> seasons 2023-24 and 2024-25 only; H_SECONDS in {20,40,60}; phase_episode_gap_seconds in {2,4,6} (dbt
> rebuild, two seasons); blocked-shot possession alternative (dbt rebuild, two seasons); 5v5-goals-only V
> variant.

Propagation note (owner): H and the 5v5-goals variant touch ONLY Stage 2 (V and constants; component
coefficients never consume V, and YoY r is invariant to uniform repricing), so report those as
V/constant sensitivity. The gap and blocked-shot cells rebuild the two seasons and refit; report
component YoY/split-half movement on those two cells only.

## Pre-registered config constants (`models_ml/config.PHASE_VALUE_CONFIG`)
`H_SECONDS=40`, `H_SENSITIVITY=[20,40,60]`, `TICK_SECONDS=5`, `MIN_EXPOSURE_SECONDS=5`,
`BOOTSTRAP_N_WINDOW=100`, `BOOTSTRAP_N_SINGLE=40`, `RELIABILITY_TIER_A=0.35`, `RELIABILITY_TIER_B=0.20`,
`VALIDATION_MIN_TOI=[400,200]`, `GOAL_COVERAGE_GATE=0.90`, `UNMAPPED_EVENT_GATE=0.005`,
`RECONCILE_EVENT_GATE=0.005`, `RECONCILE_EPISODE_GATE=0.02`, `XG_CAL_TOLERANCE=0.03`,
`COST_CAP_USD_PER_JOB=5.00`, `SEED=42`.
