"""Behavioral Scheme Detection v3 §8 — READ-ONLY confirm: phase-segmentation stats + enabling-situation exposure.
Before building the behavioral detectors, check that each detector's REQUIRED situation even occurs often enough
to be viable (v2 lesson: no fire without the enabling situation). No detectors, no nulls, no scores — only:
(1) phase segmentation with the owner-ruled 15/25-ft hysteresis dead-band; (2) how many segments contain each
detector's enabling situation (attacker-movement for man/zone; low-corner puck for five-tight; low puck for
swarm; a sustained 5-defender segment for box+1). STOP.
"""
from __future__ import annotations

import numpy as np
import polars as pl

from . import config as C
from .data import universe
from .scheme_match import SETTLE_DWELL, SETTLE_REVERSAL, DZONE_MAX, DZONE_MIN, WIN, SEASON_FILES

HIGH_ENTER, LOW_ENTER, MINSEG = 25.0, 15.0, 10   # owner-ruled hysteresis + min segment length
MOVE = 15.0                                       # attacker "crosses" (man/zone enable)
FT_DEPTH, FT_LAT = 15.0, 15.0                     # five-tight enable: puck low + to a side


def _segments(depth):
    """hysteresis phase segments (HIGH>=25 enter, LOW<15 enter, hold between); merge <MINSEG into previous."""
    cur = "HIGH" if depth[0] >= 20 else "LOW"; segs = []; start = 0
    for i, d in enumerate(depth):
        nxt = "HIGH" if (cur == "LOW" and d >= HIGH_ENTER) else ("LOW" if (cur == "HIGH" and d < LOW_ENTER) else cur)
        if nxt != cur:
            segs.append([start, i, cur]); start = i; cur = nxt
    segs.append([start, len(depth), cur])
    merged = []
    for s in segs:
        if s[1] - s[0] < MINSEG and merged:
            merged[-1][1] = s[1]                  # absorb short flicker into previous
        else:
            merged.append(s)
    if len(merged) >= 2 and merged[0][1] - merged[0][0] < MINSEG:
        merged[1][0] = merged[0][0]; merged.pop(0)
    return merged


