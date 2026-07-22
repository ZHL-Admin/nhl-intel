"""Defensive Breakdown probe — config, paths, the framing rule.

FRAMING RULE (fixed): outputs are a DESCRIPTIVE per-goal accountability log and a culprit RATE over
goals-against (a defensible denominator), never a claim of certain fault on any single goal and never a
full-defensive rating. Permitted language: "was the nearest uncontested defender", "coverage collapsed
to his side", "culprit rate". BANNED as a verdict on one goal (enforced by a code-level test, outside
quoted definitions): "bad defense", "blame", "fault", "out of position", "mistake".

This probe avoids the failed def-scheme project (F26): NO scheme labels, NO team norms, NO "where he
should have been". Every signal is anchored to what the puck/players actually did relative to the known
scorer.
"""
from __future__ import annotations

from pathlib import Path

# banned verdict words (checked in reports outside the quoted framing definition)
BANNED_WORDS = ["bad defense", "blame", "fault", "out of position", "mistake"]
FRAMING = ("Outputs are a DESCRIPTIVE per-goal accountability log and a culprit RATE over goals-against, "
           "never a claim of certain fault on any single goal and never a full-defensive rating. "
           "Permitted: 'was the nearest uncontested defender', 'coverage collapsed to his side', "
           "'culprit rate'. Banned as a single-goal verdict: bad defense, blame, fault, out of position, "
           "mistake. No scheme labels, no team norms, no 'where he should have been' (avoids F26).")

ROOT = Path(__file__).resolve().parents[2]
NIR = ROOT.parents[1]
DATA = ROOT / "data"
PARQUET = DATA / "parquet"
CACHE = DATA / "cache"
REPORTS = ROOT / "reports"

# read-only reuse
GT_ROOT = NIR / "research" / "goal-tracking"
GT_SRC = GT_ROOT / "src"
GT_FUSED = GT_ROOT / "data" / "parquet" / "fused_goals.parquet"
GT_EVENTS = GT_ROOT / "data" / "parquet" / "goal_events.parquet"
GT_FRAMES_DIR = GT_ROOT / "data" / "cache"
DEFSCHEME_PRIM = NIR / "research" / "def-scheme" / "data" / "parquet"     # def_prim_*.parquet
ATLAS_STINTS = NIR / "research" / "deployment-atlas" / "data" / "parquet" / "stints.parquet"
ROSTERS = NIR / "research" / "deployment-atlas" / "data" / "parquet" / "rosters.parquet"
SA_KEYFILE = NIR / "secrets" / "nhl-intel-sa.json"
BQ_PROJECT = "nhl-intel-498216"

SEED = "20260714d"
SEED_INT = 20260714
SEASONS = ("2023-24", "2024-25", "2025-26")

# --- signal parameters ---
# CALIBRATION RULE (owner, Link-1 gate): every distance threshold is a PERCENTILE of that measure's own
# distribution across all qualifying goals, not a guessed foot value. "breakdown" = unusual relative to
# how goals normally look. This makes the metric inherently COMPARATIVE (a fixed fraction of goals always
# sits in the top percentile), so culprit-rate ranks defenders against each other, not against an absolute.
HZ = 10.0
DEF_NET_X = 89.0
WIN_3S = 30            # frames
WIN_1_5S = 15
WIN_1S = 10
ON_PUCK_FT = 8.0      # nearest-defender-to-puck to be "on the puck" (definitional, not a threshold)
P_OPEN = 0.80         # B: scorer "open" = openness at/above this percentile of the openness distribution
P_LANE = 0.80         # B: "uncontested lane" = lane distance at/above this percentile
P_FLOAT = 0.80        # A(ii): "floating" = off-puck dist to BOTH nearest-attacker and net-front >= this pct
CROSS_SLOT_DY = 15.0
HARD_CULPRIT = 0.40    # continuous share >= this = hard culprit flag
B_WEIGHT = 0.75        # B-primary (Signal A is now ONLY the off-puck floating component A(ii))
A_WEIGHT = 0.25
