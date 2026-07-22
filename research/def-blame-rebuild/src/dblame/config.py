"""Defensive Blame · Possession-Level Rebuild — config, paths, framing.

A from-scratch rebuild. Every prior version (F27/F28) assigned blame at the INSTANT OF THE SHOT and
forced each goal to distribute exactly one unit across five defenders. That model failed (split-half ~0,
eye test backwards, median max-share 0.20 = forced even split). This rebuild abandons the snapshot:
defense is a PROCESS over the whole possession, blame lives in what a defender DID over time, blame is
ABSOLUTE (a goal may assign near-zero total blame if no coverage actually broke), and only even-strength
5v5 goals are considered.

Scheme-free by design (avoids F26): we never assert a defender's assignment or "where he should have
been". We measure CHANGE in his OWN coverage state over time — a threat he was managing becoming
dangerous because of his movement — which needs only tracking, not the playbook.

FRAMING RULE (fixed, code-enforced): outputs are a DESCRIPTIVE per-possession coverage-failure log and an
ABSOLUTE blame rate over 5v5 goals-against, never a claim of certain fault on any single goal and never a
full defensive rating. BANNED as a single-goal verdict (checked outside the quoted framing): "bad
defense", "blame", "fault", "out of position", "mistake". ("blame" is permitted as the metric name only;
the guard allows it up to its count inside FRAMING.)
"""
from __future__ import annotations

from pathlib import Path

BANNED_WORDS = ["bad defense", "fault", "out of position", "mistake"]  # "blame" is the metric name; guarded separately
FRAMING = ("Outputs are a DESCRIPTIVE per-possession coverage-failure log and an ABSOLUTE blame rate over "
           "5v5 goals-against, never a claim of certain fault on any single goal and never a full defensive "
           "rating. We measure change in a defender's own coverage state over time, not scheme or where he "
           "should have been (avoids F26). Banned as a single-goal verdict: bad defense, fault, out of "
           "position, mistake.")

ROOT = Path(__file__).resolve().parents[2]
NIR = ROOT.parents[1]
DATA = ROOT / "data"
PARQUET = DATA / "parquet"
CACHE = DATA / "cache"
REPORTS = ROOT / "reports"

# read-only reuse (Rule 7b) — timestamped in Link 0
GT_ROOT = NIR / "research" / "goal-tracking"
GT_FUSED = GT_ROOT / "data" / "parquet" / "fused_goals.parquet"
GT_EVENTS = GT_ROOT / "data" / "parquet" / "goal_events.parquet"
GT_FRAMES_DIR = GT_ROOT / "data" / "cache"       # frames_<season>.parquet
DEFSCHEME_PRIM = NIR / "research" / "def-scheme" / "data" / "parquet"   # def_prim_<season>.parquet (validation)
ATLAS = NIR / "research" / "deployment-atlas" / "data" / "parquet"
ATLAS_STINTS = ATLAS / "stints.parquet"
ATLAS_5V5 = ATLAS / "player_5v5.parquet"
ROSTERS = ATLAS / "rosters.parquet"
SA_KEYFILE = NIR / "secrets" / "nhl-intel-sa.json"
BQ_PROJECT = "nhl-intel-498216"

SEED = "20260714f"
SEED_INT = 20260714
SEASONS = ("2023-24", "2024-25", "2025-26")

# --- geometry constants (rink) ---
HZ = 10.0
NET_X = 89.0            # net at x = ±89 in standardized coords
SLOT_X = 80.0           # net-front / high-danger reference (just above the crease)
SLOT_Y = 0.0

# --- possession window ---
MAX_WINDOW_S = 12.0     # cap window length; longer buildups truncated to final approach
MIN_WINDOW_S = 0.6      # a window shorter than this is flagged (turnover chaos / no clean buildup)

# --- coverage-failure event calibration (percentiles; footage reported once, then frozen in Link 1) ---
MANAGE_MIN_S = 1.0      # E1: sustained stretch a defender must have been nearest+goal-side to count as "managing"
P_SEP_GROWTH = 0.80     # E1: separation growth in final approach past this percentile = containment loss
P_OPEN_RELEASE = 0.80   # E1/E3: attacker "open" at release = nd_scorer separation at/above this percentile
P_VACATE = 0.80         # E2: increase in dist-to-danger while pursuing puck past this percentile = overshoot
FINAL_APPROACH_S = 2.0  # window tail used for "final approach" separation and release openness
