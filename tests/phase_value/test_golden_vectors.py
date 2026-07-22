"""Golden vectors GV1-GV8 (spec Appendix A) — the binding behavior of the reference state machine.

Pure Python, no BigQuery. `pytest tests/phase_value/test_golden_vectors.py`. The dbt SQL is later
reconciled against this same reference (stage1_reconcile.py). Home team = 'H', away = 'A'; H defends
D_home, A defends D_away.
"""
from __future__ import annotations

from reference_state_machine import run, D_HOME, N, D_AWAY

H, A = "H", "A"


def _ev(t, typ, owner, zone):
    return {"t": t, "type": typ, "owner": owner, "zone": zone}


def _episodes_vs(res, d):
    return [e for e in res["episodes"] if e["defending_team"] == d]


def _pe(res, i):
    return res["per_event"][i]


def test_gv1_plain_carry():
    ev = [_ev(0, "faceoff", H, "N"), _ev(8, "shot-on-goal", H, "O")]
    r = run(ev, H, A)
    assert _pe(r, 0) == {"t": 0, "type": "faceoff", "poss": H, "zone": N, "live": True}
    assert _pe(r, 1) == {"t": 8, "type": "shot-on-goal", "poss": H, "zone": D_AWAY, "live": True}
    eps = _episodes_vs(r, A)
    assert len(eps) == 1
    assert eps[0]["start"] == 8 and eps[0]["start_type"] == "carry_other"
    assert eps[0]["attacking_team"] == H


def test_gv2_rush_off_nz_turnover():
    ev = [_ev(0, "faceoff", H, "N"), _ev(3, "giveaway", H, "N"), _ev(5, "shot-on-goal", A, "O")]
    r = run(ev, H, A)
    assert _pe(r, 1)["poss"] == A and _pe(r, 1)["zone"] == N        # giveaway flips possession, still NZ
    assert _pe(r, 2)["poss"] == A and _pe(r, 2)["zone"] == D_HOME
    eps = _episodes_vs(r, H)
    assert len(eps) == 1 and eps[0]["start"] == 5 and eps[0]["start_type"] == "rush"


def test_gv3_oz_faceoff():
    ev = [_ev(90, "faceoff", H, "N"), _ev(100, "stoppage", None, None),
          _ev(100, "faceoff", A, "O"), _ev(104, "shot-on-goal", A, "O")]
    r = run(ev, H, A)
    assert _pe(r, 1)["live"] is False                                # stoppage -> DEAD, zero duration
    assert _pe(r, 2) == {"t": 100, "type": "faceoff", "poss": A, "zone": D_HOME, "live": True}
    eps = _episodes_vs(r, H)
    assert len(eps) == 1 and eps[0]["start"] == 100 and eps[0]["start_type"] == "oz_faceoff"
    assert eps[0]["n_unblocked"] == 1                                # the shot at 104 is in-episode


def test_gv4_interruption_merges():
    ev = [_ev(0, "faceoff", A, "N"), _ev(10, "shot-on-goal", A, "O"), _ev(14, "takeaway", H, "D"),
          _ev(16, "giveaway", H, "D"), _ev(20, "stoppage", None, None)]
    r = run(ev, H, A)
    eps = _episodes_vs(r, H)
    assert len(eps) == 1                                             # 2s gap merges
    e = eps[0]
    assert e["start"] == 10 and e["end"] == 20
    assert e["start_type"] == "carry_other"                          # set by the START event (shot), not the mid giveaway
    assert e["end_reason"] == "stoppage" and e["n_unblocked"] == 1


def test_gv5_flip_sustained_then_forecheck_hit_noop():
    ev = [_ev(0, "faceoff", A, "N"), _ev(10, "shot-on-goal", A, "O"), _ev(14, "takeaway", H, "D"),
          _ev(19, "hit", A, "O"), _ev(21, "giveaway", H, "D"), _ev(30, "stoppage", None, None)]
    r = run(ev, H, A)
    assert _pe(r, 3)["poss"] == H                                    # hit is a no-op on possession
    eps = _episodes_vs(r, H)
    assert len(eps) == 2
    e1, e2 = eps
    assert e1["start"] == 10 and e1["end"] == 14 and e1["end_reason"] == "flip_sustained"
    assert e2["start"] == 21 and e2["start_type"] == "forecheck" and e2["end_reason"] == "stoppage"


