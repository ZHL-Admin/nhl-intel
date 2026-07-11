# System Effects

Research project that measures what coaching **systems** do to the players inside them
and to the opponents across from them: per-player **portability** scores and per-matchup
**style adjustments**, validated predictively before anything is claimed or promoted.

Isolated research layer under `NIR/research/system-effects`. **Removable by deleting this
folder with zero impact on the site** — production code never imports from here, and
production BigQuery is read-only except the explicitly gated Phase 7 promotion.

- **Reads (read-only):** frozen Deployment Atlas parquet (`../deployment-atlas/data/parquet`)
  via `atlas.api`; production BigQuery (`nhl_staging` / `nhl_models`) for audit + coach data.
- **Never modifies:** Atlas assets, or production — except gated Phase 7.
- **Seed:** `20260711` (all randomness seeded and recorded).
- **Stack:** Python 3.11+, httpx, polars, duckdb, scikit-learn, pyarrow; pytest under `tests/`.
- **Reproduce:** `make venv` then `make phaseN`. Every phase reproducible from cache and
  ends by writing `reports/phaseN.md`, then stops.

## Reports
`reports/phase0.md` … · `reports/upstream-ledger.md` (defects found in production/Atlas data).

## Branch hygiene
This project reads the **frozen** Atlas parquet, not rebuilt production tables, so it must
not entangle with the concurrent `rebuild/dedup-segments-retrain` work order. Do System
Effects work on its own branch (see reports/phase0.md).
