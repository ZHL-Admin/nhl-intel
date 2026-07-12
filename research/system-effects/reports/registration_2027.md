# Prospective registration — 2026-27 movers (internal track only)

**Registered:** 2026-07-11 · **Seed:** 20260711 · **Status:** predictors frozen; outcomes pending.

This is a pre-registration: the cohort definition, predictors, target, metric, primary decision
rule, and secondary subgroups are **fixed now, before any 2026-27 outcome data exists**. It
mirrors the retrospective Phase 5A test as a genuine out-of-sample confirmation. Only the
INTERNAL/deployment track is registered (the opponent style-matchup track was killed — F15).

## Free-agency timing (why only predictors freeze now)
The 2026-27 free-agency market is **in progress**. The mover cohort therefore **resolves
naturally at season start** (who changed teams over summer 2026). We freeze only the **predictor
inputs** now — each candidate player's **2025-26** values — so they cannot be revised once
destinations and outcomes are known. Frozen table:
`data/parquet/prospective_2027/frozen_predictors.parquet` (719 players: 469 F, 250 D; 245 in the
high-TOI tier), columns: `player_id, q (2025-26 variant RAPM off+def), type_id (2025-26), pg,
toi_5v5_min, xg_share_2025_26, high_toi_tier`. The frozen challenger-model coefficients are
`data/parquet/portability_model.json` (Design B fit through 2025-26; 2026-27+ outcomes are not in
its training, so application is leakage-clean).

## Cohort (resolves at 2026-27 season start)
Players in the frozen table who change teams between 2025-26 and 2026-27 and reach the minutes
floor. Stayers (same team) are the pre-specified population contrast.

## Target
Mean of 2026-27 (S+1) and 2027-28 (S+2) 5v5 on-ice xG share, 400+ prorated 5v5 min in both;
S+1-only players form the reported subgroup. (Identical to 5A.)

## Predictors (nested)
- **(i) incumbent:** variant RAPM alone, calibrated to the task (`target ~ q`).
- **(ii) challenger:** variant + destination season-start-regime deployment + type×deployment
  (`target ~ q + sys`), `sys` from the frozen Design B model, destination = the coach behind the
  2026-27 bench at game 1, role = the player's 2025-26 type.

## Metric and PRIMARY decision rule (fixed)
MAE, incumbent vs challenger. **SHIP the internal claim iff (ii) improves MAE over (i) by ≥ 3%
with a bootstrap CI excluding zero; INVESTIGATE at 0–3% or CI spanning zero; KILL if ≤ 0.**
(Same 3% bar as 5A.) Spearman reported alongside.

## Pre-specified SECONDARY subgroups (secondary claims only)
Mirroring the retrospective concentration (5A slices, logged): **(a) defensemen**, **(b) the
high-TOI tier** (`high_toi_tier` = top third of 2025-26 5v5 TOI, frozen). These are secondary —
they may support or contextualize but cannot by themselves ship the primary claim.

## Amendment discipline
Amendments are allowed **only before 2026-27 outcome data exists**, and each must be recorded here
with a date and rationale. After outcomes exist, nothing changes.

### Amendment log
- *(none yet)*
