"""Defensive-Scheme Matcher §10 — READ-ONLY confirms: (c) port-verification, (a) qualifying-goal count,
(b) discriminating-exposure distribution. Ports the templates from responsibility-map-schemes.html EXACTLY
(LM / ANCHOR_PUCK / SCHEMES / buildAnchors / zoneCenters / pressure) and STOPS before the matcher. No role
assignment, no per-defender match, no confidence — only whether the scope has enough goals and enough
scheme-divergent puck-time to be matchable, plus a faithful-port check.
"""
from __future__ import annotations

import numpy as np
import polars as pl

from . import config as C
from .data import universe

WIN = 100
SEASON_FILES = ["frames_2023_24.parquet", "frames_2024_25.parquet", "frames_2025_26.parquet"]
DZONE_MAX = 64.0        # blue line; strict scope = every frame depth <= this
DZONE_MIN = -13.0       # end boards behind net
ROLES = ["LD", "RD", "C", "LW", "RW"]

# ---- ported verbatim from responsibility-map-schemes.html (feet frame; L lateral ±42.5, D depth 0=goal line) ----
LM = {"net_front": [0, 5], "low_slot": [0, 11], "high_slot": [0, 32], "post_left": [-3, 2], "post_right": [3, 2],
      "dot_lane_left": [-22, 20], "dot_lane_right": [22, 20], "half_wall_left": [-40, 21], "half_wall_right": [40, 21],
      "point_left": [-25, 62], "point_right": [25, 62]}
FLIP = {"post_left": "post_right", "post_right": "post_left", "dot_lane_left": "dot_lane_right",
        "dot_lane_right": "dot_lane_left", "half_wall_left": "half_wall_right", "half_wall_right": "half_wall_left",
        "point_left": "point_right", "point_right": "point_left"}
SWAP = {"LD": "RD", "RD": "LD", "LW": "RW", "RW": "LW", "C": "C"}
ANCHOR_PUCK = {"cornerL": [-37, 9], "halfWallL": [-38, 22], "pointL": [-20, 60], "behindNet": [0, -5], "slot": [0, 19]}
SCHEMES = {
    "man": {"cornerL": {"LD": "PUCK", "RD": "net_front", "C": "low_slot", "LW": "point_left", "RW": "point_right"},
            "halfWallL": {"LD": "half_wall_left", "RD": "net_front", "C": "low_slot", "LW": "point_left", "RW": "point_right"},
            "pointL": {"LD": "dot_lane_left", "RD": "net_front", "C": "high_slot", "LW": "point_left", "RW": "point_right"},
            "behindNet": {"LD": "post_left", "RD": "post_right", "C": "low_slot", "LW": "dot_lane_left", "RW": "dot_lane_right"},
            "slot": {"LD": "post_left", "RD": "post_right", "C": "low_slot", "LW": "point_left", "RW": "point_right"}},
    "zone": {"cornerL": {"LD": "dot_lane_left", "RD": "net_front", "C": "low_slot", "LW": "high_slot", "RW": "dot_lane_right"},
             "halfWallL": {"LD": "half_wall_left", "RD": "net_front", "C": "low_slot", "LW": "high_slot", "RW": "dot_lane_right"},
             "pointL": {"LD": "dot_lane_left", "RD": "net_front", "C": "high_slot", "LW": "point_left", "RW": "dot_lane_right"},
             "behindNet": {"LD": "post_left", "RD": "post_right", "C": "low_slot", "LW": "dot_lane_left", "RW": "dot_lane_right"},
             "slot": {"LD": "post_left", "RD": "post_right", "C": "low_slot", "LW": "dot_lane_left", "RW": "dot_lane_right"}},
    "fiveTight": {"cornerL": {"LD": "PUCK", "RD": "net_front", "C": "dot_lane_left", "LW": "point_left", "RW": "high_slot"},
                  "halfWallL": {"LD": "half_wall_left", "RD": "net_front", "C": "dot_lane_left", "LW": "point_left", "RW": "high_slot"},
                  "pointL": {"LD": "dot_lane_left", "RD": "net_front", "C": "low_slot", "LW": "point_left", "RW": "high_slot"},
                  "behindNet": {"LD": "post_left", "RD": "post_right", "C": "low_slot", "LW": "dot_lane_left", "RW": "dot_lane_right"},
                  "slot": {"LD": "post_left", "RD": "post_right", "C": "low_slot", "LW": "dot_lane_left", "RW": "dot_lane_right"}},
    "box1": {"cornerL": {"C": "PUCK", "LD": "net_front", "RD": "post_right", "LW": "dot_lane_left", "RW": "dot_lane_right"},
             "halfWallL": {"C": "PUCK", "LD": "net_front", "RD": "post_right", "LW": "dot_lane_left", "RW": "dot_lane_right"},
             "pointL": {"C": "high_slot", "LD": "post_left", "RD": "post_right", "LW": "point_left", "RW": "point_right"},
             "behindNet": {"C": "PUCK", "LD": "post_left", "RD": "post_right", "LW": "dot_lane_left", "RW": "dot_lane_right"},
             "slot": {"C": "PUCK", "LD": "post_left", "RD": "post_right", "LW": "dot_lane_left", "RW": "dot_lane_right"}},
    "swarm": {"cornerL": {"LD": "PUCK", "RD": "dot_lane_left", "C": "high_slot", "LW": "net_front", "RW": "low_slot"},
              "halfWallL": {"LD": "PUCK", "RD": "half_wall_left", "C": "high_slot", "LW": "net_front", "RW": "low_slot"},
              "pointL": {"LD": "dot_lane_left", "RD": "net_front", "C": "high_slot", "LW": "point_left", "RW": "low_slot"},
              "behindNet": {"LD": "post_left", "RD": "post_right", "C": "low_slot", "LW": "dot_lane_left", "RW": "dot_lane_right"},
              "slot": {"LD": "post_left", "RD": "post_right", "C": "PUCK", "LW": "dot_lane_left", "RW": "dot_lane_right"}}}
