"""Settled-Play Gate 1 (norm tightness) + Gate 2 (individual spread — THE finding), on the LOCKED tiling.

Locked discipline enforced:
 - POSSESSION-LEVEL effective sample: each (defender, possession, area, slot) collapsed to ONE median per axis
   (kills the 46:1 frame autocorrelation); split-half is BY GAMES (odd/even), never frame-level.
 - PER-AXIS: depth (dist to net), strong/weak lateral (flipped to puck side; raw for central puck), dist-to-puck.
 - SLOT-stratified (within one clean role-slot) AND position-stratified (slot encodes D vs F).
 - Cells tested at >=20 goals (>=5 per half) and again at >=33 (the cleaner set).
Gate 1 = cell IQR vs shuffled-area (same-slot, all-areas) IQR — expected to pass, NOT the finding.
Gate 2 = split-half >=0.40 on possession-collapsed per-defender means AND between/within excess >~1.5.
STOP at the gate results. No tape, no profile, no aggregation.
"""
from __future__ import annotations

import numpy as np
import polars as pl

from . import config as C
from .data import universe
from .settled_confirm import _area, CENTRAL_AREAS, BL, SUSTAIN, PRE_SHOT, MIN_CELL_FR, SEASON_FILES

CELLS = C.PARQUET / "settled_cells.parquet"
AXES = ["depth", "latsw", "distpuck"]


def build_cells() -> dict:
    u = universe().select("game_id", "event_id", "season", "attack_sign", "defending_team_id",
                          "home_goalie_id", "away_goalie_id", "start_frame", "goal_frame")
    isdef = set(pl.read_parquet(C.PARQUET / "player_side.parquet").filter(pl.col("pos") == "D")["player_id"].to_list())
    parts = []
    point_depths = []
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
        puck = (fr.filter(pl.col("is_puck")).select("game_id", "event_id", "frame_index", "goal_frame",
                pdepth="depth", plat="lat").sort("game_id", "event_id", "frame_index"))
        dz = pl.col("pdepth") < BL
        brk = (dz != dz.shift(1).over(["game_id", "event_id"])) | \
              (pl.col("frame_index") != pl.col("frame_index").shift(1).over(["game_id", "event_id"]) + 1)
        puck = puck.with_columns(dz=dz).with_columns(runid=brk.fill_null(True).cast(pl.Int64).cum_sum().over(["game_id", "event_id"]))
        puck = puck.with_columns(pos_in_run=pl.col("frame_index") - pl.col("frame_index").min().over(["game_id", "event_id", "runid"]) + 1)
        puck = puck.with_columns(settled=pl.col("dz") & (pl.col("pos_in_run") >= SUSTAIN) & (pl.col("frame_index") <= pl.col("goal_frame") - PRE_SHOT))
        sp = puck.filter(pl.col("settled")).with_columns(area=_area(pl.col("pdepth"), pl.col("plat")))
        sp = sp.sort("game_id", "event_id", "frame_index").with_columns(
            pbrk=((pl.col("frame_index") != pl.col("frame_index").shift(1).over(["game_id", "event_id"]) + 1)).fill_null(True).cast(pl.Int64))
        sp = sp.with_columns(possid=pl.col("pbrk").cum_sum().over(["game_id", "event_id"]))
        point_depths.append(sp.filter(pl.col("area") == "point").select("pdepth"))
        # skaters on settled frames + axes
        sk = (fr.filter(~pl.col("is_puck") & ~goalie & (pl.col("team_id") == pl.col("defending_team_id")))
              .select("game_id", "event_id", "frame_index", "player_id", sdepth="depth", slat="lat"))
        j = sk.join(sp.select("game_id", "event_id", "frame_index", "area", "possid", "pdepth", "plat"),
                    on=["game_id", "event_id", "frame_index"], how="inner")
        pside = pl.when(pl.col("plat") < -14).then(-1).when(pl.col("plat") > 14).then(1).otherwise(0)
        kside = pl.when(pl.col("slat") < 0).then(-1).otherwise(1)
        j = j.with_columns(isd=pl.col("player_id").is_in(list(isdef)), pside=pside, kside=kside)
        netfront = (pl.col("sdepth") <= 10) & (pl.col("slat").abs() <= 12)
        highf = (~pl.col("isd")) & (pl.col("sdepth") >= 32)
        strong = pl.col("kside") == pl.col("pside")
        slot = (pl.when(netfront).then(pl.lit("net-front"))
                .when(highf).then(pl.lit("high-F"))
                .when(pl.col("isd")).then(pl.when(pl.col("pside") == 0).then(pl.lit("D"))
                                          .when(strong).then(pl.lit("strong-D")).otherwise(pl.lit("weak-D")))
                .otherwise(pl.when(pl.col("pside") == 0).then(pl.lit("low-F"))
                           .when(strong).then(pl.lit("strong-low-F")).otherwise(pl.lit("weak-low-F"))))
        # per-axis raw values
        j = j.with_columns(slot=slot, depth=pl.col("sdepth"),
                           latsw=pl.when(pl.col("pside") != 0).then(pl.col("slat") * pl.col("pside")).otherwise(pl.col("slat")),
                           distpuck=((pl.col("sdepth") - pl.col("pdepth")) ** 2 + (pl.col("slat") - pl.col("plat")) ** 2).sqrt())
        # collapse to (player, game, event, possid, area, slot): median per axis, keep >= MIN_CELL_FR frames
        cell = (j.group_by("player_id", "game_id", "event_id", "possid", "area", "slot")
                .agg(nfr=pl.len(), isd=pl.col("isd").first(), depth=pl.col("depth").median(),
                     latsw=pl.col("latsw").median(), distpuck=pl.col("distpuck").median())
                .filter(pl.col("nfr") >= MIN_CELL_FR))
        parts.append(cell)
    allc = pl.concat(parts)
    allc.write_parquet(CELLS)
    pd = pl.concat(point_depths)["pdepth"].to_numpy()
    return {"cell_rows": allc.height,
            "point_depth_quantiles": {q: round(float(np.quantile(pd, v)), 1) for q, v in
                                      {"p10": .1, "p25": .25, "p50": .5, "p75": .75, "p90": .9}.items()}}


