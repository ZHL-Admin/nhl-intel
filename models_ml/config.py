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
    # The projection numerics use the newest len(RECENCY_WEIGHTS)=3 seasons; the trajectory
    # classifier reads a slightly deeper SERIES. We pull this many seasons of history — the extra
    # (4th) season carries recency weight 0, so it is in the series for slope/"slipped N seasons"
    # detection but DOES NOT change proj_war / the quality floor (floor-neutral by construction).
    "HISTORY_SEASONS": 4,
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

    # ---- verdict clause-assembly (insight_engine/templates/team_fit.py) ----------------------
    # The verdict is assembled from conditional clauses chosen by computed signals (no flat template,
    # no LLM). Every threshold/label here is tunable; the template carries no magic numbers. See the
    # "verdict" section of docs/methodology/player-fit.md.
    #
    # TRAJECTORY classifier — buckets a player's per-season WAR series into a context word. The tier
    # word ALWAYS maps to the PROJECTION (not last season); declining/volatile carry a trend caveat
    # so a high projection never sits silently beside a downward trend.
    "TRAJ": {
        "CAREER_YEAR_GAP_WAR": 1.5,   # last season - established (prior) level >= this -> career_year
        "DOWN_YEAR_GAP_WAR": 1.2,     # established level - last season >= this -> a down-year dip
        "MIN_TRACK_DEPTH": 2,         # # prior seasons at/near the proven tier to call a dip a down_year
        "MIN_DEPTH_FOR_IS": 3,        # # seasons at/near the projected tier to allow an unhedged "is"
        "TIER_BAND_WAR": 1.0,         # |season WAR - reference| <= this counts as "at that tier"
        "SLOPE_DECLINE": 0.30,        # overall WAR slope <= -this (per season) is a real decline
        "SLOPE_DECLINE_PRIOR": 0.30,  # prior-seasons slope <= -this -> a SUSTAINED slide (vs a cliff)
        "SLOPE_FLAT": 0.50,           # prior slope >= -this -> prior was stable (a cliff, not a slide)
        "SLOPE_ASCEND": 0.30,         # overall slope >= this (per season) is a real climb
        "DECLINE_MIN_SEASONS": 2,     # consecutive season-over-season drops to call it declining
        "ASCEND_MIN_SEASONS": 2,      # consecutive rises to call it ascending
        "VOLATILE_CV": 0.90,          # proj band / |proj WAR| >= this -> volatile
        "VOLATILE_SERIES_CV": 0.60,   # season-to-season WAR CV >= this -> volatile
        "CV_EPS": 0.5,                # stabiliser in the CV denominators (WAR near 0)
    },
    # TIER labels by position group — the adjective mirrors _quality_label's cuts (elite 0.90 /
    # high-end 0.75 / solid 0.55 / depth 0.35 / below) so the verdict noun agrees with the quality
    # chip on the same page. Ordered high -> low; "lower tier" (declining) = the next entry down.
    "TIER_LABELS": {
        "D": [(0.90, "elite #1 defenseman"), (0.75, "high-end top-four defenseman"),
              (0.55, "solid top-four defenseman"), (0.35, "depth defenseman"),
              (0.0, "below-replacement defenseman")],
        "F": [(0.90, "elite first-line forward"), (0.75, "high-end top-six forward"),
              (0.55, "middle-six forward"), (0.35, "depth forward"),
              (0.0, "below-replacement forward")],
        "G": [(0.90, "elite starter"), (0.75, "high-end starter"), (0.55, "solid starter"),
              (0.35, "backup-caliber goaltender"), (0.0, "depth goaltender")],
    },
    # SIGNATURE strength — the top role/skill the identity clause names. Reuses the per-component
    # within-role percentiles already on the profile; degrades to None (no skill tail) below the bar.
    "SIGNATURE_MIN_PCT": 0.65,        # a component must clear this percentile to be a "signature"
    "SIGNATURE_TWO_WAY_PCT": 0.70,    # ev_offense AND ev_defense both >= this -> "drives play at both ends"
    "SIGNATURE_PHRASES": {
        "ev_offense": "drives even-strength offense",
        "ev_defense": "defends at even strength",
        "pp": "produces on the power play",
        "pk": "kills penalties",
        "finishing": "finishes around the net",
        "goaltending": "is a difference-maker in net",
        "two_way": "drives play at both ends",
    },
    # CAP / FLOOR clause gates.
    "MATERIAL_CAP": 0.06,             # a dimension's weighted shortfall must exceed this to be named
    "FLOOR_LIFT_MIN": 0.12,           # fit - match >= this -> quality is doing the lifting (floor note)
    "PROJ_CAP_MAG": 0.08,             # the "unproven one-year projection" cap magnitude (career/volatile)
    "TOP_GRADES": ("A", "B"),         # grades that get "the only thing keeping it from higher" / a closer
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
    # signal. MEASURED per danger tier by method of moments in archive/models_ml/measure_goalie_reliability.py
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


