"""Settled-Play spec §8 — READ-ONLY EXPOSURE CONFIRMS (the power check). Reports (a) settled-phase exposure and
(b) classifier sanity, then STOPS. No norm, no gate, no profile, no per-player output.

Settled frame (provisional, for the power check only): puck in the DZ (depth < BL≈63) AND sustained (puck has
been continuously in the DZ ≥ SUSTAIN frames = not a fresh rush-in) AND not within the last PRE_SHOT frames of
the shot (exclude the shot-moment collapse). Area tiling + role-slots are PROVISIONAL (owner rules the real
boundaries); here they exist only to size possessions-per-(area×slot×defender). The decisive output is that
finest-cell count: if a typical defender gets only a handful of settled goals per (area×slot), Gate-2 split-half
is dead on arrival.
"""
from __future__ import annotations

import numpy as np
import polars as pl

from . import config as C
from .data import universe

BL = 63.0
SUSTAIN = 15        # frames (1.5s) continuously in the DZ before a frame counts as "settled" (not a rush-in)
PRE_SHOT = 10       # exclude the last 1.0s before the shot
MIN_CELL_FR = 5     # a (defender,area,slot) is "present in goal G" only with >=5 settled frames there
SEASON_FILES = ["frames_2023_24.parquet", "frames_2024_25.parquet", "frames_2025_26.parquet"]


# ---- PROPOSED tiling for owner review (type-A hockey boundaries). depth d from goal line, lateral l, feet. ----
# Landmarks: goal line d=0, end boards d≈−11, DZ dots d≈20 & |l|≈22, hash/top-circle d≈37, blue line d≈63.
# Mutually exclusive, gap-free over the DZ (d<63). Central lane |l|<14 (inside the dots) = the prime slot width.
CENTRAL_AREAS = {"slot", "point", "behind_net"}     # lateral-0 ambiguous → NO strong/weak split


def _area(d, l):
    return (pl.when(d < 0).then(pl.lit("behind_net"))                                  # behind the goal line
            .when((d < 44) & (l.abs() < 14)).then(pl.lit("slot"))                      # central lane, net→high slot
            .when((d < 20) & (l < 0)).then(pl.lit("left_corner"))                      # low + wide
            .when(d < 20).then(pl.lit("right_corner"))
            .when((d < 44) & (l < 0)).then(pl.lit("left_halfwall"))                    # mid + wide
            .when(d < 44).then(pl.lit("right_halfwall"))
            .otherwise(pl.lit("point")))                                               # 44<=d<63, any lateral


