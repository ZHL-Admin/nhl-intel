"""Link 1 — Signal A (puck-proximity), Signal B (open-man vector), and the combined culprit share.

Per goal, per defender, all anchored to what the puck/players actually did and to the KNOWN scorer.
FRAMING: descriptive per-goal accountability, never a single-goal fault verdict (see config.FRAMING).
Fixed operational thresholds live in config; sub-condition fire rates are reported once then frozen.
"""
from __future__ import annotations

import glob

import numpy as np
import polars as pl

from . import config as C, events as E

SHARES = C.PARQUET / "culprit_shares.parquet"
THRESHOLDS = C.PARQUET / "thresholds.parquet"


def _defprim() -> pl.DataFrame:
    dp = pl.concat([pl.read_parquet(f) for f in sorted(glob.glob(str(C.DEFSCHEME_PRIM / "def_prim_*.parquet")))])
    dp = dp.filter((pl.col("n_def") == 5) & ~pl.col("defending_team_id").is_in(E.EXHIBITION))
    ctx = E._fused_ctx()
    return dp.join(ctx, on=["game_id", "event_id"], how="inner")


def _last_pass() -> pl.DataFrame:
    """Last completed pass before effective_release per goal, attack-normalized (cross-slot flag)."""
    ev = pl.read_parquet(C.GT_EVENTS).filter(pl.col("event_type") == "pass")
    ctx = E._fused_ctx().select("game_id", "event_id", "eff_rel", "attack_sign")
    p = (ev.join(ctx, on=["game_id", "event_id"], how="inner")
         .filter(pl.col("end_frame") <= pl.col("eff_rel"))
         .with_columns(rk=pl.col("end_frame").rank("ordinal", descending=True).over("game_id", "event_id"))
         .filter(pl.col("rk") == 1)
         .with_columns(psy=pl.col("start_y") * pl.col("attack_sign"), pey=pl.col("end_y") * pl.col("attack_sign"),
                       psx=pl.col("start_x") * pl.col("attack_sign"), pex=pl.col("end_x") * pl.col("attack_sign")))
    return p.with_columns(
        cross_slot=(pl.col("psy").sign() != pl.col("pey").sign()) & ((pl.col("pey") - pl.col("psy")).abs() >= C.CROSS_SLOT_DY)
    ).select("game_id", "event_id", "cross_slot", "psx", "psy")


