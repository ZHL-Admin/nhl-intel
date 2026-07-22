"""G2.1 — goalie behavioral axes.

Foregrounded (DENOMINATOR-BACKED, from the pbp spine, over SAVES):
  rebound_control : rate that a save is followed within 3 s by another on-goal shot from the same team.
      Denominator = the goalie's saves. Lower = better rebound control. This is the only behavior axis
      with a real save denominator, so it is the only one that can approach a skill claim.

Goals-only (tracking enrichment, Stage 0/1; measured on GOALS-AGAINST — carry the denominator caveat,
never a skill claim without a denominator):
  depth            : mean goalie distance off the goal line at release (deep vs aggressive).
  lateral_recovery : mean goalie lateral speed at release (UNSET's continuous form; the Stage-1 r=0.34
                     candidate, re-tested here); companion unset_rate = UNSET-flag rate.
  ew_coverage      : on east-west goals, goalie lateral displacement vs puck lateral displacement over the
                     final 1.0 s (does he track post-to-post), recomputed from the frame cache.
"""
from __future__ import annotations

import numpy as np
import polars as pl

from . import config, spine as S

REB = config.PARQUET / "behavior_rebound.parquet"
TRK = config.PARQUET / "behavior_tracking.parquet"


def rebound_per_game() -> pl.DataFrame:
    s = pl.read_parquet(S.SPINE).sort(["game_id", "event_owner_team_id", "abs_s", "event_id"])
    s = s.with_columns(next_s=pl.col("abs_s").shift(-1).over(["game_id", "event_owner_team_id"]))
    s = s.with_columns(gen_rebound=((pl.col("next_s") - pl.col("abs_s") <= config.REBOUND_SECONDS)
                                    & (pl.col("next_s") - pl.col("abs_s") >= 0) & pl.col("next_s").is_not_null()))
    sv = s.filter((pl.col("saved") == 1) & pl.col("goalie_id").is_not_null())
    return (sv.group_by("goalie_id", "game_id", "season", "game_date")
            .agg(den=pl.len(), num=pl.col("gen_rebound").sum()))


def _ew_coverage(ewgoals: pl.DataFrame) -> pl.DataFrame:
    """Goalie lateral displacement in the puck's lateral direction over the final 1.0 s, normalized by
    puck lateral displacement (~1 = tracks post-to-post; ~0 = stays; <0 = wrong way)."""
    W = config.G2_EW_WINDOW
    out = []
    for season in config.TRACKING_SEASONS:
        sub = ewgoals.filter(pl.col("season") == season)
        if sub.height == 0:
            continue
        frames = pl.read_parquet(config.GT_FRAMES_DIR / f"frames_{season.replace('-', '_')}.parquet")
        parts = frames.partition_by("game_id", "event_id", as_dict=True, include_key=False)
        for r in sub.iter_rows(named=True):
            fr = parts.get((r["game_id"], r["event_id"]))
            eff = r["effective_release"]
            if fr is None or eff is None or eff - W < 0:
                continue
            puck = fr.filter(fr["is_puck"])
            gz = fr.filter((~fr["is_puck"]) & (fr["player_id"] == r["goalie_id"]))
            n = int(fr["frame_index"].max()) + 1
            def dense(df):
                a = np.full(n, np.nan)
                a[df["frame_index"].to_numpy()] = df["y_std"].to_numpy()
                return a
            if gz.height == 0:
                continue
            py, gy = dense(puck), dense(gz)
            if np.isnan(py[eff]) or np.isnan(py[eff - W]) or np.isnan(gy[eff]) or np.isnan(gy[eff - W]):
                continue
            pdy, gdy = py[eff] - py[eff - W], gy[eff] - gy[eff - W]
            cov = gdy * np.sign(pdy) / (abs(pdy) + 1.0)
            out.append({"game_id": r["game_id"], "event_id": r["event_id"], "ew_cov": float(cov)})
    return pl.DataFrame(out) if out else pl.DataFrame({"game_id": [], "event_id": [], "ew_cov": []})


def tracking_per_game() -> pl.DataFrame:
    m = pl.read_parquet(config.GT_MECH).filter(pl.col("tracked") & pl.col("goalie_id").is_not_null())
    f = pl.read_parquet(config.GT_FUSED).select("game_id", "event_id", "goalie_depth_rel", "game_date")
    d = m.join(f, on=["game_id", "event_id"], how="left")
    ew = _ew_coverage(d.filter(pl.col("EAST_WEST") == True))       # noqa: E712
    d = d.join(ew, on=["game_id", "event_id"], how="left")
    return d.group_by("goalie_id", "game_id", "season", "game_date").agg(
        n_goals=pl.len(),
        depth_num=pl.col("goalie_depth_rel").sum(), depth_den=pl.col("goalie_depth_rel").count(),
        lat_num=pl.col("goalie_lat_speed_rel").sum(), lat_den=pl.col("goalie_lat_speed_rel").count(),
        unset_num=pl.col("UNSET").sum(), unset_den=pl.col("UNSET").count(),
        ew_num=pl.col("ew_cov").sum(), ew_den=pl.col("ew_cov").count())


def build() -> dict:
    reb = rebound_per_game(); reb.write_parquet(REB)
    trk = tracking_per_game(); trk.write_parquet(TRK)
    return {"rebound_goalie_games": reb.height, "rebound_goalies": reb["goalie_id"].n_unique(),
            "tracking_goalie_games": trk.height, "tracking_goalies": trk["goalie_id"].n_unique(),
            "ew_goals_with_cov": int(trk["ew_den"].sum())}


if __name__ == "__main__":
    import time
    t = time.time()
    r = build()
    print(f"behavior built in {time.time()-t:.0f}s")
    print(f"  rebound: {r['rebound_goalie_games']:,} goalie-games, {r['rebound_goalies']} goalies")
    print(f"  tracking: {r['tracking_goalie_games']:,} goalie-games, {r['tracking_goalies']} goalies | ew-cov goals={r['ew_goals_with_cov']:,}")