def build() -> dict:
    u = universe().select("game_id", "event_id", "season", "attack_sign", "defending_team_id",
                          "home_goalie_id", "away_goalie_id", "start_frame", "goal_frame")
    isdef = set(pl.read_parquet(C.PARQUET / "player_side.parquet").filter(pl.col("pos") == "D")["player_id"].to_list())
    parts = []
    tot_frames = tot_settled = 0
    goals_total = goals_settled = 0
    poss_total = 0
    poss_area = {}
    for season, fname in zip(C.SEASONS, SEASON_FILES):
        us = u.filter(pl.col("season") == season)
        gids = us["game_id"].unique().to_list()
        fr = (pl.read_parquet(C.GT_FRAMES_DIR / fname, columns=["game_id", "event_id", "frame_index", "is_puck",
                                                                "player_id", "team_id", "x_std", "y_std"])
              .filter(pl.col("game_id").is_in(gids))
              .join(us, on=["game_id", "event_id"], how="inner")
              .filter((pl.col("frame_index") >= pl.col("start_frame")) & (pl.col("frame_index") <= pl.col("goal_frame")))
              .with_columns(depth=89.0 - pl.col("attack_sign") * pl.col("x_std"), lat=pl.col("attack_sign") * pl.col("y_std")))
        goalie = (pl.col("player_id") == pl.col("home_goalie_id")) | (pl.col("player_id") == pl.col("away_goalie_id"))
        # ---- puck settled mask per (game,event,frame) ----
        puck = (fr.filter(pl.col("is_puck")).select("game_id", "event_id", "frame_index", "goal_frame",
                pdepth="depth", plat="lat").sort("game_id", "event_id", "frame_index"))
        dz = pl.col("pdepth") < BL
        brk = (dz != dz.shift(1).over(["game_id", "event_id"])) | \
              (pl.col("frame_index") != pl.col("frame_index").shift(1).over(["game_id", "event_id"]) + 1)
        puck = puck.with_columns(dz=dz).with_columns(runid=brk.fill_null(True).cast(pl.Int64).cum_sum().over(["game_id", "event_id"]))
        puck = puck.with_columns(pos_in_run=pl.col("frame_index") - pl.col("frame_index").min().over(["game_id", "event_id", "runid"]) + 1)
        puck = puck.with_columns(settled=pl.col("dz") & (pl.col("pos_in_run") >= SUSTAIN) & (pl.col("frame_index") <= pl.col("goal_frame") - PRE_SHOT))
        sp = puck.filter(pl.col("settled")).with_columns(area=_area(pl.col("pdepth"), pl.col("plat")))
        # possessions = maximal consecutive settled runs
        sp2 = sp.sort("game_id", "event_id", "frame_index").with_columns(
            pbrk=((pl.col("frame_index") != pl.col("frame_index").shift(1).over(["game_id", "event_id"]) + 1)).fill_null(True).cast(pl.Int64))
        sp2 = sp2.with_columns(possid=pl.col("pbrk").cum_sum().over(["game_id", "event_id"]))
        poss_total += sp2.select(pl.struct("game_id", "event_id", "possid").n_unique()).item()
        for r in sp2.group_by("area").agg(pl.struct("game_id", "event_id", "possid").n_unique().alias("p")).iter_rows(named=True):
            poss_area[r["area"]] = poss_area.get(r["area"], 0) + r["p"]
        # counts for (b)
        tot_frames += fr.filter(pl.col("is_puck")).height
        tot_settled += sp.height
        gt = us.height
        gs = sp.select(pl.struct("game_id", "event_id").n_unique()).item()
        goals_total += gt; goals_settled += gs
        # ---- skaters on settled frames -> (player, area, slot) ----
        sk = (fr.filter(~pl.col("is_puck") & ~goalie & (pl.col("team_id") == pl.col("defending_team_id")))
              .select("game_id", "event_id", "frame_index", "player_id", sdepth="depth", slat="lat"))
        j = sk.join(sp.select("game_id", "event_id", "frame_index", "area", "plat"), on=["game_id", "event_id", "frame_index"], how="inner")
        j = j.with_columns(isd=pl.col("player_id").is_in(list(isdef)),
                           pside=pl.when(pl.col("plat") < -14).then(-1).when(pl.col("plat") > 14).then(1).otherwise(0),
                           kside=pl.when(pl.col("slat") < 0).then(-1).otherwise(1))
        # PROPOSED role-slots (per skater per frame, geometry only): net-front / high-F / (strong|weak)-D /
        # (strong|weak)-low-F; central puck (|plat|<14) collapses strong/weak → D / low-F.
        netfront = (pl.col("sdepth") <= 10) & (pl.col("slat").abs() <= 12)
        highf = (~pl.col("isd")) & (pl.col("sdepth") >= 32)
        strong = pl.col("kside") == pl.col("pside")
        slot = (pl.when(netfront).then(pl.lit("net-front"))
                .when(highf).then(pl.lit("high-F"))
                .when(pl.col("isd")).then(pl.when(pl.col("pside") == 0).then(pl.lit("D"))
                                          .when(strong).then(pl.lit("strong-D")).otherwise(pl.lit("weak-D")))
                .otherwise(pl.when(pl.col("pside") == 0).then(pl.lit("low-F"))
                           .when(strong).then(pl.lit("strong-low-F")).otherwise(pl.lit("weak-low-F"))))
        j = j.with_columns(slot=slot)
        parts.append(j.select("game_id", "event_id", "player_id", "area", "slot"))
    long = pl.concat(parts)
    # per (player, area, slot, goal): frames; keep goals with >= MIN_CELL_FR
    cell_goal = (long.group_by("player_id", "area", "slot", "game_id", "event_id").agg(nfr=pl.len())
                 .filter(pl.col("nfr") >= MIN_CELL_FR))
    # decisive: distinct goals per (player, area, slot)
    cell = cell_goal.group_by("player_id", "area", "slot").agg(n_goals=pl.len())
    ng = cell["n_goals"].to_numpy()
    dist = {q: int(np.quantile(ng, v)) for q, v in {"p50": .5, "p75": .75, "p90": .9, "max": 1.0}.items()}
    # per (area, slot): how many viable cells (>=20 / >=33 goals) — where the workhorse signal would live
    as_break = (cell.group_by("area", "slot").agg(cells=pl.len(), ge20=(pl.col("n_goals") >= 20).sum(),
                ge33=(pl.col("n_goals") >= 33).sum(), med=pl.col("n_goals").median())
                .sort("ge20", descending=True))
    central_poss = sum(v for k, v in poss_area.items() if k in CENTRAL_AREAS)
    return {"as_break": as_break.to_dicts(), "central_poss_frac": round(central_poss / max(poss_total, 1), 3), "a": {
        "goals_total_5v5": goals_total, "goals_with_settled_phase": goals_settled,
        "settled_phase_frac": round(goals_settled / goals_total, 3),
        "total_settled_frames": tot_settled, "total_settled_possessions": poss_total,
        "possessions_per_area": dict(sorted(poss_area.items(), key=lambda x: -x[1])),
        "n_cells_player_area_slot": cell.height,
        "goals_per_cell_distribution": dist,
        "cells_with_ge10_goals": int((ng >= 10).sum()), "cells_with_ge20_goals": int((ng >= 20).sum()),
        "cells_with_ge10_frac": round(float((ng >= 10).mean()), 3)},
        "b": {"total_buildup_puck_frames": tot_frames, "settled_puck_frames": tot_settled,
              "settled_frac_of_buildup": round(tot_settled / tot_frames, 3),
              "goals_with_settled_vs_4066": f"{goals_settled} settled-phase goals vs RCET 4,066 rush goals"}}