def build() -> dict:
    dp = _defprim()
    sp = pl.read_parquet(E.SCORER_PUCK)
    lp = _last_pass()

    # ---------- release-frame features ----------
    rel = dp.filter(pl.col("frame_index") == pl.col("eff_rel")).select(
        "game_id", "event_id", "season", "defending_team_id", "player_id", "eff_rel",
        "x_norm", "y_norm", "dist_puck", "dist_net", "dist_nearest_atk")
    relsp = sp.join(dp.select("game_id", "event_id", "eff_rel").unique(), on=["game_id", "event_id"], how="inner") \
        .filter(pl.col("frame_index") == pl.col("eff_rel")).select("game_id", "event_id", "px", "py", "sx", "sy")
    rel = rel.join(relsp, on=["game_id", "event_id"], how="left")
    rel = rel.with_columns(
        d_scorer=((pl.col("x_norm") - pl.col("sx")) ** 2 + (pl.col("y_norm") - pl.col("sy")) ** 2).sqrt(),
        # perpendicular distance of the defender to the shot vector puck->(89,0)
        lane=_perp(pl.col("px"), pl.col("py"), pl.col("x_norm"), pl.col("y_norm")))
    rel = rel.with_columns(
        scorer_openness=pl.col("d_scorer").min().over("game_id", "event_id"),
        nearest_puck_rel=pl.col("dist_puck").min().over("game_id", "event_id"),
        lane_contest=pl.col("lane").min().over("game_id", "event_id"),
        is_nearest_scorer=pl.col("d_scorer") == pl.col("d_scorer").min().over("game_id", "event_id"),
        is_nearest_puck=pl.col("dist_puck") == pl.col("dist_puck").min().over("game_id", "event_id"))

    # ---------- window (final 3.0s) on-puck features ----------
    win = dp.filter(pl.col("frame_index").is_between(pl.col("eff_rel") - C.WIN_3S, pl.col("eff_rel")))
    win = win.with_columns(
        on_puck=(pl.col("dist_puck") == pl.col("dist_puck").min().over("game_id", "event_id", "frame_index"))
        & (pl.col("dist_puck") <= C.ON_PUCK_FT),
        in15=pl.col("frame_index") >= (pl.col("eff_rel") - C.WIN_1_5S))
    wf = win.group_by("game_id", "event_id", "player_id").agg(
        on_puck_share=pl.col("on_puck").mean(),
        was_on_puck_15=(pl.col("on_puck") & pl.col("in15")).any(),
        off_atk=pl.col("dist_nearest_atk").filter(~pl.col("on_puck")).mean(),
        off_net=pl.col("dist_net").filter(~pl.col("on_puck")).mean())

    d = rel.join(wf, on=["game_id", "event_id", "player_id"], how="left").join(lp, on=["game_id", "event_id"], how="left")

    # ---------- PERCENTILE-CALIBRATED thresholds (owner rule): footage derived from the distributions ----
    perg = d.group_by("game_id", "event_id").agg(so=pl.col("scorer_openness").first(), lc=pl.col("lane_contest").first())
    open_thr = float(perg["so"].quantile(C.P_OPEN))
    lane_thr = float(perg["lc"].quantile(C.P_LANE))
    offpuck = d.filter(~pl.col("is_nearest_puck"))     # off-puck defenders at release
    float_atk_thr = float(offpuck["dist_nearest_atk"].quantile(C.P_FLOAT))
    float_net_thr = float(offpuck["dist_net"].quantile(C.P_FLOAT))
    thr = {"open": open_thr, "lane": lane_thr, "float_atk": float_atk_thr, "float_net": float_net_thr}

    # ---------- flags (A(i) DROPPED — tautological on goals; A is now ONLY the off-puck float A(ii)) ----
    d = d.with_columns(
        A_ii=(~pl.col("is_nearest_puck")) & (pl.col("dist_nearest_atk") >= float_atk_thr) & (pl.col("dist_net") >= float_net_thr),
        B=pl.col("is_nearest_scorer") & (pl.col("scorer_openness") >= open_thr) & (pl.col("lane_contest") >= lane_thr))
    d = d.with_columns(A_i=pl.lit(False), A_flag=pl.col("A_ii"), B_flag=pl.col("B"),
                       near_origin=((pl.col("x_norm") - pl.col("psx")) ** 2 + (pl.col("y_norm") - pl.col("psy")) ** 2).sqrt())
    # secondary (strong-side/origin defender on a cross-slot feed) only supplements a REAL open-man goal
    d = d.with_columns(secondary_flag=pl.col("cross_slot").fill_null(False)
                       & pl.col("B_flag").any().over("game_id", "event_id") & pl.col("B_flag").not_()
                       & (pl.col("near_origin") == pl.col("near_origin").min().over("game_id", "event_id")))

    # ---------- graded raw components (B-primary 0.75, A(ii) support 0.25) ----------
    d = d.with_columns(
        B_raw=pl.when(pl.col("scorer_openness") >= open_thr)
        .then(pl.col("scorer_openness") / (pl.col("d_scorer") + 3.0)).otherwise(0.0)
        + pl.when(pl.col("secondary_flag")).then(pl.col("scorer_openness") * 0.25 / (pl.col("near_origin") + 3.0)).otherwise(0.0),
        # severity = how far BEYOND both thresholds he floats (both terms >= 0 for an A(ii) defender, so
        # A_raw is always non-negative -> no blow-up in the within-goal normalization)
        A_raw=pl.when(pl.col("A_ii")).then((pl.col("dist_nearest_atk") - float_atk_thr) + (pl.col("dist_net") - float_net_thr)).otherwise(0.0))
    # normalize within goal (uniform fallback if a component is silent), combine, hard flag
    d = d.with_columns(
        B_sum=pl.col("B_raw").sum().over("game_id", "event_id"),
        A_sum=pl.col("A_raw").sum().over("game_id", "event_id"))
    d = d.with_columns(
        B_norm=pl.when(pl.col("B_sum") > 0).then(pl.col("B_raw") / pl.col("B_sum")).otherwise(0.2),
        A_norm=pl.when(pl.col("A_sum") > 0).then(pl.col("A_raw") / pl.col("A_sum")).otherwise(0.2))
    d = d.with_columns(breakdown_share=C.B_WEIGHT * pl.col("B_norm") + C.A_WEIGHT * pl.col("A_norm"))
    d = d.with_columns(hard_culprit=pl.col("breakdown_share") >= C.HARD_CULPRIT,
                       no_clear_culprit=(pl.col("B_sum") == 0) & (pl.col("A_sum") == 0))

    out = d.select("game_id", "event_id", "season", "defending_team_id", "player_id", "breakdown_share",
                   "B_norm", "A_norm", "hard_culprit", "A_flag", "B_flag", "A_i", "A_ii", "secondary_flag",
                   "no_clear_culprit", "d_scorer", "scorer_openness", "lane_contest", "nearest_puck_rel",
                   "on_puck_share", "is_nearest_scorer", "cross_slot")
    C.PARQUET.mkdir(parents=True, exist_ok=True)
    out.write_parquet(SHARES)
    pl.DataFrame([{**thr, "open_med": float(perg["so"].median())}]).write_parquet(THRESHOLDS)

    ng = out.select("game_id", "event_id").n_unique()
    return {"n_goals": ng, "n_defender_rows": out.height, "thresholds": thr,
            "A_i_rate": float(out["A_i"].mean()), "A_ii_rate": float(out["A_ii"].mean()),
            "A_flag_rate": float(out["A_flag"].mean()), "B_flag_rate": float(out["B_flag"].mean()),
            "secondary_rate": float(out["secondary_flag"].mean()),
            "goals_with_hard_culprit": int(out.group_by("game_id", "event_id").agg(h=pl.col("hard_culprit").any())["h"].sum()),
            "no_clear_culprit_goals": int(out.group_by("game_id", "event_id").agg(n=pl.col("no_clear_culprit").first())["n"].sum()),
            "share_max_median": float(out.group_by("game_id", "event_id").agg(m=pl.col("breakdown_share").max())["m"].median())}


