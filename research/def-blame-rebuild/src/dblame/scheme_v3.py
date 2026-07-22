"""Behavioral Scheme Detection v3 — the five behavioral detectors, per-detector nulls, three-outcome per-segment
confidence, and the play PHASE-SEQUENCE (switch). Thresholds for FIRING are null-calibrated (z vs each detector's
own null — data-derived, not a hand-set score cutoff); the structural hockey definitions are the owner-ruled
type-A calls. §7 GUARDRAIL: descriptive, confidence-flagged ONLY — never a blame input. Goals-only aggregate
caveat: behavior FREQUENCIES are failure-conditioned. STOP at the report.
"""
from __future__ import annotations

import numpy as np
import polars as pl

from . import config as C
from .data import universe
from .scheme_match import SETTLE_DWELL, SETTLE_REVERSAL, DZONE_MAX, DZONE_MIN, WIN, SEASON_FILES
from .scheme_v3_confirm import _segments, MOVE, FT_DEPTH, FT_LAT

# owner-ruled structural (type-A) definitions
FOLLOW_COS, FOLLOW_GAP, STAY_DISP = 0.6, 6.0, 8.0
NET = np.array([0.0, 5.0]); NET_D = 8.0          # net-front + "at the net" distance
OVERLOAD_N, OVERLOAD_DEPTH = 3, 20.0
SWARM_PUCK_D = 12.0
NULLK = 4
DETS = ["man", "zone", "five_tight", "swarm", "box1"]
INZONE = 66.0        # in-zone = inside offensive blue line (~64ft) + 2ft straddle/noise buffer (owner-ruled)
EXC = 5              # a skater may leave the zone for <=5 frames (~0.5s) without ending the settled window


def _settled_start(allin, exc=EXC):
    """Owner-ruled settled window: the clock STARTS when the LAST skater enters the zone and must HOLD to the
    goal. Returns the earliest index of the excursion-tolerant (<=exc-frame gaps) all-in tail ending at the last
    frame, or None if no such tail reaches the goal (goal not settled at the shot -> drop)."""
    start = None; run = 0
    for t in range(len(allin) - 1, -1, -1):
        if allin[t]:
            start = t; run = 0
        else:
            run += 1
            if run > exc:
                break
    return start


def _man_zone(P, Dp, Ap, rng, null=False, perm=None):
    n = len(P); followed = handed = moving = 0
    for a in range(5):
        aL, aD = Ap[:, a, 0], Ap[:, a, 1]
        if (aL.max() - aL.min()) < MOVE and (aD.max() - aD.min()) < MOVE:
            continue
        moving += 1
        d0 = int(np.argmin(np.hypot(Dp[0, :, 0] - aL[0], Dp[0, :, 1] - aD[0]))) if not null else int(perm[a])
        dda = np.array([aL[-1] - aL[0], aD[-1] - aD[0]]); ddd = np.array([Dp[-1, d0, 0] - Dp[0, d0, 0], Dp[-1, d0, 1] - Dp[0, d0, 1]])
        cos = float(np.dot(dda, ddd) / (np.linalg.norm(dda) * np.linalg.norm(ddd) + 1e-9))
        gap = float(np.mean(np.hypot(Dp[:, d0, 0] - aL, Dp[:, d0, 1] - aD)))
        if cos >= FOLLOW_COS and gap <= FOLLOW_GAP:
            followed += 1; continue
        dend = int(np.argmin(np.hypot(Dp[-1, :, 0] - aL[-1], Dp[-1, :, 1] - aD[-1])))
        if np.linalg.norm(ddd) <= STAY_DISP and dend != d0:
            handed += 1
    man = (followed / moving) if (moving and followed >= 3) else 0.0
    zone = (handed / moving) if moving else 0.0
    return man, zone, moving