def _pearson(x, y):
    x, y = np.asarray(x, float), np.asarray(y, float)
    if len(x) < 6 or np.std(x) < 1e-9 or np.std(y) < 1e-9:
        return float("nan")
    return float(np.corrcoef(x, y)[0, 1])


def gates(thresh: int) -> list:
    c = pl.read_parquet(CELLS).with_columns(odd=(pl.col("game_id") % 2 == 1))
    # per (area, slot, player): possession-collapsed means per half + full; exposure = distinct goals
    agg = c.group_by("area", "slot", "player_id").agg(
        n_goals=pl.struct("game_id", "event_id").n_unique(), n_poss=pl.len(),
        odd_g=pl.col("game_id").filter(pl.col("odd")).n_unique(),
        even_g=pl.col("game_id").filter(~pl.col("odd")).n_unique(),
        isd=pl.col("isd").first(),
        **{f"{a}_full": pl.col(a).mean() for a in AXES},
        **{f"{a}_odd": pl.col(a).filter(pl.col("odd")).mean() for a in AXES},
        **{f"{a}_even": pl.col(a).filter(~pl.col("odd")).mean() for a in AXES},
        **{f"{a}_wvar": pl.col(a).var() for a in AXES})
    elig = agg.filter((pl.col("n_goals") >= thresh) & (pl.col("odd_g") >= 5) & (pl.col("even_g") >= 5))
    out = []
    slot_pool = c.group_by("slot")  # for Gate 1 shuffled-area (same slot, all areas)
    slot_iqr = {r["slot"]: {a: (r[f"{a}_p75"] - r[f"{a}_p25"]) for a in AXES}
                for r in c.group_by("slot").agg(
                    *[pl.col(a).quantile(.75).alias(f"{a}_p75") for a in AXES],
                    *[pl.col(a).quantile(.25).alias(f"{a}_p25") for a in AXES]).iter_rows(named=True)}
    for (area, slot), g in elig.group_by(["area", "slot"]):
        if g.height < 8:
            continue
        cellrows = c.filter((pl.col("area") == area) & (pl.col("slot") == slot))
        for ax in AXES:
            real_iqr = float(cellrows[ax].quantile(.75) - cellrows[ax].quantile(.25))
            g1_ratio = round(real_iqr / slot_iqr[slot][ax], 2) if slot_iqr[slot][ax] else float("nan")
            full = g[f"{ax}_full"].to_numpy(); odd = g[f"{ax}_odd"].to_numpy(); even = g[f"{ax}_even"].to_numpy()
            wvar = g[f"{ax}_wvar"].to_numpy(); npos = g["n_poss"].to_numpy()
            r = _pearson(odd, even)
            between_var = float(np.var(full, ddof=1))
            noise_var = float(np.nanmean(wvar / np.maximum(npos, 1)))
            excess = round(between_var / noise_var, 2) if noise_var > 1e-9 else float("nan")
            out.append({"area": area, "slot": slot, "axis": ax, "n_def": g.height,
                        "is_def": bool(g["isd"][0]), "g1_ratio": g1_ratio,
                        "splithalf_r": round(r, 2), "excess": excess,
                        "GATE2": bool((r >= 0.40) and (excess >= 1.5))})
    return out


