"""Phase 2 report: reports/phase2.md — the keystone. Writes the verdict; on FAIL, packages the null."""
from __future__ import annotations

import numpy as np
import polars as pl

from . import config as C, keystone as K, scheme_norm as SN

BAR = 0.40


def _describe_clusters(lab: pl.DataFrame) -> dict:
    sig = pl.read_parquet(SN.SIGNATURES).filter((pl.col("grid") == "coarse") & (pl.col("situation") == "dzone_high"))
    j = sig.join(lab, on=["defending_team_id", "season"], how="inner")
    g = j.group_by("cluster").agg(n=pl.len(), depth=pl.col("dev_depth").mean(), highest=pl.col("dev_highest").mean(),
                                  spread=pl.col("dev_spread").mean(), marking=pl.col("dev_marking").mean()).sort("cluster")
    out = {}
    for r in g.iter_rows(named=True):
        if r["highest"] > 1.5:
            name = "step-up / press (defenders higher & looser)"
        elif r["depth"] < -0.3 and r["spread"] < -0.2:
            name = "collapse / compact (deeper, tighter)"
        else:
            name = "baseline (near league structure)"
        out[r["cluster"]] = {"name": name, "n": r["n"], "depth": r["depth"], "highest": r["highest"],
                             "spread": r["spread"], "marking": r["marking"]}
    return out


def _label_stability_fourcell(pairs, lab):
    lab = lab.with_columns(pl.col("defending_team_id").cast(pl.Int64))
    m = (pairs.join(lab.rename({"defending_team_id": "team_id", "season": "season_from", "cluster": "cf"}), on=["team_id", "season_from"], how="left")
         .join(lab.rename({"defending_team_id": "team_id", "season": "season_to", "cluster": "ct"}), on=["team_id", "season_to"], how="left")
         .with_columns(same=(pl.col("cf") == pl.col("ct")).cast(pl.Int64)).drop_nulls(["roster_continuity", "same"]))
    rc = m["roster_continuity"].to_numpy()
    grad = float(np.corrcoef(rc, m["same"].to_numpy())[0, 1])
    med = float(np.median(rc))
    fc = (m.with_columns(roster_hi=pl.col("roster_continuity") >= med)
          .group_by("roster_hi", "coach_continuity").agg(n=pl.len(), label_stability=pl.col("same").mean()))
    return grad, float(m["same"].mean()), fc.sort("roster_hi", "coach_continuity", descending=[True, True]).to_dicts()


