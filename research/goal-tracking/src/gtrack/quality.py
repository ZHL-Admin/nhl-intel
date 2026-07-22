"""Stage 0.3 — clip-quality score, per goal.

Components (computed in reconstruct.py, stored on fused_goals):
  a       = scorer within 5.5 ft of the puck at any frame in the final 1.5 s pre-release (bool)
  b       = no puck-tracking gap > 0.5 s in the final 5.0 s (bool)
  c_crowd = count of bodies within 5.5 ft of the puck at release
  d       = flight detector fired (bool)
  score   = 0.4a + 0.3b + 0.1d + 0.2 * max(0, (3 - c_crowd)/3)
  CLEAN   = a AND b AND d
Crowd strata (for validation sampling): clean c_crowd<=1, medium c_crowd==2, scramble c_crowd>=3.
"""
from __future__ import annotations

import polars as pl

from . import config, fuse


def score_frame(goals: pl.DataFrame) -> pl.DataFrame:
    a = pl.col("q_a").cast(pl.Float64)
    b = pl.col("q_b").cast(pl.Float64)
    d = pl.col("q_d").cast(pl.Float64)
    crowd_term = (pl.max_horizontal(pl.lit(0.0), (3 - pl.col("q_c_crowd")) / 3.0)) * 0.2
    return goals.with_columns(
        quality_score=(0.4 * a + 0.3 * b + 0.1 * d + crowd_term),
        is_clean=(pl.col("q_a") & pl.col("q_b") & pl.col("q_d")),
        crowd_stratum=pl.when(pl.col("q_c_crowd") <= 1).then(pl.lit("clean"))
        .when(pl.col("q_c_crowd") == 2).then(pl.lit("medium")).otherwise(pl.lit("scramble")),
    )


def load_scored() -> pl.DataFrame:
    return score_frame(pl.read_parquet(fuse.FUSED))


def distribution(goals: pl.DataFrame) -> dict:
    g = score_frame(goals) if "is_clean" not in goals.columns else goals
    per_season = (g.group_by("season").agg(
        n=pl.len(), clean=pl.col("is_clean").sum(),
        mean_score=pl.col("quality_score").mean(),
        stratum_clean=(pl.col("crowd_stratum") == "clean").sum(),
        stratum_medium=(pl.col("crowd_stratum") == "medium").sum(),
        stratum_scramble=(pl.col("crowd_stratum") == "scramble").sum(),
    ).with_columns(clean_frac=pl.col("clean") / pl.col("n")).sort("season"))
    # score histogram (0.1 bins)
    hist = (g.with_columns(bin=(pl.col("quality_score") * 10).floor() / 10)
            .group_by("bin").len().sort("bin"))
    return {"per_season": per_season.to_dicts(), "hist": hist.to_dicts(),
            "overall_clean_frac": float(g["is_clean"].mean()),
            "n_clean": int(g["is_clean"].sum()), "n": g.height}
