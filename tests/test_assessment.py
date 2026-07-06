"""Player Assessment tests: the append-only write guard, tier-machinery invariants, and the
/assessment endpoint shape. All hermetic — no BigQuery, no serving file (queries monkeypatched)."""

import os
import sys
from pathlib import Path

import pandas as pd
import pytest

REPO = Path(__file__).parent.parent
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "backend"))
os.environ.setdefault("SERVING_BACKEND", "duckdb")   # keep bq_service off BigQuery at import time


# --------------------------------------------------------------------------- write guard
def test_compute_gar_append_guard_refuses_out_of_seasons():
    """_append_gar must refuse (before any BigQuery call) rows outside --seasons."""
    from models_ml import compute_gar
    bad = pd.DataFrame({"season_window": ["2015-16", "2099-99"], "player_id": [1, 2]})
    with pytest.raises(ValueError):
        compute_gar._append_gar(bad, ["2015-16"])


def test_train_rapm_write_append_guard_refuses_out_of_seasons():
    from models_ml import train_rapm
    frame = pd.DataFrame({"player_id": [1], "season_window": ["2099-99"], "off_impact": [0.1]})
    with pytest.raises(ValueError):
        train_rapm.write_append([frame], ["2015-16"])


# --------------------------------------------------------------------------- tier machinery
def test_round_probs_sums_to_one():
    from models_ml.compute_assessment import _round_probs
    for raw in ({"a": 0.3111, "b": 0.4444, "c": 0.2445}, {"a": 0.99999, "b": 1e-5}):
        r = _round_probs(raw)
        assert abs(sum(r.values()) - 1.0) < 1e-6


def test_tiers_monotone_in_assessed_war():
    """Assigning tiers over a pool must never disagree with the WAR ordering (spec 6.2 invariant)."""
    from models_ml import compute_assessment as CA
    from models_ml import config
    wars = [round(20.0 - i * 0.05, 4) for i in range(400)]   # 400 distinct descending
    bands, mode = CA._tier_bands(wars, "F", len(wars))
    assert mode == "rank"
    order = {t: i for i, (t, _c) in enumerate(config.ASSESSMENT["TIER_RANKS"]["F"])}
    ranks = [order[CA._tier_of(w, bands)] for w in wars]      # wars already descending
    assert all(ranks[i] <= ranks[i + 1] for i in range(len(ranks) - 1))


def test_boundary_tie_takes_higher_tier():
    """Amendment A: players tied in WAR at a boundary all take the HIGHER tier; the cumulative
    count may exceed the ceiling by the tie size, and monotonicity still holds."""
    from models_ml import compute_assessment as CA
    wars = [round(20.0 - 0.05 * i, 4) for i in range(400)]
    wars[18] = wars[17]                       # a tie spanning the elite (ceiling 18) boundary
    bands, _mode = CA._tier_bands(wars, "F", len(wars))
    tiers = [CA._tier_of(w, bands) for w in sorted(wars, reverse=True)]
    assert tiers[17] == "elite" and tiers[18] == "elite"     # both tied players take the higher tier
    assert tiers.count("elite") == 19                        # ceiling 18 exceeded by the tie size (1)
    order = {t: i for i, (t, _c) in enumerate(CA.CFG["TIER_RANKS"]["F"])}
    ranks = [order[t] for t in tiers]
    assert all(ranks[i] <= ranks[i + 1] for i in range(len(ranks) - 1))   # monotone preserved


def _separator_positions(tiers_desc):
    """Indices where the tier changes in an assessed_war-desc list = where the FE draws separators."""
    return [i for i in range(1, len(tiers_desc)) if tiers_desc[i] != tiers_desc[i - 1]]


def test_index_separators_match_rank_ceilings():
    """M3.5 item 4: the assessed_war-desc index order equals the tier pool order, and tier-group
    separators land exactly at the rank ceilings."""
    from models_ml import compute_assessment as CA
    wars = [round(20.0 - 0.05 * i, 4) for i in range(400)]        # 400 distinct, descending
    bands, _ = CA._tier_bands(wars, "F", len(wars))
    tiers = [CA._tier_of(w, bands) for w in sorted(wars, reverse=True)]
    ceilings = [c for _t, c in CA.CFG["TIER_RANKS"]["F"] if c is not None]   # [18,96,192,288,384]
    assert _separator_positions(tiers) == ceilings


