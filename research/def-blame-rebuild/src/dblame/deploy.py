"""Deployment features per (player, season) for the deployment-adjusted blame rate.

Replicates the Atlas context logic (zone starts, QoC/QoT as shared-TOI-weighted opponent/teammate ratings)
directly from the Atlas stint corpus, computed identically for 2024-25 AND 2025-26 so the adjustment and the
year-to-year analysis are comparable. Ratings for QoC/QoT come from the Atlas player_5v5 marts (xG-based, so
independent of the goal-tracking blame metric):
  QoC = shared-5v5-TOI-weighted mean OPPONENT xGF/60  (offensive danger of the competition faced)
  QoT = shared-5v5-TOI-weighted mean TEAMMATE xG-share (quality of the teammates a player is deployed with)
Plus oz_start_share (OZ vs DZ faceoff starts, team-relative) and trail_share (share of 5v5 TOI while trailing).
"""
from __future__ import annotations

from pathlib import Path

import polars as pl

from . import config as C

ATLAS = Path("/Users/codytownsend/Desktop/nhl/NIR/research/deployment-atlas/data/parquet")
DEP = C.PARQUET / "deploy_features.parquet"
SEASONS = ["2023-24", "2024-25", "2025-26"]


def _stints5(season: str) -> pl.DataFrame:
    st = pl.read_parquet(ATLAS / "stints.parquet")
    return st.filter((st["home_skater_ids"].list.len() == 5) & (st["away_skater_ids"].list.len() == 5)
                     & st["home_goalie_id"].is_not_null() & st["away_goalie_id"].is_not_null()
                     & ~pl.col("is_quarantined") & (pl.col("season_label") == season))


def _player_rows(st: pl.DataFrame) -> pl.DataFrame:
    """One row per (player, stint): side, teammates, opponents, duration, start_type, team-relative score."""
    cols = ["game_id", "stint_id", "duration_seconds", "start_type", "score_state"]
    h = (st.select(*cols, pl.col("home_skater_ids").alias("player_id"), pl.col("away_skater_ids").alias("opps"),
                   pl.col("home_skater_ids").alias("mates"), pl.lit(True).alias("is_home"))
         .explode("player_id"))
    a = (st.select(*cols, pl.col("away_skater_ids").alias("player_id"), pl.col("home_skater_ids").alias("opps"),
                   pl.col("away_skater_ids").alias("mates"), pl.lit(False).alias("is_home"))
         .explode("player_id"))
    return pl.concat([h, a]).with_columns(
        team_score=pl.when(pl.col("is_home")).then(pl.col("score_state")).otherwise(-pl.col("score_state")))


def features() -> pl.DataFrame:
    parts = []
    for season in SEASONS:
        st = _stints5(season)
        pr = _player_rows(st)
        p5 = pl.read_parquet(ATLAS / "player_5v5.parquet").filter(pl.col("season_label") == season)
        off = dict(zip(p5["player_id"], p5["xga_per60"] * 0 + p5["xgf_per60"]))   # opponent offense rating
        qual = dict(zip(p5["player_id"], p5["xg_share"]))                          # overall quality rating

        # zone starts (team-relative) + score-state exposure
        base = pr.with_columns(
            oz=pl.when(pl.col("is_home")).then(pl.col("start_type") == "OZ").otherwise(pl.col("start_type") == "DZ"),
            dz=pl.when(pl.col("is_home")).then(pl.col("start_type") == "DZ").otherwise(pl.col("start_type") == "OZ"),
            trail=pl.col("team_score") < 0)
        zs = base.group_by("player_id").agg(
            toi_dep_s=pl.col("duration_seconds").sum(),
            oz_starts=pl.col("oz").sum(), dz_starts=pl.col("dz").sum(),
            trail_s=(pl.col("trail") * pl.col("duration_seconds")).sum())
        zs = zs.with_columns(
            oz_start_share=pl.col("oz_starts") / (pl.col("oz_starts") + pl.col("dz_starts") + 1),
            trail_share=pl.col("trail_s") / pl.col("toi_dep_s"))

        # QoC = TOI-weighted mean opponent offense (xGF/60)
        opp = pr.select("player_id", "duration_seconds", "opps").explode("opps").with_columns(
            r=pl.col("opps").replace_strict(off, default=None, return_dtype=pl.Float64))
        qoc = opp.filter(pl.col("r").is_not_null()).group_by("player_id").agg(
            qoc=(pl.col("r") * pl.col("duration_seconds")).sum() / pl.col("duration_seconds").sum())
        # QoT = TOI-weighted mean teammate quality (xG-share), excluding self
        mate = pr.select("player_id", "duration_seconds", "mates").explode("mates").filter(
            pl.col("player_id") != pl.col("mates")).with_columns(
            r=pl.col("mates").replace_strict(qual, default=None, return_dtype=pl.Float64))
        qot = mate.filter(pl.col("r").is_not_null()).group_by("player_id").agg(
            qot=(pl.col("r") * pl.col("duration_seconds")).sum() / pl.col("duration_seconds").sum())

        s = zs.join(qoc, on="player_id", how="left").join(qot, on="player_id", how="left").with_columns(
            season=pl.lit(season), toi_dep_min=pl.col("toi_dep_s") / 60.0)
        parts.append(s.select("player_id", "season", "oz_start_share", "trail_share", "qoc", "qot", "toi_dep_min"))
    out = pl.concat(parts)
    C.PARQUET.mkdir(parents=True, exist_ok=True)
    out.write_parquet(DEP)
    return out


def load() -> pl.DataFrame:
    if not DEP.exists():
        return features()
    return pl.read_parquet(DEP)


if __name__ == "__main__":
    f = features()
    print("deployment features:", f.height, "player-seasons")
    print(f.describe())
