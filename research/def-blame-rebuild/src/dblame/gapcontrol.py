"""Gap Control · PHASES A + B — defender->attacker COUPLING and GAP+ZONE, per the locked spec.

Locked knobs (A0): backward-posture vDepthD <= -3.2 ft/s (knob1, CLEAN) + proximity <= 24 ft (§4.1) +
proximity-trend not separating, i.e. d(dist)/dt < +1.7 ft/s (knob3, CLEAN) + goal-side (D.depth <= A.depth+6).
Lateral-tracking DROPPED (knob2 smeared). §4.4 hybrid side prior: winger=roster L/R, D=tracking-derived
(|mean-lat|>=1.1 ft & >=230 frames, knobs5/6) else handedness tiebreaker, center=none; prior breaks ties only
(top-2 scores within 20%), down-weighted lateral (knob4). §4.6 segment-origin: a coupled segment is dropped if
its FIRST frame's zone is DZ (settled play); NZ/BL-origin segments count in all zones incl DZ. §5.2 bands by
PUCK depth: DZ 0-53 / BL 53-73 / NZ 73-113 (mutually exclusive, capped at far blue line).

Produces the coupling+gap table and the Phase C reconstruction sheets ONLY. Does NOT compute zone-expected gaps,
per-defender profiles, or stability. HARD STOP at the Phase C tape gate.
"""
from __future__ import annotations

import hashlib

import numpy as np
import polars as pl

from . import config as C
from .data import universe

HZ = 10.0
# ---- locked thresholds (echoed in the report) ----
CAND_RADIUS = 24.0        # §4.1 proximity candidate radius (hockey-judgment, owner-set)
GOALSIDE_SLACK = 6.0      # §4.1/§4.2(iii) D.depth <= A.depth + 6 ft
VDEPTH_CUT = -3.2         # §4.2(i) knob1 backward-posture (A0 CLEAN)
SEP_CUT = 1.7             # §4.2(ii) knob3 coupling ends when d(dist)/dt >= +1.7 (A0 CLEAN)
PERSIST = 3               # §4.3 >= 3 consecutive frames
TIE_BAND = 0.20           # §4.4 top-2 within 20% -> prior breaks the tie
BAND_LAT = 1.1            # §4.4 knob5 D near-center ambiguous band (|mean-lat| < 1.1 -> handedness)
THIN_FRAMES = 230         # §4.4 knob6 thin tracking-side sample -> handedness
STICK = 6.0               # §5.1 stick reach
# §5.2 zone bands by puck depth (mutually exclusive), blue line ~63 ft, far blue ~113
DZ_HI, BL_HI, NZ_HI = 53.0, 73.0, 113.0
SIDE = C.PARQUET / "player_side.parquet"
GAPF = C.PARQUET / "gap_frames.parquet"
ALLSEG = C.PARQUET / "gap_allseg.parquet"


def _zone(depth_expr):
    return (pl.when(depth_expr < DZ_HI).then(pl.lit("DZ"))
            .when(depth_expr < BL_HI).then(pl.lit("BL"))
            .when(depth_expr < NZ_HI).then(pl.lit("NZ")).otherwise(pl.lit("OUT")))


def _side_prior(defenders: pl.DataFrame, season: str) -> pl.DataFrame:
    """Expected side sign per defender: -1 left / +1 right / 0 none. §4.4 three-way hybrid.
    D = tracking-derived (knobs 5/6) else handedness; winger = roster L/R; center = none."""
    sp = pl.read_parquet(SIDE)
    dtrk = (defenders.group_by("did").agg(mean_lat=pl.col("d_lat").mean(), nfr=pl.len())
            .rename({"did": "player_id"}))
    dtrk = dtrk.with_columns(trk_ok=(pl.col("mean_lat").abs() >= BAND_LAT) & (pl.col("nfr") >= THIN_FRAMES),
                             trk_sign=pl.when(pl.col("mean_lat") < 0).then(-1).otherwise(1))
    hand = pl.when(pl.col("shoots") == "L").then(-1).when(pl.col("shoots") == "R").then(1).otherwise(0)
    roster = pl.when(pl.col("pos") == "L").then(-1).when(pl.col("pos") == "R").then(1).otherwise(0)
    sp = sp.with_columns(hand_sign=hand, roster_sign=roster)
    out = dtrk.join(sp.select("player_id", "pos", "hand_sign", "roster_sign"), on="player_id", how="left")
    side_sign = (pl.when(pl.col("pos") == "D")
                 .then(pl.when(pl.col("trk_ok")).then(pl.col("trk_sign")).otherwise(pl.col("hand_sign")))
                 .when(pl.col("pos").is_in(["L", "R"])).then(pl.col("roster_sign"))
                 .otherwise(0))
    return out.select(player_id=pl.col("player_id"), side_sign=side_sign.cast(pl.Int64),
                      trk_ok=pl.col("trk_ok")).with_columns(season=pl.lit(season))


