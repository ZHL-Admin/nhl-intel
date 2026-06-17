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

# --- Coach trust (Phase 4.3) ------------------------------------------------
# Deployment-trust signals, z-scored within position then combined. Weights reflect how
# strongly each reflects a coach's trust. dz_faceoff_share = share of a player's on-ice
# faceoffs that are DEFENSIVE-zone draws for his team (recovered from pbp zone_code, which is
# owner-relative: D = the faceoff winner's d-zone, flipped for the loser, joined to
# int_on_ice_events). Post-icing draws are a future refinement. (Earlier note that this was
# blocked by zone-code symmetry was wrong — outcome symmetry is irrelevant to who the coach
# deploys for the draw.)
COACH_TRUST_WEIGHTS = {
    "pk_share": 0.30,            # penalty-kill deployment (PK TOI / total TOI)
    "dz_faceoff_share": 0.30,    # share of on-ice faceoffs that are own-team d-zone draws
    "protect_lead_rate": 0.20,   # last-2-min-of-regulation-while-leading TOI / total TOI
    "road_home_ratio": 0.20,     # road vs home TOI per game (matchup-proof usage)
}

# --- Divergence board (Phase 4.3) -------------------------------------------
DIVERGENCE_MIN_MINUTES = 500     # min 5v5 minutes to appear on the board
DIVERGENCE_BOARD_SIZE = 15       # top + bottom N by |trust z - composite z|

# --- Line-fit / Lineup Lab (Phase 5.1) --------------------------------------
# Chemistry blend: a line's final projection mixes the model prediction with its own observed
# 5v5 history, weighting the observed share by minutes / (minutes + this). 150 min ~= the point
# where observed and model are weighted equally (tuned by holdout in train_linefit.py --tune-blend).
LINEFIT_OBS_PRIOR_MINUTES = 150
# A member with fewer than this many career NHL 5v5 minutes is a rookie/extrapolation: widen the
# projection interval by the multiplier below and label it "deeper extrapolation" (blueprint 6.3).
LINEFIT_ROOKIE_MIN_MINUTES = 500
LINEFIT_ROOKIE_INTERVAL_MULT = 1.5
# Letter-grade bands on projected 5v5 xGF% (descending; first band whose floor is met wins).
LINEFIT_GRADE_BANDS = [
    ("A", 0.560), ("B", 0.525), ("C", 0.490), ("D", 0.455), ("F", 0.0),
]
LINEFIT_ARTIFACT = "linefit_v1"

# --- Team needs / trade fit (Phase 5.3) -------------------------------------
# A team's need profile is measured against the average of the top-N teams by power rating.
TEAM_NEEDS_TOP_N = 8

# --- Matchup preview pregame WP (Phase 5.3) ---------------------------------
# A scheduled game has no segments, so its pregame home win probability is derived from the power
# ratings (which are on a goals/game scale, the same prior the WP model consumes): expected home
# goal differential = home_rating - away_rating + home-ice edge, mapped through a logistic.
PREVIEW_HOME_ICE_GOALS = 0.15   # pregame home-ice edge in expected goal differential
PREVIEW_WP_SCALE = 0.9          # logistic scale converting expected goal diff -> home win prob

# --- Archetypes -------------------------------------------------------------
# Minimum 5v5 minutes for a player-season to be archetyped (Phase 4.2).
ARCHETYPE_MIN_5V5_MIN = 300
# Cluster -> human label, assigned by hand from the Phase 4.2 labeling report (the one
# intentional human-in-the-loop step). Keyed to the persisted GMM components
# (artifacts/archetypes_v1.joblib). "Bottom-Pair Defensive D" (D8) replaced the approved
# "Sheltered Puck-Mover" after the locked fit moved its exemplar (Dougie Hamilton) into the
# Power-Play Quarterback cluster, where he belongs.
ARCHETYPE_NAMES: dict[str, str] = {
    "F0": "Power-Play Specialist", "F1": "High-Danger Driver", "F2": "Fourth-Line Grinder",
    "F3": "Bottom-Six Forward", "F4": "Middle-Six Driver", "F5": "Energy Forward",
    "F6": "Checking-Line Forward", "F7": "Top Six Scorer", "F8": "Top-Six Power Scorer",
    "F9": "Perimeter Playmaker", "F10": "Inside Scorer", "F11": "Perimeter Sniper",
    "D0": "Depth Stay-Home D", "D1": "Attacking D", "D2": "Elite Offensive D",
    "D3": "Power-Play Quarterback", "D4": "Defensive Defenseman", "D5": "Two-Way Top-Pair D",
    "D6": "Physical Mobile D", "D7": "Stay-Home Defender", "D8": "Bottom-Pair Defensive D",
    "D9": "Point-Shot D", "D10": "Defensive Top-Four D", "D11": "PP-Leaning Puck-Mover",
}