# --- Player Assessment (three-layer verdict: tier + confidence + role) ------------------------
# The page-level "how good is he" verdict. Point estimator is chosen by the validation bakeoff
# (models_ml/validate_assessment.py, ship gate G1 + prereg selection rule); POINT_ESTIMATOR names
# the winner and is the ONLY thing to change to swap estimators — the table schema and the tier
# machinery are estimator-agnostic. Tier boundaries are league job-count RANK ceilings within a
# position group + window (spec 6.2, RESOLVED D2). See docs/player-assessment-spec.md.
ASSESSMENT = {
    "MODEL_VERSION": "assessment_v1",
    # Winner of the M0/M0.5 bakeoff. Swappable via value_lens without any schema change; goalies
    # always carry goalie_gar through regardless of the skater estimator.
    "POINT_ESTIMATOR": "c2_roster_player",
    # (tier, cumulative_rank_ceiling): rank <= ceiling gets the tier; None = the remainder.
    # Ceilings are league job counts (F lines 96 = 3x32, D pairs 64 = 2x32, G starters 32).
    # Elite: 18 F / 12 D (All-Star slots x 3yr window), 8 G (goalie WAR shrunk hard).
    "TIER_RANKS": {
        "F": [("elite", 18), ("first_line", 96), ("second_line", 192),
              ("third_line", 288), ("fourth_line", 384), ("fringe", None)],
        "D": [("elite", 12), ("number_one", 32), ("top_pair", 64),
              ("second_pair", 128), ("third_pair", 192), ("fringe", None)],
        "G": [("elite_starter", 8), ("starter", 32), ("tandem", 48),
              ("backup", 64), ("fringe", None)],
    },
    # Small-pool fallback: if the qualified pool is smaller than the deepest ceiling, convert each
    # ceiling to its percentile equivalent against the reference pool and cut on percentiles.
    "TIER_REFERENCE_POOL": {"F": 384, "D": 192, "G": 64},
    "TIER_LABELS": {
        "elite": "Elite", "first_line": "First-line forward",
        "second_line": "Second-line forward", "third_line": "Third-line forward",
        "fourth_line": "Fourth-line forward",
        "number_one": "Number-one defenseman", "top_pair": "Top-pair defenseman",
        "second_pair": "Second-pair defenseman", "third_pair": "Third-pair defenseman",
        "elite_starter": "Elite starter", "starter": "Starter",
        "tandem": "Tandem goalie", "backup": "Backup",
        "fringe": "Fringe / replacement",
    },
    "CONFIDENCE_CUTS": {"high": 0.55, "medium": 0.35},        # RESOLVED D3
    # Range-copy trigger (spec 10.1, Amendment B): fire the two-tier range sentence when
    # tier_confidence < CONFIDENCE_CUTS["high"] AND tier_prob_within_one >= this value. Keys on the
    # RAW tier_confidence, NOT the forced-low confidence_label, so a concentrated-mass single-season
    # player is not mislabeled a straddle. Single-season windows use their own sentence template.
    "WITHIN_ONE_RANGE_COPY": 0.85,
    # (min_toi_5v5_min, min_seasons_present) per grade, skaters. D = unqualified.
    "STABILITY_GRADES": {"A": (3000, 3), "B": (2000, 2), "C": (None, 1)},
    "GOALIE_MAX_GRADE": "B",                                  # goalie rate reliability ~0.19
}


