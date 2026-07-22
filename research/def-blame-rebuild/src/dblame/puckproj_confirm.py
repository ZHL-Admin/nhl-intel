"""Puck-Path Projector §9 — READ-ONLY power confirm: match-set-size distribution BY ZONE, after distinct-goal
collapse and leave-one-goal-out, at PROVISIONAL knobs. Answers only: at a typical live state in each decision
zone, how many DISTINCT historical goals match (position within radius AND recent-motion heading within
tolerance)? If the interesting decision states match only a handful, projection is too sparse there. No
projector, no modes, no sharpness — just the match counts. STOP.
"""
from __future__ import annotations

import numpy as np
import polars as pl

from . import config as C
from .data import universe

WIN = 100          # ~10s buildup
MW = 3             # recent-motion window = 3 frames (0.3s), backward
RADIUS = 6.0       # PROVISIONAL position match radius (ft)
HEAD_TOL = 45.0    # PROVISIONAL heading tolerance (deg)
SPEED_FLOOR = 5.0  # below this the puck is "slow" (heading undefined) — excluded from moving-state matching
NPZ = 400          # live states sampled per zone
SEASON_FILES = ["frames_2023_24.parquet", "frames_2024_25.parquet", "frames_2025_26.parquet"]

# decision-relevant zones in NORMALIZED coords (scored-on net at x=+89, attack →+x). name -> (x range, y range)
ZONES = {
    "blue_line_entry": ((22, 30), (-30, 30)),      # crossing the attacking blue line
    "right_point":     ((30, 44), (10, 32)),       # high right, the point
    "half_wall_R":     ((44, 67), (16, 36)),        # right half-wall mid-zone
    "below_goal_line": ((89, 101), (-20, 20)),      # behind the net
    "near_net_slot":   ((78, 89), (-12, 12)),       # slot / net-front
}


def _zone(x, y):
    for name, ((x0, x1), (y0, y1)) in ZONES.items():
        if x0 <= x < x1 and y0 <= y < y1:
            return name
    return "other"


def _load():
    u = universe().select("game_id", "event_id", "season", "attack_sign", "goal_frame")
    parts = []
    for season, fname in zip(C.SEASONS, SEASON_FILES):
        us = u.filter(pl.col("season") == season)
        gids = us["game_id"].unique().to_list()
        pk = (pl.read_parquet(C.GT_FRAMES_DIR / fname, columns=["game_id", "event_id", "frame_index", "is_puck", "x_std", "y_std"])
              .filter(pl.col("is_puck") & pl.col("game_id").is_in(gids))
              .join(us, on=["game_id", "event_id"], how="inner")
              .filter((pl.col("frame_index") <= pl.col("goal_frame")) & (pl.col("frame_index") >= pl.col("goal_frame") - WIN))
              .with_columns(x=pl.col("attack_sign") * pl.col("x_std"), y=pl.col("attack_sign") * pl.col("y_std"))
              .sort("game_id", "event_id", "frame_index"))
        # backward recent-motion velocity over MW frames
        pk = pk.with_columns(
            vx=(pl.col("x") - pl.col("x").shift(MW).over(["game_id", "event_id"])) / (MW / 10.0),
            vy=(pl.col("y") - pl.col("y").shift(MW).over(["game_id", "event_id"])) / (MW / 10.0))
        parts.append(pk.select("game_id", "event_id", "x", "y", "vx", "vy"))
    d = pl.concat(parts).drop_nulls(["vx", "vy"]).filter(pl.col("x").is_finite() & pl.col("y").is_finite())
    gid = d.select(pl.struct("game_id", "event_id")).to_series().rank("dense").to_numpy().astype(np.int64)
    x = d["x"].to_numpy(); y = d["y"].to_numpy(); vx = d["vx"].to_numpy(); vy = d["vy"].to_numpy()
    speed = np.hypot(vx, vy); head = np.degrees(np.arctan2(vy, vx))
    return x, y, speed, head, gid


