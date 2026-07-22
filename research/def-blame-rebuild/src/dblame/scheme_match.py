"""Defensive-Scheme Matcher — SETTLED-filtered, three-outcome confidence (CONFIDENT/AMBIGUOUS/NO-FIT).
Ports templates from scheme_confirm (verbatim from responsibility-map-schemes.html). §7 GUARDRAIL: this is a
DESCRIPTIVE, confidence-flagged, human-checkable layer — NEVER an automated blame input. STOP at the report.

Settled filter (excludes rush-entry drive-ins): the buildup must have genuine settled D-zone possession —
sustained in-zone dwell AND a cycle-back (puck works back out to the perimeter after going low), not a
monotonic drive from the blue line to the net.
CONFIDENT requires ALL THREE: (1) absolute-fit floor (best weighted mismatch < data-derived floor, else NO-FIT);
(2) null-calibrated margin (real best-vs-runnerup margin beats shuffled-role null); (3) role-assignment
robustness (best scheme stable under LD↔RD and LW↔RW swaps). Divergence-weighted matching.
"""
from __future__ import annotations

import numpy as np
import polars as pl

from . import config as C
from .data import universe
from .scheme_confirm import expected, divergence, SCHEMES, ROLES

WIN = 100
SEASON_FILES = ["frames_2023_24.parquet", "frames_2024_25.parquet", "frames_2025_26.parquet"]
DZONE_MAX, DZONE_MIN = 64.0, -13.0
SETTLE_DWELL, SETTLE_REVERSAL = 25, 12.0   # >=2.5s in-zone AND >=12ft cycle-back = settled (not a drive-in)
Lg = np.arange(-42, 43); Dg = np.arange(-13, 65)
SLIST = list(SCHEMES.keys())


def _grids():
    exp = {s: np.zeros((len(Lg), len(Dg), 5, 2)) for s in SLIST}
    dv = np.zeros((len(Lg), len(Dg)))
    for il, l in enumerate(Lg):
        for jd, dd in enumerate(Dg):
            dv[il, jd] = divergence(float(l), float(dd))
            for s in SLIST:
                ex = expected(float(l), float(dd), s)[0]
                for k, r in enumerate(ROLES):
                    exp[s][il, jd, k] = ex[r]
    return exp, dv


def _cells(Larr, Darr):
    il = np.clip(np.round(Larr).astype(int) + 42, 0, len(Lg) - 1)
    jd = np.clip(np.round(Darr).astype(int) + 13, 0, len(Dg) - 1)
    return il, jd


def _assign(defs):
    """defs: list of dicts {pid,pos,shoots,mlat}. → {role:pid}, contested bool."""
    D = sorted([d for d in defs if d["pos"] == "D"], key=lambda d: d["mlat"])
    F = [d for d in defs if d["pos"] in ("C", "L", "R")]
    roles = {}; contested = False
    if len(D) == 2:
        ld, rd = D[0], D[1]
        if abs(ld["mlat"] - rd["mlat"]) < 3:   # near-center → handedness tiebreak
            contested = True
            if ld["shoots"] == "R" and rd["shoots"] == "L":
                ld, rd = rd, ld
        roles["LD"] = ld["pid"]; roles["RD"] = rd["pid"]
    else:
        contested = True
        for d in D[:2]:
            roles["RD" if d["mlat"] > 0 and "RD" not in roles else "LD"] = d["pid"]
    used = set(roles.values())
    cen = [d for d in F if d["pos"] == "C" and d["pid"] not in used]
    if cen:
        roles["C"] = cen[0]["pid"]; used.add(cen[0]["pid"])
    for pos, role in (("L", "LW"), ("R", "RW")):
        c = [d for d in F if d["pos"] == pos and d["pid"] not in used]
        if c and role not in roles:
            roles[role] = c[0]["pid"]; used.add(c[0]["pid"])
    # fill any remaining roles by lateral order of remaining players
    rem_roles = [r for r in ROLES if r not in roles]
    rem = sorted([d for d in defs if d["pid"] not in used], key=lambda d: d["mlat"])
    if rem_roles:
        contested = True
        order = {"LW": 0, "LD": 0, "C": 1, "RD": 2, "RW": 2}
        for r in sorted(rem_roles, key=lambda r: order[r]):
            if rem:
                roles[r] = rem.pop(0 if order[r] == 0 else -1 if order[r] == 2 else 0)["pid"]
    return (roles if len(roles) == 5 else None), contested