def _zone_detect(P, Dp, Ap, rng, K):
    """ZONE = MATCHED complement of man, with a FAIR null. Per moving attacker: his INITIAL-NEAREST defender
    (real geometry, NOT random) STAYS (displacement <= STAY_DISP) AND a DIFFERENT defender genuinely picks him up
    (within FOLLOW_GAP of his end position). Real fires = #(stay & real-pickup)/moving.
    FAIR NULL (attacker-shuffle): hold the stay-count constant (same stay-passing attackers, same defender
    configuration), but test the pickup against a RANDOM OTHER attacker's end position — does a defender cover
    THIS attacker's destination more than a random attacker's? If yes, the pickup is coverage structure, not
    incidental defender density. Zone CAN clear this null if the stay+specific-pickup pattern is real."""
    fires = 0; moving = 0; nullf = np.zeros(K)
    for a in range(5):
        aL, aD = Ap[:, a, 0], Ap[:, a, 1]
        if (aL.max() - aL.min()) < MOVE and (aD.max() - aD.min()) < MOVE:
            continue
        moving += 1
        d0 = int(np.argmin(np.hypot(Dp[0, :, 0] - aL[0], Dp[0, :, 1] - aD[0])))
        if np.hypot(Dp[-1, d0, 0] - Dp[0, d0, 0], Dp[-1, d0, 1] - Dp[0, d0, 1]) > STAY_DISP:
            continue                                      # zone requires the initial-nearest to STAY
        others = [d for d in range(5) if d != d0]
        if np.hypot(Dp[-1, others, 0] - aL[-1], Dp[-1, others, 1] - aD[-1]).min() <= FOLLOW_GAP:
            fires += 1                                    # a different defender genuinely covers his destination
        pool = [b for b in range(5) if b != a]
        for k in range(K):
            ap = pool[int(rng.integers(0, len(pool)))]
            if np.hypot(Dp[-1, others, 0] - Ap[-1, ap, 0], Dp[-1, others, 1] - Ap[-1, ap, 1]).min() <= FOLLOW_GAP:
                nullf[k] += 1
    zone = (fires / moving) if moving else 0.0
    znull = list(nullf / moving) if moving else [0.0] * K
    return zone, znull, moving


def _five_tight(P, Dp, isd):
    m = (P[:, 1] < FT_DEPTH) & (np.abs(P[:, 0]) >= FT_LAT)
    if m.sum() < 3:
        return None
    strong = np.sign(P[m, 0])
    fire = []
    idx = np.where(m)[0]
    for j, i in enumerate(idx):
        ss = strong[j]
        cnt = int(np.sum((np.sign(Dp[i, :, 0]) == ss) & (Dp[i, :, 1] < OVERLOAD_DEPTH)))
        dnet = bool(np.any(isd & (np.hypot(Dp[i, :, 0] - NET[0], Dp[i, :, 1] - NET[1]) <= NET_D)))
        fire.append(cnt >= OVERLOAD_N and dnet)
    return float(np.mean(fire))


def _swarm(P, Dp, isd):
    m = P[:, 1] < 20
    if m.sum() < 5:
        return None
    idx = np.where(m)[0]; fire = []
    for i in idx:
        dp = np.hypot(Dp[i, :, 0] - P[i, 0], Dp[i, :, 1] - P[i, 1])
        bothD = int(np.sum(isd & (dp <= SWARM_PUCK_D))) >= 2
        netdist = np.hypot(Dp[i, :, 0] - NET[0], Dp[i, :, 1] - NET[1])
        fwd_net = bool(np.any(~isd & (netdist <= NET_D))); noD_net = not np.any(isd & (netdist <= NET_D))
        fire.append(bothD and fwd_net and noD_net)
    return float(np.mean(fire))


def _box1(P, Dp):
    n = len(P)
    if n < 10:
        return None
    mean_dp = np.array([np.mean(np.hypot(Dp[:, k, 0] - P[:, 0], Dp[:, k, 1] - P[:, 1])) for k in range(5)])
    roamer = int(np.argmin(mean_dp)); box = [k for k in range(5) if k != roamer]
    B = Dp[:, box, :]                                   # (n,4,2)
    resid = B - B.mean(axis=1, keepdims=True)           # remove common translation
    stds = []
    for i in range(4):
        for j in range(i + 1, 4):
            stds.append(np.std(np.hypot(resid[:, i, 0] - resid[:, j, 0], resid[:, i, 1] - resid[:, j, 1])))
    rigidity = 1.0 / (1.0 + float(np.mean(stds)))
    roam_gap = float(np.mean(mean_dp[box]) - mean_dp[roamer])   # roamer closer to puck
    return rigidity * (1.0 if roam_gap > 5 else 0.4)


