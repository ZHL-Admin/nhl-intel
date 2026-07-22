"""Puck-Path Projector RE-POSE (F36 follow-up) — target = DESTINATION (where the play RESOLVES), not next-position.
Since the corpus is goals-only, every play resolves in the scoring SHOT, so DESTINATION = the shot-origin region
(puck position at the release frame). Question: does the puck-STATE predict WHERE THE PLAY RESOLVES (shot origin)
better than knowing the zone, and is it concentrated? All F36 discipline kept: leave-one-goal-out, distinct-goal
collapse (trivial here — one shot-origin per goal), mode/entropy sharpness, position-only AND same-zone-marginal
nulls. Horizon is a time-to-shot cap H (sweep 2/3/4s — destination-reaching, NOT the 0.5s trivial horizon),
tuned by DESTINATION predictive skill. Funnel guard: near_net excluded. PRE-REGISTERED bar (locked before run):
top-2 destinations ≥60% AND conditioned entropy ≤0.7× same-zone-marginal DESTINATION entropy AND held-out
destination-skill beats BOTH nulls. STOP at the gate.
"""
from __future__ import annotations

import numpy as np
import polars as pl

from . import config as C
from .data import universe
from .puckproj import _region, STATES, RNAMES, FUNNEL, DECISION, _entropy, _logp, SEASON_FILES, FLOOR, WIN


def _load():
    u = universe().select("game_id", "event_id", "season", "attack_sign", "goal_frame")
    parts = []
    for season, fname in zip(C.SEASONS, SEASON_FILES):
        us = u.filter(pl.col("season") == season)
        gids = us["game_id"].unique().to_list()
        pk = (pl.read_parquet(C.GT_FRAMES_DIR / fname, columns=["game_id", "event_id", "frame_index", "is_puck", "x_std", "y_std"])
              .filter(pl.col("is_puck") & pl.col("game_id").is_in(gids)).join(us, on=["game_id", "event_id"], how="inner")
              .filter((pl.col("frame_index") <= pl.col("goal_frame")) & (pl.col("frame_index") >= pl.col("goal_frame") - WIN))
              .with_columns(x=pl.col("attack_sign") * pl.col("x_std"), y=pl.col("attack_sign") * pl.col("y_std"))
              .sort("game_id", "event_id", "frame_index"))
        ge = ["game_id", "event_id"]
        pk = pk.with_columns(**{f"v{w}x": (pl.col("x") - pl.col("x").shift(w).over(ge)) / (w / 10.0) for w in (2, 3, 5)},
                             **{f"v{w}y": (pl.col("y") - pl.col("y").shift(w).over(ge)) / (w / 10.0) for w in (2, 3, 5)},
                             tts=(pl.col("goal_frame") - pl.col("frame_index")) / 10.0)
        # shot origin = puck at the release (goal_frame)
        shot = pk.filter(pl.col("frame_index") == pl.col("goal_frame")).select("game_id", "event_id", sx="x", sy="y")
        pk = pk.join(shot, on=ge, how="left")
        parts.append(pk)
    d = pl.concat(parts).filter(pl.col("x").is_finite() & pl.col("y").is_finite())
    d = d.with_columns(dest=_region(pl.col("sx"), pl.col("sy")).fill_null(-1).cast(pl.Int64),
                       gid=pl.struct("game_id", "event_id").rank("dense"))
    return d


class Proj:
    def __init__(self, d):
        import time, sys
        t0 = time.time()
        self.x = d["x"].to_numpy(); self.y = d["y"].to_numpy(); self.gid = d["gid"].to_numpy().astype(np.int64)
        self.dest = d["dest"].to_numpy(); self.tts = d["tts"].to_numpy()
        self.v = {w: (d[f"v{w}x"].to_numpy(), d[f"v{w}y"].to_numpy()) for w in (2, 3, 5)}
        from scipy.spatial import cKDTree
        self.tree = cKDTree(np.column_stack([self.x, self.y]))
        names = list(STATES); pxs = np.array([STATES[s][0] for s in names]); pys = np.array([STATES[s][1] for s in names])
        d2 = (self.x[:, None] - pxs[None, :]) ** 2 + (self.y[:, None] - pys[None, :]) ** 2
        am = d2.argmin(axis=1); md = np.sqrt(d2[np.arange(len(self.x)), am])
        self.zone = np.where(md < 12.0, np.array(names)[am], "other")
        self.sph = {w: (np.hypot(*self.v[w]), np.degrees(np.arctan2(self.v[w][1], self.v[w][0]))) for w in (2, 3, 5)}
        print(f"[proj2] tree+zone {time.time()-t0:.0f}s, {len(self.x):,} frames", file=sys.stderr)

    def ball(self, px, py, rmax=8.0):
        cand = np.asarray(self.tree.query_ball_point([px, py], r=rmax), dtype=np.int64)
        return cand, (np.hypot(self.x[cand] - px, self.y[cand] - py) if len(cand) else np.zeros(0))

    def dest_dist(self, cand, dist, phead, w, radius, tol, H, exclude_gid=None, use_head=True):
        if len(cand) == 0:
            return np.zeros(9)
        sp, hd = self.sph[w]
        m = (dist <= radius) & (sp[cand] > FLOOR) & (self.tts[cand] <= H) & (self.dest[cand] >= 0)
        if use_head:
            m &= np.abs((hd[cand] - phead + 180) % 360 - 180) <= tol
        if exclude_gid is not None:
            m &= self.gid[cand] != exclude_gid
        cc = cand[m]
        if len(cc) == 0:
            return np.zeros(9)
        g = self.gid[cc]; de = self.dest[cc]
        _, first = np.unique(g, return_index=True)              # one shot-origin per matched goal
        return np.bincount(de[first].astype(np.int64), minlength=9).astype(float)