def test_gv6_exit_during_gap_and_counter_rush():
    ev = [_ev(0, "faceoff", A, "N"), _ev(10, "shot-on-goal", A, "O"), _ev(13, "takeaway", H, "D"),
          _ev(16, "missed-shot", H, "O"), _ev(20, "stoppage", None, None)]
    r = run(ev, H, A)
    eh = _episodes_vs(r, H)
    ea = _episodes_vs(r, A)
    assert len(eh) == 1 and eh[0]["start"] == 10 and eh[0]["end"] == 13 and eh[0]["end_reason"] == "exit"
    assert len(ea) == 1 and ea[0]["start"] == 16 and ea[0]["start_type"] == "rush"


def test_gv7_blocked_retains_then_goal():
    # PV-D005: blocked-shot event owner is the BLOCKING team (H); shooting team = A retains possession.
    ev = [_ev(0, "faceoff", A, "N"), _ev(6, "shot-on-goal", A, "O"),
          _ev(9, "blocked-shot", H, "D"), _ev(12, "goal", A, "O")]
    r = run(ev, H, A)
    assert _pe(r, 2)["poss"] == A and _pe(r, 2)["zone"] == D_HOME    # possession stays with the attacker A
    assert _pe(r, 3)["live"] is False                                # goal -> DEAD after
    eps = _episodes_vs(r, H)
    assert len(eps) == 1
    e = eps[0]
    assert e["start"] == 6 and e["end"] == 12 and e["end_reason"] == "goal"
    assert e["n_unblocked"] == 2 and e["goals"] == 1                 # shot + goal; blocked-shot excluded


def test_gv9_outside_zone_goal_not_coerced():
    # Adversarial (PV-D008 convention (a), NOT (b)): attacker A scores from the NEUTRAL zone
    # (zone_code 'N') -> zone_abs = N, not a defensive zone. A goal is in-zone ONLY if its recorded
    # zone IS the DZ; the code does NOT coerce a goal's zone to the DZ. So this goal anchors NO episode
    # against either team. This is what keeps genuinely outside-zone goals legitimately uncovered.
    ev = [_ev(0, "faceoff", A, "N"), _ev(5, "goal", A, "N")]
    r = run(ev, H, A)
    assert _pe(r, 1)["poss"] == A and _pe(r, 1)["zone"] == N and _pe(r, 1)["live"] is False
    assert _episodes_vs(r, H) == [] and _episodes_vs(r, A) == []


def test_gv10_bare_rush_goal_zero_duration_episode():
    # Adversarial (PV-D008 convention (a) boundary inclusion): A gains the zone off a NZ turnover and
    # scores immediately — NO live in-zone event precedes the DEAD goal. The goal (recorded in the DZ)
    # anchors a ZERO-DURATION episode (start == end), end_reason goal, covered. Contrast GV9.
    ev = [_ev(0, "faceoff", H, "N"), _ev(2, "giveaway", H, "N"), _ev(4, "goal", A, "O")]
    r = run(ev, H, A)
    eps = _episodes_vs(r, H)
    assert len(eps) == 1
    e = eps[0]
    assert e["start"] == 4 and e["end"] == 4 and e["end_reason"] == "goal" and e["goals"] == 1
    assert e["start_type"] == "rush"


def test_gv8_period_boundary():
    ev = [_ev(1190, "faceoff", A, "N"), _ev(1195, "shot-on-goal", A, "O"),
          _ev(1200, "period-end", None, None)]
    r = run(ev, H, A)
    assert _pe(r, 2) == {"t": 1200, "type": "period-end", "poss": None, "zone": None, "live": False}
    eps = _episodes_vs(r, H)
    assert len(eps) == 1 and eps[0]["start"] == 1195 and eps[0]["end"] == 1200
    assert eps[0]["end_reason"] == "stoppage"
