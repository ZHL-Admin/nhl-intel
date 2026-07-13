"""Phase 2 tests — null model, drift anchor, pair-half integrity, split-half plumbing.

Fast checks on real frozen inputs; nothing writes to data/. The 2024-25 season is the probe.
"""
import sys
from pathlib import Path

import numpy as np
import polars as pl

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from chem import config, nullmodel as nm, phase2  # noqa: E402

SEASON = "2024-25"


def test_drift_coeffs_sane():
    d = nm.drift_coeffs()
    assert d["n_pairs"] > 5000
    for c in ("off", "def"):
        assert 0.0 < d[c]["slope"] < 1.0            # mean-reversion / aging drift
        assert abs(d[c]["intercept"]) < 0.05


def test_rating_table_prior_shifts_season():
    same = nm.rating_table("same")
    prior = nm.rating_table("prior")
    # a prior-anchor 2011-12 row must come from a 2010-11 rapm row -> 2010-11 absent from prior
    assert "2010-11" not in prior["season"].unique().to_list()
    assert "2010-11" in same["season"].unique().to_list()


def test_null_fit_residual_mean_zero_and_bounded_r2():
    pairs = pl.read_parquet(nm.FROZEN_PAIRS)
    pr, dropped = nm.attach_ratings(pairs, "same")
    model, diag, out = nm.fit_null(pr, "same")
    assert dropped >= 0
    assert abs(diag["residual_toi_wtd_mean"]) < 1e-6          # weighted residual centered
    assert 0.0 < diag["cv_r2_loso_weighted"] < 1.0
    # coefficient sanity: more individual quality -> higher pair xG share
    assert diag["coefficients"]["coef"]["sum_off"] > 0
    assert diag["coefficients"]["coef"]["sum_def"] > 0


def test_pair_halves_reconstitute_season():
    h = phase2.build_pair_halves(SEASON, write=False)
    from chem import corpus
    season = corpus.build_pairs(SEASON, write=False).select("a", "b", "team_id", "toi", "xgf")
    rec = h.group_by("a", "b", "team_id").agg(toi_h=pl.col("toi").sum(), xgf_h=pl.col("xgf").sum())
    m = season.join(rec, on=["a", "b", "team_id"], how="inner").with_columns(
        tr=pl.col("toi_h") / pl.col("toi"))
    assert abs(m["tr"].median() - 1.0) < 1e-9
    assert m["tr"].min() >= 0.999 and m["tr"].max() <= 1.001


def test_raw_share_split_half_is_positive():
    # measurement reliability of the pair-season xG share must be clearly positive (sanity that the
    # odd/even plumbing is sound); the residual reliability is analyzed in the report.
    pairs = pl.read_parquet(nm.FROZEN_PAIRS).filter(pl.col("season_label") == SEASON)
    sctx = pairs.select(*phase2.KEYS, pl.col("toi").alias("season_toi"))
    h = (phase2.build_pair_halves(SEASON, write=False).join(sctx, on=phase2.KEYS, how="inner")
         .filter((pl.col("season_toi") >= 6000) & ((pl.col("xgf") + pl.col("xga")) > 0)))
    odd = h.filter(pl.col("half") == 1).select(*phase2.KEYS, xo="xg_share")
    even = h.filter(pl.col("half") == 0).select(*phase2.KEYS, xe="xg_share")
    w = odd.join(even, on=phase2.KEYS, how="inner")
    r = float(np.corrcoef(w["xo"], w["xe"])[0, 1])
    assert r > 0.15


def test_within_cell_perm_stays_in_cell():
    rng = np.random.default_rng(config.SEED)
    cell = np.array([0, 0, 0, 1, 1, 2, 2, 2, 2])
    p = phase2._within_cell_perm(cell, rng)
    assert set(p) == set(range(len(cell)))          # a valid permutation
    assert np.all(cell[p] == cell)                  # each slot filled from its own cell