# =====================================================================================
# Offseason roster forecast (models_ml/project_roster_forecast.py). Projects how good a team
# will be NEXT season from the moves it made this offseason, with an honest band, a decomposed
# move ledger, a projected lineup with line-fit grades, and a style-fit read. READS team_ratings,
# player_gar, goalie_gar, aging_curves, player_archetypes, team identity/needs and the
# score_line / score_team_fit services; it trains NOTHING. Every constant is named so the
# methodology doc (docs/methodology/offseason-forecast.md) can cite it verbatim.
# =====================================================================================
ROSTER_FORECAST = {
    "MODEL_VERSION": "roster_forecast_v1",
    "RANDOM_SEED": 7,                 # deterministic tie-breaks only; the job does no sampling

    # The dressed lineup a team ices. The talent total is summed over FILLED slots, never "all
    # arrivals minus all departures" — a team plays a fixed lineup. 12 F + 6 D + a goalie TANDEM.
    "N_FWD": 12,
    "N_DEF": 6,
    "N_GOALIE": 2,                    # starter + backup. UNLIKE skaters, the two goalies are NOT
    # summed at full value: WAR is a per-82 rate (models_ml.compute_contract_value.blended_war_rate),
    # so two goalies each carry a full-season rate. Summing them would double-count goaltending (a team
    # plays ONE season split between them). The goalie slots are therefore WORKLOAD-WEIGHTED by expected
    # starts (shares sum to 1), so the tandem contributes exactly one season of goaltending, distributed.
    # Shares come from each team's PRIOR-YEAR goalie usage (load_goalie_workload); this league default is
    # the fallback for a team with too-thin prior data and for the roster builder's arbitrary rosters.
    "GOALIE_WORKLOAD_FALLBACK": [0.65, 0.35],   # starter ~53 starts / backup ~29 — typical modern tandem
    "GAMES_PER_SEASON": 82,           # season WAR (wins) -> per-game goals scaling

    # Robust end-of-season roster: a player is a roster member of his LATEST-game team that season
    # (handles in-season trades) if he played at least this many games (filters cup-of-coffee
    # call-ups). The official 21-man published snapshot is too narrow (drops regulars later sent to
    # the AHL) and the raw game-derived list is too broad (1-2 game call-ups), so we floor by games.
    "MIN_GAMES_ROSTER": 10,

    # The live (--full) forecast runs DAILY but only during the offseason (the upcoming-season forecast
    # is meaningless once that season starts). Offseason = the most recent NHL game is a finished
    # PLAYOFF run: a playoff (type 03) game at least this many days ago. 8 days clears any
    # between-playoff-round gap but triggers right after the Cup Final; an in-season break ends on a
    # regular-season game so it never qualifies. The forecast thus runs all summer and stops at the
    # next season's first game.
    "OFFSEASON_MIN_GAP_DAYS": 8,

    # GOALS_PER_WIN restated for a self-contained block; asserted == GAR_CONFIG at import so a
    # WAR delta converts to goals on the SAME scale the team rating uses (principle 2: fail loud).
    "GOALS_PER_WIN": 6.0,

    # Rating -> projected 82-game standings points: P = intercept + slope*rating, clamped to
    # [0, ceiling]. The rating is expected goal differential per game (league mean ~0), so the
    # intercept is league-average points and the slope is points per goal/game of differential.
    # Empirical OLS of final team_ratings.total_rating vs deserved_standings.actual_points
    # (see models_ml/validate_roster_forecast.py, which recomputes these). The slope runs above the
    # naive 2-points-per-win first principle (~27) because OT/SO award a third point and the
    # opponent-adjusted rating is compressed vs raw goal differential. ceiling = 82 games * 2.
    "FORECAST_POINTS": {"intercept": 91.5, "slope": 35.8, "ceiling": 164},

    # ── Roster Builder ABSOLUTE rating (the offseason tool does NOT need these) ──────────────────
    # The offseason forecast trusts a team's MEASURED rating for its returning core and only adjusts
    # for moves. The Roster Builder grades an ARBITRARY user-built roster with no trustworthy base, so
    # it derives an absolute rating from the roster's OWN projected value (see absolute_rating() in
    # project_roster_forecast):
    #   rating_abs = (total_iced_lineup_WAR - LEAGUE_AVG_LINEUP_WAR) * WAR_TO_RATING (+ chemistry)
    # Calibrated by models_ml/calibrate_roster_builder.py on the two completed forward transitions
    # (2023-24->2024-25, 2024-25->2025-26 opening rosters, 63 team-seasons), icing the lineup
    # POSITION-AWARE (the same C/L/R + handedness assignment the tool ices — a pure top-by-WAR lineup
    # overstates the total since you cannot ice 7 centers):
    #   * LEAGUE_AVG_LINEUP_WAR = the league-mean projected iced-lineup WAR, so an average roster maps
    #     to rating_abs ~= 0 (~= 91.5 league-average points).
    #   * WAR_TO_RATING = OLS slope of MEASURED team rating on centered total lineup WAR. It is ~half
    #     the move-scale GOALS_PER_WIN/GAMES (6/82 = 0.073): summed lineup WAR maps to team goal-diff
    #     at a COMPRESSED rate (shared ice, opponent-adjusted regression, a replacement baseline that
    #     does not stack linearly), so the naive 6/82 overstates spread. Fitting it against the
    #     de-lucked measured rating keeps the rating->points step the separate, already-validated map.
    # VALIDATION (reported by the calibration script): REALIZED roster WAR tracks the measured rating
    # at corr ~0.82 (the value system reconciles), but the season-AHEAD projection carries real
    # forecasting uncertainty (projected corr ~0.44; projected vs actual points MAE ~10.5, of which
    # ~5.2 is irreducible in-season luck). The Roster Builder is therefore DELTA-led (the change vs the
    # real roster, where shared players cancel and only relative value matters) with absolute points a
    # secondary, BANDED read — never presented as a measured rating. See docs/methodology/roster-builder.md.
    # Recalibrated in Handoff 12 for the component projection model (project_roster_player), whose WAR
    # scale differs from the old project_skater_war these were first fit on. Roster-Builder-only
    # (absolute_rating is not used by the offseason tool).
    "LEAGUE_AVG_LINEUP_WAR": 12.09,   # league-mean projected iced-lineup WAR (above replacement); goalie
    #                                   tandem workload-weighted, skaters iced DEPLOYMENT-AWARE (seed observed
    #                                   5v5 units, then the position-aware assignment). Recalibrated via
    #                                   calibrate_roster_builder (Phase 2: 63 team-seasons, MAE 10.51, corr 0.465).
    "WAR_TO_RATING": 0.03540,         # goals/game of team rating per 1 WAR of centered lineup value

    # Roster Builder band calibration (Handoff 12 — used ONLY by roster-evaluate, not the offseason
    # tool). The ABSOLUTE points band is sqrt((kappa * talent_quad_pts)^2 + luck_floor^2): the iced
    # players' calibrated projection sds quadratured to points, scaled by kappa, plus the irreducible
    # 82-game luck floor. kappa>1 because the season-ahead team error is dominated by a COMMON,
    # systematic component that does NOT shrink with sqrt(N) the way independent quadrature assumes —
    # fit so a 1-sigma absolute band covers ~68% of team-seasons (models_ml/project_roster_player.py).
    # The DELTA band uses RAW quadrature of only the CHANGED players (no kappa, no luck floor): that
    # common error cancels between two rosters, and a talent comparison is not a realized-season bet.
    "ROSTER_BUILDER_BAND_KAPPA": 3.50,   # (legacy) bottom-up absolute-band team multiplier
    "SEASON_LUCK_FLOOR_PTS": 6.15,       # irreducible 82-game outcome SD (Handoff-11 diagnostic)

    # Hybrid base+delta (Handoff 13 — Roster Builder only). projected_rating = R_bottomup(built) +
    # w*(R_measured - R_bottomup(actual)): anchor on the team's measured predictive rating, use player
    # projections only for the change, and fade to pure bottom-up as the roster turns over (w = retained
    # value share). R_measured = a 2-year recency-weighted, league-mean-regressed measured rating (beats
    # single-season and the bottom-up reconstruction at predicting next-year strength). Bands: the
    # absolute band interpolates the anchor/bottom-up strength error by w, in quadrature with the luck
    # floor (~68% coverage); the delta band is the changed players' projection sds plus a small
    # offset-fade term (no luck floor — a talent comparison). See docs/methodology/roster-projection.md.
    "ROSTER_BUILDER_BASE_W": [1.0, 0.5],   # R_measured recency weights (2-year)
    "ROSTER_BUILDER_BASE_K": 1.0,          # R_measured regression-to-league-mean strength
    "ROSTER_BUILDER_STRENGTH_ANCHOR": 11.45,  # anchor strength-prediction SD, points (w=1 band term)
    "ROSTER_BUILDER_STRENGTH_BU": 11.34,      # bottom-up strength SD, points (w=0 band term)
    "ROSTER_BUILDER_DELTA_OFFSET_W": 0.30,    # offset-fade uncertainty fraction in the delta band

    # Replacement-level fill for an unfilled lineup slot, or a vacated slot with no arrival. WAR is
    # value ABOVE replacement, so a replacement player is 0.0 WAR BY DEFINITION — but the slot still
    # EXISTS and is filled (a departure is never a free hole and never a dropped slot). Named so a
    # test can assert a vacated slot resolves to this baseline, not the departed player's value.
    "REPLACEMENT_WAR": 0.0,

    # Aging as a VALUE multiplier (approximation, documented loudly): aging_curves is in points/82
    # (production-shaped). We scale a player's WAR by the curve's age-t -> age-(t+1) LEVEL ratio.
    # Clamp so a sparse or extreme curve segment can't blow up or zero out a real player's value.
    "AGE_MULT_FLOOR": 0.80,
    "AGE_MULT_CEIL": 1.08,
    "AGE_CURVE_FALLBACK": {"F": "All Forwards", "D": "All Defensemen"},  # mirrors CONTRACT_VALUE

    # PROJECTION BASE (shared with the Contract Grader — both tools call compute_contract_value.
    # blended_war_rate so the same player projects to the same WAR everywhere). A player's next-season
    # value is a recency- and games-weighted blend of his last PROJ_WINDOWS single-season WARs,
    # regressed toward replacement by SAMPLE SIZE (thin samples shrink; an established track record is
    # kept). This REPLACED a per-component shrink-toward-zero that compressed every established player
    # toward replacement regardless of how stable his production was (the Byram case: 0.23 WAR three
    # years running projected to ~0.02). Anchoring to the player's own multi-season rate fixes that and
    # regresses finishing luck more honestly than a flat single-window strip (a one-year shooting spike
    # is diluted by the other seasons; a repeatable finishing skill is kept). Goalie value is carried
    # through the same blend but held FLAT (the aging curves are skater points/82); its band stays ~3x
    # a skater's because the measured goalie-rate reliability is ~0.19.
    "PROJ_WINDOWS": 5,                # single-season WAR windows feeding the blend (current heaviest)
    "WAR_SD_FALLBACK": 0.5,           # band for a tracked player whose current-season war_sd is missing

    # Chemistry overlay: the line-fit delta (projected top units vs base top units, via score_line
    # xGF%) nudges the rating, BOUNDED so a noisy chemistry read can't dominate the talent signal.
    "CHEMISTRY_ADJ_CAP": 0.06,        # goals/game, +/- cap on the chemistry term
    "CHEMISTRY_XGF_TO_GOALS": 0.30,   # maps a top-unit xGF% share delta to a goals/game nudge

    # Honest band (all in goals/game). Base value uncertainty propagates the per-slot war_sd in
    # quadrature; then we ADD band for the share of projected value from no-track-record players,
    # from goalies (value ~3x less reliable), and from roster turnover. A floor blocks false
    # precision in a quiet offseason.
    "BAND_FLOOR": 0.05,
    "BAND_NO_TRACK_W": 0.40,          # x (no-track-record value share)  -> extra band
    "BAND_GOALIE_W": 0.25,            # x (goalie value share)           -> extra band
    "BAND_TURNOVER_W": 0.015,         # x (arrivals + departures count)  -> extra band
    "NO_TRACK_RECORD_WAR_SD": 1.2,    # deliberately wide band on a replacement-level no-track player

    # Tier 1 — role/translation uncertainty for an ARRIVAL. A just-acquired player's projection still
    # reflects his OLD-team usage/role until he plays for the new club; that uncertainty belongs in the
    # BAND, not in a biased-down point estimate. We widen each arrival's war_sd by this much in
    # quadrature, which flows into both his per-player UI band and the team forecast band. A holdover
    # (same club) is untouched. Provisional default; to be calibrated against the backtest in Tier 2.
    "ARRIVAL_TRANSLATION_SD": 0.35,

    # Deep-offseason / negligible-moves guard: when the updated lineup ~ the base lineup (next
    # season's roster not yet published, or a genuinely quiet offseason) the verdict says so
    # explicitly instead of rendering a confident near-zero forecast (no-zeroed-empty-states).
    "NEGLIGIBLE_NET_WAR": 0.5,        # |net lineup WAR delta| at/below this AND ...
    "NEGLIGIBLE_MOVES": 2,            # ... arrivals+departures at/below this -> "no material moves"

    # ── Position-aware line assignment (Roster Builder auto-optimize + calibration) ──────────────
    # _ice_from_pool seats forwards by solving an ASSIGNMENT problem over (forward, forward-slot):
    #   value(player, slot) = projected_war - off_position_penalty(player, slot)
    # The penalty SHAPES THE ASSIGNMENT ONLY — it decides who sits where, biasing a locked center to a
    # C slot and a winger to his side. lineup_value and the team WAR total still sum RAW projected_war,
    # never net of penalties (a player's value does not shrink because he is off-position; the tool just
    # prefers not to place him there). Effective position (C/L/R/F_FLEX, from player_effective_position)
    # drives the bins; a locked C at a wing (or a locked W at C) pays OFF_POSITION_PENALTY_CW, a winger
    # on his off side pays WING_SIDE_PENALTY, an F_FLEX pays nothing. WAR units, tune-friendly.
    "OFF_POSITION_PENALTY_CW": 0.35,  # locked C iced at a wing slot, or locked W iced at C
    "WING_SIDE_PENALTY": 0.05,        # winger iced on the wrong side (L on RW, R on LW)

    # ── Deployment-aware line seeding (Phase 2) ──────────────────────────────────────────────────
    # Before the assignment, the builder SEEDS observed units: an int_line_seasons trio/pair (or a
    # team_current_lines unit in-season) whose full member set is present + unplaced in the pool and
    # shared >= this many 5v5 minutes is placed intact, in descending shared minutes. This reproduces
    # real deployment (e.g. a team that splits its two stars at 5v5) instead of WAR-stacking. The
    # table's own floor is 30 minutes; we require a higher bar so only genuinely established units seed.
    # Sources are MERGED (a small, documented deviation from strict prefer-current/fall-back-to-season):
    # int_line_seasons full-season units (floor below) plus team_current_lines last-10-games units at the
    # proportional CURRENT floor. Sorted by shared minutes, season units (larger) seed first, so recent
    # deployment only fills gaps a season unit does not — a strict "prefer current" rule would seed almost
    # nothing in the offseason (10-game shared minutes never clear a season-scale floor).
    "LINE_SEED_MIN_5V5_MINUTES": 100.0,          # int_line_seasons (full season)
    "LINE_SEED_MIN_5V5_MINUTES_CURRENT": 30.0,   # team_current_lines (last 10 games)
}