PRIMARY = [("point", "strong-D"), ("slot", "D"), ("left_halfwall", "strong-D"), ("right_halfwall", "strong-D"),
           ("point", "D"), ("behind_net", "strong-D"), ("left_corner", "strong-D"), ("right_corner", "strong-D")]


def write() -> dict:
    bc = build_cells()
    res20, res33 = gates(20), gates(33)
    L = []; W = L.append
    W("# Settled-Play Gates 1+2 — locked tiling, possession-level, per-axis, slot-stratified\n")
    W("Gate 1 = cell IQR / shuffled-area(same-slot) IQR (tight <1; EXPECTED to pass, not the finding). "
      "**Gate 2 (THE finding) = split-half r ≥ 0.40 on possession-collapsed per-defender means (BY GAMES) AND "
      "between/within excess ≥ 1.5.** Axes: depth (dist-to-net), latsw (strong/weak lateral), distpuck. "
      "No tape, no profile, no aggregation.\n")
    W(f"- point within-depth distribution (bimodality check for later true-point vs high-slot split): "
      f"{bc['point_depth_quantiles']} (44=area floor, 63=blue line)\n")

    def table(res, thresh):
        W(f"\n## Gate results at ≥{thresh} goals (≥5/half); cells with ≥8 eligible defenders\n")
        W("### LEAD — D primary-role cells (the individual-D-settled-coverage question)\n")
        W("| area | slot | axis | n_def | Gate1 IQR ratio | split-half r | excess | GATE 2 |")
        W("|---|---|---|---|---|---|---|---|")
        idx = {(d["area"], d["slot"], d["axis"]): d for d in res}
        for area, slot in PRIMARY:
            for ax in AXES:
                d = idx.get((area, slot, ax))
                if not d:
                    continue
                W(f"| {area} | {slot} | {ax} | {d['n_def']} | {d['g1_ratio']} | **{d['splithalf_r']}** | "
                  f"{d['excess']} | {'**PASS**' if d['GATE2'] else 'no'} |")
        W("\n### All other tested cells (D and F)\n")
        W("| area | slot | axis | pos | n_def | Gate1 | split-half r | excess | GATE 2 |")
        W("|---|---|---|---|---|---|---|---|---|")
        prim = set(PRIMARY)
        for d in sorted(res, key=lambda x: -x["splithalf_r"] if x["splithalf_r"] == x["splithalf_r"] else 0):
            if (d["area"], d["slot"]) in prim:
                continue
            W(f"| {d['area']} | {d['slot']} | {d['axis']} | {'D' if d['is_def'] else 'F'} | {d['n_def']} | "
              f"{d['g1_ratio']} | {d['splithalf_r']} | {d['excess']} | {'**PASS**' if d['GATE2'] else 'no'} |")
        npass = sum(1 for d in res if d["GATE2"])
        return npass

    n20 = table(res20, 20)
    n33 = table(res33, 33)
    W(f"\n## Summary\n")
    W(f"- Gate-2 PASS cells (r≥0.40 AND excess≥1.5): **{n20} at ≥20 goals**, **{n33} at ≥33 goals**.")
    W("- Real signal should STRENGTHEN on the cleaner ≥33 cells; noise would not.")
    W("\n## STOP — Gate results for owner review. No tape, no profile, no aggregation.\n")
    C.REPORTS.mkdir(parents=True, exist_ok=True)
    (C.REPORTS / "settled_gates.md").write_text("\n".join(L))
    return {"point_depth": bc["point_depth_quantiles"], "n_pass_20": n20, "n_pass_33": n33}


