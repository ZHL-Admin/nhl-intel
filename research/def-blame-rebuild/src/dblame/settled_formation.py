"""Settled-play strong-D signal — FORMATION control (normal vs rotated), head-to-head vs the handedness control.

Hypothesis (owner): the handedness/pairing-side residualization was OVER-aggressive — it stripped coordinated
ROTATIONS (a D covering the off side because he rotated to help his partner = real defending) along with the
roster artifact. Smarter control: classify each settled possession-area's D-pair FORMATION as NORMAL (Ds on
their natural sides) or ROTATED (a coordinated swap — roster-LD on the right AND roster-RD on the left), then
measure the individual signal WITHIN normal formations (like-with-like), not by residualizing handedness out.

Reuses: CELLS (possession-collapsed per player/possid/area/slot), the locked settled classifier / area / slot /
possession defs, split-half BY GAMES, position+slot stratification. The formation detector is the one new piece.

Head-to-head per credible strong-D cell: RAW · HANDEDNESS-controlled · FORMATION-controlled(normal-only) ·
NORMAL+HANDEDNESS (the disentangler: does real skill survive rotation-removal AND handedness-removal?).
STOP at the test. No tape, no aggregation.
"""
from __future__ import annotations

import numpy as np
import polars as pl

from . import config as C
from .data import universe
from .settled_confirm import _area, BL, SUSTAIN, PRE_SHOT, SEASON_FILES
from .settled_gates import CELLS, AXES, _agg, _pearson

MIN_D_FR = 4          # a D counts as "present" in a (possid,area) with >= this many settled frames
CREDIBLE = [("right_halfwall", "strong-D", "latsw"), ("right_halfwall", "strong-D", "distpuck"),
            ("left_halfwall", "strong-D", "latsw"), ("left_halfwall", "strong-D", "distpuck"),
            ("point", "strong-D", "latsw"), ("point", "strong-D", "distpuck"), ("point", "strong-D", "depth")]


def _pside():
    """roster side (LD/RD) per D = sign of his mean RAW lateral in the central 'D' cells (latsw=raw there)."""
    c = pl.read_parquet(CELLS).filter(pl.col("slot") == "D")
    p = c.group_by("player_id").agg(lean=pl.col("latsw").mean())
    return p.with_columns(pside=pl.when(pl.col("lean") < 0).then(pl.lit("L")).otherwise(pl.lit("R"))).select("player_id", "pside")