def _z(real, nulls):
    nulls = np.asarray(nulls, float)
    return (real - nulls.mean()) / (nulls.std() + 1e-6) if len(nulls) else 0.0


def run() -> dict:
    import sys, time
    t0 = time.time()
    isd_set = set(pl.read_parquet(C.PARQUET / "player_side.parquet").filter(pl.col("pos") == "D")["player_id"].to_list())
    nm = {r["player_id"]: r["full_name"] for r in pl.read_parquet(C.PARQUET / "player_side.parquet").select("player_id", "full_name").iter_rows(named=True)}
    u = universe().select("game_id", "event_id", "season", "attack_sign", "scoring_team_id", "defending_team_id",
                          "home_goalie_id", "away_goalie_id", "goal_frame")
    rng = np.random.default_rng(20260714)
    seg_out = []; plays = []
    for season, fname in zip(C.SEASONS, SEASON_FILES):
        us = u.filter(pl.col("season") == season); gids = us["game_id"].unique().to_list()
        fr = (pl.read_parquet(C.GT_FRAMES_DIR / fname, columns=["game_id", "event_id", "frame_index", "is_puck", "player_id", "team_id", "x_std", "y_std"])
              .filter(pl.col("game_id").is_in(gids)).join(us, on=["game_id", "event_id"], how="inner")
              .filter((pl.col("frame_index") <= pl.col("goal_frame")) & (pl.col("frame_index") >= pl.col("goal_frame") - WIN))
              .with_columns(D=89.0 - pl.col("attack_sign") * pl.col("x_std"), Lp=pl.col("attack_sign") * pl.col("y_std")))
        goalie = (pl.col("player_id") == pl.col("home_goalie_id")) | (pl.col("player_id") == pl.col("away_goalie_id"))
        puck = fr.filter(pl.col("is_puck")).select("game_id", "event_id", "frame_index", pL="Lp", pD="D")
        dff = fr.filter(~pl.col("is_puck") & ~goalie & (pl.col("team_id") == pl.col("defending_team_id"))).select("game_id", "event_id", "frame_index", "player_id", sL="Lp", sD="D")
        atk = fr.filter(~pl.col("is_puck") & ~goalie & (pl.col("team_id") == pl.col("scoring_team_id"))).select("game_id", "event_id", "frame_index", "player_id", sL="Lp", sD="D")
        # per-frame skater aggregate (max depth + count) — cheap all-10-in-zone gate WITHOUT the costly per-player pivot
        skall = (pl.concat([dff, atk]).group_by(["game_id", "event_id", "frame_index"])
                 .agg(maxD=pl.col("sD").max(), n=pl.len()))
        pdict = {k: v for k, v in puck.group_by(["game_id", "event_id"], maintain_order=True)}
        ddict = {k: v for k, v in dff.group_by(["game_id", "event_id"], maintain_order=True)}
        akdict = {k: v for k, v in atk.group_by(["game_id", "event_id"], maintain_order=True)}
        skdict = {k: v for k, v in skall.group_by(["game_id", "event_id"], maintain_order=True)}
        for key, pk in pdict.items():
            pk = pk.sort("frame_index")
            frames = pk["frame_index"].to_numpy(); pD = pk["pD"].to_numpy(); pL = pk["pL"].to_numpy()
            fin = np.isfinite(pD) & np.isfinite(pL)
            if fin.sum() < 20 or key not in ddict or key not in akdict:
                continue
            frames = frames[fin]; pD = pD[fin]; pL = pL[fin]
            # cheap NECESSARY dwell pre-filter (trimmed window is a SUBSET, so full window must also clear it):
            if (pD < 60).sum() < SETTLE_DWELL or key not in skdict:
                continue
            # SETTLED (owner-ruled): all 10 skaters inside the offensive blue line (depth<=INZONE). Cheap gate via
            # the groupby aggregate (NO pivot): per frame all skaters present (n>=10) AND max depth<=INZONE. Window
            # STARTS when the last skater enters and holds to the goal (<=EXC-frame excursions tolerated).
            sg = skdict[key]
            pos = {int(f): i for i, f in enumerate(frames)}
            allin = np.zeros(len(frames), bool)
            for f, mx, nn in zip(sg["frame_index"].to_numpy(), sg["maxD"].to_numpy(), sg["n"].to_numpy()):
                i = pos.get(int(f))
                if i is not None and nn >= 10 and mx <= INZONE:
                    allin[i] = True
            s_start = _settled_start(allin, EXC)
            if s_start is None:
                continue
            sl = slice(s_start, len(frames))
            frames = frames[sl]; pD = pD[sl]; pL = pL[sl]
            if pD.size < 20 or not (np.nanmax(pD) <= DZONE_MAX and np.nanmin(pD) >= DZONE_MIN):
                continue                                  # puck stays in zone across the (trimmed) settled window
            if not ((pD < 60).sum() >= SETTLE_DWELL and (pD[np.argmin(pD):].max() - pD.min()) >= SETTLE_REVERSAL):
                continue                                  # dwell + cycle-back re-checked on the TRIMMED window
            fmap = {int(f): i for i, f in enumerate(frames)}  # pivot ONLY the survivors, onto the trimmed frames

            def pivot(tbl, need_isd=False):
                pids = tbl["player_id"].unique().to_list()[:5]
                arr = np.full((len(frames), 5, 2), np.nan)
                for ci, pid in enumerate(pids):
                    sub = tbl.filter(pl.col("player_id") == pid)
                    for r in sub.iter_rows(named=True):
                        i = fmap.get(int(r["frame_index"]))
                        if i is not None:
                            arr[i, ci, 0] = r["sL"]; arr[i, ci, 1] = r["sD"]
                isd = np.array([pid in isd_set for pid in pids]) if need_isd else None
                return arr, pids, isd
            Dp_all, dpids, isd = pivot(ddict[key], True)
            Ap_all, _, _ = pivot(akdict[key])
            if len(dpids) < 5 or Ap_all.shape[1] < 5 or len(isd) < 5:
                continue
            good = np.isfinite(Dp_all).all(axis=(1, 2)) & np.isfinite(Ap_all).all(axis=(1, 2))
            segs = _segments(pD)
            recs = []
            for s0, s1, ph in segs:
                rec = {"ph": ph, "scores": {}, "nulls": {}, "g": key[0], "e": key[1], "verdict": "NO-CLEAR"}
                recs.append(rec)
                gsl = good[s0:s1]
                if gsl.sum() < 10:
                    continue
                P = np.column_stack([pL[s0:s1], pD[s0:s1]])[gsl]
                Dp = Dp_all[s0:s1][gsl]; Ap = Ap_all[s0:s1][gsl]
                scores, nulls = rec["scores"], rec["nulls"]
                man, _, moving = _man_zone(P, Dp, Ap, rng)          # MAN — UNCHANGED (≥3-shadow gate kept as-is)
                if moving:
                    nm_man = [_man_zone(P, Dp, Ap, rng, null=True, perm=rng.integers(0, 5, 5))[0] for _ in range(NULLK)]
                    scores["man"] = man; nulls["man"] = nm_man
                zone, znull, zmov = _zone_detect(P, Dp, Ap, rng, NULLK)   # ZONE — fixed fair null
                if zmov:
                    scores["zone"] = zone; nulls["zone"] = znull
                for dname, fn in (("five_tight", _five_tight), ("swarm", _swarm)):
                    real = fn(P, Dp, isd)
                    if real is not None:
                        scores[dname] = real
                        nulls[dname] = [fn(P[rng.permutation(len(P))], Dp, isd) or 0.0 for _ in range(NULLK)]
                b = _box1(P, Dp)
                if b is not None:
                    scores["box1"] = b
                    nulls["box1"] = [(_box1(P, Dp[rng.permutation(len(P))]) or 0.0) for _ in range(NULLK)]
            plays.append({"g": key[0], "e": key[1], "recs": recs})
            seg_out.extend(recs)
        print(f"[v3] {season} {time.time()-t0:.0f}s segs={len(seg_out)}", file=sys.stderr)
    return _finalize(seg_out, plays)


