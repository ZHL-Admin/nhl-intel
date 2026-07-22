"""Goal-Tracking program — shared configuration, paths, constants, and THE TWO LAWS.

This module holds no logic beyond path/constant definitions so every phase reads one source of
truth. Paths are all relative to the goal-tracking project root; nothing here imports production
or other-research code. BigQuery reads are cached to ``data/cache`` once per stage.
"""
from __future__ import annotations

from pathlib import Path

# --- THE TWO LAWS (verbatim; re-exported into every report, API docstring, user-facing caveat) ---
LAW_1 = (
    "LAW 1 · GOALS-ONLY. Every tracked sequence ended in a goal; there is no tracked non-goal in this "
    "data. You may DESCRIBE and ATTRIBUTE what happened on goals and build goal-as-the-unit "
    "measurements. You may NEVER make a predictive or comparative 'what causes goals / what wins' claim "
    "from this data alone."
)
LAW_2 = (
    "LAW 2 · FUSION. Tracking is faithful on position (scorer within stick-reach 88% in validation) and "
    "weak on exact stick attribution in traffic (38%). Attribution NEVER comes from geometry alone: the "
    "recorded scorer/assisters from stg_play_by_play are the anchor; tracking supplies context around "
    "those labels. Cluster-level credit is acceptable; deflection micro-mechanics may remain fuzzy and "
    "are labeled as such."
)

# --- paths ---
ROOT = Path(__file__).resolve().parents[2]           # research/goal-tracking
NIR = ROOT.parents[1]                                 # repo root
DATA = ROOT / "data"
PARQUET = DATA / "parquet"
CACHE = DATA / "cache"
REPORTS = ROOT / "reports"

# read-only frozen research inputs (rule-4)
ATLAS_PARQUET = NIR / "research" / "deployment-atlas" / "data" / "parquet"
STINTS = ATLAS_PARQUET / "stints.parquet"
PLAYER_5V5 = ATLAS_PARQUET / "player_5v5.parquet"
RAPM_VARIANT = ATLAS_PARQUET / "rapm_variant.parquet"
SYSFX_PARQUET = NIR / "research" / "system-effects" / "data" / "parquet"
TEAM_SEASON_FP = SYSFX_PARQUET / "team_season_fp.parquet"
REGIME_LEDGER = SYSFX_PARQUET / "regime_ledger.parquet"
ROLEFIT_PROFILES = NIR / "research" / "role-fit-probe" / "data" / "parquet" / "profiles_rich"
REPLAYPROBE_SRC = NIR / "research" / "replay-probe" / "src"   # reuse the validated reconstruction

# BigQuery (read-only; own creds, no atlas import)
SA_KEYFILE = NIR / "secrets" / "nhl-intel-sa.json"
BQ_PROJECT = "nhl-intel-498216"
STAGING = "nhl_staging"
RAW = "nhl_raw"

# --- fixed reproducibility ---
SEED = 20260714

# --- fixed physical/geometry constants (net box inherited from validated replay-probe reconstruction) ---
NET_X = 88.5                 # goal line |x_std|~89
NET_BACK = 93.0             # back of the net; beyond = behind-net / end boards
NET_Y_HALF = 3.5            # half net width
BLUE_LINE = 25.0            # attacking blue line at |x_std|=25
CREASE_CENTER_X = 89.0      # crease center on the goal line
LEFT_POST_Y = -3.0
RIGHT_POST_Y = 3.0

# --- fixed Stage-0 reconstruction parameters (handoff 0.2/0.3; may differ from replay-probe defaults;
#     the difference is surfaced in reports/stage0.md, NOT silently applied) ---
CARRY_RADIUS_FT = 5.5        # possession carrier = nearest skater within this (handoff: "within 5.5 ft")
LOOSE_GAP_MAX = 4            # frames of loose puck bridged within one possession (hysteresis, as in replay-probe)
FLIGHT_SPEED_FPS = 40.0      # release detector: puck flight speed threshold, ft/s (handoff)
FLIGHT_MIN_FRAMES = 2        # sustained >= this many frames (handoff)
CROWD_RADIUS_FT = 5.5        # bodies within this of the puck at release = crowd (c_crowd, handoff 0.3)
SCREEN_CREASE_RADIUS_FT = 10.0   # screen bodies must also be within this of crease center
DUMP_MIN_SECONDS = 0.5       # entry_type=dumped: no carrier within 5.5ft for >= this after crossing
RUSH_FLAG_SECONDS = 6.0      # rush_flag = entry_to_goal <= this (frozen after sensitivity table)

# --- 10 Hz honesty: smoothing (global rule) ---
HZ = 10.0
SAVGOL_WINDOW = 7            # 0.7s
SAVGOL_POLYORDER = 2
FALLBACK_ROLL_WINDOW = 5     # short-track fallback: centered rolling mean

# --- seasons present in the corpus ---
SEASONS = ("2023-24", "2024-25", "2025-26")
EXPECTED_FRAME_ROWS = 44_721_173
EXPECTED_GOALS = 25_946
EXPECTED_GOALS_BY_SEASON = {"2023-24": 8_618, "2024-25": 8_635, "2025-26": 8_693}
EXPECTED_RELEASE_ROWS = 326_456
