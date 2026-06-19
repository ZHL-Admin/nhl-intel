"""Hermetic tests for the trade evaluation engine (no BigQuery/DuckDB required).

Exercise the pure model functions on synthetic assets: netting, band propagation (variance
combination), retention math + rule enforcement, multi-team netting, and the cap soft-flag math.
"""
import math
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).parent.parent
sys.path.insert(0, str(REPO / "backend"))


@pytest.fixture
def eng():
    from services import trade_engine
    return trade_engine


def _asset(aid, atype="player", pid=None, war=2.0, war_lo=1.0, war_hi=3.0,
           surplus=5_000_000, s_lo=2_000_000, s_hi=8_000_000, capshare=0.05,
           sc_lo=0.02, sc_hi=0.08, cap_hit=4_000_000, cost=20_000_000, conf="high"):
    return {"asset_id": aid, "asset_type": atype, "player_id": pid, "label": aid,
            "value_war": war, "value_war_low": war_lo, "value_war_high": war_hi,
            "surplus_dollars": surplus, "surplus_low": s_lo, "surplus_high": s_hi,
            "surplus_capshare": capshare, "surplus_capshare_low": sc_lo, "surplus_capshare_high": sc_hi,
            "cap_hit": cap_hit, "remaining_years": 5, "cost_dollars": cost, "confidence": conf, "note": None}


# ---------------------------------------------------------------------------- netting + bands
def test_two_team_swap_is_symmetric(eng):
    assets = {"player:1": _asset("player:1", pid=1, war=3.0, surplus=6_000_000),
              "player:2": _asset("player:2", pid=2, war=2.0, surplus=1_000_000)}
    req = {"team_ids": [10, 20],
           "movements": [{"asset_id": "player:1", "from_team_id": 10, "to_team_id": 20},
                         {"asset_id": "player:2", "from_team_id": 20, "to_team_id": 10}]}
    nets = eng._net(req, assets, [])
    # team 20 gets player 1 (3 WAR) and gives player 2 (2 WAR) -> +1.0 WAR; team 10 the mirror
    assert nets[20]["talent_delta_war"] == 1.0
    assert nets[10]["talent_delta_war"] == -1.0
    assert nets[20]["surplus_delta_dollars"] == -nets[10]["surplus_delta_dollars"]


def test_band_propagation_combines_variance(eng):
    # two assets each with WAR half-width 1.0 -> combined half-width sqrt(1^2 + 1^2) = sqrt(2)
    assets = {"player:1": _asset("player:1", pid=1, war_lo=1.0, war_hi=3.0),   # hw 1.0
              "player:2": _asset("player:2", pid=2, war_lo=1.0, war_hi=3.0)}   # hw 1.0
    req = {"team_ids": [10, 20],
           "movements": [{"asset_id": "player:1", "from_team_id": 10, "to_team_id": 20},
                         {"asset_id": "player:2", "from_team_id": 20, "to_team_id": 10}]}
    nets = eng._net(req, assets, [])
    hw = nets[20]["talent_delta_war_high"] - nets[20]["talent_delta_war"]
    assert hw == pytest.approx(math.sqrt(2.0), abs=0.01)


def test_pick_heavy_side_has_wider_band(eng):
    tight = _asset("player:1", pid=1, war_lo=1.8, war_hi=2.2)            # hw 0.2
    widepick = _asset("pick:A", atype="pick", war=4.0, war_lo=1.0, war_hi=7.0)  # hw 3.0
    assets = {"player:1": tight, "pick:A": widepick}
    req = {"team_ids": [10, 20],
           "movements": [{"asset_id": "player:1", "from_team_id": 10, "to_team_id": 20},
                         {"asset_id": "pick:A", "from_team_id": 20, "to_team_id": 10}]}
    nets = eng._net(req, assets, [])
    w10 = nets[10]["talent_delta_war_high"] - nets[10]["talent_delta_war_low"]
    assert w10 > 5.0   # the pick's wide proxy band dominates


# ---------------------------------------------------------------------------- retention
def test_retention_shifts_surplus_not_talent(eng):
    assets = {"player:1": _asset("player:1", pid=1, war=3.0, surplus=-2_000_000, cost=20_000_000)}
    req = {"team_ids": [10, 20],
           "movements": [{"asset_id": "player:1", "from_team_id": 10, "to_team_id": 20}],
           "retentions": [{"player_id": 1, "retaining_team_id": 10, "retained_pct": 0.5}]}
    rets = eng._retentions(req, assets)
    assert rets[0]["retained_dollars"] == pytest.approx(0.5 * 20_000_000)
    base = eng._net(req, assets, [])
    withret = eng._net(req, assets, rets)
    # talent unchanged by retention
    assert withret[20]["talent_delta_war"] == base[20]["talent_delta_war"] == 3.0
    # receiver (20) gains +0.5*cost surplus; retainer (10) loses it
    assert withret[20]["surplus_delta_dollars"] - base[20]["surplus_delta_dollars"] == pytest.approx(10_000_000)
    assert withret[10]["surplus_delta_dollars"] - base[10]["surplus_delta_dollars"] == pytest.approx(-10_000_000)