CREDIBLE = [("left_halfwall", "strong-D", "latsw"), ("right_halfwall", "strong-D", "latsw"),
            ("right_halfwall", "strong-D", "distpuck"), ("left_halfwall", "strong-D", "distpuck"),
            ("left_corner", "strong-D", "latsw"), ("right_corner", "strong-D", "latsw")]


def _agg(c):
    return c.group_by("area", "slot", "player_id").agg(
        n_goals=pl.struct("game_id", "event_id").n_unique(), n_poss=pl.len(),
        odd_g=pl.col("game_id").filter(pl.col("odd")).n_unique(),
        even_g=pl.col("game_id").filter(~pl.col("odd")).n_unique(), isd=pl.col("isd").first(),
        **{f"{a}_full": pl.col(a).mean() for a in AXES},
        **{f"{a}_odd": pl.col(a).filter(pl.col("odd")).mean() for a in AXES},
        **{f"{a}_even": pl.col(a).filter(~pl.col("odd")).mean() for a in AXES},
        **{f"{a}_wvar": pl.col(a).var() for a in AXES})


def deployment_control() -> dict:
    """Does the credible strong-D lateral signal survive after removing HANDEDNESS (shoots) + PAIRING-SIDE?
    Pairing-side is derived from the discarded artifact itself: a D's mean latsw in the central-puck 'D' cells
    (where latsw = RAW lateral) IS his LD/RD lean. Residualize per-D means within (shoots × pairing-side) groups
    and re-run Gate 2 on the residuals."""
    c = pl.read_parquet(CELLS).with_columns(odd=(pl.col("game_id") % 2 == 1))
    side = pl.read_parquet(C.PARQUET / "player_side.parquet").select("player_id", "shoots")
    # pairing-side from central 'D' cells (latsw = raw lateral there)
    pair = (c.filter(pl.col("slot") == "D").group_by("player_id").agg(plat_lean=pl.col("latsw").mean())
            .with_columns(pside=pl.when(pl.col("plat_lean") < 0).then(pl.lit("L")).otherwise(pl.lit("R"))))
    agg = _agg(c).join(side, on="player_id", how="left").join(pair.select("player_id", "pside"), on="player_id", how="left")
    agg = agg.with_columns(grp=pl.col("shoots").fill_null("?") + "_" + pl.col("pside").fill_null("?"))
    rows = []
    for area, slot, ax in CREDIBLE:
        for thresh in (20, 33):
            g = agg.filter((pl.col("area") == area) & (pl.col("slot") == slot)
                           & (pl.col("n_goals") >= thresh) & (pl.col("odd_g") >= 5) & (pl.col("even_g") >= 5))
            if g.height < 8:
                continue
            full = g[f"{ax}_full"].to_numpy(); odd = g[f"{ax}_odd"].to_numpy(); even = g[f"{ax}_even"].to_numpy()
            wvar = g[f"{ax}_wvar"].to_numpy(); npos = g["n_poss"].to_numpy(); grp = g["grp"].to_numpy()
            noise = float(np.nanmean(wvar / np.maximum(npos, 1)))
            r0 = _pearson(odd, even); e0 = float(np.var(full, ddof=1)) / noise
            # residualize within (shoots x pairing-side): subtract each group's full-mean from full/odd/even
            gm = {gg: float(np.mean(full[grp == gg])) for gg in set(grp)}
            base = np.array([gm[gg] for gg in grp])
            rf, ro, re = full - base, odd - base, even - base
            r1 = _pearson(ro, re); e1 = float(np.var(rf, ddof=1)) / noise
            rows.append({"cell": f"{area}×{slot}", "axis": ax, "thresh": thresh, "n_def": g.height,
                         "r_before": round(r0, 2), "excess_before": round(e0, 2),
                         "r_after": round(r1, 2), "excess_after": round(e1, 2),
                         "survives": bool(r1 >= 0.40 and e1 >= 1.5)})
    # forward-depth cells (unsigned, deployment-immune by construction) — restate for reference
    fdepth = []
    for area, slot in [("point", "strong-low-F"), ("left_halfwall", "strong-low-F"), ("right_halfwall", "strong-low-F")]:
        for thresh in (20, 33):
            g = agg.filter((pl.col("area") == area) & (pl.col("slot") == slot)
                           & (pl.col("n_goals") >= thresh) & (pl.col("odd_g") >= 5) & (pl.col("even_g") >= 5))
            if g.height < 8:
                continue
            full = g["depth_full"].to_numpy(); odd = g["depth_odd"].to_numpy(); even = g["depth_even"].to_numpy()
            wvar = g["depth_wvar"].to_numpy(); npos = g["n_poss"].to_numpy()
            noise = float(np.nanmean(wvar / np.maximum(npos, 1)))
            fdepth.append({"cell": f"{area}×{slot}", "thresh": thresh, "n_def": g.height,
                           "r": round(_pearson(odd, even), 2), "excess": round(float(np.var(full, ddof=1)) / noise, 2)})
    L = []; W = L.append
    W("# Settled-Play DEPLOYMENT CONTROL — does strong-D lateral survive handedness + pairing-side?\n")
    W("Pairing-side (LD/RD) derived from the discarded artifact: a D's mean latsw in the central 'D' cells (raw "
      "lateral) = his roster side. Per-D means residualized WITHIN (shoots × pairing-side) groups; Gate 2 re-run on "
      "residuals. **Survives = r≥0.40 AND excess≥1.5 AFTER removing handedness+side → coverage skill, not "
      "deployment.**\n")
    W("## Credible strong-D cells — Gate 2 BEFORE vs AFTER the deployment control\n")
    W("| cell | axis | ≥goals | n_def | r before | excess before | **r after** | **excess after** | SURVIVES |")
    W("|---|---|---|---|---|---|---|---|---|")
    for r in rows:
        W(f"| {r['cell']} | {r['axis']} | {r['thresh']} | {r['n_def']} | {r['r_before']} | {r['excess_before']} | "
          f"**{r['r_after']}** | **{r['excess_after']}** | {'**YES**' if r['survives'] else 'no'} |")
    W("\n## Forward support-depth cells (unsigned = deployment-immune by construction; no control needed)\n")
    W("| cell | axis | ≥goals | n_def | split-half r | excess |")
    W("|---|---|---|---|---|---|")
    for r in fdepth:
        W(f"| {r['cell']} | depth | {r['thresh']} | {r['n_def']} | {r['r']} | {r['excess']} |")
    n_surv = sum(1 for r in rows if r["survives"])
    W(f"\n## Verdict\n- Credible strong-D cells surviving the handedness+pairing-side control: **{n_surv}** of {len(rows)}.")
    W("- Forward support-depth cells are deployment-immune by construction (unsigned depth) — the cleanest survivors regardless.")
    W("\n## STOP — deployment control for owner review before any tape.\n")
    C.REPORTS.mkdir(parents=True, exist_ok=True)
    (C.REPORTS / "settled_deploy_control.md").write_text("\n".join(L))
    return {"n_survive": n_surv, "n_credible": len(rows), "rows": rows, "fdepth": fdepth}


