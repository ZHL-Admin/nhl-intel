"""Phase 0.3 — defensive-frame primitive set: per goal-against, per frame, per DEFENDING skater.

Geometry only, no labels (LAW 2). Measured in the defending team's frame: coordinates are
attack-direction normalized so the DEFENDED net sits at (+89, 0) (x_norm = x_std*attack_sign,
y_norm = y_std*attack_sign — a 180deg rotation when the attack is toward -x). Per defender-frame:
  vs own net    : dist_net (to the defended net)
  vs puck       : dx_puck, dy_puck, dist_puck
  vs teammates  : off_centroid (distance to the defenders' centroid) + team_spread (mean off-centroid,
                  per frame) + n_def (defending skaters present = the pentagon size; 5 at 5v5)
  vs attackers  : dist_nearest_atk
  situation     : zone (dzone/neutral/ozone), puck_side (strong/weak), low_high (low/high/na)
Universe: TRACKED goals (Stage 0 a AND b). Goalies excluded from skaters.
"""
from __future__ import annotations

import sys

import polars as pl

from . import config as C

sys.path.insert(0, str(C.GT_SRC))


def _fused_ctx() -> pl.DataFrame:
    f = pl.read_parquet(C.GT_FUSED)
    return f.with_columns(
        defending_team_id=pl.when(pl.col("home_team_id") == pl.col("scoring_team_id"))
        .then(pl.col("away_team_id")).otherwise(pl.col("home_team_id")),
        tracked=pl.col("q_a") & pl.col("q_b")).select(
        "game_id", "event_id", "season", "scoring_team_id", "defending_team_id", "goalie_id",
        "home_goalie_id", "away_goalie_id", "attack_sign", "strength_state", "tracked", "reconstruction_ok")


def build_season(season: str) -> dict:
    ctx = _fused_ctx().filter((pl.col("season") == season) & pl.col("tracked") & pl.col("reconstruction_ok"))
    fr = (pl.read_parquet(C.GT_FRAMES_DIR / f"frames_{season.replace('-', '_')}.parquet")
          .join(ctx, on=["game_id", "event_id"], how="inner"))
    # attack-direction normalization (defended net -> +89,0) + drop goalies from skaters
    fr = fr.with_columns(x_norm=pl.col("x_std") * pl.col("attack_sign"),
                         y_norm=pl.col("y_std") * pl.col("attack_sign"))
    puck = fr.filter(pl.col("is_puck")).select("game_id", "event_id", "frame_index",
                                               puck_x=pl.col("x_norm"), puck_y=pl.col("y_norm"))
    goalies = pl.concat([ctx.select(g="home_goalie_id"), ctx.select(g="away_goalie_id")])["g"].drop_nulls().unique().to_list()
    sk = fr.filter(~pl.col("is_puck") & pl.col("player_id").is_not_null()
                   & ~pl.col("player_id").is_in(goalies) & pl.col("x_norm").is_not_null())
    defenders = sk.filter(pl.col("team_id") == pl.col("defending_team_id"))
    attackers = sk.filter(pl.col("team_id") == pl.col("scoring_team_id")).select(
        "game_id", "event_id", "frame_index", atk_x="x_norm", atk_y="y_norm")

    # centroid / spread / n_def per (goal, frame)
    cen = defenders.group_by("game_id", "event_id", "frame_index").agg(
        cx=pl.col("x_norm").mean(), cy=pl.col("y_norm").mean(), n_def=pl.len())
    d = (defenders.join(puck, on=["game_id", "event_id", "frame_index"], how="left")
         .join(cen, on=["game_id", "event_id", "frame_index"], how="left"))
    d = d.with_columns(
        dist_net=((pl.col("x_norm") - C.DEF_NET_X) ** 2 + pl.col("y_norm") ** 2).sqrt(),
        dx_puck=pl.col("x_norm") - pl.col("puck_x"), dy_puck=pl.col("y_norm") - pl.col("puck_y"),
        off_centroid=((pl.col("x_norm") - pl.col("cx")) ** 2 + (pl.col("y_norm") - pl.col("cy")) ** 2).sqrt())
    d = d.with_columns(dist_puck=(pl.col("dx_puck") ** 2 + pl.col("dy_puck") ** 2).sqrt())
    spread = d.group_by("game_id", "event_id", "frame_index").agg(team_spread=pl.col("off_centroid").mean())
    d = d.join(spread, on=["game_id", "event_id", "frame_index"], how="left")

    # nearest attacker (defender x attacker within (goal, frame))
    na = (d.select("game_id", "event_id", "frame_index", "player_id", "x_norm", "y_norm")
          .join(attackers, on=["game_id", "event_id", "frame_index"], how="left")
          .with_columns(dda=((pl.col("x_norm") - pl.col("atk_x")) ** 2 + (pl.col("y_norm") - pl.col("atk_y")) ** 2).sqrt())
          .group_by("game_id", "event_id", "frame_index", "player_id").agg(dist_nearest_atk=pl.col("dda").min()))
    d = d.join(na, on=["game_id", "event_id", "frame_index", "player_id"], how="left")

    # situation labels (geometry buckets, no scheme labels)
    d = d.with_columns(
        zone=pl.when(pl.col("x_norm") >= C.BLUE_LINE).then(pl.lit("dzone"))
        .when(pl.col("x_norm") <= -C.BLUE_LINE).then(pl.lit("ozone")).otherwise(pl.lit("neutral")),
        puck_side=pl.when(pl.col("y_norm").sign() == pl.col("puck_y").sign()).then(pl.lit("strong")).otherwise(pl.lit("weak")),
        low_high=pl.when(pl.col("x_norm") >= C.LOWHIGH_X).then(pl.lit("low"))
        .when(pl.col("x_norm") >= C.BLUE_LINE).then(pl.lit("high")).otherwise(pl.lit("na")))

    out = d.select("game_id", "event_id", "season", "defending_team_id", "scoring_team_id", "frame_index",
                   "player_id", "strength_state", "n_def", "x_norm", "y_norm", "dist_net", "dist_puck",
                   "dx_puck", "dy_puck", "off_centroid", "team_spread", "dist_nearest_atk",
                   "zone", "puck_side", "low_high")
    C.PARQUET.mkdir(parents=True, exist_ok=True)
    out.write_parquet(C.PARQUET / f"def_prim_{season.replace('-', '_')}.parquet")
    return {"season": season, "rows": out.height, "goals": out.select("game_id", "event_id").n_unique(),
            "teams": out["defending_team_id"].n_unique()}


def build() -> list[dict]:
    return [build_season(s) for s in C.SEASONS]


if __name__ == "__main__":
    import time
    t = time.time()
    for r in build():
        print(f"{r['season']}: {r['rows']:,} defender-frames | {r['goals']:,} goals-against | {r['teams']} teams", flush=True)
    print(f"done in {time.time()-t:.0f}s")
