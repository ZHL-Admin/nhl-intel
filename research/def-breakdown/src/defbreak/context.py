"""Context layer for the culprit-rate ADJUSTMENT probe (def-culprit-adj, extends def-breakdown).

Per player-season deployment covariates from Atlas stints (all 3 seasons, since player_context exists
only for 2024-25): 5v5 TOI, OZ-start share, PK share, trailing share. Plus per-goal scorer offensive
quality (rapm_variant off_impact) for the opponent-quality adjustment. Read-only.
"""
from __future__ import annotations

import polars as pl

from . import config as C

USAGE = C.PARQUET / "usage_context.parquet"
ATLAS = C.NIR / "research/deployment-atlas/data/parquet"


def usage() -> pl.DataFrame:
    st = pl.read_parquet(C.ATLAS_STINTS, columns=["game_id", "season_label", "duration_seconds",
                                                  "home_skater_ids", "away_skater_ids", "strength_state",
                                                  "score_state", "start_type"]).filter(pl.col("season_label").is_in(C.SEASONS))
    st = st.with_columns(hn=pl.col("strength_state").str.slice(0, 1).cast(pl.Int32, strict=False),
                         an=pl.col("strength_state").str.slice(2, 1).cast(pl.Int32, strict=False))
    home = st.select("game_id", season="season_label", dur="duration_seconds", start="start_type",
                     score="score_state", sk="home_skater_ids", myn="hn", oppn="an", side=pl.lit("home"))
    away = st.select("game_id", season="season_label", dur="duration_seconds", start="start_type",
                     score="score_state", sk="away_skater_ids", myn="an", oppn="hn",
                     side=pl.lit("away")).with_columns(score=-pl.col("score"))   # score_state -> my perspective
    ex = pl.concat([home, away]).explode("sk").rename({"sk": "player_id"})
    ex = ex.with_columns(
        is_5v5=(pl.col("myn") == 5) & (pl.col("oppn") == 5),
        is_pk=pl.col("myn") < pl.col("oppn"),
        # OZ start from my perspective: home OZ=start OZ; away OZ=start DZ
        oz=pl.when(pl.col("side") == "home").then(pl.col("start") == "OZ").otherwise(pl.col("start") == "DZ"),
        dz=pl.when(pl.col("side") == "home").then(pl.col("start") == "DZ").otherwise(pl.col("start") == "OZ"),
        trail=pl.col("score") < 0)
    agg = ex.group_by("player_id", "season").agg(
        toi_total=pl.col("dur").sum(),
        toi_5v5=pl.col("dur").filter(pl.col("is_5v5")).sum(),
        pk_s=pl.col("dur").filter(pl.col("is_pk")).sum(),
        trail_s=pl.col("dur").filter(pl.col("trail")).sum(),
        oz_starts=pl.col("oz").sum(), dz_starts=pl.col("dz").sum())
    return agg.with_columns(
        pk_share=pl.col("pk_s") / pl.col("toi_total"),
        trail_share=pl.col("trail_s") / pl.col("toi_total"),
        oz_start_share=pl.when(pl.col("oz_starts") + pl.col("dz_starts") > 0)
        .then(pl.col("oz_starts") / (pl.col("oz_starts") + pl.col("dz_starts"))).otherwise(0.5),
        toi_5v5_min=pl.col("toi_5v5") / 60.0)


def scorer_quality() -> pl.DataFrame:
    """Per goal: the scorer's offensive RAPM (off_impact), normalized to [0,1] within season for weighting."""
    fused = pl.read_parquet(C.GT_FUSED).select("game_id", "event_id", "season", "scorer_id")
    rapm = pl.read_parquet(ATLAS / "rapm_variant.parquet").select("player_id", "season", off="off_impact")
    j = fused.join(rapm, left_on=["scorer_id", "season"], right_on=["player_id", "season"], how="left")
    # normalize off within season to [0,1]; missing -> median
    j = j.with_columns(off=pl.col("off").fill_null(pl.col("off").median().over("season")))
    lo = pl.col("off").min().over("season"); hi = pl.col("off").max().over("season")
    return j.with_columns(scorer_off=(pl.col("off") - lo) / (hi - lo + 1e-9)).select("game_id", "event_id", "scorer_off")


def build() -> dict:
    u = usage()
    C.PARQUET.mkdir(parents=True, exist_ok=True)
    u.write_parquet(USAGE)
    return {"n_player_seasons": u.height,
            "oz_share_median": float(u["oz_start_share"].median()),
            "pk_share_median": float(u["pk_share"].median())}


if __name__ == "__main__":
    r = build()
    sc = scorer_quality()
    print(f"usage context: {r['n_player_seasons']:,} player-seasons | OZ-start median {r['oz_share_median']:.2f} "
          f"| PK-share median {r['pk_share_median']:.3f} | scorer-quality rows {sc.height:,} "
          f"(coverage {sc['scorer_off'].drop_nulls().len()/sc.height*100:.0f}%)")
