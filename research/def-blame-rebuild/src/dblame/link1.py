"""Link 1 · the coverage-failure events (the assignment, from scratch).

Blame accrues to a defender ONLY when a coverage-failure event fires in HIS OWN track. No event -> no
blame. A goal's total blame is the SUM of detected event severities (ABSOLUTE, not normalized to one), so
a goal where no defender's coverage broke assigns ~0. Three fixed events (sensitivities percentile-
calibrated once, then frozen):

  E1 CONTAINMENT LOSS  — he was the nearest, goal-side defender to a man (the scorer or the primary
      passer) for >=1.0s early, then that man's separation from him grew in the final approach and the man
      scored / made the pre-goal pass. Severity scales with how open the man got and his role.
  E2 OVER-COMMITMENT   — he was the nearest defender to the net-front early, then chased the puck (closed
      on it) and vacated the net-front, and the goal came from that dangerous ice. Severity scales with
      how much he vacated and the danger of the shot location.
  E3 FAILURE TO CLOSE  — he was the nearest defender to the eventual scorer through the final approach but
      never reduced the gap (stayed passive) and the scorer was open at release. Distinct from E1 (E1 lost
      a man he HAD goal-side; E3 never engaged). Severity scales with the scorer's openness at release.

Non-events assign ZERO: a defender consistently near a low-danger man, never near the play, or beaten by a
pre-existing advantage he had no path to, produces no event.
"""
from __future__ import annotations

import numpy as np
import polars as pl

from . import config as C
from .data import universe
from .tracks import TRACKS

BLAME = C.PARQUET / "blame.parquet"
FEATS = C.PARQUET / "goal_def_features.parquet"
FA_FR = int(C.FINAL_APPROACH_S * C.HZ)
MANAGE_FR = int(C.MANAGE_MIN_S * C.HZ)
ROLE = {"scorer": 1.0, "assist1": 0.6}


def _goal_features() -> pl.DataFrame:
    """Per goal: shot danger (release distance to net) and scorer openness at release (from fused)."""
    u = universe()
    f = pl.read_parquet(C.GT_FUSED).select(
        "game_id", "event_id", "release_x", "release_y", "nd_scorer_rel")
    g = u.join(f, on=["game_id", "event_id"], how="left").with_columns(
        release_dist_net=((pl.col("release_x") - pl.col("net_x")) ** 2 + pl.col("release_y") ** 2).sqrt())
    return g.select("game_id", "event_id", "season", "goal_frame", "scorer_id", "assist1_id",
                    "release_dist_net", "nd_scorer_rel")


def features() -> pl.DataFrame:
    """Per (goal, defender) window features feeding the three detectors."""
    t = pl.read_parquet(TRACKS)
    gf = _goal_features()
    t = t.join(gf.select("game_id", "event_id", "goal_frame"), on=["game_id", "event_id"], how="inner")
    t = t.with_columns(fa=pl.col("frame_index") > (pl.col("goal_frame") - FA_FR)).sort(
        ["game_id", "event_id", "player_id", "frame_index"])
    # per-frame: which defender is nearest to the scorer / net-front / primary passer
    over = ["game_id", "event_id", "frame_index"]
    t = t.with_columns(
        near_scorer=pl.col("dist_scorer") == pl.col("dist_scorer").min().over(over),
        near_slot=pl.col("dist_slot") == pl.col("dist_slot").min().over(over),
        near_ast1=pl.col("dist_assist1") == pl.col("dist_assist1").min().over(over))
    early = ~pl.col("fa")
    g = t.group_by("game_id", "event_id", "player_id").agg(
        n_frames=pl.len(), n_fa=pl.col("fa").sum(),
        # E1 scorer: managed early (nearest + goal-side), separation early vs final
        man_s=(early & pl.col("near_scorer") & pl.col("scorer_goal_side")).sum(),
        msep_s=pl.col("dist_scorer").filter(early & pl.col("near_scorer") & pl.col("scorer_goal_side")).median(),
        fsep_s=pl.col("dist_scorer").filter(pl.col("fa")).median(),
        # E1 assist1
        man_a=(early & pl.col("near_ast1") & pl.col("assist1_goal_side")).sum(),
        msep_a=pl.col("dist_assist1").filter(early & pl.col("near_ast1") & pl.col("assist1_goal_side")).median(),
        fsep_a=pl.col("dist_assist1").filter(pl.col("fa")).median(),
        # E2 overshoot: net-front custody early, puck chase, net-front vacated
        near_slot_early=(early & pl.col("near_slot")).sum(),
        puck_early=pl.col("dist_puck").filter(early).median(),
        puck_fa=pl.col("dist_puck").filter(pl.col("fa")).median(),
        slot_early=pl.col("dist_slot").filter(early).median(),
        slot_fa=pl.col("dist_slot").filter(pl.col("fa")).median(),
        # E3 failure to close: nearest to scorer through final approach, never reduced gap
        fa_near_scorer=(pl.col("fa") & pl.col("near_scorer")).sum(),
        dsc_fa_start=pl.col("dist_scorer").filter(pl.col("fa")).first(),
        dsc_goal=pl.col("dist_scorer").filter(pl.col("fa")).last())
    return g.join(gf, on=["game_id", "event_id"], how="left")


def _clip01(x):
    return np.clip(x, 0.0, 1.0)


