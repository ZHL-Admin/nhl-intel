"""Goalie-probe — shared config, paths, fixed thresholds. Read-only over production and prior research.

THE DENOMINATOR IS THE POINT: every save-performance figure is computed over SHOTS FACED (SOG + goals),
never over goals alone. Tracking enrichment (Stage 0 fused_goals) is goals-only and DESCRIBES goals; it
is never used as a rate without the shot denominator.
"""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]            # research/goalie-probe
NIR = ROOT.parents[1]
DATA = ROOT / "data"
PARQUET = DATA / "parquet"
CACHE = DATA / "cache"
REPORTS = ROOT / "reports"

# read-only inputs (prior research / production)
ATLAS_PARQUET = NIR / "research" / "deployment-atlas" / "data" / "parquet"
SHOT_XG = ATLAS_PARQUET / "shot_xg.parquet"
STINTS = ATLAS_PARQUET / "stints.parquet"
GT_DIR = NIR / "research" / "goal-tracking" / "data"
GT_FUSED = GT_DIR / "parquet" / "fused_goals.parquet"
GT_MECH = GT_DIR / "parquet" / "mechanism_flags.parquet"
GT_FRAMES_DIR = GT_DIR / "cache"            # frames_2023_24.parquet etc. (read-only reuse)

SA_KEYFILE = NIR / "secrets" / "nhl-intel-sa.json"
BQ_PROJECT = "nhl-intel-498216"
STAGING = "nhl_staging"

SEED = "20260714b"
SEED_INT = 20260714            # numpy rng needs an int; the 'b' tags this probe's run in the report

# tracking-window seasons (fusion); the spine itself runs the full available span
TRACKING_SEASONS = ("2023-24", "2024-25", "2025-26")

# --- SPINE definition (fixed, documented) ---
# Unblocked shots ON GOAL = shot-on-goal (saves) + goal (scored). Missed (wide) and blocked are excluded
# by "unblocked, on goal" -> the shots-faced denominator.
SHOT_EVENTS = ("shot-on-goal", "goal")

# --- fixed bucket thresholds (frozen BEFORE results) ---
# danger tier from per-shot xG (Atlas shot_xg): standard danger bands
DANGER_BANDS = (("low", 0.0, 0.05), ("mid", 0.05, 0.15), ("high", 0.15, 1.01))
# shot region from distance to net d = sqrt((89-|x|)^2 + y^2), a distance-binned slot/point proxy
REGION_BANDS = (("inner_slot", 0.0, 20.0), ("outer_slot", 20.0, 45.0), ("point", 45.0, 1e9))
# shot_type grouping
SHOT_TYPE_MAP = {"wrist": "wrist", "snap": "snap", "slap": "slap", "backhand": "backhand",
                 "tip-in": "deflection", "deflected": "deflection", "bat": "deflection",
                 "wrap-around": "other", "poke": "other", "between-legs": "other", "cradle": "other"}
REBOUND_SECONDS = 3.0          # a shot within this of a prior on-goal shot by the same team = rebound

# --- statistics (fixed) ---
EB_PRIOR_SHOTS = 200           # EB prior strength for save% shrinkage (pseudo-shots), by bucket
MIN_BUCKET_SHOTS = 50          # G1.3 minimum-sample gate: no per-goalie-bucket claim below this
STABILITY_MIN_SHOTS = 200      # G1.4: goalies with >= this many shots faced in the bucket
N_PERM = 2000
SPLIT_HALF_BAR = 0.30
CI = (0.05, 0.95)              # 90% CI

# --- G2 behavior axes ---
G2_EW_WINDOW = 10              # frames (1.0 s) for east-west net-coverage
REBOUND_MIN_SAVES = 200       # denominator gate for the rebound-control axis (saves)
GOALS_AXIS_MIN = 80           # min goals-against for a goals-only axis (depth/lat/unset)
EW_AXIS_MIN = 40              # min east-west goals for the east-west coverage axis