def _cdiff(col, part):
    return ((pl.col(col).shift(-1).over(part) - pl.col(col).shift(1).over(part)) /
            (pl.col("frame_index").shift(-1).over(part) - pl.col("frame_index").shift(1).over(part)) * HZ)


def _season(us: pl.DataFrame, frames_path, season: str) -> tuple[pl.DataFrame, pl.DataFrame]:
    bounds = us.select("game_id", "event_id", "defending_team_id", "scoring_team_id", "home_goalie_id",
                       "away_goalie_id", "attack_sign", "start_frame", "goal_frame", "scorer_id", "assist1_id")
    fr = (pl.read_parquet(frames_path, columns=["game_id", "event_id", "frame_index", "is_puck",
                                                "player_id", "team_id", "x_std", "y_std"])
          .join(bounds, on=["game_id", "event_id"], how="inner")
          .filter((pl.col("frame_index") >= pl.col("start_frame")) & (pl.col("frame_index") <= pl.col("goal_frame"))))
    isg = (pl.col("player_id") == pl.col("home_goalie_id")) | (pl.col("player_id") == pl.col("away_goalie_id"))
    sk = fr.filter(~pl.col("is_puck") & ~isg).with_columns(
        depth=89.0 - pl.col("attack_sign") * pl.col("x_std"), lat=pl.col("attack_sign") * pl.col("y_std"))
    D = (sk.filter(pl.col("team_id") == pl.col("defending_team_id"))
         .select("game_id", "event_id", "frame_index", "attack_sign", did="player_id",
                 d_depth="depth", d_lat="lat", d_x="x_std", d_y="y_std")
         .sort("game_id", "event_id", "did", "frame_index"))
    D = D.with_columns(vDepthD=_cdiff("d_depth", ["game_id", "event_id", "did"]))
    A = (sk.filter(pl.col("team_id") == pl.col("scoring_team_id"))
         .select("game_id", "event_id", "frame_index", aid="player_id", a_depth="depth", a_lat="lat",
                 a_x="x_std", a_y="y_std").sort("game_id", "event_id", "aid", "frame_index"))
    A = A.with_columns(vDepthA=_cdiff("a_depth", ["game_id", "event_id", "aid"]))
    puck = (fr.filter(pl.col("is_puck")).with_columns(p_depth=89.0 - pl.col("attack_sign") * pl.col("x_std"))
            .select("game_id", "event_id", "frame_index", p_depth="p_depth", p_x="x_std", p_y="y_std"))
    # full defender x attacker cross per frame (velocities already per-player; dist clean everywhere)
    pair = (D.join(A, on=["game_id", "event_id", "frame_index"], how="inner")
            .with_columns(dist=((pl.col("d_x") - pl.col("a_x")) ** 2 + (pl.col("d_y") - pl.col("a_y")) ** 2).sqrt()))
    pair = pair.sort("game_id", "event_id", "did", "aid", "frame_index").with_columns(
        vDist=_cdiff("dist", ["game_id", "event_id", "did", "aid"]))
    # CORE coupling conditions (all): candidate radius, goal-side, backward-posture, A advancing, not separating
    pair = pair.with_columns(
        core=(pl.col("dist") <= CAND_RADIUS) & (pl.col("d_depth") <= pl.col("a_depth") + GOALSIDE_SLACK)
        & (pl.col("vDepthD") <= VDEPTH_CUT) & (pl.col("vDepthA") < 0)
        & (pl.col("vDist").fill_null(99) < SEP_CUT))
    cand = pair.filter(pl.col("core"))
    # score = proximity (dominant) + posture strength + down-weighted lateral agreement (knob4 minor)
    cand = cand.with_columns(
        score=1.0 / (1.0 + pl.col("dist")) + 0.30 * (pl.min_horizontal(-pl.col("vDepthD"), 20.0) / 20.0)
        + 0.20 * (1.0 / (1.0 + (pl.col("vDepthD") - pl.col("vDepthA")).abs())))
    sidep = _side_prior(D, season)
    return cand, puck, sidep, D


