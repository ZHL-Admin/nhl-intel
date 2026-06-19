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

# --- Player Fit talent projection (the quality FLOOR input) --------------------------------------
# The talent that floors fit is a forward PROJECTION, not last season's result, so a contract-year
# or one-off spike doesn't inflate the floor. Derived the way the trade talent axis projects (reuse,
# not a new model): recency-weight the last ~3 seasons of WAR (also by games = sample), regress the
# weighted level toward replacement (0 WAR, the GAR baseline) by sample size AND volatility, then age
# it forward one season on the player's aging curve. A young breakout has little history to dilute and
# ages UP (tempered little); an older spike is diluted by prior seasons and ages DOWN (tempered more).
PLAYER_FIT_PROJECTION = {
    "RECENCY_WEIGHTS": [1.0, 0.6, 0.3],   # most-recent -> 2 seasons prior (normalised over present)
    "REGRESS_GAMES_K": 22.0,              # games-weighted reliability half-point (small/volatile
                                          # samples regress hard; a full-sample star barely moves —
                                          # the spike tempering comes mostly from the multi-year mean)
    "VOL_INFLATE": 0.8,                   # cross-season volatility (CV) inflates the regression K
    "BAND_SD_FLOOR": 0.4,                 # floor on the projected-WAR sd (never a too-tight band)
    "SPIKE_NOTE_GAP_WAR": 0.6,            # show "projects to X, last season Y" when last-proj >= this
    "SPIKE_BAND_INFLATE": 0.5,            # widen the band by this * (last - proj) on a spike
    "AGE_DEFAULT": 27,                    # league-ish age when bio is missing
}

# --- Player Fit (rebuilt: quality FLOORS fit, need is the core, by component-and-role) -----------
# Fit measures how well a player's profile SERVES a team. Talent never CAPS it — an elite player
# always floors at a decent fit, and a low-value specialist who lands on a real team need can still
# score high. Composition (all terms in [0, 1]):
#     match = weighted(need, style, line)
#     floor = FLOOR_CAP * overall_quality_percentile            # talent floors, never caps
#     fit   = floor + (1 - floor) * match                       # match drives the upside, uncapped
# Quality is exposed as its OWN axis beside fit, never folded into match. Position is NOT a
# dimension — it is the role axis of NEED: team_needs is role (C/W/D/G) x component, benchmarked
# against the team's OWN current depth, not the league's top teams. See docs/methodology/player-fit.md.
TRADE_FIT = {
    "MATCH_WEIGHTS": {"need": 0.55, "style": 0.20, "line": 0.25},   # need is the core; sum 1.0
    "FLOOR_CAP": 0.55,           # elite (quality pctile ~1.0) floors here; a depth player floors ~0
    # need_score at a role: opp_c = team_need_c * player_strength_c (the team is weak there AND the
    # player is strong there). Blend the single best opportunity (rewards a specialist who nails the
    # team's biggest hole) with breadth across components (rewards an all-rounder addressing several).
    "NEED_PRIMARY_W": 0.7,       # weight on max(opp_c); (1 - this) on mean(opp_c)
    "NEED_OVERLAP_MIN": 0.40,    # min opportunity (need x strength) to say "he addresses it"
    # per-role need tag thresholds (n = team need 0-1, s = his strength pctile 0-1):
    "LOW_NEED": 0.30,            # n < this -> 'low_need'
    "STRONG_NEED": 0.60,         # n >= this with s>=n -> 'fills'; with s<n -> 'gap'
    # handedness: a SMALL modifier inside need — bump when the team is short the player's shot at his
    # role, trim when over-supplied. Bounded to +/- HAND_MOD/2 so it never dominates.
    "HAND_MOD": 0.10,
    # line complementarity (Phase 3): sum of the line model's PAIRWISE feature contributions (arch
    # overlap, shot-loc variety, handedness, pace spread, tilt) — talent-INDEPENDENT — mapped through
    # a sigmoid (0.5 = neutral). Scale ~ a typical pairwise contribution magnitude in xGF% space.
    "LINE_COMP_SCALE": 0.03,
    "LINE_XGF_LO": 0.44, "LINE_XGF_HI": 0.58,   # kept for the line note's grade context
    # letter grade off the COMPOSED fit (carding only) — conventional HARD bands so the letter
    # always matches the /100: 90+ A, 80-89 B, 70-79 C, 60-69 D, <60 F. The API and UI ALWAYS render
    # the decomposition + the separate quality axis — never a lone grade. (The quality FLOOR still
    # guarantees a high-quality player a strong SCORE; the letter just follows the conventional scale,
    # so a star at a poor-stylistic-match team can read C — honestly — rather than a forced B.)
    "GRADE_BANDS": [("A", 0.90), ("B", 0.80), ("C", 0.70), ("D", 0.60), ("F", 0.0)],
}

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

