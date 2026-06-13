"""
Central configuration for the nhl-intel model layer (``models_ml/``).

Every model-layer constant and threshold lives here so that training and scoring
jobs never hardcode magic numbers. Constants are added as each model ships; the
rationale for each value belongs in the matching ``docs/methodology/`` file.

Conventions
-----------
- dbt-side thresholds (sequence-mining windows, danger geometry) live in
  ``dbt_project.yml`` vars, NOT here. This module is for the Python model layer.
- Model outputs are written to the ``nhl_models`` BigQuery dataset.
- Every shipped model writes a versioned artifact to ``models_ml/artifacts/``.
"""

from __future__ import annotations

# --- BigQuery ---------------------------------------------------------------
# Env var holding the GCP project id (read at runtime; never hardcode the value).
GCP_PROJECT_ENV = "GCP_PROJECT_ID"
# Dataset where model outputs (shot_xg, win_probability, team_ratings, ...) land.
MODELS_DATASET = "nhl_models"

# --- Rating source toggle ---------------------------------------------------
# The opponent adjustment (Phase 2.3) and the win-probability team prior
# (Phase 2.4) consume a single rating source. It starts as the interim
# score-adjusted xGF% prior and is swapped to the real power rating in one place
# once Phase 3 ships. See docs/methodology/power-ratings.md.
RATING_SOURCE = "interim_xgf"  # one of: {"interim_xgf", "power_rating"}

# --- Danger tiers -----------------------------------------------------------
# Per-shot xG bounds used by goaltending danger splits (Phase 2.5). Half-open
# intervals [lo, hi). Kept here so goalie marts and cross-validation agree.
DANGER_TIERS = {
    "low": (0.0, 0.05),
    "medium": (0.05, 0.15),
    "high": (0.15, 1.0),
}

# --- Shrinkage --------------------------------------------------------------
# Finishing/goaltending regression-to-mean shrinkage constant k (Phase 3.1),
# tuned by season-over-season predictiveness. Placeholder until tuned.
FINISHING_SHRINKAGE_K = None  # set in Phase 3.1

# --- Archetypes -------------------------------------------------------------
# Cluster -> human label, filled in by hand from the Phase 4.2 labeling report
# (the one intentional human-in-the-loop step). Empty until then.
ARCHETYPE_NAMES: dict[str, str] = {}
