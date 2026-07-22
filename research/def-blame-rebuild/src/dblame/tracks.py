"""Link 0 · per-defender COVERAGE TRACKS across the possession window (geometry only, no blame).

For every defending skater (goalies excluded), across every frame of the possession window:
  near_att_id   : identity of his nearest attacker that frame (so we can see if he manages one man
                  or switches among several)
  dist_near_atk : distance to that nearest attacker
  dist_puck     : distance to the puck
  dist_slot     : distance to the most dangerous ice (net-front / slot)
  dist_net      : his own distance to the defended net
  goal_side     : is he goal-side of his nearest attacker (nearer the defended net along the attack axis)

n_def=5 / n_att=5 is enforced here (a goal is kept only if exactly five defending and five attacking
skaters are tracked at the shot). The per-defender dist_near_atk is validated against the def-scheme
phase-0 primitive in link0.py.
"""
from __future__ import annotations

import polars as pl

from . import config as C
from .data import universe

TRACKS = C.PARQUET / "tracks.parquet"
OCC = C.PARQUET / "occupancy.parquet"


def _season_tracks(us: pl.DataFrame, frames_path) -> tuple[pl.DataFrame, pl.DataFrame]:
    bounds = us.select("game_id", "event_id", "defending_team_id", "scoring_team_id",
                       "home_goalie_id", "away_goalie_id", "net_x", "attack_sign",
                       "start_frame", "goal_frame", "scorer_id", "assist1_id")
    fr = (pl.read_parquet(frames_path, columns=["game_id", "event_id", "frame_index", "is_puck",
                                                "player_id", "team_id", "x_std", "y_std"])
          .join(bounds, on=["game_id", "event_id"], how="inner")
          .filter((pl.col("frame_index") >= pl.col("start_frame")) & (pl.col("frame_index") <= pl.col("goal_frame"))))

    is_goalie = (pl.col("player_id") == pl.col("home_goalie_id")) | (pl.col("player_id") == pl.col("away_goalie_id"))
    skaters = fr.filter(~pl.col("is_puck") & ~is_goalie)
    defenders = skaters.filter(pl.col("team_id") == pl.col("defending_team_id")).select(
        "game_id", "event_id", "frame_index", "net_x", "attack_sign", did="player_id", dx="x_std", dy="y_std")
    attackers = skaters.filter(pl.col("team_id") == pl.col("scoring_team_id")).select(
        "game_id", "event_id", "frame_index", "scorer_id", "assist1_id", aid="player_id", ax="x_std", ay="y_std")
    puck = fr.filter(pl.col("is_puck")).select("game_id", "event_id", "frame_index", px="x_std", py="y_std")
    scorer = attackers.filter(pl.col("aid") == pl.col("scorer_id")).select(
        "game_id", "event_id", "frame_index", sx="ax", sy="ay")
    ast1 = attackers.filter(pl.col("aid") == pl.col("assist1_id")).select(
        "game_id", "event_id", "frame_index", a1x="ax", a1y="ay")

    # occupancy at the shot frame: enforce n_def==5 & n_att==5
    gf = us.select("game_id", "event_id", "goal_frame")
    nd = (defenders.join(gf, on=["game_id", "event_id"]).filter(pl.col("frame_index") == pl.col("goal_frame"))
          .group_by("game_id", "event_id").agg(n_def=pl.col("did").n_unique()))
    na = (attackers.join(gf, on=["game_id", "event_id"]).filter(pl.col("frame_index") == pl.col("goal_frame"))
          .group_by("game_id", "event_id").agg(n_att=pl.col("aid").n_unique()))
    occ = nd.join(na, on=["game_id", "event_id"], how="full", coalesce=True).fill_null(0)
    keep = occ.filter((pl.col("n_def") == 5) & (pl.col("n_att") == 5)).select("game_id", "event_id")

    defenders = defenders.join(keep, on=["game_id", "event_id"], how="inner")
    # nearest attacker per (defender, frame)
    pair = defenders.join(attackers, on=["game_id", "event_id", "frame_index"], how="inner").with_columns(
        d=((pl.col("dx") - pl.col("ax")) ** 2 + (pl.col("dy") - pl.col("ay")) ** 2).sqrt())
    near = (pair.sort("d").group_by("game_id", "event_id", "frame_index", "did", maintain_order=True)
            .first().rename({"d": "dist_near_atk"}))
    t = (near.join(puck, on=["game_id", "event_id", "frame_index"], how="left")
         .join(scorer, on=["game_id", "event_id", "frame_index"], how="left")
         .join(ast1, on=["game_id", "event_id", "frame_index"], how="left")).with_columns(
        dist_puck=((pl.col("dx") - pl.col("px")) ** 2 + (pl.col("dy") - pl.col("py")) ** 2).sqrt(),
        dist_slot=((pl.col("dx") - pl.col("attack_sign") * C.SLOT_X) ** 2 + pl.col("dy") ** 2).sqrt(),
        dist_net=((pl.col("dx") - pl.col("net_x")) ** 2 + pl.col("dy") ** 2).sqrt(),
        att_dist_net=((pl.col("ax") - pl.col("net_x")) ** 2 + pl.col("ay") ** 2).sqrt(),
        goal_side=(pl.col("attack_sign") * (pl.col("dx") - pl.col("ax"))) > 0,
        dist_scorer=((pl.col("dx") - pl.col("sx")) ** 2 + (pl.col("dy") - pl.col("sy")) ** 2).sqrt(),
        scorer_goal_side=(pl.col("attack_sign") * (pl.col("dx") - pl.col("sx"))) > 0,
        dist_assist1=((pl.col("dx") - pl.col("a1x")) ** 2 + (pl.col("dy") - pl.col("a1y")) ** 2).sqrt(),
        assist1_goal_side=(pl.col("attack_sign") * (pl.col("dx") - pl.col("a1x"))) > 0)
    t = t.select("game_id", "event_id", "frame_index",
                 "dist_near_atk", "dist_puck", "dist_slot", "dist_net", "att_dist_net", "goal_side",
                 "dist_scorer", "scorer_goal_side", "dist_assist1", "assist1_goal_side",
                 player_id=pl.col("did"), near_att_id=pl.col("aid"),
                 def_x=pl.col("dx"), def_y=pl.col("dy"), att_x=pl.col("ax"), att_y=pl.col("ay"))
    return t, occ


def build() -> dict:
    u = universe()
    parts, occs = [], []
    for season, fname in zip(C.SEASONS, ["frames_2023_24.parquet", "frames_2024_25.parquet", "frames_2025_26.parquet"]):
        us = u.filter(pl.col("season") == season)
        t, occ = _season_tracks(us, C.GT_FRAMES_DIR / fname)
        t = t.with_columns(season=pl.lit(season))
        parts.append(t); occs.append(occ.with_columns(season=pl.lit(season)))
    tracks = pl.concat(parts); occ = pl.concat(occs)
    C.PARQUET.mkdir(parents=True, exist_ok=True)
    tracks.write_parquet(TRACKS); occ.write_parquet(OCC)
    kept = tracks.select(pl.struct("game_id", "event_id").n_unique()).item()
    return {"track_rows": tracks.height, "goals_with_tracks": kept,
            "n_def5_n_att5": int(occ.filter((pl.col("n_def") == 5) & (pl.col("n_att") == 5)).height),
            "occ_total": occ.height}


if __name__ == "__main__":
    r = build()
    print(f"coverage tracks: {r['track_rows']:,} defender-frames over {r['goals_with_tracks']:,} goals "
          f"(n_def=5 & n_att=5: {r['n_def5_n_att5']:,} of {r['occ_total']:,})")