def test_retention_rules_enforced(eng):
    a = {"player:1": _asset("player:1", pid=1)}
    req = {"team_ids": [10, 20], "movements": [{"asset_id": "player:1", "from_team_id": 10, "to_team_id": 20}]}
    # > 50%
    with pytest.raises(ValueError):
        eng._validate({**req, "retentions": [{"player_id": 1, "retaining_team_id": 10, "retained_pct": 0.6}]}, a)
    # retainer must be the source team
    with pytest.raises(ValueError):
        eng._validate({**req, "retentions": [{"player_id": 1, "retaining_team_id": 20, "retained_pct": 0.3}]}, a)


def test_max_three_retained_contracts(eng):
    assets = {f"player:{i}": _asset(f"player:{i}", pid=i) for i in range(1, 5)}
    req = {"team_ids": [10, 20],
           "movements": [{"asset_id": f"player:{i}", "from_team_id": 10, "to_team_id": 20} for i in range(1, 5)],
           "retentions": [{"player_id": i, "retaining_team_id": 10, "retained_pct": 0.2} for i in range(1, 5)]}
    with pytest.raises(ValueError):
        eng._validate(req, assets)


# ---------------------------------------------------------------------------- multi-team
def test_three_team_netting(eng):
    assets = {"player:1": _asset("player:1", pid=1, war=3.0),
              "player:2": _asset("player:2", pid=2, war=2.0),
              "player:3": _asset("player:3", pid=3, war=1.0)}
    # 1: 10->20, 2: 20->30, 3: 30->10  (a three-way cycle)
    req = {"team_ids": [10, 20, 30],
           "movements": [{"asset_id": "player:1", "from_team_id": 10, "to_team_id": 20},
                         {"asset_id": "player:2", "from_team_id": 20, "to_team_id": 30},
                         {"asset_id": "player:3", "from_team_id": 30, "to_team_id": 10}]}
    nets = eng._net(req, assets, [])
    assert nets[10]["talent_delta_war"] == pytest.approx(1.0 - 3.0)   # gets p3, gives p1
    assert nets[20]["talent_delta_war"] == pytest.approx(3.0 - 2.0)   # gets p1, gives p2
    assert nets[30]["talent_delta_war"] == pytest.approx(2.0 - 1.0)   # gets p2, gives p3
    assert sum(n["talent_delta_war"] for n in nets.values()) == pytest.approx(0.0)


# ---------------------------------------------------------------------------- cap math
def test_cap_math_with_retention(eng):
    assets = {"player:1": _asset("player:1", pid=1, cap_hit=10_000_000)}
    req = {"team_ids": [10, 20],
           "movements": [{"asset_id": "player:1", "from_team_id": 10, "to_team_id": 20}],
           "retentions": [{"player_id": 1, "retaining_team_id": 10, "retained_pct": 0.5}]}
    rets = eng._retentions(req, assets)
    abbr = {10: "AAA", 20: "BBB"}
    committed = {"AAA": 80_000_000, "BBB": 90_000_000}
    caps = eng._cap(req, assets, rets, abbr, "2025-26", committed)
    # receiver adds (1-0.5)*10M = 5M; source sheds 5M (keeps 5M dead money)
    assert caps[20]["cap_hit_change"] == pytest.approx(5_000_000)
    assert caps[10]["cap_hit_change"] == pytest.approx(-5_000_000)
    assert caps[20]["committed_after"] == 95_000_000
    assert caps[20]["ceiling"] == 95_500_000 and caps[20]["over_cap"] is False
    assert caps[20]["approximate"] is True


# ---------------------------------------------------------------------------- confidence
def test_confidence_from_asset_mix(eng):
    high = {"incoming": [{"confidence": "high"}], "outgoing": [{"confidence": "high"}]}
    med = {"incoming": [{"confidence": "medium"}], "outgoing": [{"confidence": "high"}]}
    proxy = {"incoming": [{"confidence": "proxy"}], "outgoing": [{"confidence": "high"}]}
    assert eng._confidence(high) == "high"
    assert eng._confidence(med) == "medium"
    assert eng._confidence(proxy) == "low"
