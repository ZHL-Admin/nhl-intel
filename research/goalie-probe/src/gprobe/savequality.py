"""G1.3 — save-quality per goalie-season and pooled, by bucket, over SHOTS FACED (the denominator).

Two metrics per (goalie, scope, bucket):
  save%      = saves / shots faced (all shots in the bucket).
  GSAx/100   = 100 * mean(xg - is_goal) over shots-with-xG = (xGA - GA) per 100 shots; the xG-adjusted
               save-quality residual (positive = saved above expectation). This is the metric the
               stability gate (G1.4) tests, because it is danger-adjusted and fair across buckets.
EB shrinkage: GSAx/100 is shrunk toward the league residual (~0) by factor n/(n+k), prior strength
k=EB_PRIOR_SHOTS pseudo-shots; save% is Beta-Binomial-shrunk toward the bucket league save%. 90% CIs.
Minimum-sample gate: no per-goalie-bucket claim below MIN_BUCKET_SHOTS shots faced (claim_ok flag).
Absolute shot counts travel with every rate.
"""
from __future__ import annotations

import numpy as np
import polars as pl

from . import config, spine as S

SAVEQ = config.PARQUET / "save_quality.parquet"
K = config.EB_PRIOR_SHOTS
Z90 = 1.6448536269514722

DIMENSIONS = {"shot_bucket": "shot_bucket", "danger": "danger", "region": "region", "rebound": "rebound"}


def _load() -> pl.DataFrame:
    s = pl.read_parquet(S.SPINE).filter(pl.col("goalie_id").is_not_null())
    return s.with_columns(
        rebound_lbl=pl.when(pl.col("rebound")).then(pl.lit("rebound")).otherwise(pl.lit("non_rebound")),
        overall=pl.lit("all"),
        xg_var=(pl.col("xg") * (1 - pl.col("xg"))))


def _agg(df: pl.DataFrame, dim: str, scope_col: str) -> pl.DataFrame:
    keys = ["goalie_id", scope_col, dim]
    g = df.group_by(keys).agg(
        n_shots=pl.len(), n_saves=pl.col("saved").sum(), n_goals=pl.col("is_goal").sum(),
        n_xg=pl.col("xg").is_not_null().sum(),
        sum_xg=pl.col("xg").sum(), sum_goal_xg=pl.col("is_goal").filter(pl.col("xg").is_not_null()).sum(),
        sum_xgvar=pl.col("xg_var").sum())
    return g.rename({scope_col: "scope", dim: "bucket"}).with_columns(
        dimension=pl.lit(dim if dim != "rebound_lbl" else "rebound"))


def build() -> pl.DataFrame:
    s = _load()
    dims = [("shot_bucket", "shot_bucket"), ("danger", "danger"), ("region", "region"),
            ("rebound", "rebound_lbl"), ("overall", "overall")]
    frames = []
    for name, col in dims:
        # pooled scope
        d = s.with_columns(scope=pl.lit("pooled"))
        frames.append(_agg(d, col, "scope").with_columns(dimension=pl.lit(name)))
        # per-season scope
        d2 = s.with_columns(scope=pl.col("season"))
        frames.append(_agg(d2, col, "scope").with_columns(dimension=pl.lit(name)))
    q = pl.concat(frames).filter(pl.col("bucket").is_not_null())

    # League baseline PER BUCKET, from the pooled shots. The xG model is not perfectly calibrated inside
    # buckets, so a goalie's SKILL is his residual measured RELATIVE to the league bucket residual (not to
    # raw xG). save% shrinks toward the bucket league save%; GSAx/100 is centered on the league bucket
    # residual and shrunk toward it (= toward 0 after centering). This is "EB shrinkage toward league by
    # bucket."
    league = (q.filter(pl.col("scope") == "pooled")
              .group_by("dimension", "bucket")
              .agg(lg_saves=pl.col("n_saves").sum(), lg_shots=pl.col("n_shots").sum(),
                   lg_gsax=(pl.col("sum_xg") - pl.col("sum_goal_xg")).sum(), lg_nxg=pl.col("n_xg").sum())
              .with_columns(lg_savepct=pl.col("lg_saves") / pl.col("lg_shots"),
                            lg_gsax_per100=100 * pl.col("lg_gsax") / pl.col("lg_nxg")))
    q = q.join(league.select("dimension", "bucket", "lg_savepct", "lg_gsax_per100"),
               on=["dimension", "bucket"], how="left")

    q = q.with_columns(
        save_pct=pl.col("n_saves") / pl.col("n_shots"),
        gsax=pl.col("sum_xg") - pl.col("sum_goal_xg"),                       # xGA - GA over shots-with-xG
    ).with_columns(
        gsax_per100_raw=pl.when(pl.col("n_xg") > 0).then(100 * pl.col("gsax") / pl.col("n_xg")).otherwise(None),
        shrink=pl.col("n_xg") / (pl.col("n_xg") + K),
        se_per100=pl.when(pl.col("n_xg") > 0).then(100 * pl.col("sum_xgvar").sqrt() / pl.col("n_xg")).otherwise(None),
        savepct_eb=(K * pl.col("lg_savepct") + pl.col("n_saves")) / (K + pl.col("n_shots")),
    ).with_columns(
        # deviation from league bucket baseline, EB-shrunk toward league (0 after centering)
        gsax_dev_raw=pl.col("gsax_per100_raw") - pl.col("lg_gsax_per100"),
    ).with_columns(
        gsax_dev_eb=pl.col("gsax_dev_raw") * pl.col("shrink"),
    ).with_columns(
        ci_lo=pl.col("gsax_dev_eb") - Z90 * pl.col("se_per100") * pl.col("shrink"),
        ci_hi=pl.col("gsax_dev_eb") + Z90 * pl.col("se_per100") * pl.col("shrink"),
        claim_ok=pl.col("n_shots") >= config.MIN_BUCKET_SHOTS)
    q.write_parquet(SAVEQ)
    return q


if __name__ == "__main__":
    q = build()
    pooled = q.filter(pl.col("scope") == "pooled")
    print(f"save-quality rows: {q.height:,} | pooled goalie-buckets: {pooled.height:,}")
    print("\nleague GSAx/100 by bucket (should ~0), and claim coverage (>=50 shots):")
    for dim in ["overall", "shot_bucket", "danger", "region", "rebound"]:
        d = pooled.filter(pl.col("dimension") == dim)
        for b in d["bucket"].unique().sort():
            db = d.filter(pl.col("bucket") == b)
            claim = int(db["claim_ok"].sum())
            cg = db.filter(pl.col("claim_ok"))
            print(f"  {dim}/{b}: goalies={db.height} claim>=50={claim} lg_GSAx/100={db['lg_gsax_per100'][0]:.2f} "
                  f"dev spread [{cg['gsax_dev_eb'].min():.2f},{cg['gsax_dev_eb'].max():.2f}]")