def _match_goal(actual, expf, wts):
    """actual (nfr,5,2) by role order; expf (5schemes,nfr,5,2); wts (nfr,). → mismatch per scheme (5,)."""
    dist = np.linalg.norm(expf - actual[None], axis=-1).sum(axis=2)   # (5schemes, nfr)
    return (dist * wts[None]).sum(axis=1) / max(wts.sum(), 1e-9)


def run() -> dict:
    import sys, time
    t0 = time.time()
    exp_grid, dv_grid = _grids()
    print(f"[sch] grids {time.time()-t0:.0f}s", file=sys.stderr)
    side = pl.read_parquet(C.PARQUET / "player_side.parquet").select("player_id", "pos", "shoots", "full_name")
    posmap = {r["player_id"]: (r["pos"], r["shoots"], r["full_name"]) for r in side.iter_rows(named=True)}
    u = universe().select("game_id", "event_id", "season", "attack_sign", "defending_team_id",
                          "home_goalie_id", "away_goalie_id", "goal_frame")
    n_5v5 = u.height; n_qual = 0; n_settled = 0
    rng = np.random.default_rng(20260714)
    goals = []
    for season, fname in zip(C.SEASONS, SEASON_FILES):
        us = u.filter(pl.col("season") == season); gids = us["game_id"].unique().to_list()
        fr = (pl.read_parquet(C.GT_FRAMES_DIR / fname, columns=["game_id", "event_id", "frame_index", "is_puck", "player_id", "team_id", "x_std", "y_std"])
              .filter(pl.col("game_id").is_in(gids)).join(us, on=["game_id", "event_id"], how="inner")
              .filter((pl.col("frame_index") <= pl.col("goal_frame")) & (pl.col("frame_index") >= pl.col("goal_frame") - WIN))
              .with_columns(D=89.0 - pl.col("attack_sign") * pl.col("x_std"), Lp=pl.col("attack_sign") * pl.col("y_std")))
        puck = fr.filter(pl.col("is_puck")).select("game_id", "event_id", "frame_index", pL="Lp", pD="D")
        for (g, e), pk in puck.group_by(["game_id", "event_id"], maintain_order=True):
            pk = pk.sort("frame_index")
            pD = pk["pD"].to_numpy(); pL = pk["pL"].to_numpy()
            fin = np.isfinite(pD) & np.isfinite(pL)
            if fin.sum() < 20:
                continue
            pDf = pD[fin]
            if not (np.nanmax(pD) <= DZONE_MAX and np.nanmin(pD) >= DZONE_MIN):
                continue
            n_qual += 1
            dwell = int((pDf < 60).sum())
            reversal = float(pDf[np.argmin(pDf):].max() - pDf.min()) if len(pDf) else 0.0
            if not (dwell >= SETTLE_DWELL and reversal >= SETTLE_REVERSAL):
                continue
            goals.append((g, e))
    n_settled = len(goals)
    print(f"[sch] scan {time.time()-t0:.0f}s qual={n_qual} settled={n_settled}", file=sys.stderr)

    # ---- second pass: match the settled goals ----
    gset = set(goals)
    results = []
    for season, fname in zip(C.SEASONS, SEASON_FILES):
        us = u.filter(pl.col("season") == season)
        sgids = list({g for (g, e) in gset})
        fr = (pl.read_parquet(C.GT_FRAMES_DIR / fname, columns=["game_id", "event_id", "frame_index", "is_puck", "player_id", "team_id", "x_std", "y_std"])
              .filter(pl.col("game_id").is_in(sgids)).join(us, on=["game_id", "event_id"], how="inner")
              .filter((pl.col("frame_index") <= pl.col("goal_frame")) & (pl.col("frame_index") >= pl.col("goal_frame") - WIN))
              .with_columns(D=89.0 - pl.col("attack_sign") * pl.col("x_std"), Lp=pl.col("attack_sign") * pl.col("y_std")))
        goalie = (pl.col("player_id") == pl.col("home_goalie_id")) | (pl.col("player_id") == pl.col("away_goalie_id"))
        puck = fr.filter(pl.col("is_puck")).select("game_id", "event_id", "frame_index", pL="Lp", pD="D")
        dff = fr.filter(~pl.col("is_puck") & ~goalie & (pl.col("team_id") == pl.col("defending_team_id"))).select(
            "game_id", "event_id", "frame_index", "player_id", sL="Lp", sD="D")
        pdict = {k: v for k, v in puck.group_by(["game_id", "event_id"], maintain_order=True)}
        ddict = {k: v for k, v in dff.group_by(["game_id", "event_id"], maintain_order=True)}
        for (g, e) in [ge for ge in gset if ge[0] in set(sgids)]:
            if (g, e) not in pdict or (g, e) not in ddict:
                continue
            pk = pdict[(g, e)].sort("frame_index"); dk = ddict[(g, e)]
            # role assignment
            perdef = dk.group_by("player_id").agg(mlat=pl.col("sL").mean(), nf=pl.len()).filter(pl.col("nf") >= 10)
            defs = []
            for r in perdef.iter_rows(named=True):
                pm = posmap.get(r["player_id"], ("?", None, str(r["player_id"])))
                defs.append({"pid": r["player_id"], "pos": pm[0], "shoots": pm[1], "mlat": r["mlat"], "name": pm[2]})
            if len(defs) < 5:
                continue
            defs = sorted(defs, key=lambda d: -d["mlat"])[:5] if len(defs) > 5 else defs
            roles, contested = _assign(defs)
            if roles is None:
                continue
            # build aligned per-frame arrays (frames where puck + all 5 role players present)
            frames = pk["frame_index"].to_numpy()
            pL = pk["pL"].to_numpy(); pD = pk["pD"].to_numpy()
            fin = np.isfinite(pL) & np.isfinite(pD)
            frames, pL, pD = frames[fin], pL[fin], pD[fin]
            pos_by = {}
            dkp = dk.filter(pl.col("player_id").is_in(list(roles.values())))
            for r in dkp.iter_rows(named=True):
                pos_by[(r["player_id"], r["frame_index"])] = (r["sL"], r["sD"])
            actual = np.full((len(frames), 5, 2), np.nan)
            for fi, fnum in enumerate(frames):
                for ri, role in enumerate(ROLES):
                    p = pos_by.get((roles[role], fnum))
                    if p:
                        actual[fi, ri] = p
            keep = np.isfinite(actual).all(axis=(1, 2))
            if keep.sum() < 15:
                continue
            actual = actual[keep]; il, jd = _cells(pL[keep], pD[keep]); wts = dv_grid[il, jd]
            expf = np.stack([exp_grid[s][il, jd] for s in SLIST])   # (5,nfr,5,2)
            mm = _match_goal(actual, expf, wts)
            order = np.argsort(mm); best_i, run_i = order[0], order[1]
            best_mm = float(mm[best_i]); margin = float((mm[run_i] - mm[best_i]) / best_mm)
            disc_frac = float(np.mean(wts > 79))
            # null-calibrated margin: shuffle role labels K times
            null_marg = []
            for _ in range(20):
                perm = rng.permutation(5)
                mmp = _match_goal(actual[:, perm], expf, wts); o = np.sort(mmp)
                null_marg.append(float((o[1] - o[0]) / o[0]))
            null_p90 = float(np.percentile(null_marg, 90))
            # role robustness: swap LD/RD (0,1) and LW/RW (3,4)
            robust = True
            for sw in ([1, 0, 2, 3, 4], [0, 1, 2, 4, 3]):
                if int(np.argmin(_match_goal(actual[:, sw], expf, wts))) != best_i:
                    robust = False; break
            results.append({"g": g, "e": e, "best": SLIST[best_i], "best_mm": best_mm, "margin": margin,
                            "null_p90": null_p90, "robust": robust, "contested": contested, "disc_frac": disc_frac,
                            "roles": {r: defs_name(defs, roles[r]) for r in ROLES}, "n": int(keep.sum())})
    print(f"[sch] matched {time.time()-t0:.0f}s n={len(results)}", file=sys.stderr)

    # ---- classify with data-derived absolute-fit floor ----
    mms = np.array([r["best_mm"] for r in results])
    FLOOR = float(np.percentile(mms, 70)) if len(mms) else 0.0   # data-derived: best fits below the 70th pct
    for r in results:
        beats_null = r["margin"] > max(r["null_p90"], 0.02)
        if r["best_mm"] > FLOOR:
            r["verdict"] = "NO-FIT"
        elif beats_null and r["robust"] and not r["contested"]:
            r["verdict"] = "CONFIDENT"
        else:
            r["verdict"] = "AMBIGUOUS"
    return _report(results, n_5v5, n_qual, n_settled, FLOOR)


