"""Puck-Path Projector — build + §5 SHARPNESS GATE. Enforces the §0e rules: knobs tuned by HELD-OUT PREDICTIVE
SKILL (leave-one-goal-out), DISTINCT-GOAL collapse, MODE-based continuation (destination regions) + ENTROPY
sharpness, and the controlled nulls (position-only AND same-zone-marginal). LOCKED bar per named decision-state:
top-2 modes ≥60% of matched distinct goals AND conditioned entropy ≤0.7× same-zone-marginal entropy AND held-out
skill beats BOTH nulls. Funnel guard: near_net excluded from any "it works" claim. STOP at the gate.
"""
from __future__ import annotations

import numpy as np
import polars as pl

from . import config as C
from .data import universe

WIN = 100
SEASON_FILES = ["frames_2023_24.parquet", "frames_2024_25.parquet", "frames_2025_26.parquet"]
FLOOR = 5.0
# destination REGIONS (normalized, scored-on net at +89). 9 interpretable modes.
RNAMES = ["OUT/back", "HIGH/point", "L-wall", "SLOT-high", "R-wall", "L-corner", "NET-FRONT", "R-corner", "BEHIND-net"]


def _region(xc, yc):
    return (pl.when(xc >= 89).then(8)
            .when(xc >= 76).then(pl.when(yc.abs() <= 11).then(6).when(yc > 11).then(7).otherwise(5))
            .when(xc >= 58).then(pl.when(yc.abs() <= 14).then(3).when(yc > 14).then(4).otherwise(2))
            .when(xc >= 40).then(1).otherwise(0))


# decision states (canonical position); heading is data-derived (median of moving pucks near the position)
STATES = {"blue_line_entry": (26.0, 12.0), "right_point": (36.0, 20.0), "half_wall_to_net": (55.0, 25.0),
          "below_goal_line": (94.0, 4.0), "near_net_slot": (82.0, 0.0)}
FUNNEL = {"near_net_slot"}
DECISION = [s for s in STATES if s not in FUNNEL]


def _zone(x, y):
    # same-zone-marginal null neighborhood = nearest canonical decision-state within 12 ft, else "other"
    best, bd = "other", 12.0
    for name, (px, py) in STATES.items():
        d = ((x - px) ** 2 + (y - py) ** 2) ** 0.5
        if d < bd:
            best, bd = name, d
    return best


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
        pk = pk.with_columns(
            **{f"v{w}x": (pl.col("x") - pl.col("x").shift(w).over(ge)) / (w / 10.0) for w in (2, 3, 5)},
            **{f"v{w}y": (pl.col("y") - pl.col("y").shift(w).over(ge)) / (w / 10.0) for w in (2, 3, 5)},
            fx5=pl.col("x").shift(-5).over(ge), fy5=pl.col("y").shift(-5).over(ge),
            fx10=pl.col("x").shift(-10).over(ge), fy10=pl.col("y").shift(-10).over(ge))
        parts.append(pk)
    d = pl.concat(parts).filter(pl.col("x").is_finite() & pl.col("y").is_finite())
    d = d.with_columns(r5=_region(pl.col("fx5"), pl.col("fy5")).fill_null(-1).cast(pl.Int64),
                       r10=_region(pl.col("fx10"), pl.col("fy10")).fill_null(-1).cast(pl.Int64),
                       gid=pl.struct("game_id", "event_id").rank("dense"))
    return d