PRESSURE = {"man": (0.82, 15), "zone": (0.20, 14), "fiveTight": (0.62, 22), "box1": (0.50, 12), "swarm": (0.92, 26)}


def _flipLM(i):
    return "PUCK" if i == "PUCK" else FLIP.get(i, i)


def _build_anchors(sid):
    A = SCHEMES[sid]; out = []
    for k in ["cornerL", "halfWallL", "pointL", "behindNet", "slot"]:
        out.append((ANCHOR_PUCK[k], A[k]))
    for k in ["cornerL", "halfWallL", "pointL"]:
        bp = ANCHOR_PUCK[k]; base = A[k]
        out.append(([-bp[0], bp[1]], {r: _flipLM(base[SWAP[r]]) for r in ROLES}))
    return out


def _resolve(i, puck):
    return puck if i == "PUCK" else LM[i]


def _zone_centers(pL, pD, sid):
    anchors = _build_anchors(sid); acc = {r: [0.0, 0.0] for r in ROLES}; ws = 0.0
    for apuck, assign in anchors:
        dl = pL - apuck[0]; dd = pD - apuck[1]; w = 1.0 / (dl * dl + dd * dd + 1.0); ws += w
        for r in ROLES:
            p = _resolve(assign[r], [pL, pD]); acc[r][0] += w * p[0]; acc[r][1] += w * p[1]
    return {r: [acc[r][0] / ws, acc[r][1] / ws] for r in ROLES}


def expected(pL, pD, sid):
    rest = _zone_centers(pL, pD, sid); P, sig = PRESSURE[sid]; out = {}
    for r in ROLES:
        rc = rest[r]; dl = pL - rc[0]; dd = pD - rc[1]; d2 = dl * dl + dd * dd
        k = P * (sig * sig) / (d2 + sig * sig)
        out[r] = [rc[0] + k * dl, rc[1] + k * dd]
    return out, rest


def divergence(pL, pD):
    """cross-scheme spread at a puck location = sum over roles of mean pairwise distance across the 5 schemes."""
    pos = {s: expected(pL, pD, s)[0] for s in SCHEMES}
    tot = 0.0
    for r in ROLES:
        pts = np.array([pos[s][r] for s in SCHEMES])
        d = 0.0; n = 0
        for i in range(len(pts)):
            for j in range(i + 1, len(pts)):
                d += float(np.hypot(*(pts[i] - pts[j]))); n += 1
        tot += d / n
    return tot