def write() -> dict:
    r = build()
    a, b = r["a"], r["b"]
    L = []; W = L.append
    W("# Settled-Play §8 — read-only EXPOSURE confirms (power check; no norm, no gate, no profile)\n")
    W("Provisional settled definition (power-check only): puck in DZ (depth<63) AND ≥1.5s continuously in-zone "
      "(not a fresh rush-in) AND ≥1.0s before the shot. Area tiling + role-slots PROVISIONAL — they exist only to "
      "size the finest cell. Owner rules the real boundaries.\n")
    W("## (a) Settled-phase exposure\n")
    W(f"- 5v5 tracked goals: **{a['goals_total_5v5']:,}** · with a real settled DZ phase: **{a['goals_with_settled_phase']:,}** "
      f"({a['settled_phase_frac']*100:.1f}%)")
    W(f"- total settled frames: {a['total_settled_frames']:,} · total settled POSSESSIONS: **{a['total_settled_possessions']:,}**")
    W(f"- settled possessions per puck-area: {a['possessions_per_area']}")
    W(f"\n**DECISIVE — goals per (defender × area × slot) cell** (split-half unit; need ~≥10/half → ≥20 total to be viable):")
    W(f"- distinct (player × area × slot) cells: {a['n_cells_player_area_slot']:,}")
    W(f"- goals-per-cell distribution: median **{a['goals_per_cell_distribution']['p50']}**, "
      f"p75 {a['goals_per_cell_distribution']['p75']}, p90 {a['goals_per_cell_distribution']['p90']}, "
      f"max {a['goals_per_cell_distribution']['max']}")
    W(f"- cells with ≥10 goals: **{a['cells_with_ge10_goals']:,}** ({a['cells_with_ge10_frac']*100:.1f}%) · "
      f"with ≥20 goals (split-half viable): **{a['cells_with_ge20_goals']:,}**")
    W("\n## (b) Classifier sanity\n")
    W(f"- settled puck-frames {b['settled_puck_frames']:,} of {b['total_buildup_puck_frames']:,} buildup puck-frames "
      f"(**{b['settled_frac_of_buildup']*100:.1f}%** of buildup is settled DZ)")
    W(f"- {b['goals_with_settled_vs_4066']}")
    W(f"\n- **central (no-split) areas {sorted(CENTRAL_AREAS)} hold {r['central_poss_frac']*100:.0f}% of settled possessions**")
    W("\n## Proposed (area × slot) cell viability — where the workhorse signal would live (cells ≥20 / ≥33 goals)\n")
    W("| area | slot | cells | ≥20 goals | ≥33 goals | median goals |")
    W("|---|---|---|---|---|---|")
    for d in r["as_break"]:
        if d["ge20"] < 15:
            continue
        W(f"| {d['area']} | {d['slot']} | {d['cells']:,} | **{d['ge20']:,}** | {d['ge33']:,} | {d['med']} |")
    W("\n## STOP — read-only exposure reported. No norm, no gate, no profile.\n")
    C.REPORTS.mkdir(parents=True, exist_ok=True)
    (C.REPORTS / "settled_confirm.md").write_text("\n".join(L))
    return r


if __name__ == "__main__":
    import json
    print(json.dumps(write(), indent=1, default=str))