class Proj:
    def __init__(self, d):
        self.x = d["x"].to_numpy(); self.y = d["y"].to_numpy(); self.gid = d["gid"].to_numpy().astype(np.int64)
        self.v = {w: (d[f"v{w}x"].to_numpy(), d[f"v{w}y"].to_numpy()) for w in (2, 3, 5)}
        self.r = {5: d["r5"].to_numpy(), 10: d["r10"].to_numpy()}
        import sys, time
        from scipy.spatial import cKDTree
        t0 = time.time()
        self.tree = cKDTree(np.column_stack([self.x, self.y]))
        # vectorized nearest-canonical zone assignment (12 ft) for the same-zone-marginal null
        names = list(STATES); pxs = np.array([STATES[s][0] for s in names]); pys = np.array([STATES[s][1] for s in names])
        d2 = (self.x[:, None] - pxs[None, :]) ** 2 + (self.y[:, None] - pys[None, :]) ** 2
        am = d2.argmin(axis=1); md = np.sqrt(d2[np.arange(len(self.x)), am])
        self.zone = np.where(md < 12.0, np.array(names)[am], "other")
        self.sph = {w: self.spdhead(w) for w in (2, 3, 5)}
        print(f"[proj] tree+zone {time.time()-t0:.0f}s, {len(self.x):,} frames", file=sys.stderr)

    def spdhead(self, w):
        vx, vy = self.v[w]
        return np.hypot(vx, vy), np.degrees(np.arctan2(vy, vx))

    def ball(self, px, py, rmax=10.0):
        cand = np.asarray(self.tree.query_ball_point([px, py], r=rmax), dtype=np.int64)
        if len(cand) == 0:
            return cand, np.zeros(0)
        return cand, np.hypot(self.x[cand] - px, self.y[cand] - py)

    def score(self, cand, dist, phead, w, radius, tol, H, exclude_gid=None, use_head=True):
        if len(cand) == 0:
            return np.zeros(9)
        sp, hd = self.sph[w]
        m = (dist <= radius) & (sp[cand] > FLOOR)
        if use_head:
            m &= np.abs((hd[cand] - phead + 180) % 360 - 180) <= tol
        if exclude_gid is not None:
            m &= self.gid[cand] != exclude_gid
        return self._collapse(cand[m], dist[m], H)

    def _collapse(self, idx, dist, H):
        """distinct-goal collapse: ONE continuation per matched goal (first within the tight radius); region counts."""
        rr = self.r[H][idx]
        ok = rr >= 0
        if not ok.any():
            return np.zeros(9)
        g = self.gid[idx][ok]; rr = rr[ok]
        _, first = np.unique(g, return_index=True)
        return np.bincount(rr[first].astype(np.int64), minlength=9).astype(float)

def _entropy(counts):
    p = counts / counts.sum() if counts.sum() > 0 else counts
    p = p[p > 0]
    return float(-(p * np.log(p)).sum())


def _logp(counts, r, K=9, alpha=0.5):
    tot = counts.sum()
    return float(np.log((counts[r] + alpha) / (tot + alpha * K)))


