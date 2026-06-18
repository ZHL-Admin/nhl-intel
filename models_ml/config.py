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
    "D6": "Depth Defenseman", "D7": "Stay-Home Defender", "D8": "Bottom-Pair Defensive D",
    "D9": "Point-Shot D", "D10": "Defensive Top-Four D", "D11": "PP-Leaning Puck-Mover",
}

# --- Archetypes v2 (enriched refit; supersedes v1) --------------------------
# v2 clusters on the ENRICHED vector (archetype_features_v2) so defensive/style signals drive
# classification. Names assert ONLY traits that are universal (>=80% one-sided) in the cluster's
# membership (governed by artifacts/archetype_trait_audit_v2.md); the descriptor below carries the
# distinctive (centroid) traits. Keyed to artifacts/archetypes_v2.joblib (F k=12, D k=12).
# NOTE the two-cluster mapping: D3 and D4 are distinct GMM components at the MODEL layer but were
# merged at DISPLAY into one "Depth Defenseman" label (their union is universally low-PP + low-PK
# = depth; see archetypes.md footnote). All consumers read these names.
ARCHETYPE_NAMES_V2: dict[str, str] = {
    "F0": "Elite Offensive Driver", "F1": "Penalty-Kill Forward", "F2": "Middle-Six Forward",
    "F3": "Physical Energy Forward", "F4": "North-South Forward", "F5": "Two-Way Forward",
    "F6": "Inside Scorer", "F7": "Checking Forward", "F8": "Perimeter Scorer",
    "F9": "Top-Six Playmaker", "F10": "Fourth-Line Forward", "F11": "Secondary Scorer",
    "D0": "Elite Offensive D", "D1": "Physical Defenseman", "D2": "Puck-Moving D",
    "D3": "Depth Defenseman", "D4": "Depth Defenseman",     # merged label, distinct model IDs
    "D5": "Penalty-Kill D", "D6": "Power-Play Quarterback", "D7": "Stay-Home Defenseman",
    "D8": "Sheltered Offensive D", "D9": "Attacking D", "D10": "Two-Way Top-Four D",
    "D11": "Point-Shot D",
}
# Per-cluster descriptor (distinctive traits, plain language) shown under the label in the UI.
ARCHETYPE_DESCRIPTORS_V2: dict[str, str] = {
    "F0": "drives play from the offensive zone with a heavy power-play role and elite shot generation",
    "F1": "penalty-kill regular with defensive-zone starts and lead-protection usage; little power-play time",
    "F2": "even-strength forward with little special-teams role; physical, draws penalties",
    "F3": "high rink-adjusted hit rate and defensive-zone deployment; little power-play time",
    "F4": "fast, low offensive-zone time; on-ice results lean conceding (xGF ~31st / xGA ~84th pctl)",
    "F5": "suppresses on-ice xGA and kills penalties; drives 5v5 offense without leaning on the power play",
    "F6": "shoots from the slot and in tight, with few point shots",
    "F7": "penalty-kill and defensive-zone deployment with low offensive-zone time",
    "F8": "perimeter shot diet with a power-play role; low physicality",
    "F9": "power-play playmaker with offensive-zone starts; low physicality",
    "F10": "heavy defensive deployment, perimeter shots, low individual offensive impact",
    "F11": "power-play role, shoots in tight; a secondary offensive forward",
    "D0": "elite skater with a heavy power-play role who drives offense from the back end",
    "D1": "very high rink-adjusted hit rate, draws penalties; little power-play time",
    "D2": "offensive-zone deployment; a mobile, transition-driving top-four puck-mover",
    "D3": "depth role with little power-play or penalty-kill time (bottom-pair usage)",
    "D4": "depth role with little power-play or penalty-kill time (bottom-pair usage)",
    "D5": "penalty-kill regular with defensive-zone starts and trusted defensive deployment",
    "D6": "quarterbacks the power play and drives offense from offensive-zone deployment",
    "D7": "stay-home: perimeter shots and a penalty-kill role; low power-play time",
    "D8": "shoots from in tight with no penalty-kill role; sheltered offensive usage",
    "D9": "activates into the offense, shooting from the slot/in tight rather than the point",
    "D10": "penalty-kill role and trusted top-four usage; shoots in tight",
    "D11": "point-shot volume, an offensive puck-mover with no penalty-kill role",
}
# Coarse "Overall" family per v2 cluster (Part B3): the headline label claims less than the
# specific cluster name. Offense is high-resolution (the cluster IS the offensive sub-label);
# the family + the spoke-derived defensive sub-label keep the headline honest.
ARCHETYPE_FAMILY_V2: dict[str, str] = {
    # forwards
    "F0": "Offensive", "F1": "Defensive", "F2": "Depth", "F3": "Defensive",
    "F4": "Offensive", "F5": "Two-Way", "F6": "Offensive", "F7": "Defensive",
    "F8": "Offensive", "F9": "Offensive", "F10": "Depth", "F11": "Offensive",
    # defensemen
    "D0": "Offensive", "D1": "Defensive", "D2": "Two-Way", "D3": "Depth", "D4": "Depth",
    "D5": "Defensive", "D6": "Offensive", "D7": "Defensive", "D8": "Offensive",
    "D9": "Offensive", "D10": "Two-Way", "D11": "Offensive",
}