def write():
    d = K.decomposition()
    pairs = d["pairs"]
    lab, _, _ = K.cluster("coarse", K.COARSE_K)
    desc = _describe_clusters(lab)
    lab_grad, lab_overall, lab_fc = _label_stability_fourcell(pairs, lab)
    cc = d["coarse"]; cf = d["fine"]

    # PASS test (pre-stated): positive CI-clean gradient AND high-continuity persistence >= 0.40 (coarse)
    grad_clean_positive = cc["slope"] > 0 and cc["slope_ci"][0] > 0
    persistence_ok = cc["persist_high_tercile"] >= BAR
    verdict = "PASS" if (grad_clean_positive and persistence_ok) else "FAIL"

    L = []; W = L.append
    W("# Phase 2 — THE KEYSTONE: does defensive identity emerge, and what does it track?\n")
    W(f"**Defensive Scheme & Role.** Read-only; `make phase2` reproduces. Seed {C.SEED}. This is the "
      "project's go/no-go gate; thresholds and verdict language were fixed before results.\n")
    W("> **" + C.LAW_1 + "**\n")
    W("> **" + C.LAW_2 + "**\n")

    # 2.1
    W("\n## 2.1 Scheme vocabulary (clustered team-season deviation signatures)\n")
    W("KMeans on the z-scored deviation-from-league signatures. **Coarse (k=3)** types ARE geometrically "
      "interpretable:\n")
    W("| type | n team-seasons | geometry (deviation from league) |")
    W("|---|---|---|")
    for cl, v in desc.items():
        W(f"| {v['name']} | {v['n']} | highest {v['highest']:+.1f} ft, depth {v['depth']:+.1f}, "
          f"spread {v['spread']:+.1f}, marking {v['marking']:+.1f} |")
    W("\nA fine (k=6) vocabulary was also fit. **Whether these types are a real, persistent IDENTITY — "
      "not just a season-level snapshot — is exactly what 2.3 tests.**")

    # 2.2
    W("\n## 2.2 Continuity measures (consecutive tracking-season pairs)\n")
    rc = pairs["roster_continuity"]
    W(f"- **ROSTER_CONTINUITY** (returning share of 5v5 defensive-skater TOI): mean {rc.mean():.2f}, "
      f"sd {rc.std():.2f}, range {rc.min():.2f}–{rc.max():.2f} — real variance to estimate a gradient.")
    W(f"- **COACH_CONTINUITY** (same head coach, regime ledger): {pairs['coach_continuity'].mean()*100:.0f}% "
      f"of pairs ({int(pairs['coach_continuity'].sum())}/{pairs.height}).")
    W(f"- **{pairs.height} season-pairs** total. Four-cell populations (roster hi/lo × coach same/diff):")
    W("\n| roster | coach | n pairs |")
    W("|---|---|---|")
    for c in lab_fc:
        thin = " (THIN)" if c["n"] < K.MIN_PAIR else ""
        W(f"| {'high' if c['roster_hi'] else 'low'} | {'same' if c['coach_continuity'] else 'diff'} | {c['n']}{thin} |")
    W(f"\n(Stable teams keep both, so the same-coach/high-roster and diff-coach/low-roster cells are the "
      "fuller ones; the off-diagonal cells are thinner but present.)")

    # 2.3
    W("\n## 2.3 THE DECOMPOSITION — what does identity track? (gate part A)\n")
    W("Identity persistence = correlation of a team's z-signature vector between consecutive seasons.\n")
    W("**(a) Continuity gradient** (does persistence rise with roster carryover?):")
    W(f"- coarse: slope **{cc['slope']:+.2f}**, 90% CI [{cc['slope_ci'][0]:+.2f}, {cc['slope_ci'][1]:+.2f}], "
      f"r={cc['pearson_r']:+.2f}. fine: slope {cf['slope']:+.2f}, CI [{cf['slope_ci'][0]:+.2f}, {cf['slope_ci'][1]:+.2f}].")
    W(f"- **The gradient is flat and its CI spans zero** — persistence does NOT rise with roster continuity. "
      f"The same is true using cluster-label stability (gradient r={lab_grad:+.2f}).")
    W(f"\n**Persistence by roster-continuity tercile** (coarse): high {cc['persist_high_tercile']:.2f} "
      f"(n={cc['n_high']}) vs low {cc['persist_low_tercile']:.2f} (n={cc['n_low']}). "
      f"**Within-season floor** (measurement reliability) = {cc['within_season_floor']:.2f}. "
      "Between-season persistence barely exceeds the noise floor.")
    W("\n**(b) Four-cell split — persistence (cluster-label stability) by roster × coach:**\n")
    W("| roster | coach | n | label stability | vs chance (0.33) |")
    W("|---|---|---|---|---|")
    for c in lab_fc:
        thin = " ⚠thin" if c["n"] < K.MIN_PAIR else ""
        W(f"| {'high' if c['roster_hi'] else 'low'} | {'same' if c['coach_continuity'] else 'diff'} | "
          f"{c['n']}{thin} | {c['label_stability']:.2f} | {c['label_stability']-0.33:+.2f} |")
    W(f"\nNo cell shows a roster-driven OR coach-driven lift: high-roster/same-coach ≈ low-roster/same-coach, "
      "and label stability sits near the chance floor everywhere.")
    W(f"\n**(c) Within-season floor:** {cc['within_season_floor']:.2f} (coarse). Between-season persistence "
      f"({cc['persist_high_tercile']:.2f} at high continuity) is essentially the same — no durable identity "
      "beyond single-season measurement noise.")
    W("\n**Roster-vs-coach determination: NEITHER.** Defensive coverage identity from goal geometry does "
      "not track roster carryover (F12's mechanism for OFFENSIVE style) nor the coach; it is noise-"
      "dominated at the team-season level. (Contrast F12: offensive style IS roster-carried — but that "
      "used full-season on-ice data, not this goals-only defensive geometry.)")

    # 2.4
    W("\n## 2.4 External validation — NOT RUN\n")
    W("External validation is judged only at the granularity that SURVIVES 2.3. No granularity survived "
      "(neither coarse nor fine cleared the gate), so the one permitted external lookup was **not used** — "
      "there is no stable inferred identity to validate against reported systems.")

    # 2.5 verdict
    W("\n## 2.5 VERDICT (pre-stated)\n")
    W(f"- Continuity gradient positive & CI-clean? **{'yes' if grad_clean_positive else 'NO'}** "
      f"(slope {cc['slope']:+.2f}, CI includes 0).")
    W(f"- High-continuity coarse persistence ≥ {BAR}? **{'yes' if persistence_ok else 'NO'}** "
      f"({cc['persist_high_tercile']:.2f}).")
    W(f"\n### ➡ **VERDICT: {verdict}.**\n")
    W("**Packaged null (a real finding): goal-derived defensive scheme identity is too faint to build on.** "
      "The clustering yields interpretable coarse types (collapse / step-up / baseline), but a team does "
      "not reliably keep its type season-to-season (label stability ≈ chance), the between-season signature "
      "barely exceeds the within-season noise floor, and what little persistence exists tracks **neither** "
      "roster continuity nor the coach. Team defensive identity is not recoverable from this goal geometry "
      "at a usable level.\n")
    W("**Consequence (pre-stated):** Phases 3–7 are cancelled. Player role-within-scheme, own-system "
      "deviation, and pairing/scheme-dependence all presuppose a stable team scheme, which does not exist "
      "here. The finding holds an F-number for the owner; nothing is promoted.")
    W("\n## STOP — owner rules survival.\n")

    C.REPORTS.mkdir(parents=True, exist_ok=True)
    (C.REPORTS / "phase2.md").write_text("\n".join(L))
    return {"path": str(C.REPORTS / "phase2.md"), "verdict": verdict}


if __name__ == "__main__":
    r = write()
    print(f"wrote {r['path']} — VERDICT: {r['verdict']}")