def run() -> dict:
    import sys, time
    t0 = time.time()
    d = _load()
    print(f"[proj2] load {time.time()-t0:.0f}s", file=sys.stderr)
    P = Proj(d)
    rng = np.random.default_rng(20260714)
    heldpool = {z: np.where(P.zone == z)[0] for z in STATES}

    # ---- tune window/tol/H by HELD-OUT DESTINATION skill (leave-one-goal-out), on the DECISION states ----
    qidx = np.concatenate([rng.choice(heldpool[z], size=min(120, len(heldpool[z])), replace=False) for z in DECISION])
    qballs = [(int(i), P.ball(P.x[i], P.y[i], 8.0)) for i in qidx]
    grid = [(w, 8, tol, H) for w in (2, 3, 5) for tol in (30, 45, 60) for H in (2.0, 3.0, 4.0)]
    best, bc = -1e9, None
    for (w, radius, tol, H) in grid:
        sp, hd = P.sph[w]; lls = []
        for i, (cand, dist) in qballs:
            if not (sp[i] > FLOOR and P.dest[i] >= 0 and P.tts[i] <= H):
                continue
            dd = P.dest_dist(cand, dist, hd[i], w, radius, tol, H, exclude_gid=P.gid[i], use_head=True)
            if dd.sum() < 3:
                continue
            lls.append(_logp(dd, int(P.dest[i])))
        m = float(np.mean(lls)) if lls else -1e9
        if m > best:
            best, bc = m, (w, radius, tol, H)
    w, radius, tol, H = bc
    sp, hd = P.sph[w]
    print(f"[proj2] tuned {time.time()-t0:.0f}s -> w={w} tol={tol} H={H} ll={best:.3f}", file=sys.stderr)

    # global marginal destination (goals overall) + per-zone marginal (moving frames in zone within H)
    gmarg = np.bincount(P.dest[(P.dest >= 0)][np.unique(P.gid[P.dest >= 0], return_index=True)[1]].astype(np.int64), minlength=9).astype(float)
    zmarg = {}
    for z in STATES:
        idx = heldpool[z]; idx = idx[(sp[idx] > FLOOR) & (P.dest[idx] >= 0) & (P.tts[idx] <= H)]
        g = P.gid[idx]; de = P.dest[idx]; _, first = np.unique(g, return_index=True)
        zmarg[z] = np.bincount(de[first].astype(np.int64), minlength=9).astype(float)

    rows = []
    for z, (px, py) in STATES.items():
        near = np.asarray(P.tree.query_ball_point([px, py], r=8.0), dtype=np.int64)
        near = near[(sp[near] > FLOOR) & (P.tts[near] <= H)]
        phead = float(np.median(hd[near])) if len(near) else 0.0
        ccand, cdist = P.ball(px, py, 8.0)
        cond = P.dest_dist(ccand, cdist, phead, w, radius, tol, H, use_head=True)
        pc = cond / cond.sum() if cond.sum() else cond
        order = np.argsort(pc)[::-1]; top2 = float(pc[order[:2]].sum())
        e_cond, e_zone = _entropy(cond), _entropy(zmarg[z])
        qz = rng.choice(heldpool[z], size=min(100 if z in FUNNEL else 250, len(heldpool[z])), replace=False)
        lc, lp, lz = [], [], []
        for i in qz:
            if not (sp[i] > FLOOR and P.dest[i] >= 0 and P.tts[i] <= H):
                continue
            r = int(P.dest[i]); cand, dist = P.ball(P.x[i], P.y[i], 8.0)
            c = P.dest_dist(cand, dist, hd[i], w, radius, tol, H, exclude_gid=P.gid[i], use_head=True)
            po = P.dest_dist(cand, dist, hd[i], w, radius, 999, H, exclude_gid=P.gid[i], use_head=False)
            if c.sum() < 3:
                continue
            lc.append(_logp(c, r)); lp.append(_logp(po, r)); lz.append(_logp(zmarg[z], r))
        sc, sp_, sz = float(np.mean(lc)), float(np.mean(lp)), float(np.mean(lz))
        modes = [(RNAMES[j], round(float(pc[j]), 3)) for j in order if pc[j] > 0.02][:6]
        clears = (top2 >= 0.60) and (e_cond <= 0.7 * e_zone) and (sc > sp_) and (sc > sz)
        rows.append({"state": z, "funnel": z in FUNNEL, "n_goals": int(cond.sum()), "top2": round(top2, 3),
                     "entropy_cond": round(e_cond, 2), "entropy_zone": round(e_zone, 2),
                     "entropy_ratio": round(e_cond / e_zone, 2) if e_zone else None,
                     "skill_cond": round(sc, 2), "skill_pos": round(sp_, 2), "skill_zone": round(sz, 2),
                     "beats_both": bool(sc > sp_ and sc > sz), "CLEARS": bool(clears), "modes": modes,
                     "zone_top": (RNAMES[int(np.argmax(zmarg[z]))], round(float(zmarg[z].max() / zmarg[z].sum()), 2))})

    L = []; W = L.append
    W("# Puck-Path Projector RE-POSE — DESTINATION (shot-origin) sharpness gate\n")
    W(f"Target = where the play RESOLVES = shot-origin region (goals-only → the scoring shot; §6 limit: 'reset/"
      f"cleared' plays aren't in the corpus). Knobs TUNED by held-out DESTINATION skill (leave-one-goal-out): "
      f"window **{w/10:.1f}s**, radius **{radius}ft**, heading **±{tol}°**, time-to-shot cap **H={H:.0f}s** "
      f"(best mean log-lik {best:.3f}).\n")
    W("**PRE-REGISTERED BAR (locked): top-2 destinations ≥60% AND conditioned entropy ≤0.7× same-zone-marginal "
      "destination entropy AND held-out destination-skill beats BOTH nulls. Funnel: near_net excluded.**\n")
    gm = gmarg / gmarg.sum()
    W(f"## Global shot-origin marginal (all goals): " + " · ".join(f"{RNAMES[j]} {gm[j]*100:.0f}%" for j in np.argsort(gm)[::-1] if gm[j] > 0.03) + "\n")
    for r in rows:
        tag = "  [FUNNEL — excluded]" if r["funnel"] else ""
        W(f"## {r['state']}{tag}\n")
        W("**Resolves to (share of matched distinct goals):** " + " · ".join(f"{n} **{p*100:.0f}%**" for n, p in r["modes"]))
        W(f"- top-2 destinations = **{r['top2']*100:.0f}%** (bar ≥60%) · matched goals {r['n_goals']:,}")
        W(f"- entropy: conditioned **{r['entropy_cond']}** vs same-zone-marginal {r['entropy_zone']} → ratio "
          f"**{r['entropy_ratio']}** (bar ≤0.70) · zone-marginal top destination: {r['zone_top'][0]} {r['zone_top'][1]*100:.0f}%")
        W(f"- held-out destination-skill: conditioned **{r['skill_cond']}** vs position-only {r['skill_pos']} vs "
          f"zone-marginal {r['skill_zone']} → beats both: **{r['beats_both']}**")
        W(f"- **CLEARS PRE-REGISTERED BAR: {'YES' if r['CLEARS'] else 'no'}**\n")
    dp = [r["state"] for r in rows if (not r["funnel"]) and r["CLEARS"]]
    W("## Verdict (funnel-guarded)\n")
    W(f"- Non-funnel decision states clearing the bar: **{dp if dp else 'NONE'}** of {DECISION}.")
    W("- Zone-marginal lopsidedness (is the destination zone-DETERMINED?): " +
      " · ".join(f"{r['state']} → {r['zone_top'][0]} {r['zone_top'][1]*100:.0f}%" for r in rows if not r["funnel"]))
    W("\n## STOP — destination sharpness gate for owner review. No defense-read, no grading.\n")
    C.REPORTS.mkdir(parents=True, exist_ok=True)
    (C.REPORTS / "puckproj2_gate.md").write_text("\n".join(L))
    return {"tuned": {"window_s": w / 10, "tol": tol, "H_s": H, "loglik": round(best, 3)}, "rows": rows, "decision_pass": dp}


if __name__ == "__main__":
    import json
    print(json.dumps(run(), indent=1, default=str))
