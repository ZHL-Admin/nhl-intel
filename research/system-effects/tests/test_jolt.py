"""Fast Jolt tests — read the frozen analysis JSON (no recompute). Guard the pre-registered
decision logic and the placebo-bias disclosure.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from syseff import config  # noqa: E402

ANALYSIS = config.REPORTS / "phase5_jolt_analysis.json"


def _d():
    return json.loads(ANALYSIS.read_text())


def test_frozen_inputs_exist():
    fr = config.PARQUET / "frozen_eval_jolt"
    for f in ("real_changes_eventtime.parquet", "placebo_matched_depth_eventtime.parquet",
              "placebo_deepest_eventtime.parquet", "target_splithalf.parquet"):
        assert (fr / f).exists(), f


def test_decision_follows_prestated_rule():
    d = _d(); dec = d["decision"]
    trough_sig = dec["trough_significant"]
    e = d["excess_over_matched_depth_placebo"]["post_+1_+10"]
    excess_incl_zero = e["ci95"][0] <= 0 <= e["ci95"][1]
    fade_neg = dec["fade_slope_negative"]
    if dec["excess_+1_+10_positive"] and fade_neg:
        assert dec["verdict"] == "EFFORT"
    elif trough_sig and excess_incl_zero:
        assert dec["verdict"] == "REVERSION"
    elif not trough_sig and not dec["excess_+1_+10_significant"]:
        assert dec["verdict"] == "NEITHER"
    else:
        assert dec["verdict"] == "MIXED"


def test_deepest_placebo_bias_disclosed():
    # the registered "deepest" placebo pre-level is below the real pre-level (regression-to-minimum);
    # the matched-depth control is the valid one.
    p = _d()["placebo_pre_level"]
    assert p["deepest_biased"] < p["real"]
    assert abs(p["matched_depth"] - p["real"]) < abs(p["deepest_biased"] - p["real"])
