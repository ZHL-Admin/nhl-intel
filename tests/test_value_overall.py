"""Hermetic tests for cross-position WAR + the card-only Overall (no BigQuery required).

B2: the mixed value leaderboard sorts by WAR, never GAR (skater GAR and goalie GAR are different
    units). A skater with a HIGHER GAR but LOWER WAR must rank below a goalie with the higher WAR.
C2: Overall is card-only — there is no /rankings/overall route, and the rankings router never
    consumes player_overall / goalie_overall.
"""

import re
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).parent.parent
sys.path.insert(0, str(REPO / "backend"))

# These imports construct the BigQuery service singleton; skip gracefully if creds are absent
# (the rest of the suite already depends on live services).
bq_creds = (REPO / "secrets" / "nhl-intel-sa.json").exists()
pytestmark = pytest.mark.skipif(not bq_creds, reason="BigQuery service-account key not present")


def _mods():
    from models.schemas import ValueRankingRow
    from routers import rankings
    return ValueRankingRow, rankings


def test_mixed_value_list_sorts_by_war_not_gar():
    ValueRankingRow, rankings = _mods()
    # Skater: BIG gar, modest war. Goalie: smaller gar, bigger war. WAR must win the ordering.
    skater = ValueRankingRow(player_id=1, player_name="Skater", position="C",
                             entity_kind="skater", component_kind="skater", gar=40.0, war=4.0)
    goalie = ValueRankingRow(player_id=2, player_name="Goalie", position="G",
                             entity_kind="goalie", component_kind="goalie", gar=30.0, war=8.0)
    out = rankings.merge_value_rows_by_war([skater], [goalie], limit=10)
    assert [r.player_id for r in out] == [2, 1], "mixed list must sort by WAR (goalie first), not GAR"
    assert out[0].war >= out[1].war
    # and the two kinds carry distinct component vocabularies for the frontend
    assert {r.component_kind for r in out} == {"skater", "goalie"}


def test_no_rankings_overall_route():
    _, rankings = _mods()
    paths = [getattr(r, "path", "") for r in rankings.router.routes]
    assert not any("overall" in p.lower() for p in paths), \
        "Overall must never be a leaderboard sort key (no /rankings/overall route)."


def test_rankings_router_does_not_consume_overall_tables():
    src = (REPO / "backend" / "routers" / "rankings.py").read_text()
    assert "player_overall" not in src and "goalie_overall" not in src, \
        "the rankings layer must not read the card-only Overall tables."


def test_overall_tables_only_consumed_by_detail_routers():
    # player_overall / goalie_overall may be read ONLY by the player/goalie DETAIL routers.
    routers_dir = REPO / "backend" / "routers"
    for f in routers_dir.glob("*.py"):
        src = f.read_text()
        if re.search(r"player_overall|goalie_overall", src):
            assert f.name in ("players.py", "goalies.py"), \
                f"{f.name} consumes an Overall table; only detail routers may."
