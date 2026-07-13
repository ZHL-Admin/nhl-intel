# Chemistry

Research project: does pair **chemistry** — over/under-performance beyond individual quality —
persist as a trait, and can a player **fit** embedding predict it on unseen pairs? Built from the
frozen Deployment Atlas stints, anchored on rapm_variant, validated predictively before any claim.

Isolated research layer under `NIR/research/chemistry`. **Removable by deleting this folder with
zero impact on the site** — production code never imports from here; production BigQuery is
read-only except the explicitly gated Phase 7.

- **Reads (read-only):** frozen Deployment Atlas parquet (`../deployment-atlas/data/parquet`) via
  `atlas.api`; frozen System Effects parquet (`../system-effects/data/parquet`) via `syseff.api`;
  production BigQuery for the Phase 0 inventory (pair/line assets + the fit incumbent).
- **Never modifies:** the Atlas or System Effects assets (or their prospective_20xx dirs), or
  production — except gated Phase 7.
- **Seed:** `20260712` (all randomness seeded and recorded).
- **Stack:** Python 3.11+, polars, duckdb, scikit-learn, pyarrow (torch permitted for the embedding
  fit only if justified). pytest under `tests/`.
- **Reproduce:** `make venv` then `make phaseN`. Every phase reproducible from cache and ends by
  writing `reports/phaseN.md`, then stops.

## Branch hygiene
Own branch `research/chemistry`. Reads the **frozen** Atlas and System Effects assets, not rebuilt
production tables, so it must not entangle with any concurrent production work.
