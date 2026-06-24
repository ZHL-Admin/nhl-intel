"""Hermetic tests for pending-RFA ingestion into the tradeable-asset layer (no BigQuery required).

Pending RFAs are a SEPARATE feed (contracts - rfas.csv -> raw_contracts_rfa) with a different schema:
no team, but a PROJECTED next deal (proj_cap / proj_term), a qualifying offer, and last-season
stats. They are matched team-lessly, unioned into mart_player_contracts as 'rfa_projected' contracts
(team derived from the latest NHL game), and valued by the normal projection over the projected term.
These tests pin the loader contract, the mart/staging wiring, and the confidence cap.
"""

import inspect
import sys
from pathlib import Path

REPO = Path(__file__).parent.parent
sys.path.insert(0, str(REPO))


def test_rfa_loader_maps_the_feed_schema():
    import scripts.load_rfas as L
    # the loader must map the RFA feed's distinct columns (note: NO team column)
    assert "TEAM" not in L.COLUMN_MAP
    for header, col in {"PROJ. CAP": "proj_cap", "PROJ. TERM": "proj_term", "QO": "qo",
                        "PLAYERS": "player_name_src"}.items():
        assert L.COLUMN_MAP.get(header) == col


def test_rfa_matcher_is_team_less():
    src = inspect.getsource(__import__("scripts.match_rfas", fromlist=["x"]))
    # team-less resolution: unique name / name+pos / name+age, never name+team
    assert "name-unique" in src and "name+pos" in src
    assert "team" not in src.split("def main")[1].split("for _, c in")[1][:1200].lower() \
        or "team_abbrev" not in src  # the matcher never keys on the RFA's (absent) team


def test_mart_unions_rfas_with_signed_winning():
    sql = (REPO / "dbt/models/mart/mart_player_contracts.sql").read_text()
    assert "rfa_player_map" in sql and "stg_contracts_rfa" in sql
    assert "'rfa_projected'" in sql and "'signed'" in sql
    # signed contract WINS the dedup (an RFA row is dropped if the player has a signed deal)
    assert "not in (select player_id from signed_final)" in sql
    # the RFA's projected deal becomes the contract; team is derived from his latest NHL game
    assert "proj_cap" in sql and "proj_term" in sql and "roster_team" in sql


def test_asset_mart_tags_rfas_off_contract_status():
    sql = (REPO / "dbt/models/mart/mart_tradeable_assets.sql").read_text()
    assert "contract_status = 'rfa_projected'" in sql
    assert "RFA" in sql and "Pending RFA" in sql


def test_value_job_caps_rfa_confidence_and_drops_the_expired_hack():
    import models_ml.compute_contract_value as cv
    src = inspect.getsource(cv.compute)
    # RFAs are valued by the normal path, with confidence capped at medium (projected cost)
    assert "rfa_projected" in src and 'confidence = "medium"' in src
    # the superseded remaining_years==0 / market-estimate hack is gone
    assert not hasattr(cv, "pending_rfa_terms")
    assert "remaining_years >= 1" in inspect.getsource(cv.pull_contracts)
    assert "remaining_years = 0" not in inspect.getsource(cv.pull_contracts)