def build_formation() -> pl.DataFrame:
    """Per (game,event,possid,area): the D-pair's RAW laterals + NORMAL/ROTATED/OTHER. Re-reads frames (new piece)."""
    u = universe().select("game_id", "event_id", "season", "attack_sign", "defending_team_id",
                          "home_goalie_id", "away_goalie_id", "start_frame", "goal_frame")
    isdef = set(pl.read_parquet(C.PARQUET / "player_side.parquet").filter(pl.col("pos") == "D")["player_id"].to_list())
    pside = _pside()
    parts = []
    for season, fname in zip(C.SEASONS, SEASON_FILES):
        us = u.filter(pl.col("season") == season)
        gids = us["game_id"].unique().to_list()
        fr = (pl.read_parquet(C.GT_FRAMES_DIR / fname, columns=["game_id", "event_id", "frame_index", "is_puck", "player_id", "team_id", "x_std", "y_std"])
              .filter(pl.col("game_id").is_in(gids)).join(us, on=["game_id", "event_id"], how="inner")
              .filter((pl.col("frame_index") >= pl.col("start_frame")) & (pl.col("frame_index") <= pl.col("goal_frame")))
              .with_columns(depth=89.0 - pl.col("attack_sign") * pl.col("x_std"), lat=pl.col("attack_sign") * pl.col("y_std")))
        goalie = (pl.col("player_id") == pl.col("home_goalie_id")) | (pl.col("player_id") == pl.col("away_goalie_id"))
        puck = (fr.filter(pl.col("is_puck")).select("game_id", "event_id", "frame_index", "goal_frame", pdepth="depth", plat="lat")
                .sort("game_id", "event_id", "frame_index"))
        dz = pl.col("pdepth") < BL
        brk = (dz != dz.shift(1).over(["game_id", "event_id"])) | (pl.col("frame_index") != pl.col("frame_index").shift(1).over(["game_id", "event_id"]) + 1)
        puck = puck.with_columns(dz=dz).with_columns(runid=brk.fill_null(True).cast(pl.Int64).cum_sum().over(["game_id", "event_id"]))
        puck = puck.with_columns(pos_in_run=pl.col("frame_index") - pl.col("frame_index").min().over(["game_id", "event_id", "runid"]) + 1)
        puck = puck.with_columns(settled=pl.col("dz") & (pl.col("pos_in_run") >= SUSTAIN) & (pl.col("frame_index") <= pl.col("goal_frame") - PRE_SHOT))
        sp = puck.filter(pl.col("settled")).with_columns(area=_area(pl.col("pdepth"), pl.col("plat")))
        sp = sp.sort("game_id", "event_id", "frame_index").with_columns(
            pbrk=((pl.col("frame_index") != pl.col("frame_index").shift(1).over(["game_id", "event_id"]) + 1)).fill_null(True).cast(pl.Int64))
        sp = sp.with_columns(possid=pl.col("pbrk").cum_sum().over(["game_id", "event_id"]))
        # defensemen on settled frames, raw lateral, joined to area/possid
        dfr = (fr.filter(~pl.col("is_puck") & ~goalie & (pl.col("team_id") == pl.col("defending_team_id")) & pl.col("player_id").is_in(list(isdef)))
               .select("game_id", "event_id", "frame_index", "player_id", slat="lat")
               .join(sp.select("game_id", "event_id", "frame_index", "area", "possid"), on=["game_id", "event_id", "frame_index"], how="inner"))
        dd = (dfr.group_by("game_id", "event_id", "possid", "area", "player_id").agg(slat=pl.col("slat").median(), nfr=pl.len())
              .filter(pl.col("nfr") >= MIN_D_FR).join(pside, on="player_id", how="left"))
        parts.append(dd.with_columns(season=pl.lit(season)))
    dd = pl.concat(parts)
    # per (game,event,possid,area): roster-LD lateral and roster-RD lateral
    ld = dd.filter(pl.col("pside") == "L").group_by("game_id", "event_id", "possid", "area").agg(ld_lat=pl.col("slat").median(), n_ld=pl.len())
    rd = dd.filter(pl.col("pside") == "R").group_by("game_id", "event_id", "possid", "area").agg(rd_lat=pl.col("slat").median(), n_rd=pl.len())
    fm = ld.join(rd, on=["game_id", "event_id", "possid", "area"], how="inner")   # need both an LD and RD present
    # RELATIVE ORDER (both Ds shift toward the puck in normal coverage, so use their order not absolute side):
    # NORMAL = roster-LD still LEFT of roster-RD; ROTATED = order inverted (LD right of RD = a coordinated swap).
    M = 2.0
    fm = fm.with_columns(formation=pl.when(pl.col("rd_lat") - pl.col("ld_lat") > M).then(pl.lit("NORMAL"))
                         .when(pl.col("ld_lat") - pl.col("rd_lat") > M).then(pl.lit("ROTATED"))
                         .otherwise(pl.lit("AMBIG")))
    return fm


def _gate(sub: pl.DataFrame, axis: str, thresh: int, resid: bool, side: pl.DataFrame):
    a = _agg(sub)
    if resid:
        a = a.join(side, on="player_id", how="left").with_columns(grp=pl.col("shoots").fill_null("?") + "_" + pl.col("pside").fill_null("?"))
    g = a.filter((pl.col("n_goals") >= thresh) & (pl.col("odd_g") >= 5) & (pl.col("even_g") >= 5))
    if g.height < 8:
        return {"r": float("nan"), "excess": float("nan"), "n_def": g.height}
    full = g[f"{axis}_full"].to_numpy(); odd = g[f"{axis}_odd"].to_numpy(); even = g[f"{axis}_even"].to_numpy()
    wvar = g[f"{axis}_wvar"].to_numpy(); npos = g["n_poss"].to_numpy()
    noise = float(np.nanmean(wvar / np.maximum(npos, 1)))
    if resid:
        grp = g["grp"].to_numpy(); gm = {k: float(np.mean(full[grp == k])) for k in set(grp)}
        base = np.array([gm[k] for k in grp]); full, odd, even = full - base, odd - base, even - base
    return {"r": round(_pearson(odd, even), 2), "excess": round(float(np.var(full, ddof=1)) / noise, 2), "n_def": g.height}


