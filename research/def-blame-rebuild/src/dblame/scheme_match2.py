"""Assignment-Free Scheme Matcher (v2, fixes the F37 role-flip wall). ONE change from F37: match the SET of five
defender positions to the SET of five scheme-predicted zone-centers via OPTIMAL ASSIGNMENT (Hungarian) — no
roster roles at all. Reuses F37's verified template port, settled corpus, divergence weighting, three-outcome
confidence. §7 GUARDRAIL absolute: descriptive/confidence-flagged ONLY, never an automated blame input.

Refinements folded in: (1) NO-FIT floor is an ABSOLUTE per-defender feet tolerance re-grounded on the new
(lower) assignment-free scale, NOT a percentile; (2) permutation-invariance reported as a CODE-CORRECTNESS check
(trivially true by Hungarian); (3) null-margin = PUCK-PATH SHUFFLE (decouple the scheme's puck-conditioning from
the real formation).
"""
from __future__ import annotations

import numpy as np
import polars as pl
from scipy.optimize import linear_sum_assignment

from . import config as C
from .data import universe
from .scheme_match import _grids, _cells, SLIST, SETTLE_DWELL, SETTLE_REVERSAL, DZONE_MAX, DZONE_MIN, WIN, SEASON_FILES

FLOOR_PD = 14.0        # ABSOLUTE per-defender feet tolerance for a "fit" (a defender ~1 zone-width off is in-shape)
NULL_K = 6             # puck-path shuffles for the margin null
DISC = 79.0            # discriminating divergence threshold (from §10 confirm)


def _cost(act, exp):
    """optimal-assignment (Hungarian) total pairing distance between 5 actual and 5 predicted points."""
    d = np.linalg.norm(act[:, None, :] - exp[None, :, :], axis=2)
    ri, ci = linear_sum_assignment(d)
    return float(d[ri, ci].sum())


def _play_mismatch(actual, expf, wts):
    """actual (nfr,5,2); expf (5schemes,nfr,5,2); wts (nfr,). → weighted-avg mismatch per scheme (5,)."""
    nfr = actual.shape[0]; out = np.zeros(len(SLIST))
    ws = max(wts.sum(), 1e-9)
    for si in range(len(SLIST)):
        acc = 0.0
        for f in range(nfr):
            acc += wts[f] * _cost(actual[f], expf[si, f])
        out[si] = acc / ws
    return out