# --- Value: GAR / WAR (companion to RAPM impact) ----------------------------
# GAR is the goals-REALITY counterpart to RAPM. RAPM (player_impact) measures repeatable
# play-driving on the xG layer and is UNTOUCHED by this model. GAR measures ACTUAL goals
# contributed above a freely-available replacement player, across all situations, on the goals
# scale — so it inherits shooting luck BY DESIGN (a labeled feature: GAR = "what happened",
# RAPM = "what tends to repeat"). Every modeling decision lives here, each sourced.
GAR_CONFIG = {
    # Goals per standings win. ~6 GF ≈ 1 win in the modern NHL; the standard GAR->WAR divisor
    # (Evolving-Hockey GAR, Hockey-Reference point shares). WAR = GAR / GOALS_PER_WIN.
    "GOALS_PER_WIN": 6.0,

    # Assist values relative to a goal (1.0). A goal is worth more than the assists on it; public
    # GAR / point-share models weight the primary assist ~0.7 and the secondary ~0.5 of a goal.
    # ADOPTED from that literature (cited) rather than re-derived; a league regression of
    # goals/primary/secondary on team scoring is a documented future refinement (value-gar.md).
    "PRIMARY_ASSIST_VALUE": 0.70,
    "SECONDARY_ASSIST_VALUE": 0.50,

    # Marginal goals per drawn penalty (a drawn penalty gives the team a power play; a taken one
    # gives it to the opponent). League PP conversion is ~17-20% of opportunities, so a drawn
    # penalty is worth ~0.17 goals. (composite.py uses 0.2 flat for penalty_diff; GAR uses the
    # slightly conservative league-conversion figure. Per-season computed conversion is a
    # documented refinement — the term is minor.) Drawn = +value, taken = -value.
    "PENALTY_VALUE_GOALS": 0.17,

    # Marginal goals per NET faceoff win, centers only. A single faceoff win is worth ~0.001
    # goals (public faceoff-value research); a tiny term included for completeness, not a driver.
    "FACEOFF_VALUE_GOALS": 0.001,

    # Replacement level = a freely-available player (waiver / AHL call-up / 13th-14th F, 7th-8th
    # D). Defined per (position, strength, season) as the mean per-60 production of the DEPTH
    # pool: skaters ranked below their team's depth threshold by season 5v5 TOI. Absolute GAR
    # levels are sensitive to this choice; RANKINGS are stable (validated in value-gar.md), so
    # the UI leads with ranking, not the raw number.
    "REPLACEMENT_DEPTH_RANK": {"F": 9, "D": 6},   # F ranked >9 / D >6 on their team = replacement
    "REPLACEMENT_MIN_TOI_5V5": 50.0,              # min 5v5 min to enter the pool (rate stability)
    "REPLACEMENT_MIN_POOL": 40,                   # min pool size per (pos,season); else pool all seasons

    "MIN_TOI_5V5_FOR_RANKING": 200.0,             # display/validation floor (not a model cutoff)
}


