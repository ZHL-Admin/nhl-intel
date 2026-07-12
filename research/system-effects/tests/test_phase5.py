"""Fast Phase 5 tests — read frozen eval inputs + the analysis JSON (no refit). Guard the
pre-registration invariants: inputs frozen, decision in the fixed set, leakage discipline shape.
"""
import json
import sys
from pathlib import Path

import polars as pl

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from syseff import config  # noqa: E402

FROZEN = config.PARQUET / "frozen_eval"
ANALYSIS = config.REPORTS / "phase5_analysis.json"


def test_eval_inputs_frozen():
    for f in ("movers_eval_frame.parquet", "stayers_eval_frame.parquet",
              "season_start_regime_deploy.parquet", "target_splithalf.parquet"):
        assert (FROZEN / f).exists(), f"frozen input missing: {f}"


def test_decision_in_fixed_set():
    d = json.loads(ANALYSIS.read_text())
    assert d["movers"]["decision"] in {"SHIP", "INVESTIGATE", "KILL"}
    # decision rule is deterministic from the numbers
    imp = d["movers"]["mae_improvement_pct"]; lo = d["movers"]["mae_diff_ci95"][0]
    expect = "SHIP" if (imp >= 3.0 and lo > 0) else ("KILL" if imp <= 0.0 else "INVESTIGATE")
    assert d["movers"]["decision"] == expect


def test_target_reliability_reported():
    d = json.loads(ANALYSIS.read_text())
    r = d["noise_ceiling_movers"]["target_reliability_spearman_brown"]
    assert 0.5 < r < 0.85   # the known ~0.70 5v5 xG-share reliability band


def test_movers_target_no_leakage_shape():
    # every mover's target uses seasons strictly AFTER the origin season
    m = pl.read_parquet(FROZEN / "movers_eval_frame.parquet")
    assert (m["origin_season"] < m["dest_season"]).all()
    assert m.filter(pl.col("subgroup") == "s1_only").height > 0
    assert m.filter(pl.col("subgroup") == "both").height > 0