def _perp(px, py, x, y):
    # perpendicular distance from point (x,y) to the line through (px,py) and the net (89,0)
    ax, ay = px, py
    bx, by = pl.lit(C.DEF_NET_X), pl.lit(0.0)
    num = ((by - ay) * x - (bx - ax) * y + bx * ay - by * ax).abs()
    den = (((by - ay) ** 2 + (bx - ax) ** 2).sqrt())
    return num / (den + 1e-6)


if __name__ == "__main__":
    import time
    t = time.time()
    r = build()
    print(f"culprit shares: {r['n_goals']:,} goals, {r['n_defender_rows']:,} defender-rows in {time.time()-t:.0f}s")
    print(f"  A(i) fire {r['A_i_rate']*100:.1f}% | A(ii) fire {r['A_ii_rate']*100:.1f}% | A_flag {r['A_flag_rate']*100:.1f}% "
          f"| B_flag {r['B_flag_rate']*100:.1f}% | secondary {r['secondary_rate']*100:.1f}%")
    print(f"  goals with a hard culprit (share>=0.40): {r['goals_with_hard_culprit']:,}/{r['n_goals']:,} "
          f"| no-clear-culprit goals: {r['no_clear_culprit_goals']:,} | median max-share/goal {r['share_max_median']:.2f}")
