"""Defensive Scheme & Role — shared config, paths, THE TWO LAWS.

LAW 1 · GOALS-ONLY. The tracking corpus contains only goal buildups; there is no tracked non-goal. This
project INFERS team scheme and player role from goal geometry and measures deviation from the team's own
norm. It never claims "this positioning caused the goal" nor compares against non-goal plays it does not
have. The scheme-norm is learned from goals and is therefore a norm ON GOALS.

LAW 2 · NO FAULT LANGUAGE. "out of position", "blame", "fault", "mistake", "responsible" never appear.
The only permitted claim is DEVIATION FROM THE TEAM'S OWN STRUCTURAL NORM — a descriptive geometric fact,
never a verdict of error. Scheme vs individual error cannot be separated per-goal; only aggregate
deviation tendency is claimed.
"""
from __future__ import annotations

from pathlib import Path

LAW_1 = ("LAW 1 · GOALS-ONLY. The tracking corpus contains only goal buildups; there is no tracked "
         "non-goal. This project INFERS team scheme and player role from goal geometry and measures "
         "deviation from the team's own norm. It never claims 'this positioning caused the goal' nor "
         "compares against non-goal plays it does not have. The scheme-norm is a norm ON GOALS.")
LAW_2 = ("LAW 2 · NO FAULT LANGUAGE. 'out of position', 'blame', 'fault', 'mistake', 'responsible' never "
         "appear. The only permitted claim is DEVIATION FROM THE TEAM'S OWN STRUCTURAL NORM — a "
         "descriptive geometric fact, never a verdict of error. Scheme vs individual error cannot be "
         "separated per-goal; only aggregate deviation tendency is claimed.")

ROOT = Path(__file__).resolve().parents[2]            # research/def-scheme
NIR = ROOT.parents[1]
DATA = ROOT / "data"
PARQUET = DATA / "parquet"
CACHE = DATA / "cache"
REPORTS = ROOT / "reports"

# read-only reuse (prior research / production)
GT_ROOT = NIR / "research" / "goal-tracking"
GT_SRC = GT_ROOT / "src"                               # import gtrack.api from here
GT_FUSED = GT_ROOT / "data" / "parquet" / "fused_goals.parquet"
GT_EVENTS = GT_ROOT / "data" / "parquet" / "goal_events.parquet"
GT_FRAMES_DIR = GT_ROOT / "data" / "cache"            # frames_2023_24.parquet etc.
ATLAS_STINTS = NIR / "research" / "deployment-atlas" / "data" / "parquet" / "stints.parquet"
SYSFX_REGIME = NIR / "research" / "system-effects" / "data" / "parquet" / "regime_ledger.parquet"
SYSFX_FP = NIR / "research" / "system-effects" / "data" / "parquet" / "team_season_fp.parquet"
CHEM_PAIRS = NIR / "research" / "chemistry" / "data" / "parquet"   # pairs_corpus (located in Phase 0.2)
SA_KEYFILE = NIR / "secrets" / "nhl-intel-sa.json"
BQ_PROJECT = "nhl-intel-498216"

SEED = "20260714c"
SEED_INT = 20260714

SEASONS = ("2023-24", "2024-25", "2025-26")

# --- defensive-frame geometry constants (defended net normalized to +x) ---
DEF_NET_X = 89.0             # after attack-direction normalization the DEFENDED net sits at (+89, 0)
BLUE_LINE = 25.0            # D-zone = x_norm >= +25 ; neutral = -25..+25
LOWHIGH_X = 54.0           # low (near net) = x_norm >= 54 ; high (toward blue) = 25..54
HZ = 10.0
