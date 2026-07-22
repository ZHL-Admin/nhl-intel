"""Link 1 rev2 · possession + pass layer from goal_events (read-only).

goal_events carries `segment` rows (the possession/carrier timeline: player_id, team_id, start/end
frame) and `pass` rows (passer, receiver, start/end frame + coords). From these we build:
  - the possession timeline per goal (who controls the puck over the window),
  - E4 turnover candidates (a defending-team possession flipping to the attacking team in the
    defensive half, retained to the goal), attributed to the last controlled defending possessor,
  - the pre-goal pass list (for R6 soft-close on the key passer).

Map frame (per R1-SPEC): the defended net is normalised to nx=+89 by nx = attack_sign*x_std,
ny = attack_sign*y_std (a 180 deg rotation that preserves left/right from the defending goalie's view);
depth = 89 - nx (0 at goal line, ~64 at blue line), lateral = ny (negative = left).
"""
from __future__ import annotations

import polars as pl

from . import config as C
from .data import universe
from .puckctrl import NEAREST, STICK

SEG = C.PARQUET / "segments.parquet"
TURN = C.PARQUET / "turnovers.parquet"
TURN_RAW = C.PARQUET / "turnovers_raw.parquet"    # pre-reality-gate (segment-based), for the phantom audit
PASSES = C.PARQUET / "passes.parquet"
PUCK = C.PARQUET / "puck_positions.parquet"
GENUINE_SPEED = 20.0     # ft/s: genuine puck control/reception (stricter than the phantom-gate 35)
MIN_CTRL_RUN = 3         # frames: a real defending possession (>=0.3s)
RECENT_FR = 30           # frames: the defending possession must be within 3s of the flip to be "this" turnover
CTRL_MIN = 2          # frames: a "controlled" possession segment (drop 1-frame deflections for attribution)
REGAIN_MIN = 8        # frames: a defending segment this long after the flip = control regained (cancels E4)
MAX_T2G = 10.0        # s: goal must follow the turnover within this
DANGER_DEPTH, DANGER_LAT = 20.0, 0.0   # slot reference in map frame for turnover danger


def _puck_positions() -> pl.DataFrame:
    u = universe().select("game_id", "event_id", "season", "start_frame", "goal_frame", "attack_sign")
    parts = []
    for season, fname in zip(C.SEASONS, ["frames_2023_24.parquet", "frames_2024_25.parquet", "frames_2025_26.parquet"]):
        us = u.filter(pl.col("season") == season)
        fr = (pl.read_parquet(C.GT_FRAMES_DIR / fname, columns=["game_id", "event_id", "frame_index", "is_puck", "x_std", "y_std"])
              .filter(pl.col("is_puck")).join(us, on=["game_id", "event_id"], how="inner"))
        parts.append(fr.select("game_id", "event_id", "frame_index",
                               p_depth=89.0 - pl.col("attack_sign") * pl.col("x_std"),
                               p_lat=pl.col("attack_sign") * pl.col("y_std")))
    return pl.concat(parts)