def run() -> dict:
    L = []; W = L.append
    W("# Defensive-Scheme Matcher §10 — read-only confirms (port-verify + qualifying count + discriminating exposure)\n")
    # ---- (c) PORT VERIFICATION ----
    W("## (c) Port verification (the easy-to-break things)\n")
    # mirror: right-corner puck in man → RD on the PUCK
    ex, _ = expected(37, 9, "man"); rd = ex["RD"]; ddp = float(np.hypot(rd[0] - 37, rd[1] - 9))
    W(f"- **L/R mirror:** man @ right-corner puck (37,9) → RD expected ({rd[0]:.1f},{rd[1]:.1f}); distance to PUCK "
      f"= **{ddp:.1f} ft** (should be small — RD covers the puck, the mirror of LD-on-PUCK at the left corner). "
      f"{'PASS' if ddp < 6 else 'CHECK'}")
    # pressure sign: a role pulls toward the puck
    exs, rest = expected(0, 19, "swarm")   # swarm slot: C='PUCK'; check C pulled to puck
    cr, cp = rest["C"], exs["C"]
    dr = float(np.hypot(cr[0] - 0, cr[1] - 19)); dp = float(np.hypot(cp[0] - 0, cp[1] - 19))
    W(f"- **Pressure sign:** swarm @ slot (0,19), role C — resting ({cr[0]:.1f},{cr[1]:.1f}) dist-to-puck {dr:.1f} → "
      f"pressured ({cp[0]:.1f},{cp[1]:.1f}) dist-to-puck {dp:.1f}. Pull is TOWARD the puck: {'PASS' if dp < dr else 'FAIL'}")
    # anchor dominance: at each ANCHOR_PUCK the resting centers ≈ that anchor's assignment
    W("- **Anchor dominance** (resting center at each ANCHOR_PUCK ≈ that anchor's assigned landmark):")
    for k, ap in ANCHOR_PUCK.items():
        rest = _zone_centers(ap[0], ap[1], "man")
        assign = SCHEMES["man"][k]
        errs = []
        for r in ROLES:
            want = _resolve(assign[r], ap); got = rest[r]
            errs.append(float(np.hypot(got[0] - want[0], got[1] - want[1])))
        W(f"    - man @ {k}{tuple(ap)}: max role error **{max(errs):.1f} ft**, mean {np.mean(errs):.1f} "
          f"({'PASS' if max(errs) < 10 else 'CHECK'})")
    # divergence at the 8 preset puck locations (grounds the discriminating threshold)
    presets = {"L corner": (-37, 9), "R corner": (37, 9), "L half-wall": (-38, 22), "R half-wall": (38, 22),
               "L point": (-20, 60), "R point": (20, 60), "Behind net": (0, -5), "Slot": (0, 19)}
    dvals = {n: divergence(*p) for n, p in presets.items()}
    W("\n## Divergence by puck location (grounds discriminating vs overlap)\n")
    for n, v in sorted(dvals.items(), key=lambda x: -x[1]):
        W(f"- {n}: **{v:.0f}** ft cross-scheme spread")
    # discriminating threshold = midway between the overlap floor (behind/slot) and the divergent zones
    overlap = np.mean([dvals["Behind net"], dvals["Slot"]]); divg = np.mean([dvals["L corner"], dvals["R corner"], dvals["L half-wall"], dvals["R half-wall"]])
    DISC = round((overlap + divg) / 2, 0)
    W(f"\nDiscriminating threshold (data-derived) = midpoint of overlap ({overlap:.0f}) and divergent ({divg:.0f}) = **{DISC:.0f} ft**.\n")

    # ---- precompute divergence grid for fast per-frame lookup ----
    Lg = np.arange(-42, 43); Dg = np.arange(-13, 65)
    grid = np.zeros((len(Lg), len(Dg)))
    for i, l in enumerate(Lg):
        for j, dd in enumerate(Dg):
            grid[i, j] = divergence(float(l), float(dd))

    # ---- (a) qualifying goals + (b) discriminating exposure ----
    u = universe().select("game_id", "event_id", "season", "attack_sign", "goal_frame")
    n_5v5 = u.height; qual = 0
    disc_frac = []; disc_total = []; nfr_list = []
    for season, fname in zip(C.SEASONS, SEASON_FILES):
        us = u.filter(pl.col("season") == season); gids = us["game_id"].unique().to_list()
        pk = (pl.read_parquet(C.GT_FRAMES_DIR / fname, columns=["game_id", "event_id", "frame_index", "is_puck", "x_std", "y_std"])
              .filter(pl.col("is_puck") & pl.col("game_id").is_in(gids)).join(us, on=["game_id", "event_id"], how="inner")
              .filter((pl.col("frame_index") <= pl.col("goal_frame")) & (pl.col("frame_index") >= pl.col("goal_frame") - WIN))
              .with_columns(D=89.0 - pl.col("attack_sign") * pl.col("x_std"), Lp=pl.col("attack_sign") * pl.col("y_std")))
        g = pk.group_by("game_id", "event_id").agg(Dmax=pl.col("D").max(), Dmin=pl.col("D").min(),
                                                   Ls=pl.col("Lp"), Ds=pl.col("D"))
        for row in g.iter_rows(named=True):
            if row["Dmax"] > DZONE_MAX or row["Dmin"] < DZONE_MIN:
                continue
            qual += 1
            Ls = np.clip(np.round(np.asarray(row["Ls"], dtype=float)).astype(int) + 42, 0, len(Lg) - 1)
            Ds = np.clip(np.round(np.asarray(row["Ds"], dtype=float)).astype(int) + 13, 0, len(Dg) - 1)
            dv = grid[Ls, Ds]
            disc_frac.append(float(np.mean(dv > DISC))); disc_total.append(float(np.sum(dv))); nfr_list.append(len(dv))
    df = np.array(disc_frac); dt = np.array(disc_total)
    W("## (a) Qualifying-goal count\n")
    W(f"- 5v5 tracked goals: **{n_5v5:,}** · puck in D-zone (depth ∈ [{DZONE_MIN:.0f},{DZONE_MAX:.0f}]) for the "
      f"ENTIRE buildup: **{qual:,}** ({qual/n_5v5*100:.1f}%)\n")
    W("## (b) Discriminating-exposure distribution (over qualifying goals)\n")
    if len(df):
        W(f"- fraction of a goal's frames that are DISCRIMINATING (divergence > {DISC:.0f} ft): "
          f"median **{np.median(df)*100:.0f}%**, p25 {np.percentile(df,25)*100:.0f}%, p75 {np.percentile(df,75)*100:.0f}%, p90 {np.percentile(df,90)*100:.0f}%")
        for thr in (0.15, 0.30, 0.50):
            W(f"- goals with ≥{int(thr*100)}% discriminating frames (matchable): **{int((df>=thr).sum()):,}** ({(df>=thr).mean()*100:.0f}%)")
        W(f"- goals with <15% discriminating frames (net-front/slot overlap → forced-AMBIGUOUS regardless): "
          f"**{int((df<0.15).sum()):,}** ({(df<0.15).mean()*100:.0f}%)")
    W("\n## Read\n- (a) sizes the strict-scope corpus; (b) sizes how many of those even HAVE enough corner/half-wall/"
      "point puck-time to distinguish schemes (the rest are forced-ambiguous in the behind-net/slot overlap, per §4). "
      "Together they bound where the matcher can say anything at all. (c) confirms the port is faithful before building.")
    W("\n## STOP — read-only confirms. No matcher, no role assignment, no confidence.\n")
    C.REPORTS.mkdir(parents=True, exist_ok=True)
    (C.REPORTS / "scheme_confirm.md").write_text("\n".join(L))
    return {"qualifying": qual, "n_5v5": n_5v5, "disc_median_frac": round(float(np.median(df)), 3) if len(df) else None,
            "DISC_thresh": DISC, "divergence_presets": {k: round(v, 1) for k, v in dvals.items()}}


if __name__ == "__main__":
    import json
    print(json.dumps(run(), indent=1, default=str))