def run() -> dict:
    import sys, time
    t0 = time.time()
    d = _load()
    print(f"[proj] load {time.time()-t0:.0f}s", file=sys.stderr)
    P = Proj(d)
    rng = np.random.default_rng(20260714)
    # held-out query pool: moving frames in decision neighborhoods with valid futures
    heldpool = {}
    for zname in STATES:
        base = np.where((P.zone == zname))[0]
        heldpool[zname] = base
    # ---- knob tuning by HELD-OUT PREDICTIVE SKILL (mean log-lik of the TRUE continuation, leave-one-goal-out) ----
    # amortize: ONE ball query (rmax) per held-out point, reused across all 36 combos.
    # tune on the DECISION states only (near_net is a funnel state — its huge dense candidate sets don't inform knobs)
    qidx = np.concatenate([rng.choice(heldpool[z], size=min(120, len(heldpool[z])), replace=False) for z in DECISION])
    qballs = [(int(i), P.ball(P.x[i], P.y[i], 8.0)) for i in qidx]
    # radius FIXED at 8 (given the library's richness, radius drives match-count not sharpness; the sharpness
    # knobs are the motion-window, heading-tol, look-ahead). Sweep those by held-out skill.
    grid = [(w, 8, tol, H) for w in (2, 3, 5) for tol in (30, 45, 60) for H in (5, 10)]
    best, best_combo = -1e9, None
    for (w, radius, tol, H) in grid:
        sp, hd = P.sph[w]
        lls = []
        for i, (cand, dist) in qballs:
            if not (sp[i] > FLOOR and P.r[H][i] >= 0):
                continue
            cnt = P.score(cand, dist, hd[i], w, radius, tol, H, exclude_gid=P.gid[i], use_head=True)
            if cnt.sum() < 3:
                continue
            lls.append(_logp(cnt, int(P.r[H][i])))
        m = float(np.mean(lls)) if lls else -1e9
        if m > best:
            best, best_combo = m, (w, radius, tol, H)
    w, radius, tol, H = best_combo
    print(f"[proj] tuned {time.time()-t0:.0f}s -> w={w} r={radius} tol={tol} H={H} ll={best:.3f}", file=sys.stderr)
    sp, hd = P.sph[w]
    # same-zone-marginal null — built on the SAME (moving) population as the conditioned set, at the tuned window,
    # one continuation per distinct goal in the zone. (Including stationary pucks would trivially concentrate it.)
    zmarg = {}
    for zname in STATES:
        idx = heldpool[zname]
        idx = idx[(sp[idx] > FLOOR) & (P.r[H][idx] >= 0)]
        g = P.gid[idx]; rr = P.r[H][idx]
        _, first = np.unique(g, return_index=True)
        zmarg[(zname, H)] = np.bincount(rr[first].astype(np.int64), minlength=9).astype(float)

    # ---- GATE per decision state at tuned knobs ----
    rows = []
    for zname, (px, py) in STATES.items():
        # data-derived representative heading = median heading of moving pucks near the canonical position
        near = np.asarray(P.tree.query_ball_point([px, py], r=8.0), dtype=np.int64)
        near = near[sp[near] > FLOOR]
        phead = float(np.median(hd[near])) if len(near) else 0.0
        ccand, cdist = P.ball(px, py, 8.0)
        cond = P.score(ccand, cdist, phead, w, radius, tol, H, use_head=True)
        pos = P.score(ccand, cdist, phead, w, radius, 999, H, use_head=False)   # position-only null
        zm = zmarg[(zname, H)]
        # sharpness
        pc = cond / cond.sum() if cond.sum() else cond
        order = np.argsort(pc)[::-1]
        top2 = float(pc[order[:2]].sum())
        e_cond, e_zone = _entropy(cond), _entropy(zm)
        # held-out predictive skill in this zone: cond vs both nulls
        qz = rng.choice(heldpool[zname], size=min(100 if zname in FUNNEL else 250, len(heldpool[zname])), replace=False)
        lc, lp, lz = [], [], []
        for i in qz:
            if not (sp[i] > FLOOR and P.r[H][i] >= 0):
                continue
            r = int(P.r[H][i])
            cand, dist = P.ball(P.x[i], P.y[i], 8.0)
            c = P.score(cand, dist, hd[i], w, radius, tol, H, exclude_gid=P.gid[i], use_head=True)
            po = P.score(cand, dist, hd[i], w, radius, 999, H, exclude_gid=P.gid[i], use_head=False)
            if c.sum() < 3:
                continue
            lc.append(_logp(c, r)); lp.append(_logp(po, r)); lz.append(_logp(zm, r))
        skill_c, skill_p, skill_z = float(np.mean(lc)), float(np.mean(lp)), float(np.mean(lz))
        modes = [(RNAMES[j], round(float(pc[j]), 3)) for j in order if pc[j] > 0.02][:5]
        clears = (top2 >= 0.60) and (e_cond <= 0.7 * e_zone) and (skill_c > skill_p) and (skill_c > skill_z)
        rows.append({"state": zname, "funnel": zname in FUNNEL, "n_modes_goals": int(cond.sum()),
                     "top2": round(top2, 3), "entropy_cond": round(e_cond, 2), "entropy_zone": round(e_zone, 2),
                     "entropy_ratio": round(e_cond / e_zone, 2) if e_zone else None,
                     "skill_cond": round(skill_c, 2), "skill_posonly": round(skill_p, 2), "skill_zone": round(skill_z, 2),
                     "beats_both_nulls": bool(skill_c > skill_p and skill_c > skill_z),
                     "CLEARS_BAR": bool(clears), "modes": modes})

    # ---- report ----
    L = []; Wl = L.append
    Wl("# Puck-Path Projector — §5 SHARPNESS GATE (mode-based, held-out-tuned, controlled nulls)\n")
    Wl(f"Library {int(P.gid.max()):,} 5v5 goals. Knobs TUNED by held-out predictive skill (leave-one-goal-out): "
       f"motion-window **{w/10:.1f}s**, radius **{radius} ft**, heading-tol **±{tol}°**, look-ahead **{H/10:.1f}s** "
       f"(best mean log-lik {best:.3f}). Distinct-goal collapse + mode/entropy per §0e.\n")
    Wl("**LOCKED BAR (per decision-state): top-2 modes ≥60% AND conditioned entropy ≤0.7× same-zone-marginal AND "
       "held-out skill beats BOTH nulls. Funnel guard: near_net EXCLUDED from any 'works' claim.**\n")
    for r in rows:
        tag = "  [FUNNEL — excluded from the claim]" if r["funnel"] else ""
        Wl(f"## {r['state']}{tag}\n")
        Wl("**Dominant continuations (share of matched distinct goals):** " +
           " · ".join(f"{n} **{p*100:.0f}%**" for n, p in r["modes"]))
        Wl(f"- top-2 modes = **{r['top2']*100:.0f}%** (bar ≥60%) · matched goals {r['n_modes_goals']:,}")
        Wl(f"- entropy: conditioned **{r['entropy_cond']}** vs same-zone-marginal {r['entropy_zone']} → ratio "
           f"**{r['entropy_ratio']}** (bar ≤0.70)")
        Wl(f"- held-out skill (log-lik of the TRUE continuation): conditioned **{r['skill_cond']}** vs position-only "
           f"{r['skill_posonly']} vs zone-marginal {r['skill_zone']} → beats both: **{r['beats_both_nulls']}**")
        Wl(f"- **CLEARS LOCKED BAR: {'YES' if r['CLEARS_BAR'] else 'no'}**\n")
    decision_pass = [r["state"] for r in rows if (not r["funnel"]) and r["CLEARS_BAR"]]
    Wl("## Verdict (funnel-guarded — the 4 non-funnel decision states must pass on their own)\n")
    Wl(f"- Non-funnel decision states clearing the locked bar: **{decision_pass if decision_pass else 'NONE'}** "
       f"of {DECISION}.")
    nf = next(r for r in rows if r["state"] == "near_net_slot")
    Wl(f"- near_net (funnel, excluded): CLEARS={nf['CLEARS_BAR']} — expected/boring, not counted.")
    if decision_pass:
        Wl("- → the puck's likely path is WELL-POSED at those states; a 'correct defensive read' is meaningful there "
           "→ part two would be gated to those states only.")
    else:
        Wl("- → at the interesting non-funnel decision states the projection is MUSH by the locked bar; the likely "
           "path is NOT well-posed there and the defensive read rests on sand. Honest negative.")
    Wl("\n## STOP — sharpness gate for owner review. No defense-read, no grading.\n")
    C.REPORTS.mkdir(parents=True, exist_ok=True)
    (C.REPORTS / "puckproj_gate.md").write_text("\n".join(L))
    return {"tuned": {"window_s": w / 10, "radius": radius, "tol": tol, "H_s": H / 10, "held_out_loglik": round(best, 3)},
            "rows": rows, "decision_pass": decision_pass}


if __name__ == "__main__":
    import json
    print(json.dumps(run(), indent=1, default=str))