def run() -> dict:
    from scipy.spatial import cKDTree
    x, y, speed, head, gid = _load()
    tree = cKDTree(np.column_stack([x, y]))
    n_goals = int(len(np.unique(gid)))
    zone = np.array([_zone(xi, yi) for xi, yi in zip(x, y)])
    rng = np.random.default_rng(20260714)
    out = {}
    for zname in ZONES:
        pool = np.where((zone == zname) & (speed > SPEED_FLOOR))[0]   # moving live states in this zone
        if len(pool) == 0:
            out[zname] = {"pool_moving_frames": 0}
            continue
        samp = rng.choice(pool, size=min(NPZ, len(pool)), replace=False)
        counts = []
        for i in samp:
            cand = np.array(tree.query_ball_point([x[i], y[i]], r=RADIUS), dtype=np.int64)
            if len(cand) == 0:
                counts.append(0); continue
            dh = np.abs((head[cand] - head[i] + 180) % 360 - 180)     # circular heading diff
            keep = cand[(dh <= HEAD_TOL) & (speed[cand] > SPEED_FLOOR) & (gid[cand] != gid[i])]  # leave-one-goal-out
            counts.append(int(len(np.unique(gid[keep]))))
        c = np.array(counts)
        out[zname] = {"pool_moving_frames": int(len(pool)), "n_sampled": int(len(samp)),
                      "distinct_goal_matches": {"p10": int(np.percentile(c, 10)), "p25": int(np.percentile(c, 25)),
                      "median": int(np.median(c)), "p75": int(np.percentile(c, 75)), "p90": int(np.percentile(c, 90))},
                      "frac_lt5": round(float(np.mean(c < 5)), 3), "frac_lt10": round(float(np.mean(c < 10)), 3),
                      "frac_ge30": round(float(np.mean(c >= 30)), 3)}
    # report
    L = []; W = L.append
    W("# Puck-Path Projector §9 — read-only match-set-size by zone (distinct goals, leave-one-goal-out)\n")
    W(f"Library: {n_goals:,} 5v5 goal paths, {len(x):,} moving puck-frames (recent-motion over {MW/10:.1f}s). "
      f"PROVISIONAL knobs: radius **{RADIUS:.0f} ft**, heading tol **±{HEAD_TOL:.0f}°**, speed floor **{SPEED_FLOOR:.0f} ft/s** "
      "(real knobs are held-out-tuned later). Each live state matched against ALL OTHER goals (leave-one-out); a "
      "goal counts ONCE (distinct-goal collapse). Question: how many distinct goals match a typical live state per zone.\n")
    W("| decision zone | moving frames (pool) | distinct-goal matches p10/p25/**med**/p75/p90 | % states <5 | % <10 | % ≥30 |")
    W("|---|---|---|---|---|---|---|")
    for z, r in out.items():
        if not r.get("pool_moving_frames"):
            W(f"| {z} | 0 | — (no moving frames) | — | — | — |"); continue
        d = r["distinct_goal_matches"]
        W(f"| {z} | {r['pool_moving_frames']:,} | {d['p10']}/{d['p25']}/**{d['median']}**/{d['p75']}/{d['p90']} | "
          f"{r['frac_lt5']*100:.0f}% | {r['frac_lt10']*100:.0f}% | {r['frac_ge30']*100:.0f}% |")
    W("\n## Read\n- A zone whose typical live state matches only a HANDFUL of distinct goals (median <~10, or a "
      "large %<5) is too SPARSE to project sharply there, no matter how rich the generic o-zone looks — the "
      "projector would be estimating a continuation distribution from a few goals. A zone matching many tens is "
      "well-powered. This sizes where (if anywhere) the projection can even be posed.")
    W("- Provisional knobs only; tighter radius/heading (the real held-out-tuned values) will REDUCE these counts, "
      "so treat these as an UPPER bound on match richness.")
    W("\n## STOP — read-only power confirm. No projector, no sharpness, no modes.\n")
    C.REPORTS.mkdir(parents=True, exist_ok=True)
    (C.REPORTS / "puckproj_confirm.md").write_text("\n".join(L))
    return {"n_goals": n_goals, "n_frames": int(len(x)), "zones": out}


if __name__ == "__main__":
    import json
    print(json.dumps(run(), indent=1, default=str))