# --- Value: Goalie GAR / WAR (cross-position currency) ----------------------
# The goalie companion to skater GAR. Goalie value = GOALS SAVED above a freely-available
# replacement (backup) goalie, on the SAME goals scale as skaters, so WAR = GAR / GOALS_PER_WIN
# uses the SAME divisor — that shared 6.0 is exactly what makes a skater and a goalie comparable
# on one WAR list (the only cross-position-comparable unit). Read-only over the GSAx layer
# (mart_goalie_* / int_goalie_shots); the xG model and RAPM are untouched. See value-gar.md.
GOALIE_GAR_CONFIG = {
    # SAME goals-per-win as skaters (config.GAR_CONFIG['GOALS_PER_WIN']); restated here so the
    # goalie job is self-contained, but it MUST equal the skater value — asserted at import below.
    "GOALS_PER_WIN": 6.0,

    # Replacement-level goalie = a freely-available backup / AHL call-up. Defined per
    # (season-window) as the bottom band by workload: goalies ranked OUTSIDE the top-32 by games
    # (32 = one starter per NHL team) who still cleared a minimum shot floor (rate stability).
    # The replacement SAVE performance is measured per danger tier and per strength (GSAx per shot
    # in each bucket) so GSAx-above-replacement decomposes cleanly into the stacked-bar components.
    # Absolute GAR levels move with this choice; RANKINGS are stable (validated, value-gar.md), so
    # the UI leads with WAR/ranking and presents goalie order at tier-level confidence.
    "REPLACEMENT_GAMES_RANK": 32,        # ranked > this by window games = replacement pool
    "REPLACEMENT_MIN_SHOTS": 150,        # min shots faced to enter the pool (rate stability)
    "REPLACEMENT_MIN_POOL": 15,          # min pool size per window; else widen (drop the shot floor)

    # RELIABILITY SHRINKAGE (empirical Bayes). Goaltending is low-signal: a single window's GSAx is
    # mostly noise, so the honest point estimate is the raw value regressed toward the workload-
    # conditional league mean in proportion to MEASURED reliability — the same regularization logic
    # already applied to low-sample skaters (RAPM ridge, player-finishing shrinkage), extended to
    # goalies. reliability(shots) = shots / (shots + k); k is the shots at which the rate is 50%
    # signal. MEASURED per danger tier by method of moments in models_ml/measure_goalie_reliability.py
    # (single-season rows 2021-22..2025-26) — NOT hand-tuned. 'ld' showed var_true <= 0 (no reliable
    # talent on routine low-danger shots — goalies don't repeatably differ there), so it is set to a
    # large k => reliability ~ 0 => low-danger value fully regressed to average. Re-run that script
    # to refresh these. See docs/methodology/value-gar.md.
    "RELIABILITY_K": {
        "hd": 277,          # high-danger: reliable per shot but few shots/season
        "md": 1125,         # mid-danger
        "ld": 10_000_000,   # low-danger: no detectable talent signal (var_true<=0) -> ~0 reliability
        "pk": 599,          # penalty-kill / special teams
        "overall": 2028,    # overall rate (reported for context; shrinkage is applied per tier)
    },

    "MIN_GAMES_FOR_RANKING": 15,         # display/validation floor (matches the goalie radar)
}
# Goalie GAR component keys (the stacked-bar vocabulary) -> label. EV save value is split by
# danger tier (the high-danger component is the difference-maker); PK is the shorthanded save
# value above replacement. These four partition every faced shot, so they sum to goalie GAR.
GOALIE_GAR_COMPONENTS = [
    ("hd_saves", "High-Danger Saves"), ("md_saves", "Mid-Danger Saves"),
    ("ld_saves", "Low-Danger Saves"), ("pk_goaltending", "Penalty-Kill"),
]

# --- Per-player Overall (player detail card ONLY; never a leaderboard sort key) ---
# Overall is a WITHIN-POSITION percentile summary: a weighted average of a player's component
# percentiles, RE-PERCENTILED within position so "Overall" is itself a 0-100 within-position
# percentile (this corrects the thinning-at-the-top effect of averaging percentiles). It
# SUMMARIZES; it must never hide the divergence, so it is always shown beside its components and
# there is no /rankings/overall endpoint. See docs/methodology/overall-rating.md.
#
# Skater weights: Production (GAR) is weighted slightly above Play-Driving (RAPM) because actual
# production is the MORE stable lens year to year (production r=0.66 vs RAPM isolated rate r=0.38;
# config.GAR_STABILITY_YOY) — a documented, tunable choice, deliberately NOT a hidden 50/50.
OVERALL_WEIGHTS = {"production": 0.55, "play_driving": 0.45}

# Goalie Overall has no play-driving axis; it averages the goalie's within-goalie percentiles
# across its own skill axes (from the goalie radar). Save value (overall + high-danger) leads;
# workload and consistency are lighter (usage / steadiness, not pure quality). Re-percentiled
# within goalies. Keys match the goalie_radar spoke keys.
OVERALL_WEIGHTS_GOALIE = {"gsax": 0.40, "hd_gsax": 0.30, "workload": 0.10, "consistency": 0.20}

# --- Confidence-aware value sort (cross-position leaderboard default) ------------------------
# The mixed WAR leaderboard ranks by a LOWER-CONFIDENCE BOUND, value − k·band, not the raw point
# estimate, so a low-variance skater (±~0.8 WAR) is not buried under a high-variance goalie
# (±~2.2 WAR) of equal point estimate. The DISPLAYED number stays the point estimate; only the SORT
# KEY uses this. Started at k = 1.0 (lower edge of the ~68% interval); a full sd buried goalies
# entirely (the genuine goalie sampling band is ~2.2 WAR), so TUNED to 0.5 — a half-sd conservative
# bound that still demotes noisy goalies below confident skaters yet keeps genuinely-elite high-
# workload goalies visible near the top (validated, value-gar.md). Tunable.
CONFIDENCE_SORT_K = 0.5