# NHL salary-cap UPPER LIMIT by season (announced NHL/NHLPA figures). Cost is measured as a SHARE of
# the cap (era-neutral), and the cap is projected FORWARD across a contract's remaining years, so a
# fixed-dollar cap hit correctly becomes a shrinking share of a rising cap over the life of the deal.
CAP_UPPER_LIMIT_BY_SEASON = {
    "2024-25":  88_000_000,
    "2025-26":  95_500_000,
    "2026-27": 104_000_000,
    "2027-28": 113_500_000,
}
# Past the announced window the cap is unknown (the CBA comes up around then), so project each later
# season as the prior one x (1 + this). A MODERATE default — the current 8-9%/yr jumps are post-
# pandemic catch-up, not a durable rate. This is the single most important assumption for long deals;
# it is deliberately adjustable. Documented in docs/methodology/contract-surplus.md.
CAP_GROWTH_BEYOND_KNOWN = 0.05

# ---------------------------------------------------------------------------------------------
# Trade tool — contract surplus (models_ml/compute_contract_value.py -> nhl_models.player_contract_value)
# Surplus = market value of a player's PROJECTED on-ice production minus their cap COST, measured in
# CAP SHARE (era-neutral) across the remaining years with the cap projected forward, then discounted
# to present value. Every number traces to a computed column (current WAR -> aging projection ->
# position market curve in cap-share -> per-year surplus).
CONTRACT_VALUE = {
    # Present-value discount applied to each future season's surplus (a win next year is worth less
    # than a win now: aging risk, injury risk, money's time value). 0.90/yr.
    "DISCOUNT": 0.90,
    # Aging: project WAR forward by the per-archetype aging curve (nhl_models.aging_curves, a
    # points/82 LEVEL by age) used as a RATIO vs the player's current age. Ages outside a curve's
    # support are clamped to its covered range (no extrapolation past observed aging).
    "AGE_FALLBACK": {"F": "All Forwards", "D": "All Defensemen"},
    # Goalies have no aging curve here (curves are skater points/82); hold goalie WAR flat across
    # remaining years and tag it lower-confidence. Documented gap, revisited when a goalie curve exists.
    "GOALIE_AGING_FLAT": True,
    # Market curve: a MONOTONE, smooth AAV-as-a-function-of-WAR fit PER position group on the
    # league's matched contracts. Form: log(AAV) is LINEAR in WAR (so the top end is multiplicative
    # and keeps rising, never plateaus), with the intercept shifted to the MARKET_QUANTILE conditional
    # quantile, then passed through a smooth soft-cap that asymptotes to the CBA max-contract ceiling.
    # This replaced isotonic regression, whose terminal block FLATTENED the sparse top well below the
    # AAVs elite production actually commands, making max-deal stars read as huge false negatives.
    "MARKET_MIN_N": 60,          # min sample to fit a position group; below it, pool all skaters
    # The curve targets the upper-mid conditional quantile of AAV (not the mean): contracts price
    # peak/reputation that single-season WAR understates, and the high-WAR cohort is diluted by ELC /
    # bridge deals, so the mean reads stars as overpaid. 0.65 lands the sample stars at modest surplus
    # while keeping the mid/low range sane (a 2-WAR forward ~ $9M).
    "MARKET_QUANTILE": 0.65,
    # Soft-cap to the CBA maximum (a contract cannot exceed ~20% of the cap). Ceiling = mult x the max
    # observed AAV (data-derived); the cap bends in smoothly from KNEE_FRAC x ceiling, always rising.
    "MARKET_CEIL_MULT": 1.05,
    "MARKET_KNEE_FRAC": 0.75,
    # The top decile of production has few comparables, so its value is lower-confidence: widen the
    # band there and cap the confidence tag at 'medium'.
    "TOP_DECILE_BAND_MULT": 1.6,
    # A player with no current-season WAR (injured, just called up, too few games) cannot be
    # grounded: floor their production NEAR REPLACEMENT (war_floor) with a WIDE band and a proxy
    # tag, never a fabricated point estimate.
    "REPLACEMENT_WAR": 0.0,      # GAR is above-replacement, so replacement ≈ 0 WAR by construction
    "PROXY_WAR_BAND": 1.0,       # ± WAR band on a floored (proxy) player — deliberately wide
    "GROUNDED_MIN_GAMES": 25,    # current-season games to call a WAR estimate "grounded"/high-confidence
    # Band on grounded players: propagate the GAR war_sd through the projection (± this many SDs).
    "BAND_SDS": 1.0,
    "MODEL_VERSION": "contract_value_v2",   # v2: cap-share cost + forward cap projection
}

