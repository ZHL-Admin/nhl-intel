"""Fast summer-addendum tests — read the analysis JSON (no recompute). Guard the pre-stated
verdict logic and the deployment-calibration invariant (the test must have power).
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from syseff import config  # noqa: E402

ANALYSIS = config.REPORTS / "phase5_summer_analysis.json"


def _d():
    return json.loads(ANALYSIS.read_text())


def test_cohorts_split():
    c = _d()["S1_cohorts"]["all_transitions"]
    assert c["total"] == c["summer_change"] + c["summer_continuation"]
    assert c["summer_change"] > 0 and c["summer_continuation"] > 0


def test_deployment_calibration_clears():
    """Pre-specified: deployment should clear both tests, proving the design has power."""
    d = _d()
    assert d["S3_dose"]["deployment"]["ci95"][0] > 0            # dose CI excludes zero
    assert d["S4_directional"]["families"]["deployment"]["perm_p"] < 0.05


def test_verdict_follows_prestated_rule():
    d = _d()
    style_dir = d["S4_directional"]["families"]["style"]
    ds = d["S3_dose"]["style"]
    dir_clears = style_dir["perm_p"] < 0.05 and style_dir["directional_corr"] > 0
    dose_clears = (ds["summer_change_mean_absdelta_sd"] > ds["summer_continuation_mean_absdelta_sd"]
                   and ds["coach_change_coef_sd_units"] > 0 and ds["ci95"][0] > 0)
    v = d["S5_verdict"]["verdict"]
    if dir_clears and dose_clears:
        assert v.startswith("AMEND")
    elif not dir_clears and not dose_clears:
        assert v.startswith("EXTEND")
    else:
        assert v.startswith("MIXED")


def test_continuity_confound_direction():
    # coach-change summers have <= continuation continuity (the confound the design controls)
    d = _d()["S2_continuity"]
    assert d["summer_change__ret_toi"]["median"] <= d["summer_continuation__ret_toi"]["median"]