def build() -> dict:
    g = features().to_pandas()
    # ---- calibration distributions (computed once, frozen, reported as footage) ----
    e1_growth = []
    for man, mcol, fcol in [("s", "man_s", "msep_s"), ("a", "man_a", "msep_a")]:
        m = g[g[mcol] >= MANAGE_FR]
        gr = m[f"fsep_{man}"] - m[f"msep_{man}"]
        e1_growth.append(gr.dropna().values)
    growth_all = np.concatenate(e1_growth) if e1_growth else np.array([0.0])
    growth_thr = float(np.quantile(growth_all, C.P_SEP_GROWTH))
    growth_p95 = float(np.quantile(growth_all, 0.95))

    pursuit = g["puck_early"] - g["puck_fa"]            # +ve = closed on the puck
    vacate = g["slot_fa"] - g["slot_early"]             # +ve = left the net-front
    pursuers = (pursuit > 0) & (g["near_slot_early"] > 0)
    vac_all = vacate[pursuers].dropna().values if pursuers.any() else np.array([0.0])
    vac_thr = float(np.quantile(vac_all, C.P_VACATE))
    vac_p95 = float(np.quantile(vac_all, 0.95))
    rdn = g["release_dist_net"].dropna().values
    danger_lo, danger_hi = float(np.quantile(rdn, 0.10)), float(np.quantile(rdn, 0.90))

    ndr = g["nd_scorer_rel"].dropna().values
    open_thr = float(np.quantile(ndr, C.P_OPEN_RELEASE))
    open_p95 = float(np.quantile(ndr, 0.95))

    # ---- fire events + severities ----
    growth_s = g["fsep_s"] - g["msep_s"]
    growth_a = g["fsep_a"] - g["msep_a"]
    e1s_fire = (g["man_s"] >= MANAGE_FR) & (growth_s >= growth_thr)
    e1a_fire = (g["man_a"] >= MANAGE_FR) & (growth_a >= growth_thr)
    sev_e1s = np.where(e1s_fire, _clip01((growth_s - growth_thr) / (growth_p95 - growth_thr + 1e-9)) * ROLE["scorer"], 0.0)
    sev_e1a = np.where(e1a_fire, _clip01((growth_a - growth_thr) / (growth_p95 - growth_thr + 1e-9)) * ROLE["assist1"], 0.0)
    sev_e1 = np.maximum(sev_e1s, sev_e1a)
    e1_man = np.where(sev_e1s >= sev_e1a, "scorer", "assist1")
    e1_fire = sev_e1 > 0

    danger = _clip01((danger_hi - g["release_dist_net"]) / (danger_hi - danger_lo + 1e-9))
    e2_fire = pursuers & (vacate >= vac_thr) & (g["release_dist_net"] <= float(np.quantile(rdn, 0.60)))
    sev_e2 = np.where(e2_fire, _clip01((vacate - vac_thr) / (vac_p95 - vac_thr + 1e-9)) * danger, 0.0)
    e2_fire = sev_e2 > 0

    fa_frac = g["fa_near_scorer"] / g["n_fa"].clip(lower=1)
    closed = g["dsc_fa_start"] - g["dsc_goal"]          # +ve = reduced the gap (engaged)
    e3_fire = (fa_frac >= 0.5) & (closed <= 0) & (g["nd_scorer_rel"] >= open_thr) & (g["man_s"] < MANAGE_FR)
    sev_e3 = np.where(e3_fire, _clip01((g["nd_scorer_rel"] - open_thr) / (open_p95 - open_thr + 1e-9)) * ROLE["scorer"], 0.0)
    e3_fire = sev_e3 > 0

    g["e1"] = sev_e1; g["e1_man"] = e1_man; g["e2"] = sev_e2; g["e3"] = sev_e3
    g["blame"] = g["e1"] + g["e2"] + g["e3"]
    out = pl.from_pandas(g[["game_id", "event_id", "season", "player_id", "scorer_id",
                            "e1", "e1_man", "e2", "e3", "blame", "man_s", "man_a",
                            "release_dist_net", "nd_scorer_rel"]])
    C.PARQUET.mkdir(parents=True, exist_ok=True)
    out.write_parquet(BLAME)
    pl.from_pandas(g).write_parquet(FEATS)

    cal = {"growth_thr": growth_thr, "growth_p95": growth_p95, "vac_thr": vac_thr, "vac_p95": vac_p95,
           "danger_lo": danger_lo, "danger_hi": danger_hi, "open_thr": open_thr, "open_p95": open_p95,
           "n_managed_pairs": int(len(growth_all)), "n_pursuers": int(pursuers.sum())}
    fires = {"E1": int(e1_fire.sum()), "E2": int(e2_fire.sum()), "E3": int(e3_fire.sum())}
    # per-goal total blame
    per_goal = out.group_by("game_id", "event_id").agg(total=pl.col("blame").sum())
    ng = per_goal.height
    zero = int((per_goal["total"] < 1e-6).sum())
    return {"cal": cal, "fires": fires, "n_def_goal_rows": out.height, "n_goals": ng,
            "zero_blame_goals": zero, "zero_frac": zero / ng,
            "total_q": {k: round(float(per_goal["total"].quantile(q)), 3) for k, q in
                        [("p10", .1), ("p25", .25), ("med", .5), ("p75", .75), ("p90", .9), ("max", 1.0)]}}


if __name__ == "__main__":
    r = build()
    print("calibration:", {k: round(v, 2) if isinstance(v, float) else v for k, v in r["cal"].items()})
    print("event fires:", r["fires"])
    print(f"goals: {r['n_goals']:,} | zero-blame goals: {r['zero_blame_goals']:,} ({r['zero_frac']*100:.1f}%)")
    print("per-goal total blame quantiles:", r["total_q"])
