"""Validation basket for contract grades — consensus deals must land in their expected band.

The same validation discipline the other model docs use (gar-validate, trade-fit-validate): pin the
model against outside consensus, not against its own output. Known steals must grade high, known
albatrosses must grade low, fair deals in the middle. Bands are ±1 grade wide so a legitimate
recalibration can move a deal one notch without breaking consensus — but a steal grading D, or an
albatross grading A, fails loudly.

Data-dependent (runs the live grader over the local DuckDB serving mirror). Skips cleanly when the
serving data is unavailable, so the hermetic suite still passes in CI without BigQuery/DuckDB.
"""
import os
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).parent.parent
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "backend"))
# serve from the local DuckDB mirror (no network); must be set before importing the bq facade
os.environ.setdefault("SERVING_BACKEND", "duckdb")

SEASON = "2025-26"

# (name fragment, cap hit $, term yrs, allowed grades) — consensus, not model output.
BASKET = [
    # known steals
    ("celebrini",       0.975e6, 2, {"A", "B"}),   # elite player on an ELC
    ("makar",           9.0e6,   6, {"A", "B"}),   # elite D, team-friendly star deal
    ("kucherov",        9.5e6,   3, {"A", "B"}),   # elite F well below market
    # fair deals (consensus band B-D: not a steal, not an albatross)
    ("barzal",          9.15e6,  6, {"B", "C", "D"}),   # good top-six C at roughly his price
    ("seth jones",      9.5e6,   4, {"B", "C", "D"}),   # paid like a #1 D, produces below it
    # known albatrosses
    ("huberdeau",      10.5e6,   6, {"D", "F"}),   # large AAV, sharp decline
    ("darnell nurse",   9.25e6,  5, {"D", "F"}),   # consensus overpay on a long term
    ("erik karlsson",  11.5e6,   2, {"D", "F"}),   # aging star, top-of-market AAV
]


@pytest.fixture(scope="module")
def grader():
    """Resolve the live grader + a name->id lookup, or skip if the serving data isn't reachable."""
    try:
        from services.contract_grade import grade_contract
        from services.bigquery import bq_service
        ros = bq_service.get_models_table_id("dim_current_roster")

        def player_id(fragment: str) -> int:
            rows = bq_service.query(
                f"SELECT player_id FROM {ros} WHERE name_lower LIKE '%{fragment}%' LIMIT 1")
            if not rows:
                pytest.skip(f"player not found in serving data: {fragment}")
            return rows[0]["player_id"]

        # smoke-check the pipeline is wired (curves fit) before parametrized asserts
        grade_contract(player_id("celebrini"), 1.0e6, 2, SEASON)
        return grade_contract, player_id
    except Exception as e:                                   # missing serving file, schema, etc.
        pytest.skip(f"contract serving data unavailable: {e}")


@pytest.mark.parametrize("name,cap_hit,term,allowed", BASKET, ids=[b[0] for b in BASKET])
def test_consensus_contract_lands_in_band(grader, name, cap_hit, term, allowed):
    grade_contract, player_id = grader
    g = grade_contract(player_id(name), cap_hit, term, SEASON)
    assert g["grade"] in allowed, (
        f"{name} (${cap_hit/1e6:.2f}M x {term}y) graded {g['grade']}, expected one of {sorted(allowed)} "
        f"[surplus/cost ratio {g['total_discounted_surplus']/g['cost_dollars']:+.2f}]")