assert ROSTER_FORECAST["GOALS_PER_WIN"] == GAR_CONFIG["GOALS_PER_WIN"], (
    "ROSTER_FORECAST GOALS_PER_WIN must match GAR_CONFIG so a projected WAR delta and the team "
    "rating share one goals scale.")


# ── Effective position (player_effective_position precompute) ────────────────────────────────────
# The NHL roster feed lists a player's NOMINAL position (e.g. J.T. Compher as LW), which is often not
# the position he actually plays. Faceoff VOLUME is the cleanest deployment signal for the C/W split:
# a center takes draws every shift, a winger almost never. player_effective_position classifies each
# forward from his last-two-seasons faceoffs-per-game (regular season + playoffs, GP-weighted):
#   fo_per_gp >= FO_CENTER_PER_GP  (>= FO_MIN_GP games) -> effective C, locked
#   fo_per_gp <= FO_WINGER_PER_GP  (>= FO_MIN_GP games) -> effective winger, locked (side: listed side
#                                     if listed L/R, else by handedness — L shot -> L, R shot -> R)
#   otherwise / thin sample / rookie -> F_FLEX (fills any forward slot, no off-position penalty)
#   no faceoff rows at all -> absent from the table; the builder falls back to the listed position.
# Defensemen/goalies pass through unchanged (effective = listed, locked). These are STARTING points —
# validate the disagreement list (calibrate/precompute prints it) and tune if a known winger flips.
EFFECTIVE_POSITION = {
    "FO_WINDOW_SEASONS": 2,     # last N seasons of faceoff data, GP-weighted
    "FO_CENTER_PER_GP": 7.0,    # >= this faceoffs/game -> effective center
    "FO_WINGER_PER_GP": 2.5,    # <= this faceoffs/game -> effective winger
    "FO_MIN_GP": 10,            # games in the window required to LOCK a C/W classification
}


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

