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
# (Phase 2.4) consume a single rating source. Swapped to the Phase 3.1 power
# rating (nhl_models.team_ratings) here; the dbt mart mirrors this via the
# `rating_source` var in dbt_project.yml. See docs/methodology/power-ratings.md.
RATING_SOURCE = "power_rating"  # one of: {"interim_xgf", "power_rating"}

# --- Danger tiers -----------------------------------------------------------
# Per-shot xG bounds used by goaltending danger splits (Phase 2.5). Half-open
# intervals [lo, hi). Kept here so goalie marts and cross-validation agree.
DANGER_TIERS = {
    "low": (0.0, 0.05),
    "medium": (0.05, 0.15),
    "high": (0.15, 1.0),
}

# --- Shrinkage --------------------------------------------------------------
# Finishing/goaltending regression-to-mean shrinkage constants k (Phase 3.1),
# tuned by season-over-season predictiveness (compute_ratings.py --tune-k).
# Both shrink a per-game component toward 0 by accumulated shot volume:
# shrunk = raw * vol / (vol + k). Larger k => more regression.
# Tuned 2026-06 by next-season MSE (compute_ratings.py --tune-k): both have an interior
# optimum at 4000 (team finishing/goaltending regress hard year to year -- mostly noise).
FINISHING_SHRINKAGE_K = 4000     # 5v5 shots
GOALTENDING_SHRINKAGE_K = 4000   # EV shots faced

# --- Streak Doctor ----------------------------------------------------------
# Component persistence weights (Phase 3.3), used for the 0-100 sustainability meter:
# how much each driver of a hot/cold run tends to carry forward. xG-share (genuine play
# change) persists most; on-ice shooting and goaltending swings regress hardest. Rationale
# in docs/methodology/streak-doctor.md.
STREAK_PERSISTENCE = {
    "play_change": 0.8,     # underlying 5v5 xG-share change
    "schedule": 0.5,        # strength of opponents faced
    "special_teams": 0.3,   # PP/PK variance
    "goaltending": 0.2,     # GSAx
    "shooting_luck": 0.1,   # on-ice shooting vs expected
}
STREAK_WINDOWS = [5, 10, 20]      # precomputed last-N windows
STREAK_DEFAULT_WINDOW = 10
STREAK_NOTABLE_Z = 1.5            # |points-pace z| threshold for a notable run
STREAK_NOTABLE_STREAK = 4         # consecutive W or L threshold

# --- Composite (Phase 4.2) --------------------------------------------------
# Player finishing (goals - ixG) regresses toward 0 by individual shot volume. Skater shot
# samples are ~100-300/season, so the team-level FINISHING_SHRINKAGE_K (4000, tuned on team
# shot volumes) would erase all player signal; shooting talent stabilises around ~350 shots
# (public-research consensus), so we use a player-appropriate k here.
PLAYER_FINISHING_SHRINKAGE_K = 350   # individual shots
# Value of a drawn penalty in goals: a power play is worth ~0.2 expected goals (league PP
# conversion). Penalty differential = (drawn - taken) * this.
PP_GOAL_VALUE = 0.2

# --- Archetypes -------------------------------------------------------------
# Minimum 5v5 minutes for a player-season to be archetyped (Phase 4.2).
ARCHETYPE_MIN_5V5_MIN = 300
# Cluster -> human label, filled in by hand from the Phase 4.2 labeling report
# (the one intentional human-in-the-loop step). Empty until then. Keyed "F0".."Dn".
ARCHETYPE_NAMES: dict[str, str] = {}