FDEPTH_CELLS = [("point", "strong-low-F"), ("left_halfwall", "strong-low-F"), ("right_halfwall", "strong-low-F")]


def cw_control() -> dict:
    """Does forward SUPPORT-DEPTH survive controlling for forward POSITION (C vs W)? Centers play deeper than
    wingers in DZ coverage, so the depth spread could be C-vs-W role, not individual skill (the LD/RD-analogue).
    Residualize per-F depth means WITHIN forward-position (C/L/R) groups; Gate 2 re-run on residuals."""
    c = pl.read_parquet(CELLS).with_columns(odd=(pl.col("game_id") % 2 == 1))
    pos = pl.read_parquet(C.PARQUET / "player_side.parquet").select("player_id", "pos")
    agg = _agg(c).join(pos, on="player_id", how="left")
    rows = []
    for area, slot in FDEPTH_CELLS:
        for thresh in (20, 33):
            g = agg.filter((pl.col("area") == area) & (pl.col("slot") == slot)
                           & (pl.col("n_goals") >= thresh) & (pl.col("odd_g") >= 5) & (pl.col("even_g") >= 5))
            if g.height < 8:
                continue
            full = g["depth_full"].to_numpy(); odd = g["depth_odd"].to_numpy(); even = g["depth_even"].to_numpy()
            wvar = g["depth_wvar"].to_numpy(); npos = g["n_poss"].to_numpy(); grp = g["pos"].fill_null("?").to_numpy()
            noise = float(np.nanmean(wvar / np.maximum(npos, 1)))
            r0 = _pearson(odd, even); e0 = float(np.var(full, ddof=1)) / noise
            gm = {gg: float(np.mean(full[grp == gg])) for gg in set(grp)}
            base = np.array([gm[gg] for gg in grp])
            r1 = _pearson(odd - base, even - base); e1 = float(np.var(full - base, ddof=1)) / noise
            posmix = {gg: int((grp == gg).sum()) for gg in sorted(set(grp))}
            rows.append({"cell": f"{area}×{slot}", "thresh": thresh, "n_def": g.height, "pos_mix": posmix,
                         "r_before": round(r0, 2), "excess_before": round(e0, 2),
                         "r_after": round(r1, 2), "excess_after": round(e1, 2),
                         "survives": bool(r1 >= 0.40 and e1 >= 1.5)})
    L = []; W = L.append
    W("# Settled-Play C/W CONTROL — does forward support-depth survive forward-position (C vs W)?\n")
    W("The LD/RD-analogue for forwards: centers play deeper than wingers in DZ coverage, so `strong-low-F` depth "
      "spread could be C-vs-W ROLE, not individual skill. Per-F depth means residualized WITHIN forward-position "
      "(C/L/R) groups; Gate 2 re-run on residuals. **Survives = r≥0.40 AND excess≥1.5 AFTER → genuine individual "
      "support-depth skill (the program's first fully-controlled positive). Collapses → C-vs-W role, wall holds.**\n")
    W("| cell | ≥goals | n_F | pos mix (C/L/R) | r before | excess before | **r after** | **excess after** | SURVIVES |")
    W("|---|---|---|---|---|---|---|---|---|")
    for r in rows:
        W(f"| {r['cell']} | {r['thresh']} | {r['n_def']} | {r['pos_mix']} | {r['r_before']} | {r['excess_before']} | "
          f"**{r['r_after']}** | **{r['excess_after']}** | {'**YES**' if r['survives'] else 'no'} |")
    n_surv = sum(1 for r in rows if r["survives"])
    W(f"\n## Verdict\n- Forward support-depth cells surviving the C/W control: **{n_surv}** of {len(rows)}.")
    if n_surv:
        W("- **A forward's DZ support-depth is individually stable BEYOND C-vs-W role → the program's FIRST genuine, "
          "fully-controlled individual defensive signal. Proceed to tape.**")
    else:
        W("- **Collapses to C-vs-W role → the wall holds for forwards too; defense is fully walled on this data.**")
    W("\n## STOP — C/W control for owner review before any tape.\n")
    C.REPORTS.mkdir(parents=True, exist_ok=True)
    (C.REPORTS / "settled_cw_control.md").write_text("\n".join(L))
    return {"n_survive": n_surv, "rows": rows}


if __name__ == "__main__":
    import json, sys
    if "--cw" in sys.argv:
        print(json.dumps(cw_control(), indent=1, default=str))
    elif "--deploy" in sys.argv:
        print(json.dumps(deployment_control(), indent=1, default=str))
    else:
        print(json.dumps(write(), indent=1, default=str))