def run(thresh=20) -> dict:
    fm = build_formation()
    c = pl.read_parquet(CELLS).with_columns(odd=(pl.col("game_id") % 2 == 1))
    side = pl.read_parquet(C.PARQUET / "player_side.parquet").select("player_id", "shoots").join(_pside(), on="player_id", how="left")
    cfm = c.join(fm.select("game_id", "event_id", "possid", "area", "formation"), on=["game_id", "event_id", "possid", "area"], how="left")
    # formation split (over the strong-D observations we test)
    strongd = cfm.filter(pl.col("slot") == "strong-D")
    fsplit = strongd.group_by("formation").agg(obs=pl.len()).sort("obs", descending=True).to_dicts()
    # sanity examples
    def _names():
        m = pl.read_parquet(C.PARQUET / "player_side.parquet").select("player_id", "full_name")
        return {r["player_id"]: r["full_name"] for r in m.iter_rows(named=True)}
    nm = _names()
    ex = {}
    for f in ("NORMAL", "ROTATED"):
        e = fm.filter(pl.col("formation") == f).sort("game_id", "event_id").head(3)
        ex[f] = [{"goal": f"{r['game_id']}-{r['event_id']}", "area": r["area"],
                  "LD_lat": round(r["ld_lat"], 1), "RD_lat": round(r["rd_lat"], 1)} for r in e.iter_rows(named=True)]
    # head-to-head per cell
    rows = []
    for area, slot, ax in CREDIBLE:
        cell = cfm.filter((pl.col("area") == area) & (pl.col("slot") == slot))
        cell_norm = cell.filter(pl.col("formation") == "NORMAL")
        rows.append({"cell": f"{area}×{slot}", "axis": ax,
                     "raw": _gate(cell, ax, thresh, False, side),
                     "handedness": _gate(cell, ax, thresh, True, side),
                     "formation_normal": _gate(cell_norm, ax, thresh, False, side),
                     "normal_plus_handedness": _gate(cell_norm, ax, thresh, True, side)})
    # report
    L = []; W = L.append
    W("# Settled-D FORMATION control — head-to-head vs handedness control (strong-D cells)\n")
    W("Formation state per (possession × area) from the D-pair: **NORMAL** = roster-LD on the left AND roster-RD "
      "on the right (natural sides); **ROTATED** = roster-LD on the right AND roster-RD on the left (a coordinated "
      "swap — both crossed); OTHER = lone/partial. Individual stability (split-half ≥0.40 by GAMES, possession-"
      "collapsed, AND excess ≥1.5) measured WITHIN normal formations, vs residualizing handedness out.\n")
    W("## Formation split (strong-D observations)\n")
    tot = sum(d["obs"] for d in fsplit)
    for d in fsplit:
        W(f"- {d['formation']}: {d['obs']:,} ({d['obs']/tot*100:.1f}%)")
    W("\n## Sanity examples (D-pair lateral; NORMAL should be LD-left/RD-right, ROTATED a clear swap)\n")
    for f in ("NORMAL", "ROTATED"):
        W(f"- **{f}:** " + " · ".join(f"{x['goal']} {x['area']} (LD {x['LD_lat']}, RD {x['RD_lat']})" for x in ex[f]))
    W(f"\n## HEAD-TO-HEAD — split-half r (excess) at ≥{thresh} goals · Gate 2 = r≥0.40 & excess≥1.5\n")
    W("| cell | axis | RAW | +HANDEDNESS | +FORMATION (normal) | +NORMAL & HANDEDNESS | n_def raw→normal |")
    W("|---|---|---|---|---|---|---|")
    for r in rows:
        def cell_str(k):
            d = r[k]; return f"{d['r']} ({d['excess']})" + ("✓" if (d['r'] == d['r'] and d['r'] >= 0.4 and d['excess'] >= 1.5) else "")
        W(f"| {r['cell']} | {r['axis']} | {cell_str('raw')} | {cell_str('handedness')} | **{cell_str('formation_normal')}** | "
          f"{cell_str('normal_plus_handedness')} | {r['raw']['n_def']}→{r['formation_normal']['n_def']} |")
    W("\n## Read\n")
    W("- If **+FORMATION(normal)** stays high (≈raw) where **+HANDEDNESS** collapsed → the handedness control was "
      "over-aggressive (it removed coordinated rotations). BUT normal-only RETAINS handedness variation, so the "
      "decisive disentangler is **+NORMAL & HANDEDNESS**: only if THAT stays ≥0.40 is there real coverage skill "
      "beyond BOTH rotation and handedness. If normal-only is high but normal+handedness collapses, the formation "
      "'preservation' was just retained handedness (deployment), and the wall stands.")
    W("- Guard (Step 4): n_def raw→normal shows normal-only power; excess (between/within, possession-level) shows "
      "it's not mere variance-shrink; split-half is by odd/even GAMES throughout.")
    W("\n## STOP — head-to-head for owner review. No tape, no aggregation.\n")
    C.REPORTS.mkdir(parents=True, exist_ok=True)
    (C.REPORTS / "settled_formation.md").write_text("\n".join(L))
    return {"formation_split": fsplit, "rows": rows}


if __name__ == "__main__":
    import json
    print(json.dumps(run(), indent=1, default=str))