# ---------------------------------------------------------------------------------------------
# Trade tool — futures value (models_ml/compute_futures_value.py -> nhl_models.futures_value)
# Prospects and draft picks valued in the SAME currency as contracts (WAR + dollars), but as
# explicit PROXIES with wide bands and a proxy confidence tag — never a bare precise estimate. The
# spine is a slot curve: expected career WAR-above-replacement as a function of overall draft pick.
FUTURES = {
    # Slot curve V(p) = a / (p + c)^b, floored at a small positive WAR. A documented PROXY
    # calibrated to public draft-value research (round-1 picks dominate; value decays as a power
    # law; late picks regress to ~replacement). Anchors: V(1)≈22, V(31)≈3.5, V(100)≈1.2, V(200)≈0.5
    # career WAR — EXPECTED over all picks at that slot, so busts are already priced in.
    "SLOT_A": 100.0,
    "SLOT_C": 4.0,
    "SLOT_B": 0.95,
    "SLOT_FLOOR_WAR": 0.3,        # never below ~replacement, even for the last pick / undrafted
    "UNDRAFTED_WAR": 0.4,         # an undrafted org prospect: floored near replacement, wide band
    # Time value: a future win is discounted per season until it is expected to arrive in the NHL.
    "DISCOUNT": 0.90,
    "NHL_READY_AGE": 23.0,        # time_to_NHL for a prospect ≈ max(0, this - current age)
    "DRAFT_TO_NHL_YEARS": 3.0,    # a not-yet-drafted future pick adds ~3 dev years on top of years_out
    # Development risk for a prospect lingering past the typical breakout age without an NHL footprint:
    # discount value once age exceeds NHL_READY_AGE (older un-broken-through => more bust-like).
    "DEV_DECAY_PER_YEAR": 0.85,
    # Dollars per win — the market price of a WAR in the cap era (public estimate ≈ $3.0M/WAR).
    # Documented proxy used to express futures value in dollars alongside contract surplus.
    "DOLLARS_PER_WAR": 3_000_000,
    # Wide multiplicative band on every futures point estimate (these are proxies): [lo, hi] x value.
    "BAND_LO": 0.45,
    "BAND_HI": 1.9,
    # ELC cost proxy for a SIGNED prospect with no parsed contract (cap hit unknown but small).
    "ELC_COST": 900_000,
    "PICKS_PER_ROUND": 32,        # representative overall = (round-1)*32 + 16; band spans the round
    "MODEL_VERSION": "futures_value_v1",
}
