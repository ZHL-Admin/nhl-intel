"""Link 1 rev2 iter2 · frame-level PUCK-CONTROL timeline (replaces proximity-based possession).

Per goal, per frame: the nearest skater to the puck (all skaters + both goalies), his team side (D/A),
his distance, and the puck kinematics (speed, turn angle). CONTROL is defined physically — a slow puck
with a skater at stick-reach — so a fast shot flying past a net-front defender is NOT his possession
(the Ex10 phantom fix). Cached to nearest_puck.parquet.
"""
from __future__ import annotations

import numpy as np
import polars as pl

from . import config as C
from .data import universe

NEAREST = C.PARQUET / "nearest_puck.parquet"
CONTROL_DIST = 6.0      # ft: a skater this close to a slow puck "has" it
CONTROL_SPEED = 35.0    # ft/s: a puck moving faster than this is in flight, not controlled
STICK = 5.0             # ft: "the puck came to him" (reception reach; control not required)


def build() -> pl.DataFrame:
    u = universe().select("game_id", "event_id", "season", "start_frame", "goal_frame",
                          "defending_team_id", "scoring_team_id", "home_goalie_id", "away_goalie_id")
    parts = []
    for season, fname in zip(C.SEASONS, ["frames_2023_24.parquet", "frames_2024_25.parquet", "frames_2025_26.parquet"]):
        us = u.filter(pl.col("season") == season)
        fr = (pl.read_parquet(C.GT_FRAMES_DIR / fname,
                              columns=["game_id", "event_id", "frame_index", "is_puck", "player_id", "team_id", "x_std", "y_std"])
              .join(us, on=["game_id", "event_id"], how="inner")
              .filter(pl.col("frame_index") <= pl.col("goal_frame")))
        puck = fr.filter(pl.col("is_puck")).select("game_id", "event_id", "frame_index", px="x_std", py="y_std")
        # puck kinematics
        puck = puck.sort(["game_id", "event_id", "frame_index"]).with_columns(
            vx=(pl.col("px") - pl.col("px").shift(1)).over(["game_id", "event_id"]),
            vy=(pl.col("py") - pl.col("py").shift(1)).over(["game_id", "event_id"]))
        puck = puck.with_columns(
            speed=(pl.col("vx") ** 2 + pl.col("vy") ** 2).sqrt() * C.HZ,
            vx2=pl.col("vx").shift(-1).over(["game_id", "event_id"]),
            vy2=pl.col("vy").shift(-1).over(["game_id", "event_id"]))
        dot = pl.col("vx") * pl.col("vx2") + pl.col("vy") * pl.col("vy2")
        mag = ((pl.col("vx") ** 2 + pl.col("vy") ** 2).sqrt() * (pl.col("vx2") ** 2 + pl.col("vy2") ** 2).sqrt())
        puck = puck.with_columns(turn=(dot / (mag + 1e-9)).clip(-1, 1).arccos().degrees())
        # nearest skater (incl goalies) to the puck each frame
        sk = fr.filter(~pl.col("is_puck")).join(puck.select("game_id", "event_id", "frame_index", "px", "py"),
                                                on=["game_id", "event_id", "frame_index"], how="inner")
        sk = sk.with_columns(d=((pl.col("x_std") - pl.col("px")) ** 2 + (pl.col("y_std") - pl.col("py")) ** 2).sqrt())
        near = (sk.sort("d").group_by("game_id", "event_id", "frame_index", maintain_order=True).first()
                .with_columns(near_side=pl.when(pl.col("team_id") == pl.col("defending_team_id")).then(pl.lit("D")).otherwise(pl.lit("A")),
                              is_goalie=(pl.col("player_id") == pl.col("home_goalie_id")) | (pl.col("player_id") == pl.col("away_goalie_id")))
                .select("game_id", "event_id", "frame_index", near_id="player_id", near_side="near_side",
                        near_dist="d", is_goalie="is_goalie"))
        near = near.join(puck.select("game_id", "event_id", "frame_index", "speed", "turn", "px", "py"),
                         on=["game_id", "event_id", "frame_index"], how="left")
        near = near.with_columns(
            control=(pl.col("near_dist") <= CONTROL_DIST) & (pl.col("speed") <= CONTROL_SPEED),
            season=pl.lit(season))
        parts.append(near)
    out = pl.concat(parts)
    C.PARQUET.mkdir(parents=True, exist_ok=True)
    out.write_parquet(NEAREST)
    return out


if __name__ == "__main__":
    o = build()
    print(f"nearest-puck frames: {o.height:,} | control frames: {int(o['control'].sum()):,} "
          f"({o['control'].mean()*100:.0f}%) | goals: {o.select(pl.struct('game_id','event_id').n_unique()).item():,}")