# Surplus leaderboards (best-value / most-overpaid) rank on CAP-SHARE RATE (per-year surplus as a
# share of the cap — era-neutral, bounded, the unit the market curve is built in), NOT on PV dollars
# (buries cheap elite deals under long veteran deals) and NOT on surplus-to-cost ratio (a sub-$1M cap
# hit blows the ratio up and turns the board into an ELC leaderboard). To take a board slot a contract
# must also clear a minimum ABSOLUTE PV surplus so trivial short/cheap deals don't occupy a top-10 row;
# below-floor contracts are still graded and shown on player pages, they just don't rank. $4M sits just
# above the non-ELC |PV surplus| median (~$3.1M), dropping the trivial bottom-half while every genuine
# board bargain (top-10 are $20M+) clears it ~5x; currently non-binding for the top-10 (the rate sort
# alone is clean) — a documented safeguard, not a tuned cutoff. A judgment lever; revisit per season.
LEADERBOARD_MIN_SURPLUS = 4_000_000

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
    # TWO-ANCHOR PIVOT (replaces the intercept-only MARKET_QUANTILE shift). The curve is pinned through
    # two empirical points on the NON-ELC (free-market) sample: a LOW anchor = the median going rate at
    # the median WAR (so the median market deal's production is worth ~what it's paid -> grades C/fair),
    # and a HIGH anchor = observed elite pay in a high-WAR band (so stars stay priced right and the
    # elite guard passes). Two anchors give the slope a degree of freedom the single quantile lacked:
    # the curve ROTATES to lower the middle while holding the top, which a uniform shift cannot do. Each
    # anchor is the median of a WAR-percentile BAND (not a single quantile point) so a thin tail isn't
    # pinned by one or two contracts. MARKET_QUANTILE is retired (no longer read by fit_market_curves).
    "MARKET_ANCHOR_LO": (0.30, 0.50),     # mid-WAR band -> median going rate (lowest non-ELC median)
    "MARKET_ANCHOR_HI": (0.85, 0.97),     # high-WAR band -> observed elite pay (holds the top)
    "MARKET_QUANTILE": 0.65,              # retired; kept for reference / older model versions
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
    # Pending RFAs are sourced as their own feed (contracts - rfas.csv -> raw_contracts_rfa) and carry
    # a PROJECTED next deal (proj_cap / proj_term), unioned into mart_player_contracts with
    # contract_status='rfa_projected'. They are valued by the same projection as a signed player (over
    # the projected term); the only special handling is capping their confidence at medium (the cost
    # is projected, not signed) — see compute().
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

