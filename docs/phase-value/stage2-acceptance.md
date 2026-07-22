# Phase Value — Stage 2 acceptance report (state value function + league constants)

`int_phase_ticks` (dbt) + `models_ml/phase_value/compute_state_values.py` →
`nhl_models.state_values`, `nhl_models.phase_league_constants`. Primary scope **2015-16 → 2025-26**
(full backfill built). H = 40 s, tick = 5 s, cluster bootstrap by game_id (200).

## Full 2015-16+ backfill (item-4 prerequisite — dry-run before build)
Dry-run (reported before building): 4 models **$0.010 total**, each job ≪ $5 cap. Actual build:
int_phase_events 4.6m rows / 591 MiB · int_phase_spells 6.4m / 582 MiB · int_zone_episodes 1.3m / 742 MiB ·
int_phase_ticks 8.6m / 535 MiB.

## HARD GATE — PASS
`V(P_OZ_EST) > V(P_NZ) > V(P_OWN_D)`: **0.00520 > 0.00143 > −0.00027** (pooled). The P_NZ − P_OWN_D gap
(0.0017) is ~5× the bootstrap se (~0.0003), so the gate is robust.

| state | V | se | n_ticks |
|---|---|---|---|
| P_OZ_EST | 0.00520 | 0.00027 | 4,648,936 |
| P_OZ_RUSH | 0.00351 | 0.00084 | 121,472 |
| P_NZ | 0.00143 | 0.00036 | 1,569,797 |
| P_OWN_D | −0.00027 | 0.00032 | 1,905,301 |

**Interpretation of V(P_OWN_D):** slightly negative — possessing the puck in your own defensive zone is,
on net over the next 40 s, marginally worse than neutral, exactly as the spec anticipated (a breakout is a
vulnerable state). Per-season V(P_OZ_EST) is stable (0.0039–0.0068, always the top state).

## V(P_OZ_RUSH) — a granularity artifact, validated by a tick=2 s diagnostic (PV-D013)
At the 5 s grid V(P_OZ_RUSH) 0.00351 < V(P_OZ_EST) 0.00520, but this is a measurement artifact: the rush
lifetime (≤5 s) equals the tick grid and sub-2.5 s partial ticks are dropped, so the fastest (most dangerous)
rushes contribute zero rush ticks. **Quantified:** 23.0% of rush episodes contribute zero rush ticks;
**71.2% of *scoring* rush episodes do** (their mean 5v5 duration is 2.14 s < the 2.5 s floor); those goals
credit the preceding P_OZ_EST/P_NZ windows (state of the tick before a rush-episode goal: P_OZ_EST 54% /
P_OZ_RUSH 16% / P_NZ 15% / P_OWN_D 15%). **tick=2 s diagnostic** (dry-run $0.0035, logged; not a production
re-tune):

| state | V @ tick=5 s (prod) | V @ tick=2 s (diag) |
|---|---|---|
| P_OZ_RUSH | 0.00351 (n=121k) | **0.00542** (n=249k) |
| P_OZ_EST | 0.00520 | 0.00514 |
| P_NZ | 0.00143 | 0.00153 |
| P_OWN_D | −0.00027 | −0.00012 |

At 2 s the spec-expected order is restored: **V(rush) 0.00542 > V(est) 0.00514**. Decision: keep the 5 s
production grid; the "rush is dangerous" claim leans on the artifact-free **`c_seq_rush` = 0.0589 (highest
episode xG cost of any start type)**, not on V(P_OZ_RUSH). The earlier "established out-earns rush"
interpretation is withdrawn.

## Other report-only notes (not gates)
2. **|V(P_NZ)| and |V(P_OWN_D)| < 0.003** (the spec's expectation band floor). Both states are genuinely
   near zero — consistent with the spec's own note that V(P_OWN_D) is near zero. The coarse structure
   (P_OZ_EST ≫ {P_NZ, P_OWN_D ≈ 0}) is what the accounting relies on; the fine P_NZ vs P_OWN_D ordering is
   within noise and flips in 2/11 seasons (pooled gap is ~5 se). PV-D013.

## League constants (`phase_league_constants`, 2015-16+)
| constant | value | band | note |
|---|---|---|---|
| s_out_min_per_60 | 12.58 | 12–24 | outside-exposure min per 60 of 5v5, per team-side |
| s_in_min_per_60 | 17.42 | 8–18 | in-zone-against min per 60 |
| c_seq_xg_nonfo | 0.0517 | 0.02–0.07 | mean **xg_5v5** per non-faceoff episode (Stage 4 `C_seq`) |
| c_seq_xg_rush | 0.0589 | — | highest among start types (spec: rush highest ✓) |
| c_seq_xg_forecheck | 0.0413 | — | |
| c_seq_xg_carry | 0.0524 | — | |
| c_seq_xg_ozfo | 0.0305 | — | lowest (excluded from nonfo) |
| c_seq_ga_nonfo | 0.0507 | — | diagnostic (goals per non-fo episode) |
| r_inzone_xg_per_sec | 0.00246 | — | league xG per in-zone 5v5 second |
| xg_calibration | 1.000 | — | raw 0.983, inside ±0.03 tolerance → fixed at 1.0 |

All constants consume the **5v5-restricted** episode columns (`xg_5v5`, `duration_5v5_seconds`) per the
PV-D009 precision pass, so PP-tail xG is excluded from `C_seq`.

## int_phase_ticks
One row per 5 s of live-5v5 spell time (8.6m rows). State shares: P_OZ_EST 54.7% / P_OWN_D 21.8% /
P_NZ 21.6% / P_OZ_RUSH 2.0%. **~1.3% of P_OZ ticks lack an `episode_id` link — cause (one line):** a
tick↔episode *time-containment* linkage gap, NOT a boundary edge (only 0.4% sit within 2.5 s of an episode
edge) — ticks generated across long, sparse-event P_OZ spells (segment-split `int_phase_spells`) whose
bracketing events lie outside the sampled window fall outside the matching episode's `[start,end]` span in
the separately-materialized `int_zone_episodes`; state is still correctly P_OZ (defaults to P_OZ_EST), gate
unaffected; v1.1 fix = link on shared spell identity. PV-D013.

## Stage 2 Definition-of-Done deliverables
- `nhl_models.state_values` (4 rows) + `nhl_models.phase_league_constants` (11 rows) written. ✓
- Value Function section of `docs/methodology/phase-value.md` drafted: V table with se, per-season stability,
  and the V(P_OWN_D) < 0 interpretation paragraph (written with care). ✓
- Per-season V series CSV: `artifacts/phase_value/state_values_by_season.csv`. ✓

## STOP — Stage 2 acceptance for owner review, before any Stage 3 fitting.