def test_index_separator_shifts_with_tie():
    """A WAR tie spanning a boundary pushes the separator down by the tie size (tie-takes-higher)."""
    from models_ml import compute_assessment as CA
    wars = [round(20.0 - 0.05 * i, 4) for i in range(400)]
    wars[18] = wars[17]                                            # tie across the elite (18) boundary
    bands, _ = CA._tier_bands(wars, "F", len(wars))
    tiers = [CA._tier_of(w, bands) for w in sorted(wars, reverse=True)]
    seps = _separator_positions(tiers)
    assert seps[0] == 19        # elite now holds 19 (18 + the tie); separator shifted down one


def test_index_consistency_live():
    """M3.5 item 3 (LIVE): against the running /rankings/value payload, the filtered order ==
    assessed_war desc, tiers are monotone (separators fall at the rank ceilings with the
    tie-takes-higher rule already applied at model time), and the ranked value IS assessed_war."""
    import json
    import urllib.request
    from collections import Counter
    from models_ml import config
    url = "http://localhost:8000/rankings/value?scope=skaters&position=D&season=2024-25&limit=400"
    try:
        rows = json.load(urllib.request.urlopen(url, timeout=5))
    except Exception:
        pytest.skip("live backend not reachable on :8000")
    if len(rows) < 40:
        pytest.skip("thin live pool")
    aw = [r["assessed_war"] for r in rows]
    assert aw == sorted(aw, reverse=True), "index order must equal assessed_war desc"
    tiers = [r["tier"] for r in rows]
    order = {t: i for i, (t, _c) in enumerate(config.ASSESSMENT["TIER_RANKS"]["D"])}
    ranks = [order[t] for t in tiers]
    assert all(ranks[i] <= ranks[i + 1] for i in range(len(ranks) - 1)), "tiers monotone in the ranked order"
    seps = [i for i in range(1, len(tiers)) if tiers[i] != tiers[i - 1]]
    cnt = Counter(tiers)
    cum, expected = 0, []
    for t, _c in config.ASSESSMENT["TIER_RANKS"]["D"]:
        if cnt.get(t):
            cum += cnt[t]
            if cum < len(tiers):
                expected.append(cum)
    assert seps == expected, "separator positions == cumulative tier counts (== ceilings, tie-adjusted)"


def test_dependence_map_null_to_populated():
    """P1: _dependence_map turns WOWY into real dependence fields; D17 excludes partners < 3000s;
    empty WOWY yields no entry (the prior null path)."""
    from models_ml import compute_assessment as CA
    wowy = pd.DataFrame([
        {"player_id": 1, "partner_id": 10, "season": "2024-25", "toi_together_sec": 4000, "together_minus_focal_alone": 0.05},
        {"player_id": 1, "partner_id": 11, "season": "2024-25", "toi_together_sec": 1000, "together_minus_focal_alone": 0.20},
    ])
    m = CA._dependence_map(wowy, ["2024-25"])
    d = m[(1, "2024-25")]
    assert d["dependence_n_partners"] == 1        # only the >=3000s partner counts (D17)
    assert d["top_partner_id"] == 10
    assert abs(d["dependence_index"] - 0.05) < 1e-9
    assert CA._dependence_map(pd.DataFrame(columns=wowy.columns), ["2024-25"]) == {}


def test_dependence_hedge_rule():
    """The verdict checker requires a hedge for a linemate-dependence claim when n_partners < 3."""
    from models_ml.generate_verdicts import assessment_check
    base = {"tier": "first_line", "tier_label": "First-line forward", "tier_confidence": 0.7,
            "tier_prob_within_one": 0.9, "confidence_label": "high", "stability_grade": "A",
            "qualified": True, "disqualify_reason": None, "last_played_season": None,
            "within_one_range_copy": 0.85, "dependence_index": 0.06, "dependence_n_partners": 2}
    unhedged = assessment_check({"current": {"assessment": base}},
                                {"long": "He is a first-line forward who leans on his linemate to drive results."})
    hedged = assessment_check({"current": {"assessment": base}},
                              {"long": "He is a first-line forward; on a thin sample his linemate pairing looks strong."})
    assert unhedged[0] is False and any("dependence" in f for f in unhedged[1])
    assert hedged[0] is True


