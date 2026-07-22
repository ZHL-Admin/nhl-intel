"""Phase 1 report: reports/phase1.md — coverage-signature norm, bias mitigation, per-bucket counts."""
from __future__ import annotations

import polars as pl

from . import config as C, scheme_norm as SN

FEATURE_DEFS = {
    "depth": "mean distance of the 5 defenders to the defended net (deep vs stepped-up)",
    "spread": "mean distance to the defenders' centroid (compactness; low = tight box)",
    "netfront": "count of defenders within 15 ft of the net (collapse / net-front load)",
    "marking": "mean distance to the nearest attacker (low = tight man, high = zone/sag)",
    "highest": "distance to net of the highest defender (how far the top of the structure steps up)",
    "strong_frac": "fraction of defenders on the puck's strong side (puck-side loading)",
}


def write():
    r = SN.build()
    sig = pl.read_parquet(SN.SIGNATURES)
    counts = pl.read_parquet(SN.COUNTS)

    L = []; W = L.append
    W("# Phase 1 — The scheme-norm, with goals-only bias mitigation\n")
    W(f"**Defensive Scheme & Role** (`NIR/research/def-scheme/`). Read-only; `make phase1` reproduces. "
      f"Seed {C.SEED}. Universe: 5v5 (n_def=5), real NHL team-seasons (≥20 GA; exhibition rosters excluded).\n")
    W("> **" + C.LAW_1 + "**\n")
    W("> **" + C.LAW_2 + "**\n")

    # 1.1 representation
    W("\n## 1.1 Coverage-signature representation\n")
    W("For each team-season, the typical **five-defender shape as a function of the PUCK situation**, as "
      "**distributions** (mean + spread), not single points — spread is itself part of the signature "
      "(tight = disciplined, wide = variable). Six interpretable geometry features per situation:\n")
    W("| feature | meaning |")
    W("|---|---|")
    for f, d in FEATURE_DEFS.items():
        W(f"| `{f}` | {d} |")
    W("\n**Situation grid (the PUCK's location):** coarse = "
      f"{r['coarse_situ']}; fine = {r['fine_situ']}. \n\n*Design note (flagged for review):* a raw "
      "left/right \"side\" is symmetric and not a distinct scheme situation, so the spec's "
      "\"strong/weak side\" is operationalized as the puck's **lateral band** (mid/slot vs wide/boards) "
      "after folding out left-right symmetry. The coarse grid drops it; the fine grid adds it in the "
      "defensive zone.")
    lg = sig.filter(pl.col("grid") == "coarse").group_by("situation").agg(
        **{f: pl.col("lg_" + f).first() for f in SN.FEATURES}).sort("situation")
    W("\n**League-baseline shape by situation** (the norm ON GOALS every team is read against):\n")
    W("| situation | depth | spread | netfront | marking | highest | strong_frac |")
    W("|---|---|---|---|---|---|---|")
    for row in lg.iter_rows(named=True):
        W(f"| {row['situation']} | {row['depth']:.1f} | {row['spread']:.1f} | {row['netfront']:.2f} | "
          f"{row['marking']:.1f} | {row['highest']:.1f} | {row['strong_frac']:.2f} |")

    # 1.2 bias mitigation
    W("\n## 1.2 Goals-only bias mitigation (Law 1)\n")
    W("The norm learned from a team's OWN goals-against is biased toward broken coverage. Two mitigations:\n")
    W("- **(a) League baseline → deviation.** Each situation's shape is pooled across the whole league's "
      "goals-against; every team-season is then read as a **deviation from league structure** (`dev_*` / "
      "z-scored `z_*` in the signature), not an absolute. The broken-coverage bias common to all teams "
      "cancels in the deviation.")
    W("- **(b) Independent-view agreement + offensive-goals cross-view.** The same frames are, from the "
      "scoring team's side, their OFFENSIVE goals; pooling every team's offensive goals reproduces the "
      "identical league defensive baseline (consistency by construction). The genuinely independent check "
      "of a team's *own* signature is a split-half of its goals-against, reported below.")
    W("\n**Residual bias that cannot be removed (stated honestly):** every view here is still drawn from "
      "GOALS ONLY. There is no tracked non-goal, so the *absolute* coverage shape is a shape-on-goals, and "
      "the selection toward sequences that ended in goals is shared by team, league, and offensive-goals "
      "views alike. Only **relative** (deviation-from-league) claims are made; no view recovers the "
      "team's coverage on non-scoring possessions, which this data does not contain.")

    # per-feature absolute vs team-deviation reproducibility
    W("\n**Signal check (feeds the keystone).** The *absolute* geometry is highly reproducible across "
      "independent goal-halves — it is driven by the situation, common to all teams:\n")
    W("| feature | absolute split-half r |")
    W("|---|---|")
    for f in SN.FEATURES:
        W(f"| {f} | {r['per_feature_abs'][f]:.2f} |")
    W(f"\nBut the **team-specific deviation** — the part that would distinguish one team's scheme from "
      f"another — reproduces only weakly at single-team-season granularity: **standardized split-half "
      f"median r = {r['split_half_median_r']:.2f}**. The gross shape is stable; the team fingerprint on "
      "top of it is faint per season.")

    # 1.3 counts + granularity (THE EMPHASIS)
    W("\n## 1.3 Per-situation sample counts & resolvable granularity\n")
    W("**How many goals-against populate each situation bucket, per team-season** (a goal populates a "
      f"bucket with ≥{SN.MIN_FRAMES_IN_SITU} frames there; min-sample gate = {SN.MIN_CELL_GOALS} GA to "
      "characterize a cell — a thin cell gets **no norm, not a guess**):\n")
    W("| grid | situation | min GA | median GA | team-seasons below gate |")
    W("|---|---|---|---|---|")
    for d in r["per_cell_counts"]:
        W(f"| {d['grid']} | {d['situation']} | {d['min_goals']} | {int(d['med_goals'])} | {d['below_gate']} |")
    for g in r["granularity"]:
        W(f"\n- **{g['grid']} grid** ({g['n_situations']} situations): "
          f"**{g['team_seasons_full']}/{g['n_team_seasons']} team-seasons** populate ALL cells above the "
          f"{SN.MIN_CELL_GOALS}-GA gate (median {g['median_cells_covered']:.0f} cells covered).")
    W("\n### Resolvable granularity — the honest bound for the keystone\n")
    W("**Sample size is NOT the binding constraint at this granularity.** Every team-season fully "
      "populates both the 4-cell coarse and the 6-cell fine puck-situation grids (min 50 GA/cell). A team "
      "defensive norm is therefore *resolvable at the situation level the fine grid describes.*\n")
    W("**The binding constraint is signal, not sample.** Even with ample counts, the team-specific "
      f"deviation reproduces at only ~{r['split_half_median_r']:.2f} within a single season. So the "
      "keystone (Phase 2) should be judged **at the granularity the data supports — the 6-cell puck-"
      "situation grid — and with within-COACH pooling** (multiple seasons of one bench) to lift the team "
      "signal, rather than expecting a sharp per-single-season fingerprint. Going finer than 6 cells is "
      "unnecessary for samples but would not help the signal; going to per-single-season sharp schemes is "
      "where the data is thin — not in counts, but in reproducible team deviation.")

    W("\n## STOP — Phase 1 for owner review (before the Phase 2 keystone)\n")
    W("Coverage signatures built (deviation-from-league, standardized); samples ample to the 6-cell grid; "
      "the team-deviation signal is faint per season and is the keystone's real test. No scheme is named "
      "or claimed in Phase 1.")

    C.REPORTS.mkdir(parents=True, exist_ok=True)
    (C.REPORTS / "phase1.md").write_text("\n".join(L))
    return {"path": str(C.REPORTS / "phase1.md"), "split_half": r["split_half_median_r"]}


if __name__ == "__main__":
    out = write()
    print(f"wrote {out['path']} (team-deviation split-half r={out['split_half']:.2f})")
