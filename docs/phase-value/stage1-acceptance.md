# Phase Value — Stage 1 acceptance report + under-specified-regions

State engine: `int_phase_events`, `int_phase_spells`, `int_zone_episodes` (dbt, `nhl_staging`),
conforming to `tests/phase_value/reference_state_machine.py` (the authority). Built + validated on
2023-24 → 2025-26.

## Hard gates (all PASS)
| gate | result | threshold |
|---|---|---|
| Conservation (5v5 spell-sec vs 5v5 segment-sec) | mean/max \|Δ\| = **0.000%**, 0 games > 1% | ≤ 1% |
| Golden vectors | **10/10** (GV1–GV11 incl. adversarial GV9/GV10) | all pass |
| Unmapped events | **0.0017%** | < 0.5% |
| Goal coverage (in-scope 5v5 universe) | **99.95%** (residual = 8 outside-zone, 0 artifacts) | ≥ 90% |
| dbt↔reference reconciliation | per-event state **0.0000%** (0/22,809), episode count **0.0000%** (6,362=6,362), 75 games | ≤ 0.5% / ≤ 2% |
| schema.yml tests | **18/18** | all pass |

Report-only bands (all in range): episodes/team-game 45.0 (20–55); mean episode duration 17.4 s (6–25);
start_type carry 59% / oz_faceoff 19% / rush 11% / forecheck 11%; end_reason exit 56% / stoppage 33% /
flip 6% / goal 5%; clipped_by_strength 4.7% (< 10%); 5v5 possession shares P_OZ 51.7% / P_NZ 30.1% /
P_OWN_D 18.1% (per-team in-zone-against ≈ 25.8%).

## Bytes scanned: dev builds (actual) and full-scope (dry-run)
Actual dev builds (3 seasons, per `dbt run`): int_phase_events 591 MiB, int_phase_spells 330 MiB,
int_zone_episodes 427 MiB. Full 2015-16+ dry-run (compiled SQL, on-demand ≈ $6.25/TB):

| model | dry-run GB | $ | note |
|---|---|---|---|
| int_phase_events | 0.620 | 0.0039 | scans stg_play_by_play; season filter does not prune bytes |
| int_phase_spells | 0.347 | 0.0022 | scales with full int_phase_events (~×3.7 → still ≪ cap) |
| int_zone_episodes | 0.448 | 0.0028 | joins int_shot_sequence/shot_xg (already full-history) |

Every job is **≪ COST_CAP_USD_PER_JOB ($5.00)**; full backfill ≈ $0.01–0.02. `int_phase_ticks` (Stage 2)
will be dry-run when authored, before build.

## Under-specified regions — boundary conventions now load-bearing
These were under-specified in the build doc and became load-bearing during Stage 1. Each is pinned by an
adversarial golden vector so the convention can't silently drift.

1. **Goal anchoring = boundary convention (a), NOT zone coercion (b).** An attacker goal counts as
   in-zone **only if its recorded `zone_abs` is the defensive zone**; the `(is_live OR goal)` clause
   relaxes ONLY liveness (a goal is DEAD after recording), never the zone. Reference:
   `in_zone: poss==attacker and zone==dz and (live or is_atk_goal)`; SQL: `zone_abs = d_dzone and
   (is_live or spell_has_goal)`. **GV9** (goal from the neutral zone → anchors NO episode either side)
   and **GV10** (bare rush DZ goal → zero-duration episode, end_reason goal) lock (a) vs (b). This is
   why the residual is genuinely outside-zone: 8 goals, all `zone_code` ∈ {N, D}.
2. **Zero-duration point episodes.** A rush/quick-strike goal at a whistle yields start==end. Kept
   (not dropped by a degenerate segment-overlap test); 5v5 tested via events, not span. **Binding for
   Stage 3 (PV-D011):** these contribute an episode start + a goal with ~0 in-zone seconds, so the
   `inzone_sec >= 4` row filter and stint aggregation must not silently drop them — that would delete the
   most dangerous events (the goals) from the `suppress` fit. ~54% of covered goals arrive this way.
3. **5v5 keep rule (PV-D009).** Keep an episode iff any in-zone spell has a 5v5 event; flag clipped when
   the span crosses a strength boundary. This retains 5v5 goals whose sequence STARTED in non-5v5 (a PP
   expiring). Reference and SQL use the identical per-event/per-spell rule → reconciliation 0.0000%.
4. **Goal-coverage scope (PV-D010).** Computed on segment-covered games (the RAPM 5v5 universe).
   `int_phase_events.is_5v5` requires a segment (no situation_code fallback), matching RAPM exactly;
   preseason/no-segment games (where `int_shot_sequence` falls back to situation_code) are out of scope.
5. **Penalty keeps the previous zone.** Penalties carry a `zone_code` ~99% of the time but must not
   update `zone_abs` (spec §5.2 "unchanged"). Caught by reconciliation (0.96% → 0.00%).
6. **Blocked-shot owner = blocking team (PV-D005), with a ~6% owner-inconsistency residual** (5.70%
   zone-'O' rows where the owner is recorded as the shooter; see schema-map.md). Covered by the Stage 5
   blocked-shot possession sensitivity.

## Pre-fix 43.8% → 99.95%, explained
- **43.8% (pre-fix):** only goals that TERMINATED a pre-existing episode were covered — i.e. DZ goals
  with a preceding live in-zone spell.
- **+ ~54% reclaimed by PV-D008** (goal anchors an episode): rush/quick-strike DZ goals with no preceding
  live in-zone event. (43.8% → 98.3%.)
- **+ ~1.7% reclaimed by PV-D009** (any-in-zone-5v5 keep rule): DZ goals in episodes that start in
  non-5v5 and cross into 5v5 (95 goals that the earlier start-event gate dropped). (98.3% → 99.9%.)
- **+ 1 edge reclaimed by `spell_has_goal`** (stoppage-recorded-before-goal at the same instant).
- **Residual 8 goals (0.05%):** genuinely outside-zone (neutral-zone / own-zone long shots) — left
  uncovered by design (convention (a)). Separately, 237 preseason "5v5" goals are out of scope (PV-D010).