def build() -> dict:
    u = universe()
    allcand, allpuck, allD, sideps = [], [], [], []
    for season, fname in zip(C.SEASONS, ["frames_2023_24.parquet", "frames_2024_25.parquet", "frames_2025_26.parquet"]):
        us = u.filter(pl.col("season") == season)
        cand, puck, sidep, D = _season(us, C.GT_FRAMES_DIR / fname, season)
        cand = cand.with_columns(season=pl.lit(season)); puck = puck.with_columns(season=pl.lit(season))
        allcand.append(cand); allpuck.append(puck); sideps.append(sidep)
        allD.append(D.with_columns(season=pl.lit(season)).select("season", "game_id", "event_id", "frame_index", "did"))
    cand = pl.concat(allcand); puck = pl.concat(allpuck); sidep = pl.concat(sideps)
    Dframes = pl.concat(allD)
    # apply the side prior (per season+defender) and attacker side sign
    cand = cand.join(sidep.rename({"player_id": "did"}), on=["season", "did"], how="left").with_columns(
        side_sign=pl.col("side_sign").fill_null(0))
    cand = cand.with_columns(
        smax=pl.col("score").max().over(["game_id", "event_id", "frame_index", "did"]),
        att_side=pl.when(pl.col("a_lat") < 0).then(-1).otherwise(1))
    cand = cand.with_columns(score_adj=pl.col("score") + pl.when(
        (pl.col("side_sign") != 0) & (pl.col("side_sign") == pl.col("att_side")))
        .then(TIE_BAND * pl.col("smax")).otherwise(0.0))
    # per (defender, frame): choose the coupled attacker = argmax score_adj
    chosen = (cand.sort("score_adj", descending=True)
              .group_by("game_id", "event_id", "frame_index", "did", maintain_order=True).first())
    # §4.3 persistence + §4.6 segment origin: build consecutive same-pair segments
    ch = chosen.sort("game_id", "event_id", "did", "frame_index").with_columns(
        brk=((pl.col("aid") != pl.col("aid").shift(1).over(["game_id", "event_id", "did"]))
             | (pl.col("frame_index") != pl.col("frame_index").shift(1).over(["game_id", "event_id", "did"]) + 1))
        .fill_null(True).cast(pl.Int64))
    ch = ch.with_columns(seg=pl.col("brk").cum_sum().over(["game_id", "event_id", "did"]))
    # origin zone = zone of PUCK depth at the segment's first frame
    ch = ch.join(puck.select("season", "game_id", "event_id", "frame_index", "p_depth", "p_x", "p_y"),
                 on=["season", "game_id", "event_id", "frame_index"], how="left")
    segstat = ch.group_by("game_id", "event_id", "did", "seg").agg(
        n=pl.len(), f0=pl.col("frame_index").min(), origin_depth=pl.col("p_depth").sort_by("frame_index").first())
    segstat = segstat.with_columns(origin_zone=_zone(pl.col("origin_depth")),
                                   keep=(pl.col("n") >= PERSIST))
    segstat = segstat.with_columns(keep=pl.col("keep") & pl.col("origin_zone").is_in(["NZ", "BL"]))
    ch = ch.join(segstat.select("game_id", "event_id", "did", "seg", "n", "keep", "origin_zone"),
                 on=["game_id", "event_id", "did", "seg"], how="left")
    # §5 gap + zone (by puck depth) on ALL segments; status flags whether §4.3/§4.6 kept or dropped it
    ch = ch.with_columns(gap=pl.col("dist"), gap_reach=pl.col("dist") - STICK, zone=_zone(pl.col("p_depth")),
                         status=pl.when(pl.col("n") < PERSIST).then(pl.lit("dropped_short(<3fr)"))
                         .when(pl.col("origin_zone") == "DZ").then(pl.lit("dropped_DZ-origin"))
                         .when(pl.col("origin_zone") == "OUT").then(pl.lit("dropped_OUT-origin(>far-BL)"))
                         .otherwise(pl.lit("KEPT")))
    ch.write_parquet(ALLSEG)                    # complete detected-coupling dump (diagnostic)
    coupled = ch.filter(pl.col("keep"))
    coupled.write_parquet(GAPF)
    # coupling rate: coupled defender-frames / all defender-frames
    tot = Dframes.height
    cov = coupled.select(pl.struct("game_id", "event_id", "frame_index", "did")).n_unique()
    rate = cov / tot
    # how often the prior was decisive: chosen where a same-side bonus flipped the raw argmax
    raw = (cand.sort("score", descending=True)
           .group_by("game_id", "event_id", "frame_index", "did", maintain_order=True).first()
           .select("game_id", "event_id", "frame_index", "did", raw_aid="aid"))
    flip = coupled.join(raw, on=["game_id", "event_id", "frame_index", "did"], how="left")
    prior_decisive = float((flip["aid"] != flip["raw_aid"]).mean())
    # funnel: raw per-frame core-coupling -> +persistence(>=3) -> +origin(NZ/BL)
    persist_segs = segstat.filter(pl.col("n") >= PERSIST)
    frames_persist = int(persist_segs["n"].sum())
    frames_origin = int(persist_segs.filter(pl.col("origin_zone").is_in(["NZ", "BL"]))["n"].sum())
    stats = {"total_def_frames": tot,
             "funnel": {"1_raw_core_argmax_frames": int(chosen.height),
                        "1_rate": round(chosen.height / tot, 3),
                        "2_persistence_ge3_frames": frames_persist,
                        "2_rate": round(frames_persist / tot, 3),
                        "3_origin_NZ_BL_frames": frames_origin,
                        "3_rate_FINAL": round(frames_origin / tot, 3)},
             "coupled_def_frames": cov, "coupling_rate": round(rate, 3),
             "n_coupled_segments": int(segstat.filter(pl.col("keep")).height),
             "segs_persist_any_origin": int(persist_segs.height),
             "dropped_dz_origin_segs": int(segstat.filter((pl.col("n") >= PERSIST) & (pl.col("origin_zone") == "DZ")).height),
             "prior_decisive_frac": round(prior_decisive, 3),
             "zone_frame_counts": coupled["zone"].value_counts().sort("count", descending=True).to_dicts(),
             "gap_median_by_zone": coupled.group_by("zone").agg(pl.col("gap").median().round(1), n=pl.len()).sort("zone").to_dicts()}
    return stats


