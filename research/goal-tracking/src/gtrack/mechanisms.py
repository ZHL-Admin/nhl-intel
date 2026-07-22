"""Stage 1.0/1.1 — effective_release geometry + the goal-against mechanism taxonomy.

AMENDMENT 2026-07-14 governs this stage:
  TRACKED = a AND b (scorer tracked to the puck, puck continuous); the working universe for geometry.
  effective_release = the flight-start frame where the detector fired, else the arrival frame
    (release_source in {flight, arrival}). For no-flight goals the contact IS the release; every
    release-anchored window (east-west 2.0 s, goalie state, screen count) uses effective_release.
  Class-by-class universe: EAST_WEST/UNSET/SCREENED/LOCATION -> TRACKED clips at effective_release;
    CLEAN_LOOK -> flight-fired clips only; RUSH/IN_ZONE/SECOND_CHANCE -> all clips.

THE TWO LAWS hold: this DESCRIBES how tracked goals beat goalies (goals-only, no non-goal counterfactual
-> never a predictive "what beats goalies" claim); the beaten goalie is the stg_play_by_play label, the
geometry is context. Screen-/east-west-heavy profiles implicate the defense as much as the goalie.
"""
from __future__ import annotations

import numpy as np
import polars as pl

from . import bq, config, fuse, kinematics

MECH_FLAGS = config.PARQUET / "mechanism_flags.parquet"

# thresholds (frozen after the sensitivity table in the report)
EW_FT = 15.0
CLEAN_LOOK_DIST = 25.0
CLEAN_LOOK_GLAT = 3.0
UNSET_GLAT = 6.0
UNSET_DEPTH_DFT = 2.0
DEPTH_WINDOW = int(round(0.5 * config.HZ))       # 0.5 s = 5 frames
SECOND_CHANCE_S = 3.0
SHOT_FAMILY = ("shot-on-goal", "missed-shot", "blocked-shot")
LOC_CENTER_FT = 1.0                              # |puck_y - goalie_y| <= this => center third
SCREEN_R = config.SCREEN_CREASE_RADIUS_FT


def _dense(fidx, x, y, n):
    ax = np.full(n, np.nan); ay = np.full(n, np.nan)
    ax[fidx] = x; ay[fidx] = y
    return ax, ay


def _tri(px, py, ax, ay, bx, by, qx, qy):
    d = (ay - by) * (px - bx) + (bx - ax) * (py - by)
    d = d if d != 0 else 1e-9
    wa = ((ay - by) * (qx - bx) + (bx - ax) * (qy - by)) / d
    wb = ((by - py) * (qx - bx) + (px - bx) * (qy - by)) / d
    return (wa >= 0) & (wb >= 0) & (1 - wa - wb >= 0)