def run() -> dict:
    import sys, time
    t0 = time.time()
    exp_grid, dv_grid = _grids()
    print(f"[v2] grids {time.time()-t0:.0f}s", file=sys.stderr)
    u = universe().select("game_id", "event_id", "season", "attack_sign", "defending_team_id",
                          "home_goalie_id", "away_goalie_id", "goal_frame")
    n_5v5 = u.height; n_qual = 0; n_settled = 0
    rng = np.random.default_rng(20260714)
    results = []; inv_checks = []
    for season, fname in zip(C.SEASONS, SEASON_FILES):
        us = u.filter(pl.col("season") == season); gids = us["game_id"].unique().to_list()
        fr = (pl.read_parquet(C.GT_FRAMES_DIR / fname, columns=["game_id", "event_id", "frame_index", "is_puck", "player_id", "team_id", "x_std", "y_std"])
              .filter(pl.col("game_id").is_in(gids)).join(us, on=["game_id", "event_id"], how="inner")
              .filter((pl.col("frame_index") <= pl.col("goal_frame")) & (pl.col("frame_index") >= pl.col("goal_frame") - WIN))
              .with_columns(D=89.0 - pl.col("attack_sign") * pl.col("x_std"), Lp=pl.col("attack_sign") * pl.col("y_std")))
        goalie = (pl.col("player_id") == pl.col("home_goalie_id")) | (pl.col("player_id") == pl.col("away_goalie_id"))
        puck = fr.filter(pl.col("is_puck")).select("game_id", "event_id", "frame_index", pL="Lp", pD="D")
        dff = fr.filter(~pl.col("is_puck") & ~goalie & (pl.col("team_id") == pl.col("defending_team_id"))).select(
            "game_id", "event_id", "frame_index", sL="Lp", sD="D")
        pdict = {k: v for k, v in puck.group_by(["game_id", "event_id"], maintain_order=True)}
        ddict = {k: v for k, v in dff.group_by(["game_id", "event_id"], maintain_order=True)}
        for key, pk in pdict.items():
            pk = pk.sort("frame_index")
            pD = pk["pD"].to_numpy(); pL = pk["pL"].to_numpy(); fr_idx = pk["frame_index"].to_numpy()
            fin = np.isfinite(pD) & np.isfinite(pL)
            if fin.sum() < 20 or not (np.nanmax(pD) <= DZONE_MAX and np.nanmin(pD) >= DZONE_MIN):
                continue
            n_qual += 1
            pDf = pD[fin]
            if not ((pDf < 60).sum() >= SETTLE_DWELL and (pDf[np.argmin(pDf):].max() - pDf.min()) >= SETTLE_REVERSAL):
                continue
            n_settled += 1
            if key not in ddict:
                continue
            dk = ddict[key]
            # per-frame 5 defender positions (ANY order — assignment-free); keep frames with >=5 defenders + finite puck
            dg = dk.group_by("frame_index").agg(Ls=pl.col("sL"), Ds=pl.col("sD"), n=pl.len())
            dmap = {r["frame_index"]: (np.asarray(r["Ls"], float), np.asarray(r["Ds"], float)) for r in dg.iter_rows(named=True) if r["n"] >= 5}
            fsel = [i for i, f in enumerate(fr_idx) if fin[i] and f in dmap]
            if len(fsel) < 15:
                continue
            fsel = np.array(fsel)
            aL = pL[fsel]; aD = pD[fsel]
            actual = np.zeros((len(fsel), 5, 2))
            for j, i in enumerate(fsel):
                Ls, Ds = dmap[fr_idx[i]]
                fok = np.isfinite(Ls) & np.isfinite(Ds)
                if fok.sum() < 5:
                    actual[j] = np.nan; continue
                actual[j, :, 0] = Ls[fok][:5]; actual[j, :, 1] = Ds[fok][:5]
            good = np.isfinite(actual).all(axis=(1, 2))
            if good.sum() < 15:
                continue
            actual = actual[good]; aL = aL[good]; aD = aD[good]
            il, jd = _cells(aL, aD); wts = dv_grid[il, jd]
            expf = np.stack([exp_grid[s][il, jd] for s in SLIST])
            mm = _play_mismatch(actual, expf, wts)
            order = np.argsort(mm); best_i = int(order[0]); best_mm = float(mm[best_i])
            margin = float((mm[order[1]] - best_mm) / best_mm) if best_mm > 0 else 0.0
            pd_fit = best_mm / 5.0
            disc_frac = float(np.mean(wts > DISC))
            # null margin: shuffle puck-path frames (decouple scheme puck-conditioning from the real formation)
            null_marg = []
            for _ in range(NULL_K):
                perm = rng.permutation(len(actual))
                mmn = _play_mismatch(actual, expf[:, perm], wts[perm]); on = np.sort(mmn)
                null_marg.append(float((on[1] - on[0]) / on[0]) if on[0] > 0 else 0.0)
            null_p90 = float(np.percentile(null_marg, 90))
            # permutation-invariance CODE check (first 30 goals): relabel defenders → mismatch identical
            if len(inv_checks) < 30:
                p = rng.permutation(5)
                mm2 = _play_mismatch(actual[:, p], expf, wts)
                inv_checks.append(float(np.max(np.abs(mm2 - mm))))
            results.append({"g": key[0], "e": key[1], "best": SLIST[best_i], "best_mm": best_mm, "pd_fit": pd_fit,
                            "margin": margin, "null_p90": null_p90, "disc_frac": disc_frac, "n": int(good.sum())})
        print(f"[v2] {season} {time.time()-t0:.0f}s settled={n_settled} matched={len(results)}", file=sys.stderr)

    # classify: absolute per-defender floor + null-calibrated margin (no role flag — assignment-free)
    for r in results:
        beats_null = r["margin"] > max(r["null_p90"], 0.02)
        r["verdict"] = "NO-FIT" if r["pd_fit"] > FLOOR_PD else ("CONFIDENT" if beats_null else "AMBIGUOUS")
    return _report(results, n_5v5, n_qual, n_settled, inv_checks)