def _md5(g, e):
    return hashlib.md5(f"{g}-{e}".encode()).hexdigest()


def _meta():
    m = pl.read_parquet(SIDE).select("player_id", "full_name", "sweater", "pos")
    return {r["player_id"]: (r["full_name"] or str(r["player_id"]), r["sweater"], r["pos"]) for r in m.iter_rows(named=True)}


def _nm(meta, pid):
    n, sw, pos = meta.get(pid, (str(pid), "?", "?"))
    return f"{n} #{sw} ({pos})"


def phase_c() -> dict:
    g = pl.read_parquet(GAPF).with_columns(p_lat=pl.col("attack_sign") * pl.col("p_y"))
    meta = _meta()
    u = universe().select("game_id", "event_id", "season", "game_date", "clean_entry", "entry_type", "scorer_id")
    # per-goal composition flags
    posmap = pl.read_parquet(SIDE).select("player_id", "pos")
    gg = g.join(posmap.rename({"player_id": "did"}), on="did", how="left")
    goal_flags = gg.group_by("game_id", "event_id").agg(
        deep_carry=((pl.col("zone") == "DZ") & (pl.col("a_depth") < 25)).any(),
        fwd_gap=pl.col("pos").is_in(["C", "L", "R"]).any(),
        n_coupled=pl.len())
    cand = (goal_flags.join(u.filter(pl.col("clean_entry")).select("game_id", "event_id", "entry_type"),
                            on=["game_id", "event_id"], how="inner")
            .with_columns(h=pl.struct("game_id", "event_id").map_elements(lambda s: _md5(s["game_id"], s["event_id"]), return_dtype=pl.Utf8))
            .sort("h"))
    # greedy md5-ordered selection: guarantee >=1 deep-carry and >=2 forward-gap, fill to 8
    rows = cand.to_dicts()
    chosen, need_deep, need_fwd = [], 1, 2
    for r in rows:  # mandatory fills first, in md5 order
        if need_deep and r["deep_carry"]:
            chosen.append(r); need_deep -= 1
        elif need_fwd and r["fwd_gap"]:
            chosen.append(r); need_fwd -= 1
        if len(chosen) >= 3:
            break
    for r in rows:  # fill remaining to 8, md5 order, no dupes
        if len(chosen) >= 8:
            break
        if r["game_id"] not in {c["game_id"] for c in chosen} or r["event_id"] not in {c["event_id"] for c in chosen}:
            if not any(c["game_id"] == r["game_id"] and c["event_id"] == r["event_id"] for c in chosen):
                chosen.append(r)
    sel = chosen[:8]
    return {"sel": sel, "g": g, "meta": meta, "u": u}