def defs_name(defs, pid):
    for d in defs:
        if d["pid"] == pid:
            return d.get("name", str(pid))
    return str(pid)


def _report(results, n_5v5, n_qual, n_settled, FLOOR) -> dict:
    from collections import Counter
    L = []; W = L.append
    verd = Counter(r["verdict"] for r in results)
    best = Counter(r["best"] for r in results)
    conf = [r for r in results if r["verdict"] == "CONFIDENT"]
    W("# Defensive-Scheme Matcher — settled-filtered, three-outcome confidence (§7 guardrail: DESCRIPTIVE only)\n")
    W(f"5v5 goals {n_5v5:,} → D-zone-entire-buildup {n_qual:,} → **SETTLED (drive-ins excluded): {n_settled:,}** "
      f"(dwell ≥{SETTLE_DWELL}fr AND cycle-back ≥{SETTLE_REVERSAL:.0f}ft). Matched: {len(results):,}. "
      f"Absolute-fit floor (data-derived, 70th pct of best-mismatch) = {FLOOR:.0f} ft.\n")
    W("**GUARDRAIL: descriptive, confidence-flagged, human-checkable. NEVER an automated blame input.**\n")
    W("## Confidence breakdown (THE key result)\n")
    tot = max(len(results), 1)
    for v in ("CONFIDENT", "AMBIGUOUS", "NO-FIT"):
        W(f"- **{v}: {verd.get(v,0):,}** ({verd.get(v,0)/tot*100:.0f}%)")
    flip = np.mean([not r["robust"] for r in results]) if results else 0
    cont = np.mean([r["contested"] for r in results]) if results else 0
    dfm = np.median([r["disc_frac"] for r in results]) if results else 0
    W(f"\n- role-assignment robustness FLIP rate (best scheme changes under LD↔RD / LW↔RW swap): **{flip*100:.0f}%**")
    W(f"- role-assignment contested rate: {cont*100:.0f}% · median discriminating-frame fraction: {dfm*100:.0f}%")
    W("\n## Best-fit scheme distribution (all matched, for context — NOT a claim; many are ambiguous/no-fit)\n")
    for s, c in best.most_common():
        W(f"- {s}: {c:,} ({c/tot*100:.0f}%)")
    W("\n## Example goals (6–8) for owner TAPE review\n")
    ex = sorted(conf, key=lambda r: -r["margin"])[:4] + sorted([r for r in results if r["verdict"] == "AMBIGUOUS"], key=lambda r: r["margin"])[:2] + [r for r in results if r["verdict"] == "NO-FIT"][:2]
    for r in ex:
        W(f"\n### {r['g']}-{r['e']} — **{r['verdict']}** · best-fit **{r['best']}** (mismatch {r['best_mm']:.0f}ft, "
          f"margin {r['margin']:.2f} vs null-p90 {r['null_p90']:.2f}, robust={r['robust']}, disc {r['disc_frac']*100:.0f}%)")
        W("  - roles: " + " · ".join(f"{role}={r['roles'][role]}" for role in ROLES))
    W("\n## STOP — descriptive scheme read for owner tape review. No aggregation, no grade, no blame.\n")
    C.REPORTS.mkdir(parents=True, exist_ok=True)
    (C.REPORTS / "scheme_match.md").write_text("\n".join(L))
    return {"n_settled": n_settled, "matched": len(results), "verdict": dict(verd), "floor": round(FLOOR, 1),
            "flip_rate": round(float(flip), 3), "best_dist": dict(best)}


if __name__ == "__main__":
    import json
    print(json.dumps(run(), indent=1, default=str))
