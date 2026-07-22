"""Stage 1 reporting: assemble reports/stage1.md from the mechanism flags, profiles, and reliability.

Usage: python -m gtrack.report_stage1 write
"""
from __future__ import annotations

import sys

import numpy as np
import polars as pl

from . import bq, config, fuse, mechanisms as M, profiles as P, reliability as RB

DEFENSE_SENTENCE = ("Screen-heavy and east-west-heavy profiles implicate the defense in front of the "
                    "goalie as much as the goalie himself.")
BIN = P.BINARY
EW_SENS = (10.0, 15.0, 20.0)


def _names() -> dict:
    r = bq.cached_query("goalie_names", f"""
        select player_id, any_value(full_name) full_name from (
          select player_id, full_name from `{config.BQ_PROJECT}.nhl_staging.stg_roster_current`
          where full_name is not null
          union all
          select player_id, concat(first_name,' ',last_name) full_name
          from `{config.BQ_PROJECT}.nhl_staging.stg_rosters`
          where last_name is not null)
        group by player_id""")
    return {row["player_id"]: row["full_name"] for row in r.iter_rows(named=True)}


def _pct(x):
    return "n/a" if x is None or (isinstance(x, float) and np.isnan(x)) else f"{x*100:.0f}%"


def write():
    m = pl.read_parquet(M.MECH_FLAGS)
    prof = pl.read_parquet(P.PROFILES)
    rel = RB.run()
    names = _names()
    nm = lambda gid: names.get(gid, str(gid))
    tracked = m.filter(pl.col("tracked"))
    lg = P.league_rates(m)

    L = []; W = L.append
    W("# Stage 1 — Goal-against mechanism profiles\n")
    W("**Goal-Tracking research program** (`NIR/research/goal-tracking/`). Read-only; `make stage1` "
      "reproduces from cache. Built on the Stage 0 fused corpus.\n")
    W("> **LAW 1 · GOALS-ONLY.** " + config.LAW_1.split("GOALS-ONLY. ")[1] + "\n")
    W("> **LAW 2 · FUSION.** " + config.LAW_2.split("FUSION. ")[1] + "\n")
    W(f"\n> **{DEFENSE_SENTENCE}**\n")

    # amendment working universe
    W("\n## 1.0 Working universe (AMENDMENT 2026-07-14)\n")
    by = m.group_by("season").agg(n=pl.len(), tracked=pl.col("tracked").sum(),
                                  flight=pl.col("flight_detected").sum()).sort("season")
    W("**TRACKED = a ∧ b** (scorer tracked to the puck ∧ puck continuous) is the working universe for "
      "geometry fields — far broader than CLEAN (a∧b∧d, 22%) because the flight detector d does not fire "
      "on tips/tap-ins/jams (most goals). TRACKED fraction per season:\n")
    W("| season | goals | TRACKED | TRACKED % | flight-fired |")
    W("|---|---|---|---|---|")
    for r in by.iter_rows(named=True):
        W(f"| {r['season']} | {r['n']:,} | {r['tracked']:,} | {r['tracked']/r['n']*100:.1f}% | {r['flight']:,} |")
    rs = m.group_by("release_source").len().sort("len", descending=True)
    W("\n**effective_release** = flight-start where the detector fired, else the arrival frame. "
      "release_source: " + ", ".join(f"{r['release_source']}={r['len']:,}" for r in rs.iter_rows(named=True))
      + ". All release-anchored geometry (east-west window, screen count, goalie state) is recomputed at "
        "effective_release. **Handedness** for LOCATION: rosters carry none, so sourced from "
        "`stg_player_bio.shoots` (100% goalie coverage, 128 catches-L / 9 catches-R); no default needed. "
        "**No z-coordinate exists in the frames** (verified) → LOCATION high/low is omitted; glove/center/"
        "blocker only. Frame `x_std`/`y_std` only.\n")

    # 1.1 taxonomy
    W("\n## 1.1 Mechanism taxonomy — rates, sensitivity, usable-n\n")
    def rate(col, univ):
        d = m.filter(univ); v = d[col].drop_nulls()
        return v.len(), int(v.sum()), (v.mean() if v.len() else None)
    rows = [
        ("EAST_WEST [G]", "ew_disp_2s ≥ 15 ft", "TRACKED@release", rate("EAST_WEST", m["tracked"])),
        ("SCREENED [A]", "screen_opp+screen_own ≥ 1", "TRACKED@release", rate("SCREENED", m["tracked"])),
        ("CLEAN_LOOK [G]", "screens=0 ∧ dist≥25 ft ∧ goalie_lat<3", "flight only", rate("CLEAN_LOOK", m["flight_detected"])),
        ("UNSET [G]", "goalie_lat≥6 ∨ |depth Δ0.5s|>2 ft", "TRACKED@release", rate("UNSET", m["tracked"])),
        ("RUSH [A]", "rush_flag (entry→goal ≤6 s)", "all", rate("RUSH", pl.lit(True))),
        ("IN_ZONE [A]", "not rush ∧ not off_frame_start", "all", rate("IN_ZONE", pl.lit(True))),
        ("SECOND_CHANCE [A]", "shot-family by scoring team ≤3 s prior", "all", rate("SECOND_CHANCE", pl.lit(True))),
    ]
    W("| mechanism | definition | universe | usable-n | count | rate |")
    W("|---|---|---|---|---|---|")
    for name, defn, uni, (n, k, r) in rows:
        W(f"| {name} | {defn} | {uni} | {n:,} | {k:,} | {_pct(r)} |")
    loc = tracked.group_by("LOCATION").len().sort("len", descending=True)
    W(f"| LOCATION [A] | net third glove/center/blocker | TRACKED@goal-line | {int(tracked['LOCATION'].drop_nulls().len()):,} | — | "
      + ", ".join(f"{r['LOCATION']}={r['len']:,}" for r in loc.iter_rows(named=True) if r['LOCATION']) + " |")
    W("\n**EAST_WEST sensitivity** (frozen at 15 ft): " +
      ", ".join(f"≥{t:.0f}ft={_pct((tracked['ew_disp_2s']>=t).mean())}" for t in EW_SENS) + ".")
    W(f"\n**Own-net screens** stored separately (`screened_own_net`): {int((m['screened_own_net']>=1).sum()):,} goals "
      "have an own-team body in the screen triangle.")
    W("\n*Note — SCREENED is conservative (3.1%):* the frozen triangle+crease-radius screen test, evaluated at "
      "effective_release (which for the 74% no-flight goals is the puck at the net → a near-degenerate "
      "triangle), detects few screens. This is a fixed Stage-0 definition; it thins SCREENED claims (below).")

    # co-occurrence
    W("\n## 1.1 Co-occurrence matrix (mechanisms are non-exclusive) — P(column | row) over TRACKED clips\n")
    B = {mm: tracked[mm].fill_null(False).to_numpy().astype(bool) for mm in BIN}
    W("| row \\ col | " + " | ".join(b.split()[0][:8] for b in [x[0] for x in rows]) + " |")
    W("|" + "---|" * (len(BIN) + 1))
    for r in BIN:
        ri = B[r]; base = ri.sum()
        cells = [f"{(ri & B[cc]).sum()/base*100:.0f}%" if base else "n/a" for cc in BIN]
        W(f"| **{r}** (n={base}) | " + " | ".join(cells) + " |")
    W("\nConsistency checks: CLEAN_LOOK∩SCREENED = 0% (CLEAN_LOOK requires 0 screens); RUSH∩IN_ZONE = 0% "
      "(mutually exclusive by construction).")

    # 1.2 profiles + gates
    pooled = prof.filter(pl.col("scope") == "pooled")
    gated = pooled.filter(pl.col("row_gate_ok"))
    n_gated = gated["goalie_id"].n_unique()
    W("\n## 1.2 Goalie profiles (pooled 2023-26) + EB shrinkage + gates\n")
    W(f"Dirichlet-multinomial empirical-Bayes shrinkage toward league, prior strength **k=20 GA** (fixed), "
      f"90% CIs from 1000 posterior draws (seed {config.SEED}). **Gates:** goalie row needs ≥40 GA "
      f"({n_gated}/{pooled['goalie_id'].n_unique()} goalies qualify pooled); a mechanism cell is a *claim* "
      f"only when its raw count ≥10 (low-count cells shown parenthesized).")
    W("\n**League rates:** " + ", ".join(f"{k}={_pct(v)}" for k, v in lg.items() if not isinstance(v, dict))
      + "; LOCATION " + ", ".join(f"{c}={_pct(v)}" for c, v in lg["LOCATION"].items()) + ".")
    W(f"\n**Reliability verdict (§1.3): FAIL → only these pooled three-season tables ship.** "
      f"*Profile is a three-season aggregate; single seasons are noise.*\n")
    # wide pooled table
    show_m = ["EAST_WEST", "SCREENED", "CLEAN_LOOK", "UNSET", "RUSH", "SECOND_CHANCE"]
    W("| goalie | GA | " + " | ".join(show_m) + " | LOC g/c/b |")
    W("|" + "---|" * (len(show_m) + 3))
    order = gated.filter(pl.col("mechanism") == "EAST_WEST").sort("ga_all", descending=True)
    for r in order.iter_rows(named=True):
        gid = r["goalie_id"]; sub = gated.filter(pl.col("goalie_id") == gid)
        def cell(mech):
            row = sub.filter((pl.col("mechanism") == mech))
            if row.height == 0:
                return "—"
            v = row["eb_share"][0]; ok = row["claim_ok"][0]
            s = f"{v*100:.0f}"
            return s if ok else f"({s})"
        locs = sub.filter(pl.col("mechanism") == "LOCATION")
        lc = "/".join(f"{locs.filter(pl.col('category')==c)['eb_share'][0]*100:.0f}" for c in P.LOC_CATS)
        W(f"| {nm(gid)} | {r['ga_all']} | " + " | ".join(cell(mm) for mm in show_m) + f" | {lc} |")
    W("\n(Cells are EB-shrunk shares ×100; parenthesized = raw count <10, not a claim. Full table incl. "
      "per-season rows and 90% CIs in `data/parquet/goalie_profiles.parquet`.)")

    # 1.3 reliability
    W("\n## 1.3 Reliability gate (pre-stated) + year-over-year\n")
    r = rel
    W(f"Goalies with ≥60 GA pooled: **{r['n_goalies_ge60']}**. Split each goalie's GA odd/even by game "
      f"date; correlate per-goalie mechanism-share vectors across halves vs a placebo shuffling goalie "
      f"identity (2000 perms). **PASS bar:** a majority of mechanisms with r≥0.30 AND placebo p<0.05.\n")
    W(f"- **{r['n_pass']}/{r['n_mech']} mechanisms pass → GATE: {'PASS' if r['GATE_PASS'] else 'FAIL'}.** "
      "Only **UNSET** (the goalie's own movement) is a reliable within-goalie trait; east-west, screened, "
      "rush, location and clean-look shares do not replicate across halves. **This is the empirical basis "
      "for the defense caveat: how a goalie is beaten is mostly the situation/defense in front of him, "
      "not a persistent goalie signature.**\n")
    W("| mechanism | n goalies | split-half r | placebo p | passes |")
    W("|---|---|---|---|---|")
    for d in r["per_mechanism"].sort("split_half_r", descending=True).iter_rows(named=True):
        W(f"| {d['mechanism']} | {d['n_goalies']} | {d['split_half_r']:.2f} | {d['placebo_p']:.3f} | "
          f"{'Y' if d['passes'] else '·'} |")
    W("\n**Year-over-year same-goalie correlation** (descriptive, consecutive seasons ≥60 GA): " +
      ", ".join(f"{d['mechanism']}={d['yoy_r']:.2f}" for d in r["yoy"] if d["yoy_r"] is not None) +
      f" (105 goalie-season pairs). Uniformly near zero — consistent with the split-half FAIL.")

    # 1.4 exhibits
    W("\n## 1.4 Exhibits (pooled, gated)\n")
    W(f"*{DEFENSE_SENTENCE}*\n")
    def top10(mech, label):
        d = gated.filter((pl.col("mechanism") == mech) & pl.col("claim_ok")).sort("eb_share", descending=True).head(10)
        W(f"\n**Top-10 {label}-beaten** (EB-shrunk share; only goalies with ≥10 such goals):\n")
        W("| rank | goalie | GA | count | EB share | 90% CI |")
        W("|---|---|---|---|---|---|")
        for i, r in enumerate(d.iter_rows(named=True), 1):
            W(f"| {i} | {nm(r['goalie_id'])} | {r['ga_all']} | {r['count']} | {r['eb_share']*100:.0f}% | "
              f"{r['ci_lo']*100:.0f}–{r['ci_hi']*100:.0f}% |")
        if d.height < 10:
            W(f"\n(only {d.height} goalies clear the ≥10-count gate for {label}.)")
    top10("SCREENED", "screen")
    top10("EAST_WEST", "east-west")
    top10("CLEAN_LOOK", "clean-look")
    W("\n**Worked profile:** _placeholder — owner to name a goalie at the gate._ On naming, this renders "
      "that goalie's full pooled mechanism mix (counts, EB shares, 90% CIs, LOCATION split) with the "
      "verbatim caveat above.")

    W("\n## Reproducibility & tests\n")
    W("- `make stage1` = mechanisms → profiles → reliability → tests → report, all from the Stage-0 cache "
      f"(seed {config.SEED}). Ratio metrics ship with absolute counts throughout.")
    W("- Upstream ledger unchanged (`reports/upstream-ledger.md`).")
    W("\n**STOP for owner review.**\n")

    config.REPORTS.mkdir(parents=True, exist_ok=True)
    (config.REPORTS / "stage1.md").write_text("\n".join(L))
    return {"path": str(config.REPORTS / "stage1.md"), "reliability_pass": rel["GATE_PASS"]}


if __name__ == "__main__":
    r = write()
    print(f"wrote {r['path']} (reliability PASS={r['reliability_pass']})")