def _finalize(seg_out, plays) -> dict:
    """Pooled-null thresholding: derive each detector's fire threshold from the p95 of its OWN pooled null
    (data-derived, not hand-set), then fire per segment against it. Dominant = firing detector with largest
    null-normalized excess. Three-outcome: CONFIDENT (one clear winner) / AMBIGUOUS (≥2 comparable) / NO-CLEAR."""
    # pool nulls per detector -> threshold T (p95) and normalizing spread
    T, MED, SPREAD = {}, {}, {}
    for d in DETS:
        pool = np.array([v for s in seg_out for v in s["nulls"].get(d, [])], float)
        pool = pool[np.isfinite(pool)]
        T[d] = float(np.percentile(pool, 95)) if len(pool) else 1e9
        MED[d] = float(np.percentile(pool, 50)) if len(pool) else 0.0
        SPREAD[d] = max(T[d] - MED[d], 0.05)
    # per-segment verdict
    for s in seg_out:
        fired = {d: (s["scores"][d] - T[d]) / SPREAD[d] for d in s["scores"] if s["scores"][d] > T[d]}
        if not fired:
            s["verdict"] = "NO-CLEAR"; s["exc"] = {}; continue
        s["exc"] = {d: round(v, 2) for d, v in fired.items()}
        order = sorted(fired.items(), key=lambda x: -x[1])
        top, te = order[0]; re = order[1][1] if len(order) > 1 else -9
        # CONFIDENT if sole firer OR dominant excess beats runner-up by >=50% (relative), else AMBIGUOUS
        s["verdict"] = top if (len(order) == 1 or (te - re) >= 0.5 * abs(te)) else "AMBIGUOUS"
        s["top"] = top; s["te"] = round(float(te), 2)
    for p in plays:
        p["seq"] = [(r["ph"], r["verdict"]) for r in p["recs"]]
    return _report(seg_out, plays, T, MED)