def _report(results, n_5v5, n_qual, n_settled, inv_checks) -> dict:
    from collections import Counter
    L = []; W = L.append
    verd = Counter(r["verdict"] for r in results); best = Counter(r["best"] for r in results if r["verdict"] == "CONFIDENT")
    tot = max(len(results), 1)
    pdv = np.array([r["pd_fit"] for r in results]) if results else np.array([0.0])
    inv = max(inv_checks) if inv_checks else 0.0
    W("# Assignment-Free Scheme Matcher (v2) — Hungarian shape-match, no roster roles (§7: DESCRIPTIVE only)\n")
    W(f"5v5 {n_5v5:,} → D-zone-entire-buildup {n_qual:,} → SETTLED {n_settled:,} → matched **{len(results):,}**. "
      f"Match = optimal 5→5 assignment (defenders↔predicted zones), NO roster roles. Absolute NO-FIT floor = "
      f"**{FLOOR_PD:.0f} ft/defender** (re-grounded on the assignment-free scale; NOT a percentile).\n")
    W(f"**Permutation-invariance CODE check (§6): max mismatch change when defenders are relabeled (over "
      f"{len(inv_checks)} goals) = {inv:.2e} ft** → assignment-free confirmed (0 by Hungarian construction; this "
      "proves the implementation carries no hidden order).\n")
    W("**GUARDRAIL: descriptive, confidence-flagged, human-checkable. NEVER an automated blame input.**\n")
    W("## Confidence breakdown (THE key result)\n")
    for v in ("CONFIDENT", "AMBIGUOUS", "NO-FIT"):
        W(f"- **{v}: {verd.get(v,0):,}** ({verd.get(v,0)/tot*100:.0f}%)")
    W(f"\n- per-defender fit distribution (ft): p10 {np.percentile(pdv,10):.1f} · median **{np.median(pdv):.1f}** · "
      f"p90 {np.percentile(pdv,90):.1f} (floor {FLOOR_PD:.0f})")
    W(f"- median discriminating-frame fraction: {np.median([r['disc_frac'] for r in results])*100:.0f}%")
    W("\n## HEAD-TO-HEAD vs F37 (the decisive comparison)\n")
    cr = verd.get("CONFIDENT", 0) / tot * 100
    W(f"- F37 (role-fixed): CONFIDENT **0.3%**, role-flip 64% (the wall was role assignment).")
    W(f"- v2 (assignment-free): CONFIDENT **{cr:.0f}%**, role-flip N/A (no roles).")
    if cr >= 5:
        W("- → confident rate ROSE materially → the F37 wall WAS the role-assignment artifact; assignment-free "
          "formation-matching recovers scheme signal. Coaches' shape-first view is right.")
    else:
        W("- → confident rate stayed **near zero even assignment-free** → the wall is the SCHEMES OVERLAPPING AS "
          "SHAPES, not role assignment. Removing roles (the F37 fix) does not recover scheme signal; the five "
          "formations are not distinct enough to separate one goal's coverage from another. Scheme detection is "
          "genuinely not recoverable on this data — and we've now cleanly separated the two causes F37 conflated.")
    W("\n## Best-fit scheme among CONFIDENT goals (context; tape-check needed)\n")
    for s, c in best.most_common():
        W(f"- {s}: {c:,}")
    W("\n## Example goals (6–8) for owner TAPE review\n")
    conf = [r for r in results if r["verdict"] == "CONFIDENT"]
    amb = [r for r in results if r["verdict"] == "AMBIGUOUS"]; nof = [r for r in results if r["verdict"] == "NO-FIT"]
    ex = sorted(conf, key=lambda r: -r["margin"])[:4] + sorted(amb, key=lambda r: r["margin"])[:2] + sorted(nof, key=lambda r: -r["pd_fit"])[:2]
    for r in ex:
        W(f"- {r['g']}-{r['e']} — **{r['verdict']}** · best-fit **{r['best']}** · fit {r['pd_fit']:.1f} ft/def · "
          f"margin {r['margin']:.2f} (null-p90 {r['null_p90']:.2f}) · disc {r['disc_frac']*100:.0f}% · {r['n']}fr")
    W("\n## STOP — assignment-free scheme read for owner review. No aggregation, no grade, no blame.\n")
    C.REPORTS.mkdir(parents=True, exist_ok=True)
    (C.REPORTS / "scheme_match2.md").write_text("\n".join(L))
    return {"n_settled": n_settled, "matched": len(results), "verdict": dict(verd), "floor_pd": FLOOR_PD,
            "inv_max": inv, "median_pd_fit": round(float(np.median(pdv)), 1), "confident_pct": round(cr, 1)}


if __name__ == "__main__":
    import json
    print(json.dumps(run(), indent=1, default=str))