def run() -> dict:
    u = universe().select("game_id", "event_id", "season", "attack_sign", "scoring_team_id", "defending_team_id",
                          "home_goalie_id", "away_goalie_id", "goal_frame")
    n_settled = 0
    seg_len, seg_phase = [], []; segs_per_goal = []
    en_move1, en_move3, en_ft, en_swarm, en_box = [], [], [], [], []   # per-segment enabling flags
    for season, fname in zip(C.SEASONS, SEASON_FILES):
        us = u.filter(pl.col("season") == season); gids = us["game_id"].unique().to_list()
        fr = (pl.read_parquet(C.GT_FRAMES_DIR / fname, columns=["game_id", "event_id", "frame_index", "is_puck", "player_id", "team_id", "x_std", "y_std"])
              .filter(pl.col("game_id").is_in(gids)).join(us, on=["game_id", "event_id"], how="inner")
              .filter((pl.col("frame_index") <= pl.col("goal_frame")) & (pl.col("frame_index") >= pl.col("goal_frame") - WIN))
              .with_columns(D=89.0 - pl.col("attack_sign") * pl.col("x_std"), Lp=pl.col("attack_sign") * pl.col("y_std")))
        goalie = (pl.col("player_id") == pl.col("home_goalie_id")) | (pl.col("player_id") == pl.col("away_goalie_id"))
        puck = fr.filter(pl.col("is_puck")).select("game_id", "event_id", "frame_index", pL="Lp", pD="D")
        att = fr.filter(~pl.col("is_puck") & ~goalie & (pl.col("team_id") == pl.col("scoring_team_id"))).select(
            "game_id", "event_id", "frame_index", "player_id", aL="Lp", aD="D")
        dfn = fr.filter(~pl.col("is_puck") & ~goalie & (pl.col("team_id") == pl.col("defending_team_id"))).select(
            "game_id", "event_id", "frame_index", dpid="player_id")
        pdict = {k: v for k, v in puck.group_by(["game_id", "event_id"], maintain_order=True)}
        adict = {k: v for k, v in att.group_by(["game_id", "event_id"], maintain_order=True)}
        ndef = {k: v for k, v in dfn.group_by(["game_id", "event_id"], maintain_order=True)}
        for key, pk in pdict.items():
            pk = pk.sort("frame_index")
            frames = pk["frame_index"].to_numpy(); pD = pk["pD"].to_numpy(); pL = pk["pL"].to_numpy()
            fin = np.isfinite(pD) & np.isfinite(pL)
            if fin.sum() < 20 or not (np.nanmax(pD) <= DZONE_MAX and np.nanmin(pD) >= DZONE_MIN):
                continue
            pDf = pD[fin]
            if not ((pDf < 60).sum() >= SETTLE_DWELL and (pDf[np.argmin(pDf):].max() - pDf.min()) >= SETTLE_REVERSAL):
                continue
            n_settled += 1
            frames, pD, pL = frames[fin], pD[fin], pL[fin]
            segs = _segments(pD)
            segs_per_goal.append(len(segs))
            # attacker positions aligned to puck frames
            amove = None
            if key in adict:
                ak = adict[key]; fmap = {f: i for i, f in enumerate(frames)}
                apos = {}
                for r in ak.iter_rows(named=True):
                    i = fmap.get(r["frame_index"])
                    if i is not None and np.isfinite(r["aL"]) and np.isfinite(r["aD"]):
                        apos.setdefault(r["player_id"], []).append((i, r["aL"], r["aD"]))
                amove = apos
            # defender count per frame position
            dcount = np.zeros(len(frames))
            if key in ndef:
                dk = ndef[key]; fmap = {f: i for i, f in enumerate(frames)}
                cnt = dk.group_by("frame_index").agg(n=pl.col("dpid").n_unique())
                for r in cnt.iter_rows(named=True):
                    i = fmap.get(r["frame_index"])
                    if i is not None:
                        dcount[i] = r["n"]
            for s0, s1, ph in segs:
                seg_len.append((s1 - s0) / 10.0); seg_phase.append(ph)
                # man/zone enable: attackers moving >=15ft within this segment
                nmove = 0
                if amove:
                    for pid, pts in amove.items():
                        seg_pts = [(i, l, d) for (i, l, d) in pts if s0 <= i < s1]
                        if len(seg_pts) >= 5:
                            ls = np.array([p[1] for p in seg_pts]); ds = np.array([p[2] for p in seg_pts])
                            if (ls.max() - ls.min()) >= MOVE or (ds.max() - ds.min()) >= MOVE:
                                nmove += 1
                en_move1.append(nmove >= 1); en_move3.append(nmove >= 3)
                # five-tight enable: LOW puck in a corner (depth<15 & |lat|>=15) somewhere in the segment
                sd = pD[s0:s1]; sl = pL[s0:s1]
                en_ft.append(bool(np.any((sd < FT_DEPTH) & (np.abs(sl) >= FT_LAT))))
                # swarm enable: LOW-phase segment (puck low)
                en_swarm.append(ph == "LOW")
                # box enable: sustained segment with 5 defenders present most frames
                en_box.append((s1 - s0) >= MINSEG and np.mean(dcount[s0:s1] >= 5) > 0.5)
        # (progress omitted)
    seg_len = np.array(seg_len); nseg = len(seg_len)
    hi = np.mean(np.array(seg_phase) == "HIGH")
    L = []; W = L.append
    W("# Behavioral Scheme Detection v3 §8 — read-only confirm (phase segmentation + enabling-situation exposure)\n")
    W(f"Settled goals: **{n_settled:,}**. Hysteresis phases (HIGH≥25 / LOW<15, hold between), min segment "
      f"{MINSEG/10:.1f}s. **No detectors fired — enabling-situation exposure only.**\n")
    W("## Phase segmentation\n")
    W(f"- total segments: **{nseg:,}** · segments/goal: mean {np.mean(segs_per_goal):.1f}, "
      f"median {int(np.median(segs_per_goal))}, p90 {int(np.percentile(segs_per_goal,90))}")
    W(f"- HIGH {hi*100:.0f}% / LOW {(1-hi)*100:.0f}% of segments · segment length (s): median {np.median(seg_len):.1f}, "
      f"p25 {np.percentile(seg_len,25):.1f}, p75 {np.percentile(seg_len,75):.1f}")
    W("\n## Enabling-situation exposure per detector (fraction of segments that CONTAIN the required situation)\n")
    W("| detector | enabling situation | % of segments | viable? |")
    W("|---|---|---|---|")
    rows = [("MAN", "≥1 attacker moves ≥15ft", np.mean(en_move1)),
            ("MAN (≥3 shadows)", "≥3 attackers move ≥15ft", np.mean(en_move3)),
            ("ZONE", "≥1 attacker moves ≥15ft (same as man)", np.mean(en_move1)),
            ("FIVE-TIGHT", "low-corner puck (depth<15 & |lat|≥15)", np.mean(en_ft)),
            ("SWARM", "LOW-phase (puck low)", np.mean(en_swarm)),
            ("BOX+1", "sustained ≥1s seg, 5 defenders", np.mean(en_box))]
    for nm, sit, fr_ in rows:
        W(f"| {nm} | {sit} | **{fr_*100:.0f}%** | {'yes' if fr_ > 0.10 else 'THIN'} |")
    W("\n## Read\n- A detector whose enabling situation is rare (<~10% of segments) is largely dead on arrival — "
      "it can only fire on the few segments that contain its situation. This sizes viability BEFORE building. "
      "MAN's ≥3-simultaneous-shadow requirement (issue #4) is the tightest enabling gate; watch it.")
    W("\n## STOP — read-only confirm. No detectors, no nulls, no scores.\n")
    C.REPORTS.mkdir(parents=True, exist_ok=True)
    (C.REPORTS / "scheme_v3_confirm.md").write_text("\n".join(L))
    return {"n_settled": n_settled, "n_segments": nseg, "high_frac": round(float(hi), 3),
            "seg_per_goal_med": int(np.median(segs_per_goal)) if segs_per_goal else 0,
            "enable": {"man_move1": round(float(np.mean(en_move1)), 3), "man_move3": round(float(np.mean(en_move3)), 3),
                       "five_tight": round(float(np.mean(en_ft)), 3), "swarm_low": round(float(np.mean(en_swarm)), 3),
                       "box": round(float(np.mean(en_box)), 3)}}


if __name__ == "__main__":
    import json
    print(json.dumps(run(), indent=1, default=str))
