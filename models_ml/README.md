# models_ml — Python model layer

Local training and scoring jobs for every in-house model. Outputs are written
back to the BigQuery `nhl_models` dataset so dbt marts and the FastAPI backend
can join them by reference.

## Contents
- `config.py` — **all** model-layer constants and thresholds (single source).
- `artifacts/` — versioned, serialized model artifacts (gitignored except `.gitkeep`).
- `train_*.py` / `score_*.py` / `compute_*.py` — one job per model (added per phase).

## Rules
- No hardcoded magic numbers in jobs — import from `config.py`.
- Every shipped model writes a versioned artifact here and a methodology doc to
  `docs/methodology/`.
- Scoring jobs are incremental where possible (`--since` flags) and wired into
  `dags/nhl_daily.py`.

## Training order (built out across phases)
sequence → xG → win-probability → RAPM → archetypes → line-fit → ratings → insights
