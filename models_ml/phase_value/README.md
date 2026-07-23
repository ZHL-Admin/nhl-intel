# phase_value — Phase Value (phase_value_v1)

Transition-based DEFENSIVE value. Companion to RAPM `def_impact` (never modifies it). Decomposes defence
into three components priced in goals via an empirical state-value function V(state):

- `deny` — episode-frequency suppression (Tier C: team/pair only)
- `suppress` — in-episode xG-intensity suppression (Tier B)
- `escape` — favourable episode-end rate (Tier B; published as a rate)
- `deny_rush` — event-space rush diagnostic (Tier C)
- `pv_def_g60` — composite = deny_g60 + suppress_g60 (Tier B)

**Verdict (validation §9):** no Tier A; PV does not beat the `def_impact` baseline on year-over-year
reliability or team-OOS. `escape` is the genuinely new orthogonal channel. `deny`/`deny_rush` are an
instrumented null (not roster-carried, not arena-biased). See `docs/methodology/phase-value.md`,
`docs/phase-value/validation-report.md`, `docs/phase-value/DECISIONS.md`, `docs/phase-value/spec.md`,
`docs/phase-value/INCIDENTS.md`.

## Pipeline (dependency order)

```
dbt (int_phase_events → int_phase_spells → int_zone_episodes → int_phase_ticks)   # state engine, full history
  → compute_state_values      # V(state) + phase_league_constants  (nhl_models.state_values, phase_league_constants)
  → train_phase_value         # the 3 fits + rush sub-fit + shared-draw bootstrap  → artifacts/phase_value/*.parquet
  → assemble_phase_value      # g60 accounting + def_impact join    → nhl_models.player_phase_value
  → validate_phase_value      # pre-registered tiers (report-only; --write-tiers is OWNER-GATED)
```

`train_rapm` (→ `player_impact`) must have run first — `assemble` joins `def_impact` as the baseline.

## Backfill / rebuild from scratch

All jobs run from repo root with the BQ env sourced
(`GCP_PROJECT_ID`, `GOOGLE_APPLICATION_CREDENTIALS=secrets/nhl-intel-sa.json`).

```bash
# 1. State engine (dbt) — full history, prod defaults. This is the ONLY step that writes int_phase_*.
cd dbt && dbt run --select int_phase_events int_phase_spells int_zone_episodes int_phase_ticks --target dev && cd ..

# 2. State value function + league constants (Stage 2)
python -m models_ml.phase_value.compute_state_values

# 3. Fits (Stage 3) — 3-season window B=100, singles B=40; writes component parquets to artifacts/
python -m models_ml.phase_value.train_phase_value                 # full
python -m models_ml.phase_value.train_phase_value --season 2024-25 --no-bootstrap   # quick smoke test

# 4. Accounting + assembly (Stage 4) — writes nhl_models.player_phase_value
python -m models_ml.phase_value.assemble_phase_value              # --dry-run to skip the BQ write

# 5. Validation (Stage 5) — report only; tiers written ONLY after owner review
python -m models_ml.phase_value.validate_phase_value             # report-only
python -m models_ml.phase_value.validate_phase_value --full      # + split-half / team-OOS / §1c refits
python -m models_ml.phase_value.validate_phase_value --write-tiers   # persist phase_component_tiers (owner-gated)

# 6. Serving (Stage 6)
python -m scripts.export_to_duckdb --only player_phase_value,phase_component_tiers

# Stage-1 gate re-check on the rebuilt state engine
python -m models_ml.phase_value.stage1_reconcile --seasons 2024-25 --n 25
python -m models_ml.phase_value.stage1_conservation --scope 2015-16
```

## Nightly (Airflow `dags/nhl_daily.py`)

Registered **weekly (Monday-gated)**, mirroring RAPM/GAR:
`run_dbt_marts >> compute_state_values >> train_phase_value >> assemble_phase_value >> export_serving`,
with `train_rapm >> assemble_phase_value` for the `def_impact` join. Tiers are NOT re-written nightly
(static validation artifact). See PV-D020 for the §9.3 sensitivity isolation mechanism and the
canary-before-isolated-write protocol (INCIDENTS.md PV-I001).

## Sensitivity / variant builds (production-safe)

NEVER rebuild `int_phase_*` in `nhl_staging` for a variant — that overwrites production (PV-I001). Use the
var-driven schema isolation + canary proof:

```bash
cd dbt && dbt compile --target dev && cp target/manifest.json prod_state/manifest.json    # prod state for --defer
# CANARY first (one model), then prove prod unchanged via INFORMATION_SCHEMA, THEN the full variant:
dbt run --select int_phase_events int_phase_spells int_zone_episodes --target dev --defer --state prod_state \
  --vars '{schema_suffix: sens_gap2, phase_dev_seasons: ["2023-24","2024-25"], phase_episode_gap_seconds: 2}'
python -m models_ml.phase_value.sensitivity --phase-schema nhl_staging_sens_gap2 --label gap2
# tear the sens datasets down when done.
```