def test_percentile_fallback_for_small_pool():
    from models_ml import compute_assessment as CA
    wars = [5.0 - i * 0.1 for i in range(30)]                 # 30 < deepest F ceiling (384)
    _bands, mode = CA._tier_bands(wars, "F", len(wars))
    assert mode == "percentile_fallback"


def test_probs_over_bands_normalize():
    from models_ml import compute_assessment as CA
    wars = [10.0 - i * 0.1 for i in range(200)]
    bands, _ = CA._tier_bands(wars, "D", len(wars))
    p = CA._probs(2.0, 0.8, bands)
    assert abs(sum(p.values()) - 1.0) < 1e-6


# --------------------------------------------------------------------------- endpoint shape
class _FakeBQ:
    def __init__(self, rows):
        self._rows = rows
    def get_full_table_id(self, t):
        return t
    def get_models_table_id(self, t):
        return t
    def query(self, sql):
        return self._rows


def _call(rows, pid):
    import asyncio
    from routers import players
    players.bq_service = _FakeBQ(rows)
    return asyncio.run(players.get_player_assessment(pid, None))


def test_endpoint_unqualified_returns_false_shape():
    r = _call([], 900001)
    assert r.qualified is False and r.tier is None and r.tier_probs == []
    assert r.provenance.model_version == "assessment_v1"


def test_endpoint_qualified_skater_maps_fields():
    row = {
        "season_window": "2023-24_2025-26", "position": "F", "qualified": True,
        "tier": "first_line", "tier_label": "First-line forward", "tier_confidence": 0.62,
        "confidence_label": "high", "tier_prob_within_one": 0.95, "tier_mode": "rank",
        "tier_probs": '{"elite": 0.1, "first_line": 0.62, "second_line": 0.28}',
        "assessed_war": 6.2, "war_sd": 1.1, "war_p10": 4.8, "war_p90": 7.6,
        "stability_grade": "A", "role_primary": "Two-Way Forward", "role_deployment": "Balanced",
        "pool_size": 400, "toi_basis_min": 3200.0, "seasons_present": 3,
        "point_estimator": "c2_roster_player", "model_version": "assessment_v1",
    }
    r = _call([row], 900002)
    assert r.qualified and r.tier == "first_line" and r.confidence_label == "high"
    assert len(r.tier_probs) == 3 and r.tier_probs[1].label == "First-line forward"
    assert r.provenance.point_estimator == "c2_roster_player"
    assert (r.provenance.production_r, r.provenance.rapm_r, r.provenance.finishing_r) == (0.66, 0.38, 0.35)


def test_endpoint_goalie_grade_cap_passthrough():
    row = {"season_window": "2023-24_2025-26", "position": "G", "qualified": True,
           "tier": "starter", "tier_label": "Starter", "tier_confidence": 0.5,
           "confidence_label": "medium", "tier_prob_within_one": 0.9, "tier_mode": "rank",
           "tier_probs": '{"starter": 0.5, "tandem": 0.4, "backup": 0.1}',
           "assessed_war": 3.0, "war_sd": 2.0, "war_p10": 0.5, "war_p90": 5.5,
           "stability_grade": "B", "role_primary": None, "role_deployment": None,
           "pool_size": 60, "toi_basis_min": 1400.0, "seasons_present": 3,
           "point_estimator": "goalie_gar", "model_version": "assessment_v1"}
    r = _call([row], 900003)
    assert r.position == "G" and r.stability_grade == "B" and r.provenance.point_estimator == "goalie_gar"


def test_assessment_route_has_no_tier_sort_param():
    """Product rule: no tier sort / tier rank affordance anywhere on the endpoint."""
    import inspect
    from routers import players
    params = set(inspect.signature(players.get_player_assessment).parameters)
    assert params == {"player_id", "season_window"}
    assert not (params & {"sort", "sort_by", "order", "tier_rank", "rank"})
