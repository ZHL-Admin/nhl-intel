"""Link 0 — the fused defensive event per goal.

Reuses the def-scheme phase-0 defensive-frame primitives (the 5 defenders' normalized trajectories +
dist-to-puck/net/nearest-attacker) and adds, from gtrack frames, the PUCK and the KNOWN scorer's
trajectory (pbp scorer fused to his tracked skater, with a Stage-0-style fidelity flag). Everything is in
the defending team's attack-normalized frame (defended net at +89,0).
"""
from __future__ import annotations

import glob

import numpy as np
import polars as pl

from . import config as C

EXHIBITION = [60, 62, 66, 67, 68, 7801, 7802, 7803, 7804, 7805, 7806]
SCORER_PUCK = C.PARQUET / "scorer_puck.parquet"
QUAL = C.PARQUET / "qualifying_goals.parquet"


def qualifying() -> pl.DataFrame:
    prim = sorted(glob.glob(str(C.DEFSCHEME_PRIM / "def_prim_*.parquet")))
    allp = pl.concat([pl.read_parquet(f, columns=["game_id", "event_id", "season", "defending_team_id", "scoring_team_id", "n_def"]) for f in prim])
    return (allp.filter((pl.col("n_def") == 5) & ~pl.col("defending_team_id").is_in(EXHIBITION))
            .select("game_id", "event_id", "season", "defending_team_id", "scoring_team_id").unique())


def _fused_ctx() -> pl.DataFrame:
    f = pl.read_parquet(C.GT_FUSED)
    return f.with_columns(
        eff_rel=pl.when(pl.col("flight_detected")).then(pl.col("release_frame")).otherwise(pl.col("arrival_frame"))
    ).select("game_id", "event_id", "scorer_id", "goalie_id", "attack_sign", "eff_rel", "arrival_frame")


def build() -> dict:
    qual = qualifying()
    ctx = _fused_ctx()
    rows_sp = []
    fid = []
    for season in C.SEASONS:
        qs = qual.filter(pl.col("season") == season)
        fr = (pl.read_parquet(C.GT_FRAMES_DIR / f"frames_{season.replace('-', '_')}.parquet")
              .join(qs.select("game_id", "event_id"), on=["game_id", "event_id"], how="inner")
              .join(ctx, on=["game_id", "event_id"], how="left")
              .with_columns(x_norm=pl.col("x_std") * pl.col("attack_sign"),
                            y_norm=pl.col("y_std") * pl.col("attack_sign")))
        puck = fr.filter(pl.col("is_puck")).select("game_id", "event_id", "frame_index",
                                                   px=pl.col("x_norm"), py=pl.col("y_norm"))
        scorer = fr.filter(pl.col("player_id") == pl.col("scorer_id")).select(
            "game_id", "event_id", "frame_index", sx=pl.col("x_norm"), sy=pl.col("y_norm"))
        sp = puck.join(scorer, on=["game_id", "event_id", "frame_index"], how="outer_coalesce" if False else "full", coalesce=True)
        sp = sp.with_columns(season=pl.lit(season))
        rows_sp.append(sp)
        # fidelity (RELEASE-anchored, Stage-0 style): the scorer's tracked skater is within stick-reach of
        # the puck in the final 1.0 s up to effective_release -> the pbp scorer is the tracked shooter and
        # Signal B (scorer-anchored) is trustworthy on this goal.
        sc_present = scorer.group_by("game_id", "event_id").agg(n=pl.len())
        near_rel = (puck.join(scorer, on=["game_id", "event_id", "frame_index"], how="inner")
                    .join(ctx.select("game_id", "event_id", "eff_rel"), on=["game_id", "event_id"], how="left")
                    .filter(pl.col("frame_index").is_between(pl.col("eff_rel") - C.WIN_1S, pl.col("eff_rel")))
                    .with_columns(d=((pl.col("px") - pl.col("sx")) ** 2 + (pl.col("py") - pl.col("sy")) ** 2).sqrt())
                    .group_by("game_id", "event_id").agg(min_scorer_puck_rel=pl.col("d").min()))
        f = (qs.join(sc_present, on=["game_id", "event_id"], how="left")
             .join(near_rel, on=["game_id", "event_id"], how="left")
             .with_columns(scorer_tracked=pl.col("n").is_not_null(),
                           fidelity=(pl.col("min_scorer_puck_rel") <= 6.0).fill_null(False)))
        fid.append(f)
    sp = pl.concat(rows_sp)
    C.PARQUET.mkdir(parents=True, exist_ok=True)
    sp.write_parquet(SCORER_PUCK)
    fids = pl.concat(fid)
    fids.write_parquet(QUAL)
    per_ts = fids.group_by("defending_team_id", "season").agg(
        qualifying=pl.len(), fidelity=pl.col("fidelity").mean(), scorer_tracked=pl.col("scorer_tracked").mean())
    return {"n_goals": qual.height, "n_teams": qual["defending_team_id"].n_unique(),
            "scorer_tracked_rate": float(fids["scorer_tracked"].mean()),
            "fidelity_rate": float(fids["fidelity"].mean()),
            "per_team_season": {"median_qual": int(per_ts["qualifying"].median()),
                                "min_qual": int(per_ts["qualifying"].min()), "max_qual": int(per_ts["qualifying"].max()),
                                "n_team_seasons": per_ts.height}}


if __name__ == "__main__":
    import time
    t = time.time()
    r = build()
    print(f"fused defensive event: {r['n_goals']:,} qualifying goals-against, {r['n_teams']} teams, in {time.time()-t:.0f}s")
    print(f"  scorer-tracked rate {r['scorer_tracked_rate']*100:.1f}% | fidelity (scorer within stick-reach of puck) {r['fidelity_rate']*100:.1f}%")
    print(f"  per team-season qualifying: median {r['per_team_season']['median_qual']} "
          f"(min {r['per_team_season']['min_qual']}, max {r['per_team_season']['max_qual']}, {r['per_team_season']['n_team_seasons']} team-seasons)")