def geom_at_release(fr: pl.DataFrame, eff_rel: int, arrival: int, sign: float,
                    scoring_team: int, goalie_id: int, catches: str) -> dict:
    """Recompute all release-anchored geometry at effective_release (+ LOCATION at the goal line)."""
    n = int(fr["frame_index"].max()) + 1
    p = fr.filter(fr["is_puck"])
    px, py = _dense(p["frame_index"].to_numpy(), p["x_std"].to_numpy(), p["y_std"].to_numpy(), n)
    gl_x = 89.0 * sign
    out = {"release_dist": None, "ew_disp_2s": None, "screen_opp": 0, "screen_own": 0,
           "goalie_lat_speed_rel": None, "goalie_depth_change": None, "location": None}
    if eff_rel is None or eff_rel >= n or np.isnan(px[eff_rel]):
        # fall back to arrival if effective_release puck missing
        eff_rel = arrival if (arrival is not None and arrival < n and not np.isnan(px[arrival])) else None
        if eff_rel is None:
            return out
    rpx, rpy = px[eff_rel], py[eff_rel]
    out["release_dist"] = float(np.hypot(rpx - gl_x, rpy))
    # east-west: max lateral swing crossing y=0 in the 2.0 s before effective_release
    w = py[max(0, eff_rel - 20):eff_rel + 1]; w = w[~np.isnan(w)]
    out["ew_disp_2s"] = float(w.max() - w.min()) if w.size and (w.min() < 0 < w.max()) else 0.0
    # screens: bodies in triangle(puck, posts) within 10 ft of crease center
    skaters = fr.filter(~fr["is_puck"] & fr["player_id"].is_not_null() & (fr["frame_index"] == eff_rel))
    for row in skaters.iter_rows(named=True):
        xf, yf = row["x_std"], row["y_std"]
        if xf is None or row["player_id"] == goalie_id:
            continue
        if np.hypot(xf - gl_x, yf) <= SCREEN_R and _tri(rpx, rpy, gl_x, -3.0, gl_x, 3.0, xf, yf):
            if row["team_id"] == scoring_team:
                out["screen_own"] += 1
            else:
                out["screen_opp"] += 1
    # goalie kinematics (skip empty-net goals: no goalie in net)
    g = fr.filter(~fr["is_puck"] & (fr["player_id"] == goalie_id)) if goalie_id is not None else fr.head(0)
    if g.height:
        gx, gy = _dense(g["frame_index"].to_numpy(), g["x_std"].to_numpy(), g["y_std"].to_numpy(), n)
        gls = kinematics.lateral_speed_series(gy)
        if not np.isnan(gy[eff_rel]):
            out["goalie_lat_speed_rel"] = float(gls[eff_rel])
        # depth = distance off the goal line (|x - goal line|); change over the final 0.5 s
        f0 = max(0, eff_rel - DEPTH_WINDOW)
        if not np.isnan(gx[eff_rel]) and not np.isnan(gx[f0]):
            out["goalie_depth_change"] = float(abs(abs(gx[eff_rel] - gl_x) - abs(gx[f0] - gl_x)))
        # LOCATION at the goal line: puck y where it crosses vs goalie y, mapped to glove/center/blocker
        ay_puck = py[arrival] if (arrival is not None and arrival < n and not np.isnan(py[arrival])) else rpy
        gy_arr = gy[arrival] if (arrival is not None and arrival < n and not np.isnan(gy[arrival])) else (gy[eff_rel] if not np.isnan(gy[eff_rel]) else None)
        if gy_arr is not None:
            rel_y = ay_puck - gy_arr
            if abs(rel_y) <= LOC_CENTER_FT:
                out["location"] = "center"
            else:
                # facing up-ice: catch-left glove covers rink-y sign = -attack_sign; catch-right = +attack_sign
                glove_sign = (-sign) if catches == "L" else sign
                out["location"] = "glove" if np.sign(rel_y) == glove_sign else "blocker"
    return out


def _second_chance() -> pl.DataFrame:
    """Per goal: was there a shot-family pbp event by the scoring team within 3.0 s before it."""
    shots = bq.cached_query("shot_family", f"""
        select game_id, event_owner_team_id, period_number, time_in_period
        from `{config.BQ_PROJECT}.{config.STAGING}.stg_play_by_play`
        where type_desc_key in ('shot-on-goal','missed-shot','blocked-shot')
    """).with_columns(
        abs_s=(pl.col("period_number") - 1) * 1200
        + pl.col("time_in_period").str.split(":").list.get(0).cast(pl.Int64) * 60
        + pl.col("time_in_period").str.split(":").list.get(1).cast(pl.Int64))
    return shots.select("game_id", "event_owner_team_id", "abs_s")