# --- Draft Value tool (Handoff 5): empirical pick-value curve + the "85%" theory test ----------
# All constants for the Phase B model chain (fit_pwar_anchor -> compute_pwar -> int_draft_player_value
# -> fit_pick_value -> run_draft_theory) live here so SQL/Python never hardcode them.
DRAFT_VALUE = {
    "RANDOM_SEED": 7,
    # --- Currency: realized value in the SAME WAR units as player_gar ---
    "ANCHOR_VERSION": "pwar_anchor_v1",
    "PWAR_VERSION": "player_pwar_v1",
    # Single-season GAR windows where real WAR AND box production both exist (the anchor overlap).
    "ANCHOR_SEASONS": ["2021-22", "2022-23", "2023-24", "2024-25", "2025-26"],
    # Box production reaches back to here; pre-overlap seasons are BACK-CAST (estimated), wider band.
    "PWAR_START_SEASON": "2010-11",
    "BACKCAST_SD_MULT": 1.6,        # inflate pwar_sd for back-cast (pre-2021-22) seasons
    "GAMES_FULL_82": 82,            # per-82 normalization for points
    # --- Evaluation window / universe ---
    "EVAL_WINDOW_YEARS": 7,         # first 7 NHL-eligible post-draft seasons (decision 2.2)
    "EVAL_CLASS_MIN": 2010,         # classes fully observable under the 7yr window (decision 2.2)
    "EVAL_CLASS_MAX": 2018,
    "BACKFILL_CLASS_MIN": 2005,     # ingested floor (older classes shown but not in the headline)
    "REGULAR_GP": 200,             # "became a regular" threshold, career GP (literature; state it)
    # --- Anchor model (LightGBM monotone, with a linear baseline for comparison) ---
    # The original 0.90 Spearman target is NOT achievable from long-history box stats: WAR's value
    # also lives in RAPM defense, penalties, and deployment, none of which appear in the box score,
    # and the anchor may only use signals reaching 2010-11 so it can back-cast. Achieved (LOSO):
    # R2 ~0.54, Spearman ~0.59 (all) / ~0.76 (regulars). Accepted as a labeled wide-band estimate
    # (decision 2026-06-25): the pick-value curve's shape is dominated by the EXACT never-NHL=0 rate
    # measured in Phase A, and per-player pWAR noise averages out at the slot level. This floor is a
    # sanity check (catches a broken anchor), not the original aspiration.
    "MIN_SPEARMAN": 0.55,          # sanity floor on fitted-vs-real WAR Spearman (overlap, LOSO)
    # NHL game-type filter applied in every pWAR aggregation (mart includes preseason 01 + international
    # 09/04/19/.. games that player_gar excludes; keep only regular season 02 + playoffs 03).
    "NHL_GAME_TYPES": ["02", "03"],
    "LGB_PARAMS": {
        "objective": "regression", "metric": "l2", "learning_rate": 0.05,
        "num_leaves": 16, "min_data_in_leaf": 40, "feature_fraction": 0.9,
        "bagging_fraction": 0.8, "bagging_freq": 1, "verbose": -1, "seed": 7,
    },
    "LGB_NUM_ROUNDS": 600,
    # --- Empirical pick-value curve (fit_pick_value) ---
    # Loess is applied in LOG space (the curve spans ~2 orders of magnitude; linear loess crushes the
    # steep top-pick premium). frac=0.10 preserves #1's premium while smoothing the noisy ~9-sample
    # tail; the smoothed mean is forced monotone non-increasing. The resulting career-extrapolated #1
    # (~18 WAR) validates against the old hand-set slot_war proxy (V(1)≈22).
    "LOESS_FRAC": 0.10,            # loess span across overall pick number (log space)
    "MAX_OVERALL": 224,            # curve domain (deepest modern draft slot)
    "CURVE_VERSION": "pick_value_curve_v1",
    # --- Career extrapolation (decision 2.5): windowed -> whole-career via the aging-curve tail ---
    "CAREER_EXTRAP_FACTOR": None,  # computed from aging_curves at fit time; None = derive, not hardcode
    "THEORY_VERSION": "draft_value_v1",
    "DOLLARS_PER_WAR": 3_000_000,  # mirror FUTURES for dollar display consistency
}