def build() -> dict:
    u = universe()
    ge = pl.read_parquet(C.GT_EVENTS)
    keep = u.select("game_id", "event_id", "defending_team_id", "scoring_team_id", "start_frame", "goal_frame", "attack_sign")

    seg = (ge.filter(pl.col("event_type") == "segment")
           .select("game_id", "event_id", "event_index", "player_id", "team_id", "start_frame", "end_frame")
           .join(keep, on=["game_id", "event_id"], how="inner")
           .filter((pl.col("start_frame") <= pl.col("goal_frame")))
           .with_columns(dur=pl.col("end_frame") - pl.col("start_frame") + 1,
                         side=pl.when(pl.col("team_id") == pl.col("defending_team_id")).then(pl.lit("D")).otherwise(pl.lit("A")))
           .sort(["game_id", "event_id", "start_frame"]))
    seg.write_parquet(SEG)

    puck = _puck_positions()
    puck.write_parquet(PUCK)

    # (A) segment/proximity-based turnovers (the PRE-reality-gate baseline, for the phantom audit)
    raw = []
    for (gid, eid), g in seg.group_by(["game_id", "event_id"], maintain_order=True):
        s = g.sort("start_frame").to_dicts()
        gf = s[0]["goal_frame"]
        flips = [i for i in range(len(s) - 1) if s[i]["side"] == "D" and s[i + 1]["side"] == "A"]
        for i in reversed(flips):
            ff = s[i + 1]["start_frame"]
            if ff > gf:
                continue
            if any(x["side"] == "D" and x["dur"] >= REGAIN_MIN and ff < x["start_frame"] <= gf for x in s[i + 1:]):
                continue
            giver = next((x for x in s[i::-1] if x["side"] == "D" and x["dur"] >= CTRL_MIN), s[i])
            if (gf - ff) / C.HZ <= MAX_T2G:
                raw.append({"game_id": gid, "event_id": eid, "giveaway_player": giver["player_id"], "flip_frame": ff})
            break
    tv_raw = pl.DataFrame(raw) if raw else pl.DataFrame(schema={"game_id": pl.Int64, "event_id": pl.Int64, "giveaway_player": pl.Int64, "flip_frame": pl.Int64})
    tv_raw.write_parquet(TURN_RAW)

    # (B) reality-gated, frame-based turnovers from the puck-control timeline
    near = pl.read_parquet(NEAREST).sort(["game_id", "event_id", "frame_index"])
    rows = []
    for (gid, eid), g in near.group_by(["game_id", "event_id"], maintain_order=True):
        ctrl = [r for r in g.to_dicts() if r["control"]]
        gf = g["frame_index"][-1]
        if len(ctrl) < MIN_CTRL_RUN:
            continue
        # per-touch control runs (merge same-side, gaps <= 2 frames)
        runs, cur = [], None
        for r in ctrl:
            if cur and r["near_side"] == cur["side"] and r["frame_index"] - cur["rows"][-1]["frame_index"] <= 2:
                cur["rows"].append(r)
            else:
                if cur:
                    runs.append(cur)
                cur = {"side": r["near_side"], "rows": [r]}
        if cur:
            runs.append(cur)
        for run in runs:
            run["len"] = len(run["rows"])
            run["is_goalie"] = all(x["is_goalie"] for x in run["rows"])
        # REALITY-GATED FLIP: the last attacking takeover that leads to the goal, where (a) the defending
        # team held REAL possession (a >=MIN control run, goalie eligible) within RECENT frames before it,
        # and (b) no non-goalie defending real possession regains it before the goal (a goalie stop after
        # the flip is not a regain). No real prior D possession => no turnover (kills the Ex10 phantom).
        d_real = [run for run in runs if run["side"] == "D" and run["len"] >= MIN_CTRL_RUN]
        nong_d_real = [run for run in d_real if not run["is_goalie"]]
        a_runs = [run for run in runs if run["side"] == "A"]
        if not d_real or not a_runs:
            continue
        flip_frame = None
        for arun in reversed(a_runs):
            ff = arun["rows"][0]["frame_index"]
            if ff > gf:
                continue
            if any(dr["rows"][0]["frame_index"] > ff for dr in nong_d_real):     # non-goalie D regained -> not final
                continue
            if not any(0 <= ff - dr["rows"][-1]["frame_index"] <= RECENT_FR for dr in d_real):  # real recent D possession
                continue
            flip_frame = ff
            break
        if flip_frame is None:
            continue
        t2g = (gf - flip_frame) / C.HZ
        if t2g > MAX_T2G:
            continue
        drows = [x for run in runs if run["side"] == "D" for x in run["rows"] if x["frame_index"] < flip_frame]
        if not drows:
            continue
        # attribution: last GENUINE controller (slow puck) = who had it and lost it; a later within-STICK
        # defending touch that TURNED the puck is a botched reception (that receiver instead).
        genuine = [r for r in drows if (r["speed"] or 99) <= GENUINE_SPEED]
        giver = genuine[-1] if genuine else drows[-1]
        for r in drows:
            if r["frame_index"] > giver["frame_index"] and r["near_dist"] <= STICK and (r["turn"] or 0) >= 25:
                giver = r
        recv_kind = "botched_reception" if (giver["near_dist"] <= STICK and (giver["turn"] or 0) >= 25 and (giver["speed"] or 0) > GENUINE_SPEED) else "genuine_or_passer"
        rows.append({"game_id": gid, "event_id": eid, "giveaway_player": giver["near_id"],
                     "flip_frame": flip_frame, "time_to_goal": t2g,
                     "giver_is_goalie": bool(giver["is_goalie"]), "attribution_kind": recv_kind,
                     "touches": sum(1 for p in a_runs if p["rows"][0]["frame_index"] > flip_frame)})
    tv = pl.DataFrame(rows) if rows else pl.DataFrame(
        schema={"game_id": pl.Int64, "event_id": pl.Int64, "giveaway_player": pl.Int64, "flip_frame": pl.Int64,
                "time_to_goal": pl.Float64, "giver_is_goalie": pl.Boolean, "attribution_kind": pl.Utf8, "touches": pl.Int64})
    tv = tv.join(puck.rename({"frame_index": "flip_frame"}), on=["game_id", "event_id", "flip_frame"], how="left")
    tv = tv.with_columns(dist_slot_turn=((pl.col("p_depth") - DANGER_DEPTH) ** 2 + (pl.col("p_lat") - DANGER_LAT) ** 2).sqrt())
    tv.write_parquet(TURN)
    # phantom rate: raw fires with no surviving gated turnover on the same goal
    gated_goals = set(zip(tv["game_id"].to_list(), tv["event_id"].to_list())) if tv.height else set()
    phantom = sum(1 for r in tv_raw.iter_rows(named=True) if (r["game_id"], r["event_id"]) not in gated_goals)

    passes = (ge.filter(pl.col("event_type") == "pass")
              .select("game_id", "event_id", "passer_id", "receiver_id", "start_frame", "end_frame",
                      "start_x", "start_y", "end_x", "end_y")
              .join(keep, on=["game_id", "event_id"], how="inner")
              .filter(pl.col("end_frame") <= pl.col("goal_frame"))
              .with_columns(
                  recv_depth=89.0 - pl.col("attack_sign") * pl.col("end_x"),
                  recv_lat=pl.col("attack_sign") * pl.col("end_y")))
    passes.write_parquet(PASSES)

    return {"segments": seg.height, "turnover_goals": tv.height, "raw_turnovers": tv_raw.height,
            "phantom": phantom, "phantom_rate": phantom / tv_raw.height if tv_raw.height else 0.0,
            "goalie_turnovers": int(tv["giver_is_goalie"].sum()) if tv.height else 0,
            "passes": passes.height}


if __name__ == "__main__":
    r = build()
    print(f"segments: {r['segments']:,} | pre-gate (segment) turnovers: {r['raw_turnovers']:,} "
          f"| reality-gated turnovers: {r['turnover_goals']:,} (goalie-attributed: {r['goalie_turnovers']:,})")
    print(f"PHANTOM RATE: {r['phantom']:,} of {r['raw_turnovers']:,} segment fires fail the reality gate "
          f"({r['phantom_rate']*100:.0f}%)")