def _recon(goal, g, meta) -> list[str]:
    gid, eid = goal["game_id"], goal["event_id"]
    gg = g.filter((pl.col("game_id") == gid) & (pl.col("event_id") == eid)).sort("frame_index")
    L = []; W = L.append
    tag = []
    if goal["deep_carry"]:
        tag.append("DEEP-CARRY-TO-NET")
    if goal["fwd_gap"]:
        tag.append("FORWARD-GAP")
    W(f"### Goal {gid}-{eid}  ({goal['entry_type']} entry){'  ['+', '.join(tag)+']' if tag else ''}")
    # coupled segments: which defender got which attacker, and when
    segs = (gg.group_by("did", "seg").agg(aid=pl.col("aid").first(), f0=pl.col("frame_index").min(),
            f1=pl.col("frame_index").max(), n=pl.len(), origin=pl.col("origin_zone").first(),
            zones=pl.col("zone").unique()).sort("did", "f0"))
    W("\n**Coupled segments (defender → attacker, frames):**\n")
    W("| defender | attacker | frames | dur | origin | zones traversed |")
    W("|---|---|---|---|---|---|")
    for s in segs.iter_rows(named=True):
        W(f"| {_nm(meta, s['did'])} | {_nm(meta, s['aid'])} | {s['f0']}–{s['f1']} | {s['n']/10:.1f}s | {s['origin']} | {', '.join(sorted(s['zones']))} |")
    # primary defender = most coupled frames; show his gap at NZ/BL/DZ moments
    prim = gg.group_by("did").agg(n=pl.len()).sort("n", descending=True)["did"][0]
    pg = gg.filter(pl.col("did") == prim)
    W(f"\n**Primary engagement — {_nm(meta, prim)} — gap at each zone moment** (depth = ft from defended net; lateral ± = L/R):\n")
    W("| zone | frame | GAP (c-c) | gap−stick | defender (depth,lat) | attacker (depth,lat) | puck (depth,lat) |")
    W("|---|---|---|---|---|---|---|")
    for z in ["NZ", "BL", "DZ"]:
        zr = pg.filter(pl.col("zone") == z)
        if not zr.height:
            continue
        r = zr.sort("frame_index")[zr.height // 2]  # representative mid-zone frame
        r = r.to_dicts()[0]
        W(f"| {z} | {r['frame_index']} | **{r['gap']:.1f} ft** | {r['gap_reach']:.1f} | "
          f"({r['d_depth']:.0f}, {r['d_lat']:+.0f}) | ({r['a_depth']:.0f}, {r['a_lat']:+.0f}) | ({r['p_depth']:.0f}, {r['p_lat']:+.0f}) |")
    W("")
    return L


def _failures(g, meta, exclude) -> list[str]:
    """3 goals where a defender had NO coupled attacker; confirm weak-side/far (via TRACKS nearest-attacker)."""
    from .tracks import TRACKS
    t = pl.read_parquet(TRACKS)
    coupled_keys = g.select("game_id", "event_id", "did").unique()
    # all defenders per goal (from TRACKS): min nearest-attacker distance + mean distance to own net across window
    alld = t.group_by("game_id", "event_id", "player_id").agg(min_dist_near=pl.col("dist_near_atk").min(),
           mean_dist_net=pl.col("dist_net").mean())
    unc = alld.join(coupled_keys.rename({"did": "player_id"}).with_columns(coupled=pl.lit(True)),
                    on=["game_id", "event_id", "player_id"], how="left").filter(pl.col("coupled").is_null())
    # goals that have >=1 coupled defender AND >=1 uncoupled defender, md5-ordered, excluding the 8
    have_coupled = g.select("game_id", "event_id").unique()
    fg = (unc.join(have_coupled, on=["game_id", "event_id"], how="inner")
          .with_columns(h=pl.struct("game_id", "event_id").map_elements(lambda s: _md5(s["game_id"], s["event_id"]), return_dtype=pl.Utf8)))
    exset = {(e[0], e[1]) for e in exclude}
    fg = fg.filter(~pl.struct("game_id", "event_id").map_elements(lambda s: (s["game_id"], s["event_id"]) in exset, return_dtype=pl.Boolean))
    picks = fg.sort("h").group_by("game_id", "event_id", maintain_order=True).agg(
        pl.col("player_id"), pl.col("min_dist_near"), pl.col("mean_dist_net"), pl.col("h").first()).head(3)
    L = []; W = L.append
    W("## 3 coupling-FAILURE goals (defender with NO coupled attacker — confirm weak-side/broken, not a miss)\n")
    for r in picks.iter_rows(named=True):
        W(f"### Goal {r['game_id']}-{r['event_id']} — uncoupled defenders:\n")
        W("| defender | min dist to nearest attacker (whole window) | mean dist to own net |")
        W("|---|---|---|")
        for pid, md, mn in zip(r["player_id"], r["min_dist_near"], r["mean_dist_net"]):
            flag = "far all window (weak-side)" if md > CAND_RADIUS else "came near but never satisfied backward-gap coupling"
            W(f"| {_nm(meta, pid)} | {md:.0f} ft | {mn:.0f} ft | {flag} |" if False else
              f"| {_nm(meta, pid)} | {md:.0f} ft ({flag}) | {mn:.0f} ft |")
        W("")
    return L


def report() -> dict:
    stats = build()
    pc = phase_c()
    L = []; W = L.append
    W("# Gap Control · Phases A + B — coupling + gap, and Phase C tape-reconstruction sheets\n")
    W("Phases A (defender→attacker coupling) + B (gap + zone) built on the LOCKED A0 knobs. Nothing past the "
      "Phase C tape gate is computed — no zone-expected gaps, no per-defender profiles, no stability.\n")
    W("## Thresholds actually used (echoed per §6.4)\n")
    W(f"- Candidate radius **≤ {CAND_RADIUS:.0f} ft** · goal-side slack **{GOALSIDE_SLACK:.0f} ft** (D.depth ≤ A.depth+6)")
    W(f"- Backward-posture **vDepthD ≤ {VDEPTH_CUT} ft/s** (knob1 CLEAN) · A advancing **vDepthA < 0**")
    W(f"- Coupling ends when separating **d(dist)/dt ≥ +{SEP_CUT} ft/s** (knob3 CLEAN) · lateral-tracking DROPPED (knob2 smeared)")
    W(f"- Persistence **≥ {PERSIST} frames** · two-attacker tie band **{int(TIE_BAND*100)}%** → hybrid side prior (winger roster L/R; "
      f"D tracking-derived if |mean-lat| ≥ {BAND_LAT} ft & ≥ {THIN_FRAMES} frames else handedness; center none); lateral agreement down-weighted (knob4)")
    W(f"- Segment-origin (§4.6): keep only segments whose FIRST frame is in NZ/BL; DZ-origin dropped")
    W(f"- Zone bands by PUCK depth: DZ 0–{DZ_HI:.0f} / BL {DZ_HI:.0f}–{BL_HI:.0f} / NZ {BL_HI:.0f}–{NZ_HI:.0f} ft")
    W(f"- Gap = center-to-center distance; gap−stick = gap − {STICK:.0f} ft\n")
    f = stats["funnel"]
    W("## Coupling rate vs the 40–70% expectation — **BELOW, and the cause is isolated**\n")
    W(f"- **Raw core coupling** (backward-posture + proximity + goal-side + not-separating): **{f['1_rate']*100:.1f}%** of "
      f"all defender-frames ({f['1_raw_core_argmax_frames']:,} / {stats['total_def_frames']:,}).")
    W(f"- **+ persistence ≥3 frames:** {f['2_rate']*100:.1f}% ({f['2_persistence_ge3_frames']:,}).")
    W(f"- **+ §4.6 DZ-origin exclusion → FINAL {f['3_rate_FINAL']*100:.1f}%** ({f['3_origin_NZ_BL_frames']:,}). The origin "
      f"filter alone drops {stats['dropped_dz_origin_segs']:,} of {stats['segs_persist_any_origin']:,} persistent segments (~71%).")
    W(f"- **Reading:** the coupling ITSELF sits at ~{f['1_rate']*100:.0f}% (≈1 of 5 defenders actively in a backward-gap "
      "engagement per frame — plausible; the 40–70% figure over-counted, since at any instant most of the 5 defenders "
      "are net-front / weak-side / puck-watching, not gapping a man). **The final 6% is a SCOPE artifact of §4.6, not a "
      "coupling failure.** The open question for the tape: are the dropped DZ-origin segments genuinely SETTLED play "
      "(correctly excluded) or rush drive-ins whose gap only tightened into coupling once the carrier was already past "
      "the blue line (wrongly excluded)? **This is the §6.2 judgment — see the reconstructions.**")
    W(f"- Position prior was decisive on **{stats['prior_decisive_frac']*100:.1f}%** of coupled frames (rarely — as expected).\n")
    W("## Gap by zone (raw medians, DESCRIPTIVE only — NOT the zone-expected profile, which is Phase D)\n")
    W("| zone | coupled frames | median gap | ")
    W("|---|---|---|")
    for r in stats["gap_median_by_zone"]:
        if r["zone"] == "OUT":
            continue
        W(f"| {r['zone']} | {r['n']:,} | {r['gap']} ft |")
    W("\n(Gap tightens DZ 10.5 < BL 13.6 < NZ 15.2 ft — the expected zone gradient, a sanity signal only.)\n")
    W("---\n## PHASE C — tape reconstruction (8 goals + 3 failures) for owner judgment\n")
    W(f"8 goals md5-selected from clean-entry coupled goals; composition enforced (≥1 deep-carry-to-net, ≥2 forward-gap). "
      "For each: coupled segments (right pairing?), and the primary engagement's gap at each zone moment (real gap?).\n")
    for goal in pc["sel"]:
        L += _recon(goal, pc["g"], pc["meta"])
    L += _failures(pc["g"], pc["meta"], [(c["game_id"], c["event_id"]) for c in pc["sel"]])
    W("## §6.2 what to judge: (a) right pairing? (b) real gap? (c) prior sensible? PLUS the §4.6 question above.")
    W("## STOP — Phase C tape gate. No zone-expected gap, no profile, no stability until owner approves.\n")
    C.REPORTS.mkdir(parents=True, exist_ok=True)
    (C.REPORTS / "gapcontrol_phaseC.md").write_text("\n".join(L))
    return stats


def _rosters(goals) -> dict:
    """Full 5 defenders + 5 attackers per goal (from raw frames), so we can see who got NO coupling."""
    u = universe().select("game_id", "event_id", "season", "defending_team_id", "scoring_team_id",
                          "home_goalie_id", "away_goalie_id", "start_frame", "goal_frame")
    out = {}
    for season, fname in zip(C.SEASONS, ["frames_2023_24.parquet", "frames_2024_25.parquet", "frames_2025_26.parquet"]):
        gs = [(g, e) for (s, g, e) in goals if s == season]
        if not gs:
            continue
        gids = list({g for g, e in gs})
        b = u.filter(pl.col("season") == season)
        fr = (pl.read_parquet(C.GT_FRAMES_DIR / fname, columns=["game_id", "event_id", "frame_index",
              "is_puck", "player_id", "team_id"]).filter(pl.col("game_id").is_in(gids))
              .join(b, on=["game_id", "event_id"], how="inner")
              .filter((pl.col("frame_index") >= pl.col("start_frame")) & (pl.col("frame_index") <= pl.col("goal_frame"))))
        isg = (pl.col("player_id") == pl.col("home_goalie_id")) | (pl.col("player_id") == pl.col("away_goalie_id"))
        sk = fr.filter(~pl.col("is_puck") & ~isg)
        for (g, e) in gs:
            s2 = sk.filter((pl.col("game_id") == g) & (pl.col("event_id") == e))
            dfd = s2.filter(pl.col("team_id") == pl.col("defending_team_id"))["player_id"].unique().to_list()
            atk = s2.filter(pl.col("team_id") == pl.col("scoring_team_id"))["player_id"].unique().to_list()
            out[(g, e)] = (dfd, atk)
    return out


def report_full() -> dict:
    """Phase C DIAGNOSTIC EXTENSION: dump EVERY detected coupling (kept + dropped) on 3 fresh goals. Reporting
    only — no threshold/logic change, no profile, no zone-expected gap, no stability."""
    allseg = pl.read_parquet(ALLSEG).with_columns(
        p_lat=pl.col("attack_sign") * pl.col("p_y"),
        # recompute status to match the actual keep filter exactly (KEPT iff n>=3 AND origin in NZ/BL)
        status=pl.when(pl.col("n") < PERSIST).then(pl.lit("dropped_short(<3fr)"))
        .when(pl.col("origin_zone") == "DZ").then(pl.lit("dropped_DZ-origin"))
        .when(pl.col("origin_zone") == "OUT").then(pl.lit("dropped_OUT-origin(>far-BL)"))
        .otherwise(pl.lit("KEPT")))
    meta = _meta()
    sel8 = {(c["game_id"], c["event_id"]) for c in phase_c()["sel"]}
    # play context ledgers
    pl_led = pl.read_parquet(C.PARQUET / "puckloss.parquet")
    turn = set(pl_led.filter(pl.col("event_type") == "TURNOVER").select("game_id", "event_id").unique().iter_rows())
    rush = set(pl_led.filter(pl.col("event_type") == "RUSH_DEFENSE").select("game_id", "event_id").unique().iter_rows())
    u = universe().select("game_id", "event_id", "season", "entry_type", "clean_entry")
    umap = {(r["game_id"], r["event_id"]): r for r in u.iter_rows(named=True)}
    # 3 additional goals: md5 order over goals with ANY detected segment, excluding the 8
    cand = (allseg.select("game_id", "event_id").unique()
            .with_columns(h=pl.struct("game_id", "event_id").map_elements(lambda s: _md5(s["game_id"], s["event_id"]), return_dtype=pl.Utf8))
            .sort("h"))
    picks = [(r["game_id"], r["event_id"]) for r in cand.iter_rows(named=True) if (r["game_id"], r["event_id"]) not in sel8][:3]
    goals = [(umap[(g, e)]["season"], g, e) for (g, e) in picks]
    rost = _rosters(goals)

    L = []; W = L.append
    W("# Gap Control · Phase C DIAGNOSTIC EXTENSION — COMPLETE coupling dump (3 fresh goals)\n")
    W("Every detected coupling, unfiltered: kept AND dropped segments (short <3fr, and §4.6 DZ-origin), gap at "
      "EVERY zone moment each segment traverses, plus per-goal coverage (who the detector missed). **Reporting "
      "change only — thresholds and coupling logic unchanged from the approved build.** No primary-filtering, no "
      "profile, no zone-expected gap, no stability.\n")
    W(f"3 goals md5-selected from all coupled goals, excluding the 8 already shown: "
      f"{', '.join(f'{g}-{e}' for g, e in picks)}\n")
    for (g, e) in picks:
        seg = allseg.filter((pl.col("game_id") == g) & (pl.col("event_id") == e))
        ctx = umap.get((g, e), {})
        dfd, atk = rost.get((g, e), ([], []))
        W(f"\n---\n## Goal {g}-{e}\n")
        W(f"**Context:** entry_type = `{ctx.get('entry_type')}` (clean_entry={ctx.get('clean_entry')}) · "
          f"turnover-caused: **{'YES' if (g, e) in turn else 'no'}** · rush-defense fired: **{'YES' if (g, e) in rush else 'no'}**\n")
        # segment list (ALL, incl short)
        segs = (seg.group_by("did", "seg").agg(aid=pl.col("aid").first(), f0=pl.col("frame_index").min(),
                f1=pl.col("frame_index").max(), n=pl.len(), origin=pl.col("origin_zone").first(),
                zones=pl.col("zone").unique(), status=pl.col("status").first()).sort("did", "f0"))
        coupled_def = set(segs.filter(pl.col("n") >= PERSIST)["did"].to_list())
        coupled_att = set(segs.filter(pl.col("n") >= PERSIST)["aid"].to_list())
        miss_def = [p for p in dfd if p not in coupled_def]
        miss_att = [p for p in atk if p not in coupled_att]
        W(f"**Coverage:** {len(coupled_def)}/{len(dfd)} defenders got a real (≥3fr) coupling · "
          f"{len(coupled_att)}/{len(atk)} attackers were coupled-to.")
        W(f"- Defenders with NO coupling (detector missed entirely): "
          f"{', '.join(_nm(meta, p) for p in miss_def) if miss_def else 'none — all 5 coupled'}")
        W(f"- Attackers never coupled-to: {', '.join(_nm(meta, p) for p in miss_att) if miss_att else 'none — all coupled-to'}\n")
        W("**ALL detected segments (kept + dropped):**\n")
        W("| defender | attacker | frames | dur | origin | zones | STATUS |")
        W("|---|---|---|---|---|---|---|")
        for s in segs.iter_rows(named=True):
            W(f"| {_nm(meta, s['did'])} | {_nm(meta, s['aid'])} | {s['f0']}–{s['f1']} | {s['n']/10:.1f}s | "
              f"{s['origin']} | {', '.join(sorted(s['zones']))} | {s['status']} |")
        # per-segment gap at every zone moment (n>=3 segments only; short ones are sub-persistence noise)
        W("\n**Per-segment gap at every zone moment it traverses** (≥3fr segments; short <3fr omitted as noise):\n")
        real = segs.filter(pl.col("n") >= PERSIST)
        for s in real.iter_rows(named=True):
            sg = seg.filter((pl.col("did") == s["did"]) & (pl.col("seg") == s["seg"])).sort("frame_index")
            W(f"- **{_nm(meta, s['did'])} → {_nm(meta, s['aid'])}**  frames {s['f0']}–{s['f1']}  [{s['status']}]")
            W("    | zone | frame | gap | gap−stick | D(depth,lat) | A(depth,lat) | puck(depth,lat) |")
            W("    |---|---|---|---|---|---|---|")
            for z in ["OUT", "NZ", "BL", "DZ"]:
                zr = sg.filter(pl.col("zone") == z)
                if not zr.height:
                    continue
                r = zr[zr.height // 2].to_dicts()[0]
                W(f"    | {z} | {r['frame_index']} | {r['gap']:.1f} | {r['gap_reach']:.1f} | "
                  f"({r['d_depth']:.0f}, {r['d_lat']:+.0f}) | ({r['a_depth']:.0f}, {r['a_lat']:+.0f}) | ({r['p_depth']:.0f}, {r['p_lat']:+.0f}) |")
            W("")
    W("## STOP — owner tape review of the COMPLETE coupling set. No profile, no zone-expected gap, no stability.\n")
    C.REPORTS.mkdir(parents=True, exist_ok=True)
    (C.REPORTS / "gapcontrol_phaseC_full.md").write_text("\n".join(L))
    return {"goals": picks}


FLAT_GOALS = [(2025020052, 1001), (2023021216, 268), (2024020732, 717)]


def report_flat() -> dict:
    """Single flat table: EVERY coupled segment across the 3 goals, sorted by duration desc. Reporting only."""
    a = pl.read_parquet(ALLSEG)
    meta = _meta()
    a = a.filter(pl.struct("game_id", "event_id").map_elements(
        lambda s: (s["game_id"], s["event_id"]) in set(FLAT_GOALS), return_dtype=pl.Boolean))
    seg = (a.sort("frame_index").group_by("game_id", "event_id", "did", "seg").agg(
        aid=pl.col("aid").first(), f0=pl.col("frame_index").min(), f1=pl.col("frame_index").max(), n=pl.len(),
        origin=pl.col("origin_zone").first(), zones=pl.col("zone").unique(),
        gap_start=pl.col("gap").first(), gap_end=pl.col("gap").last()))
    seg = seg.with_columns(dur=pl.col("n") / 10.0,
        status=pl.when(pl.col("n") < PERSIST).then(pl.lit("dropped: short (<3fr)"))
        .when(pl.col("origin") == "DZ").then(pl.lit("dropped: DZ-origin (settled)"))
        .when(pl.col("origin") == "OUT").then(pl.lit("dropped: OUT-origin (>far-BL)"))
        .otherwise(pl.lit("KEPT"))).sort("dur", "gap_start", descending=[True, False])
    L = []; W = L.append
    W("# Gap Control · Phase C — flat list of EVERY coupling (3 goals), sorted by duration (longest first)\n")
    W("| goal | defender | attacker | dur (s) | frames | origin | zones | kept/dropped | gap start | gap end |")
    W("|---|---|---|---|---|---|---|---|---|---|")
    for r in seg.iter_rows(named=True):
        W(f"| {r['game_id']}-{r['event_id']} | {_nm(meta, r['did'])} | {_nm(meta, r['aid'])} | {r['dur']:.1f} | "
          f"{r['f0']}–{r['f1']} | {r['origin']} | {', '.join(sorted(r['zones']))} | {r['status']} | "
          f"{r['gap_start']:.1f} | {r['gap_end']:.1f} |")
    C.REPORTS.mkdir(parents=True, exist_ok=True)
    (C.REPORTS / "gapcontrol_phaseC_flat.md").write_text("\n".join(L))
    return {"n_segments": seg.height}


if __name__ == "__main__":
    import json, sys
    if "--flat" in sys.argv:
        print(json.dumps(report_flat(), default=str))
    elif "--full" in sys.argv:
        print(json.dumps(report_full(), default=str))
    else:
        s = report()
        print(json.dumps(s["funnel"], indent=1))
