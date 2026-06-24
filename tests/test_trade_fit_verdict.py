"""Hermetic tests for the context-aware trade-fit verdict (no BigQuery/DuckDB required).

The verdict is assembled from conditional clauses chosen by computed signals
(insight_engine/templates/team_fit.py). Everything under test is a PURE function over
already-computed numbers, so the claims can be guaranteed against the page and the string is
deterministic. Mirrors the acceptance criteria (a)-(g) in the task.
"""

import re
import sys
from pathlib import Path

REPO = Path(__file__).parent.parent
sys.path.insert(0, str(REPO))

from insight_engine.templates import team_fit as tf       # noqa: E402
from models_ml import config                               # noqa: E402

CFG = config.TRADE_FIT


# ---------------------------------------------------------------- fixtures / builders
def _traj(series, proj, last, sd=0.5, age=27, aging=1.0):
    return tf.classify_trajectory(series=series, proj_war=proj, last_war=last, proj_sd=sd,
                                  age=age, aging_ratio=aging, cfg=CFG)


def _dim(key, level):
    return {"key": key, "label": key, "level": level}


def _need_bd(*, fills=True):
    """A need breakdown with (or without) a component the player FILLS."""
    if fills:
        return [{"component": "ev_offense", "label": "Even-strength · Even-strength offense",
                 "team_need": 0.82, "player_strength": 0.88, "tag": "fills"},
                {"component": "pp", "label": "Special teams · Power play",
                 "team_need": 0.2, "player_strength": 0.3, "tag": "low_need"}]
    return [{"component": "ev_offense", "label": "Even-strength · Even-strength offense",
             "team_need": 0.25, "player_strength": 0.88, "tag": "low_need"},
            {"component": "pp", "label": "Special teams · Power play",
             "team_need": 0.2, "player_strength": 0.3, "tag": "low_need"}]


def _verdict(*, traj, grade, fit, match, dims, need_bd, signature="drives even-strength offense from the back end",
             role="D", is_goalie=False, name="Test Player", abbr="DET",
             pctile=0.80, pos_group="D"):
    tier = tf.tier_phrase(pctile, pos_group, CFG)
    return tf.build_verdict(name=name, abbr=abbr, grade=grade, fit=fit, match=match, dims=dims,
                            need_breakdown=need_bd, traj=traj, tier=tier, signature=signature,
                            role=role, is_goalie=is_goalie, cfg=CFG), tier


# ================================================================ (a) trajectory classifier
def test_a_classifier_buckets():
    career = _traj([5.0, 1.4, 1.2], proj=2.0, last=5.0, sd=1.0)
    down = _traj([1.0, 4.0, 4.2, 3.9], proj=3.3, last=1.0, sd=0.8)
    decline = _traj([1.5, 2.5, 3.5], proj=1.4, last=1.5, sd=0.5)
    assert career["bucket"] == "career_year"
    assert down["bucket"] == "down_year"
    assert decline["bucket"] == "declining"
    # the 3-season slide reports its consecutive-decline count for the "slipped N seasons" phrase
    assert decline["n_straight"] == 2


def test_a_down_year_and_declining_differ_from_same_last_below_baseline():
    """Both have last season BELOW the multi-season baseline, but they must read differently."""
    down = _traj([1.0, 4.0, 4.2, 3.9], proj=3.3, last=1.0, sd=0.8)
    decline = _traj([1.5, 2.5, 3.5], proj=1.4, last=1.5, sd=0.5)
    # precondition: both are "last < baseline"
    assert down["prior_mean"] > 1.0 and decline["prior_mean"] > 1.5
    v_down, _ = _verdict(traj=down, grade="A", fit=0.92, match=0.85, dims=[_dim("need", 0.85)],
                         need_bd=_need_bd(fills=True), pctile=0.92)
    v_dec, _ = _verdict(traj=decline, grade="C", fit=0.74, match=0.5, dims=[_dim("need", 0.5)],
                        need_bd=_need_bd(fills=True), pctile=0.78)
    assert "coming off a down year" in v_down
    assert "slipped 2 straight seasons" in v_dec
    assert "coming off a down year" not in v_dec and "slipped" not in v_down


# ================================================================ (b) the unhedged "is" rule
def test_b_flat_is_only_for_established_stable_with_depth():
    noun = tf.tier_phrase(0.80, "D", CFG)["noun"]            # "high-end top-four defenseman"
    flat = re.compile(r"\bis an? " + re.escape(noun))

    # established_stable + deep track record (4 seasons at tier) -> the flat "is a {tier}" is allowed
    stable = _traj([3.0, 3.1, 2.9, 3.0], proj=3.0, last=3.0, sd=0.4)
    assert stable["bucket"] == "established_stable" and stable["depth_proj"] >= CFG["TRAJ"]["MIN_DEPTH_FOR_IS"]
    v_stable, _ = _verdict(traj=stable, grade="A", fit=0.9, match=0.85, dims=[_dim("need", 0.85)],
                           need_bd=_need_bd(), pctile=0.80)
    assert flat.search(v_stable), "established_stable + deep record may use the flat 'is a {tier}'"

    # established_stable but SHALLOW (one season) -> must hedge with 'profiles as'
    thin = _traj([3.0], proj=3.0, last=3.0, sd=0.4)
    assert thin["depth_proj"] < CFG["TRAJ"]["MIN_DEPTH_FOR_IS"]
    v_thin, _ = _verdict(traj=thin, grade="A", fit=0.9, match=0.85, dims=[_dim("need", 0.85)],
                         need_bd=_need_bd(), pctile=0.80)
    assert not flat.search(v_thin) and "profiles as" in v_thin

    # every other bucket hedges, never a flat "is {tier}"
    for series, proj, last in (([5.0, 1.4, 1.2], 2.0, 5.0), ([1.0, 4.0, 4.2, 3.9], 3.3, 1.0),
                               ([1.5, 2.5, 3.5], 1.4, 1.5)):
        tr = _traj(series, proj, last)
        v, _ = _verdict(traj=tr, grade="B", fit=0.82, match=0.7, dims=[_dim("need", 0.7)],
                        need_bd=_need_bd(), pctile=0.80)
        assert not flat.search(v), f"{tr['bucket']} must not assert a flat 'is {{tier}}'"