# --- Trade-outcome retrospective (Handoff 5, Phase D): who won a past trade, in realized WAR ----
# A retrospective on realized outcomes, NOT a grade of the decision at the time (the information then
# was different). Two lenses per asset; netted per team per trade, bands in quadrature (reusing the
# trade engine's propagation). All constants here so nothing is hardcoded in the job.
TRADE_OUTCOMES = {
    "MODEL_VERSION": "trade_outcomes_v2",   # v2: incomplete trades graded on realized-to-date + widened band
    # The one knob: how many seasons of realized value to count after a trade (player tenure cap). 5
    # balances "enough career to judge" against the recency of new trades. Distinct from the Draft Value
    # tool's separate fixed 7-year curve window (EVAL_WINDOW_YEARS) — do not conflate. State it in the doc.
    "REALIZED_HORIZON_YEARS": 5,
    # Maturity-band widening: a trade whose horizon has not fully elapsed is still GRADED on its
    # realized-to-date value (never zeroed, never projected), but its net band is widened to reflect the
    # value still to accrue. The added uncertainty (in quadrature) is MATURITY_BAND_SCALE * |net| *
    # (REALIZED_HORIZON_YEARS - years_elapsed) / REALIZED_HORIZON_YEARS, so a trade one season in is far
    # wider than one four seasons in, and a settled trade is unchanged. This is honest uncertainty on
    # what HAS happened, not a forecast of what will.
    "MATURITY_BAND_SCALE": 1.0,
    "PICKS_PER_ROUND": 32,         # round midpoint overall = (round-1)*32 + 16 (mirror FUTURES)
    "DOLLARS_PER_WAR": 3_000_000,  # for dollar display alongside WAR (mirror FUTURES)
}