def _report(seg_out, plays, T, MED) -> dict:
    from collections import Counter
    L = []; W = L.append
    n = len(seg_out)
    behav = Counter(s["verdict"] for s in seg_out)
    W("# Behavioral Scheme Detection v3 — five detectors, per-detector nulls, phase-sequence switches (§7: DESCRIPTIVE only)\n")
    W("**SETTLED (tightened, owner-ruled 2026-07-18):** a play is settled only once ALL 10 skaters are inside the "
      "offensive blue line (depth≤66ft); the window STARTS when the last skater enters and holds to the goal "
      "(≤5-frame excursions tolerated), then puck dwell≥25 + cycle-back≥12ft are re-checked on that trimmed "
      "window. Entry/rush frames where players are still streaming in are dropped.\n")
    W(f"Segments scored: **{n:,}** over {len(plays):,} settled plays. Firing is NULL-CALIBRATED against each "
      "detector's OWN pooled null (identity-shuffle for man/zone, puck/time-shuffle for the configurational three): "
      "the fire threshold is the p95 of the pooled null — DATA-DERIVED, not a hand-set score. A segment's behavior "
      "is the firing detector with the largest null-normalized excess; CONFIDENT = one clear winner, AMBIGUOUS = ≥2 "
      "comparable, NO-CLEAR = none beats its null. **GOALS-ONLY CAVEAT: behavior FREQUENCIES are failure-conditioned "
      "(e.g. swarm may over-appear); per-segment detection is descriptive.**\n")
    W("**GUARDRAIL: descriptive, confidence-flagged, human-checkable. NEVER an automated blame input.**\n")
    W("## Per-segment outcome distribution\n")
    for k in DETS + ["AMBIGUOUS", "NO-CLEAR"]:
        W(f"- {k}: {behav.get(k,0):,} ({behav.get(k,0)/max(n,1)*100:.0f}%)")
    W("\n## Per-detector — real-vs-null margin (over enabling segments) and confident-fire rate\n")
    W("mean-real = mean detector score where enabling; null p50 / p95 = pooled-null median / fire threshold; "
      "fire = confident-fire count (this detector won the segment).\n")
    W("| detector | enabling segs | mean-real | null p50 | null p95 (thresh) | mean-real − thresh | confident-fire |")
    W("|---|---|---|---|---|---|---|")
    for d in DETS:
        rv = np.array([s["scores"][d] for s in seg_out if d in s["scores"]], float)
        mr = float(rv.mean()) if len(rv) else 0.0
        W(f"| {d} | {len(rv):,} | {mr:.3f} | {MED[d]:.3f} | {T[d]:.3f} | {mr-T[d]:+.3f} | {behav.get(d,0):,} |")
    W("\n## SWITCH patterns — common HIGH→LOW behavior sequences (does 'man/box high → five-tight/swarm low' emerge?)\n")
    sw = Counter()
    for p in plays:
        hs = [b for ph, b in p["seq"] if ph == "HIGH" and b in DETS]
        ls = [b for ph, b in p["seq"] if ph == "LOW" and b in DETS]
        if hs and ls:
            sw[(hs[0], ls[0])] += 1
    W(f"Plays with a confident HIGH behavior AND a confident LOW behavior: **{sum(sw.values()):,}**.\n")
    for (h, l), c in sw.most_common(12):
        W(f"- HIGH:{h} → LOW:{l} — {c:,}")
    W("\n## Example plays (8–10) for owner TAPE review — phase sequence + per-detector excess-over-null (×null-spread)\n")
    exp = [p for p in plays if any(v in DETS for _, v in p["seq"])]
    # prefer variety: some switches, some single-behavior
    picked = [p for p in exp if len({v for _, v in p["seq"] if v in DETS}) > 1][:5] + \
             [p for p in exp if len({v for _, v in p["seq"] if v in DETS}) == 1][:5]
    for p in picked[:10]:
        parts = []
        for r in p["recs"]:
            tag = r["verdict"]
            if r.get("exc"):
                tag += "{" + ",".join(f"{k}:{v}" for k, v in sorted(r["exc"].items(), key=lambda x: -x[1])) + "}"
            parts.append(f"{r['ph']}:{tag}")
        W(f"- **{p['g']}-{p['e']}**: " + " → ".join(parts))
    W("\n## TAPE — FIVE-TIGHT confident fires (the one detector clearing chance; game-event, phase, excess×null-spread)\n")
    ft = [s for s in seg_out if s["verdict"] == "five_tight"]
    for s in ft[:12]:
        W(f"- {s['g']}-{s['e']} [{s['ph']}] excess={s.get('te','?')}")
    W(f"\n(total five-tight confident fires: {len(ft):,})\n")
    W("\n## TAPE — 'STRUCTURED HIGH → COLLAPSE LOW' switch plays (box1 HIGH → five_tight/swarm LOW) for owner eyes\n")
    bc = []
    for p in plays:
        hs = [b for ph, b in p["seq"] if ph == "HIGH" and b in DETS]
        ls = [b for ph, b in p["seq"] if ph == "LOW" and b in DETS]
        if hs and ls and hs[0] == "box1" and ls[0] in ("five_tight", "swarm"):
            bc.append(p)
    for p in bc[:20]:
        seqstr = " → ".join(f"{ph}:{b}" for ph, b in p["seq"] if b in DETS)
        W(f"- {p['g']}-{p['e']}: {seqstr}")
    W(f"\n(total box→collapse switch plays: {len(bc):,})\n")
    W("\n## TAPE — NO-CLEAR plays (settled, but NO segment beat any detector's null) for owner eyes\n")
    nc = [p for p in plays if p["seq"] and all(v not in DETS for _, v in p["seq"])]
    for p in nc[:15]:
        seqstr = " → ".join(f"{ph}:{b}" for ph, b in p["seq"])
        W(f"- {p['g']}-{p['e']}: {seqstr}")
    W(f"\n(total all-NO-CLEAR settled plays: {len(nc):,} of {len(plays):,})\n")
    W("\n## STOP — behavioral scheme read for owner tape review. No aggregation past the gate, no grade, no blame.\n")
    C.REPORTS.mkdir(parents=True, exist_ok=True)
    (C.REPORTS / "scheme_v3.md").write_text("\n".join(L))
    return {"segments": n, "plays": len(plays), "outcomes": dict(behav),
            "thresholds": {d: round(T[d], 3) for d in DETS},
            "switch_top": [f"{h}->{l}:{c}" for (h, l), c in sw.most_common(6)]}


if __name__ == "__main__":
    import json
    print(json.dumps(run(), indent=1, default=str))