def build(from_cache: bool = True) -> dict:
    goals = pl.read_parquet(fuse.FUSED)
    bio = bq.cached_query("player_bio", f"""
        select player_id, shoots from `{config.BQ_PROJECT}.{config.STAGING}.stg_player_bio`""")
    hand = {r["player_id"]: r["shoots"] for r in bio.iter_rows(named=True)}
    shots = _second_chance()

    rows = []
    for season in config.SEASONS:
        frames = fuse.pull_frames_season(season)
        parts = frames.partition_by("game_id", "event_id", as_dict=True, include_key=False)
        gs = goals.filter(pl.col("season") == season)
        for r in gs.iter_rows(named=True):
            key = (r["game_id"], r["event_id"])
            fr = parts.get(key)
            eff_rel = r["release_frame"] if r["flight_detected"] else r["arrival_frame"]
            rel_src = "flight" if r["flight_detected"] else "arrival"
            catches = hand.get(r["goalie_id"], "L")           # 100% covered; "L" is only a safety net
            g = geom_at_release(fr, eff_rel, r["arrival_frame"], r["attack_sign"], r["scoring_team_id"],
                                r["goalie_id"], catches) if (fr is not None and eff_rel is not None
                                                             and r["reconstruction_ok"]) else {
                "release_dist": None, "ew_disp_2s": None, "screen_opp": 0, "screen_own": 0,
                "goalie_lat_speed_rel": None, "goalie_depth_change": None, "location": None}
            tracked = bool(r["q_a"] and r["q_b"])
            rows.append({"game_id": r["game_id"], "event_id": r["event_id"], "season": season,
                         "goalie_id": r["goalie_id"], "scoring_team_id": r["scoring_team_id"],
                         "catches": catches, "abs_game_seconds": r["abs_game_seconds"],
                         "effective_release": eff_rel, "release_source": rel_src,
                         "flight_detected": r["flight_detected"], "tracked": tracked,
                         "rush_flag": r["rush_flag"], "entry_type": r["entry_type"],
                         "handedness_source": "stg_player_bio", **g})
    m = pl.DataFrame(rows)

    # SECOND_CHANCE: any shot-family by the scoring team in [goal_abs-3s, goal_abs)
    sc = (m.select("game_id", "event_id", "scoring_team_id", "abs_game_seconds")
          .join(shots, left_on=["game_id", "scoring_team_id"], right_on=["game_id", "event_owner_team_id"], how="left")
          .with_columns(dt=pl.col("abs_game_seconds") - pl.col("abs_s"))
          .with_columns(hit=(pl.col("dt") > 0) & (pl.col("dt") <= SECOND_CHANCE_S))
          .group_by("game_id", "event_id").agg(second_chance=pl.col("hit").fill_null(False).any()))
    m = m.join(sc, on=["game_id", "event_id"], how="left").with_columns(
        second_chance=pl.col("second_chance").fill_null(False))

    # ---- mechanism flags (class-by-class universes) ----
    scr = pl.col("screen_opp") + pl.col("screen_own")
    m = m.with_columns(
        screen_total=scr,
        EAST_WEST=pl.when(pl.col("tracked")).then(pl.col("ew_disp_2s") >= EW_FT).otherwise(None),
        SCREENED=pl.when(pl.col("tracked")).then(scr >= 1).otherwise(None),
        CLEAN_LOOK=pl.when(pl.col("flight_detected")).then(
            (scr == 0) & (pl.col("release_dist") >= CLEAN_LOOK_DIST)
            & (pl.col("goalie_lat_speed_rel") < CLEAN_LOOK_GLAT)).otherwise(None),
        UNSET=pl.when(pl.col("tracked")).then(
            (pl.col("goalie_lat_speed_rel") >= UNSET_GLAT)
            | (pl.col("goalie_depth_change") > UNSET_DEPTH_DFT)).otherwise(None),
        RUSH=pl.col("rush_flag"),
        IN_ZONE=(~pl.col("rush_flag")) & (pl.col("entry_type") != "off_frame_start"),
        SECOND_CHANCE=pl.col("second_chance"),
        LOCATION=pl.when(pl.col("tracked")).then(pl.col("location")).otherwise(None),
        screened_own_net=pl.col("screen_own"),
    )
    config.PARQUET.mkdir(parents=True, exist_ok=True)
    m.write_parquet(MECH_FLAGS)
    return {"n": m.height, "tracked": int(m["tracked"].sum()),
            "by_season_tracked": m.group_by("season").agg(n=pl.len(), tracked=pl.col("tracked").sum(),
                                                          flight=pl.col("flight_detected").sum()).sort("season").to_dicts()}


if __name__ == "__main__":
    import time
    t = time.time()
    r = build()
    print(f"mechanism flags for {r['n']:,} goals ({r['tracked']:,} TRACKED) in {time.time()-t:.0f}s")
    for d in r["by_season_tracked"]:
        print(f"  {d['season']}: n={d['n']:,} tracked={d['tracked']:,} ({d['tracked']/d['n']*100:.1f}%) flight={d['flight']:,}")
