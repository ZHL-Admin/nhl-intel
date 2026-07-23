# Phase Value — incidents

## PV-I001 | 2026-07-23 | Sensitivity build overwrote production `int_phase_*` (schema-isolation failure)

**Summary.** A §9.3 sensitivity build intended to write a gap=2 variant into a separate `nhl_staging_sens`
dataset instead overwrote the production `int_phase_events` / `int_phase_spells` / `int_zone_episodes`
tables in `nhl_staging`, truncating them from full history (2015-16→2025-26, gap=4) to two seasons
(2023-24→2024-25, gap=2).

**Root cause.** The `intermediate` models carry a hardcoded `+schema: staging` in `dbt_project.yml`.
`macros/generate_schema_name.sql` returns `nhl_<custom_schema_name>` whenever a custom schema is set —
i.e. **`nhl_staging` regardless of `--target`**. The dedicated `sens` target (dataset
`nhl_staging_sens`) and `--defer` were therefore silently ignored; every model resolved to `nhl_staging`
and the `dbt run` overwrote production. The run log even printed `OK created ... nhl_staging.int_phase_*`,
which was the signal — caught only after the write, not before.

**Blast radius.**
- Damaged: the three `int_phase_*` intermediate tables (later also `int_phase_ticks`, rebuilt during
  restore to remove any staleness question).
- NOT damaged: all materialized outputs, which do not re-read these tables — `nhl_models.player_phase_value`,
  `phase_component_tiers`, `state_values`, `phase_league_constants`, and the validation report / methodology
  / DECISIONS. `nhl_staging_sens` was never created.
- Restore: `dbt run --select int_phase_events int_phase_spells int_zone_episodes int_phase_ticks --target dev`
  at default vars (gap=4, `blocked_shot_possession='opp'`, `phase_dev_seasons=[]`), proven by row counts +
  Stage-1 hard gates + `stage1_reconcile` + a `state_values` spot-check (see the restore-proof log).

**What held.** (1) The shipped outputs were already materialized, so no player-facing number changed.
(2) The Claude Code auto-classifier blocked the *restore* write as a production modification, forcing an
explicit stop-and-ask. (3) The build was staged on a branch with everything else committed, so state was
recoverable and auditable.

**Corrective rule — STANDING PROTOCOL (canary-before-isolated-write).**
> No run intended to write anywhere other than its usual production destination executes without a canary
> proof first. The canary builds exactly ONE model through the isolation mechanism, then queries
> `INFORMATION_SCHEMA` in BOTH datasets to confirm: the intended (e.g. sens) dataset GAINED the table, and
> `nhl_staging` gained nothing and lost nothing (row counts unchanged on every production table the run
> touches). Only after that proof passes does the full variant build run. If the canary cannot prove
> isolation cleanly, STOP — do not iterate against production.

**Note on the approval chain.** The original guardrail ("dedicated target writing ONLY to
`nhl_staging_sens`; production refs read-only") was stated as an intended OUTCOME, not a VERIFIED
precondition — so it did not prevent the write. This rule converts the guarantee from an assertion into a
checked precondition (the canary), which is the actual fix.