# ================================================================ (c) fit-driver flip
def test_c_fit_driver_flips_to_low_need_form():
    fills_clause, factor_a = tf._fit_driver_clause("DET", _need_bd(fills=True), "defense", "on the blue line")
    none_clause, factor_b = tf._fit_driver_clause("EDM", _need_bd(fills=False), "defense", "on the blue line")
    assert "fills a real need" in fills_clause
    assert "doesn't fill a real need" in none_clause
    assert factor_a == factor_b == "need"


# ================================================================ (d) cap clause
def test_d_cap_omitted_on_clean_top_grade():
    stable = _traj([3.0, 3.1, 2.9, 3.0], proj=3.0, last=3.0, sd=0.4)
    dims = [_dim("need", 0.9), _dim("style", 0.95), _dim("line", 0.95)]
    v, _ = _verdict(traj=stable, grade="A", fit=0.93, match=0.90, dims=dims, need_bd=_need_bd())
    # no MATERIAL cap reason on a clean top grade
    for bad in ("style mismatch", "line projection", "unproven one-year projection", "keeping it from higher"):
        assert bad not in v
    assert "Nothing meaningful argues against the fit." in v


def test_d_cap_names_a_different_factor_than_the_fit_driver_no_double_low_need():
    decline = _traj([1.5, 2.5, 3.5], proj=1.4, last=1.5, sd=0.5)
    dims = [_dim("need", 0.3), _dim("style", 0.3), _dim("line", 0.6)]   # style is the worst shortfall
    v, _ = _verdict(traj=decline, grade="C", fit=0.74, match=0.5, dims=dims,
                    need_bd=_need_bd(fills=False), pctile=0.78)
    assert "style mismatch" in v                          # cap names style, a DIFFERENT factor
    assert v.count("doesn't fill a real need") == 1       # need is stated once (fit driver), never restated


# ================================================================ (e) floor note
def test_e_floor_note_gated_by_floor_lift():
    stable = _traj([3.0, 3.1, 2.9, 3.0], proj=3.0, last=3.0, sd=0.4)
    nb = _need_bd()
    big = _verdict(traj=stable, grade="C", fit=0.74, match=0.74 - 0.20, dims=[_dim("need", 0.54)],
                   need_bd=nb)[0]
    small = _verdict(traj=stable, grade="A", fit=0.90, match=0.90 - 0.05, dims=[_dim("need", 0.85)],
                     need_bd=nb)[0]
    assert "His quality keeps a floor under the grade." in big      # lift 0.20 >= 0.12
    assert "His quality keeps a floor under the grade." not in small  # lift 0.05 < 0.12


# ================================================================ (f) verdict <-> quality card coherence
def test_f_verdict_descriptor_and_numbers_match_quality_card():
    down = _traj([1.0, 4.0, 4.2, 3.9], proj=3.3, last=1.0, sd=0.8)
    quality = {"percentile": 0.92, "war": 3.3, "war_sd": 0.8, "last_war": 1.0, "label": "elite"}
    tier = tf.tier_phrase(quality["percentile"], "D", CFG)
    verdict = tf.build_verdict(name="Test Player", abbr="DET", grade="A", fit=0.92, match=0.85,
                               dims=[_dim("need", 0.85)], need_breakdown=_need_bd(), traj=down,
                               tier=tier, signature="drives play at both ends", role="D",
                               is_goalie=False, cfg=CFG)
    note = tf.quality_note(quality=quality, pos_label="defensemen", tier=tier, traj=down, cfg=CFG)
    # SAME tier descriptor in both surfaces
    assert tier["noun"] in verdict and tier["noun"] in note
    # the quality card's numbers (the only place they're rendered) match the projection inputs
    assert "+3.3 WAR" in note and "92nd-percentile" in note
    # both reference the same trajectory (a down year)
    assert "down year" in verdict and "down year" in note


# ================================================================ (g) determinism
def test_g_determinism_same_inputs_same_string():
    decline = _traj([1.5, 2.5, 3.5], proj=1.4, last=1.5, sd=0.5)
    dims = [_dim("need", 0.3), _dim("style", 0.3), _dim("line", 0.6)]
    a = _verdict(traj=decline, grade="C", fit=0.74, match=0.5, dims=dims,
                 need_bd=_need_bd(fills=False), pctile=0.78)[0]
    b = _verdict(traj=decline, grade="C", fit=0.74, match=0.5, dims=dims,
                 need_bd=_need_bd(fills=False), pctile=0.78)[0]
    assert a == b