# Year-over-year stability of the offensive lenses, MEASURED in models_ml/validate_gar.py
# (single-season pairs 2021-22..2025-26, qualified skaters). These are a genuine finding, not
# tuning: the folk ordering ("actual goals = noisy, advanced impact = stable") is half-backwards
# here. Production is sticky; RAPM's isolated rate is the noisier MEASUREMENT; only the finishing
# residual is truly luck-flavored. The Impact-vs-Value read + value-gar.md cite these verbatim so
# "least repeatable" traces to a number (consistency rule).
GAR_STABILITY_YOY = {
    "production_r": 0.66,   # actual 5v5 goal-rate, year over year
    "rapm_r": 0.38,         # RAPM isolated offensive rate (regularized -> measurement noise)
    "finishing_r": 0.35,    # finishing residual (goals - xG) -- the least repeatable piece
}

# Cross-position WAR is only valid if skaters and goalies share the goals-per-win divisor.
# Fail loudly at import if the two ever drift apart (principle 2).
assert GOALIE_GAR_CONFIG["GOALS_PER_WIN"] == GAR_CONFIG["GOALS_PER_WIN"], (
    "Goalie and skater GOALS_PER_WIN must match for cross-position WAR to be comparable.")


# ── Deployment efficiency (Divergence Board rework) ──────────────────────────────────────────
# The board compares a player's ACTUAL situational usage against the usage his situation-
# appropriate VALUE justifies. Divergence = actual_usage_pctile − justified_usage_pctile
# (within position); positive = over-used, negative = under-used.
DEPLOYMENT = {
    # Min total window TOI (minutes) + games to qualify — high enough that the VALUE estimate is
    # reliable (RAPM/composite of a fringe call-up is small-sample noise and otherwise floods the
    # under-used side with players who barely played). ~a rotation regular over three seasons.
    "MIN_TOTAL_TOI": 600,
    "MIN_GAMES": 60,
    # Additional 5v5-minutes floor: RAPM/composite need even-strength volume to be trustworthy,
    # so a value estimate below this is too noisy to call a player "mis-deployed" (mirrors the old
    # board's 500-5v5-minute gate).
    "MIN_EV_TOI": 500,
    # Boards SORT by a confidence-adjusted gap = gap shrunk toward 0 by K·gap_sd, so a soft (wide-
    # band) mismatch ranks below a confident one of equal point estimate.
    "CONFIDENCE_K": 1.0,
    # For TOTAL-ice lenses (all / 5v5 / key moments) a near-zero-usage player is a healthy scratch,
    # not "under-used" — require a floor of actual usage to appear on the under-used side. NOT
    # applied to PP/PK, where zero situational usage IS the insight (a strong PK candidate who
    # kills nothing). Usage type 'total'|'ev'|'hilev' -> floored; 'pp'|'pk' -> not.
    "MIN_UNDERUSED_ACTUAL_PCTILE": 0.12,
    "FLOORED_USAGE_TYPES": ["total", "ev", "hilev"],
    # "Key moments" = the most pivotal share of game time, defined as a PERCENTILE of the real
    # win-probability leverage distribution (not a hand-picked situation list). Top quartile.
    "KEY_MOMENT_LEVERAGE_PCTILE": 0.75,
    # Justified usage is capped at a realistic ceiling so a maxed-out star (whose value would
    # predict impossible minutes) does NOT read as under-used. The ceiling is data-derived: the
    # given percentile of OBSERVED per-game usage within position+situation (not an arbitrary
    # number). 0.97 ≈ the busiest handful of players define the realistic max.
    "USAGE_CEILING_PCTILE": 0.97,
    # Each situation pairs the right value against the right usage (the fix for the broken side).
    # value_key is resolved in compute_deployment_efficiency against player_impact/composite.
    "SITUATIONS": {
        "all":         {"usage": "total", "value": "composite", "label": "overall value"},
        "5v5":         {"usage": "ev",    "value": "ev_impact", "label": "even-strength impact"},
        "pp":          {"usage": "pp",    "value": "pp_impact", "label": "power-play impact"},
        "pk":          {"usage": "pk",    "value": "pk_blend", "label": "penalty-kill + defensive impact"},
        "key_moments": {"usage": "hilev", "value": "composite", "label": "overall value"},
    },
    # PK justified value blends the PK-specific RAPM coefficient with general defensive impact,
    # weighted TOWARD pk_impact (each normalised to unit variance first). Pure def_impact floods the
    # under-used side with offensive forwards whose single-season defensive RAPM is noisily high but
    # who have no PK track record; weighting toward pk_impact (≈0 for non-killers) damps that noise
    # while a genuine kill-some-and-defend-well specialist keeps a real signal.
    "PK_BLEND_W": 0.75,
    # Reliability gate (PK under-used only): a player may only be flagged under-deployed on the PK if
    # his value estimate is reliable enough — value-sd at or below this within-position percentile.
    "DEF_SD_GATE_PCTILE": 0.5,
    "MODEL_VERSION": "deployment_v1",
}