# --- Trade board / GM layer (Handoff 6): entity-first trade-outcome surfaces ----------------------
# Read-time composition over nhl_models.trade_outcomes + stg_gm_tenures; all thresholds here so no
# literals scatter into SQL/TSX. WAR throughout (same units as mart_tradeable_assets).
TRADE_BOARD = {
    # Three-tier verdict (realized-only): decisive when |margin| - band_hw >= DECISIVE_WAR (the only
    # claim the band must clear); "even" when |margin| < EDGE_FLOOR_WAR (the realized value came out
    # level); edge otherwise (the sign is known and exceeds the floor but doesn't clear the band — a
    # directional-but-uncertain call). NOTE: the third tier was renamed too_close -> even (label only;
    # the EDGE_FLOOR_WAR threshold and all band/verdict math are unchanged).
    "DECISIVE_WAR": 2.0,       # |margin| - band_hw >= this => a decisive win
    "EDGE_FLOOR_WAR": 0.5,     # |margin| < this => "even" (realized value came out level)
    "ARCHETYPE_SHARE": 0.70,   # a side is "player-" or "pick-"heavy at >= this share of received value
    "BLOCKBUSTER_WAR": 8.0,    # total WAR moved across the trade >= this => blockbuster
    "WAR_DOMAIN": 12.0,        # balance-bar x-axis domain (+/-), front end mirrors this
    "REALIZED_HORIZON_YEARS": 5,   # mirrors TRADE_OUTCOMES; for "through year k of 5" labels
    # Confidence-aware entity ranking (Teams & GMs tab). The point-estimate net records are mostly inside
    # band noise, so the ranked list is SHRUNK rather than a false 1..N ordering. band_hw is the native
    # uncertainty unit (a mixed empirical-pick-p10/p90 + player-sd interval) — NO normal-interval factor.
    #   z_i      = net_i / band_hw_i                                  (standardized distance from even)
    #   mu       = mean(net_i) for this kind (~0)
    #   tau2     = max(0, sample_var(net_i) - mean(band_hw_i^2))      (estimated true between-entity var)
    #   B_i      = tau2 / (tau2 + band_hw_i^2)                        (shrinkage weight in [0,1])
    #   rank_i   = mu + B_i*(net_i - mu)                              (shrunk record = default sort key)
    # method "eb" (default) uses the above; "net_minus_k" uses sign(net)*max(0,|net|-K*band_hw).
    "RANKING": {
        "method": "eb",                 # "eb" | "net_minus_k"
        "uncertainty_unit": "band_hw",
        "K": 1.0,                        # used only by net_minus_k
        "MIN_SETTLED": 5,               # below this -> low_n flag (muted in UI), never dropped
        "CLEAR_Z": 2.0,                 # |z| >= this => separation "clear"
        "LEANS_Z": 1.0,                 # |z| >= this => "leans"; else "noise"
    },
}
GM_LAYER = {
    "TRANSITION_WINDOW_DAYS": 14,   # trade within this many days of a tenure boundary => attribution flagged
}

# --- Player Verdict (composed scouting read; Gemini narrates a deterministic two-horizon payload) ---
VERDICT = {
    "MODEL_VERSION": "verdict_v1",
    "LLM_MODEL": "gemini-2.5-flash-lite",   # stable; the -exp alias was retired. Bump to gemini-2.5-flash on a paid key.
    "IDENTITY_WINDOW": "2023-24_2025-26",   # the stored 3-year window the identity block reads
    # Identity confidence from career games played (shrinkage: short sample -> hedged language).
    "CONF_HIGH_GAMES": 250,
    "CONF_MED_GAMES": 100,
    # Durable-trait selection is a BAND, not a hard top-N: take the player's top impact dim as the
    # anchor and keep every dim within DURABLE_BAND points of it (and not below DURABLE_FLOOR), so a
    # value spread across several mid-high traits is described as a spread, not collapsed to one spike
    # (and a characterizing trait is not dropped by a one-point percentile edge). EV impact (off/def)
    # gets a small ordering bonus over special teams so the lead trait characterizes, not just ranks.
    "DURABLE_BAND": 15,        # points below the anchor still counted as durable
    "DURABLE_FLOOR": 60,       # never call a sub-median dim a durable strength
    "DURABLE_EV_BONUS": 3,     # ordering nudge for EV (off/def) impact over special teams on near-ties
    "DURABLE_MAX": 4,          # at most this many durable traits (there are only four impact dims)
    # Horizon divergence: flag (neutrally) when current production outruns 3yr play-driving impact by
    # at least this many percentile points (or vice versa). Never written as the model being "wrong".
    "HORIZON_GAP_PTS": 20,
    "TOP_TRAITS_N": 3,
    "WATCH_OUTS_N": 2,
    # Hard cap on the long read; a verdict exceeding this is regenerated, then dropped.
    "MAX_SENTENCES": 4,
    # Agreement between the two value lenses (production vs play-driving), in percentile points.
    "AGREE_GAP_PTS": 15,
    # Consistency checker tolerance: a cited number must match the payload value within this
    # absolute tolerance (after both are normalised to the same unit, e.g. 0-100 percentiles).
    "CHECK_TOL": 1.0,
    "MAX_REGEN_ATTEMPTS": 4,   # regenerate on a failed check up to this many times, then drop
    "BACKFILL_CONCURRENCY": 8,  # default parallel workers for --full (Gemini calls are I/O-bound)
    "PERSIST_BATCH": 40,        # checkpoint: flush completed verdicts every N (crash-safe, resumable)
}
