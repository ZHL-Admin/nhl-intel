"""Fast Phase 4 tests — read cached surfaces (no rebuild). Guard the API contracts and the
Phase-3 ruling constraints (F14 caveat present; zone-pol is the primary axis; schedule surface
is descriptive-only).
"""
import sys
from pathlib import Path

import polars as pl

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from syseff import api, portability as PORT, config  # noqa: E402


def test_portability_wellformed():
    p = pl.read_parquet(config.PARQUET / "portability.parquet")
    assert p.height > 5000
    sd = p["system_dependence"]
    assert sd.min() >= 0.0 and sd.max() <= 1.0
    # portability = 1 - system_dependence
    assert (p.select((pl.col("portability") + pl.col("system_dependence") - 1).abs().max()).item()) < 1e-9


def test_f14_caveat_verbatim_in_api_and_delta():
    assert "F14 (thin mediation)" in api.portability.__doc__
    assert "mediation R^2=0.04" in api.portability.__doc__
    d = api.predicted_delta(8481556, "2024-25", 12, "2023-24")
    assert "F14 (thin mediation)" in d["caveat"]
    assert d["ci90"] is not None


def test_primary_axis_is_zone_pol():
    assert PORT.PRIMARY_AXIS == "zone_start_polarization"


def test_materiality_rule_4_1a():
    p = pl.read_parquet(config.PARQUET / "portability.parquet")
    # material == sys CI excludes zero AND |sys| >= 0.004
    expect = ((p["sys_ci_lo"] > 0) | (p["sys_ci_hi"] < 0)) & (p["sys_contrib"].abs() >= PORT.MATERIALITY_MIN)
    assert (p["material"] == expect).all()
    # exhibit ranks by |sys|, not the ratio
    ex = PORT.exhibit()
    assert ex["ranked_by"].startswith("absolute system contribution")
    syss = [abs(r["sys_contrib"]) for r in ex["most_system_dependent"]]
    assert syss == sorted(syss, reverse=True)
    # leaderboard default is material-only, sorted by |sys|
    lb = api.portability_leaderboard("2024-25")
    assert lb["material"].all()


def test_schedule_surface_descriptive():
    s = pl.read_parquet(config.PARQUET / "schedule_adjustment.parquet")
    assert s.height > 5000
    ex = api.schedule_extremes("2024-25")
    assert "NO predictive claim" in ex["framing"]
    # magnitude is honestly small
    assert ex["mean_abs"] < 0.01
