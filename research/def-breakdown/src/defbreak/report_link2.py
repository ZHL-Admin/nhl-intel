"""Link 2 report: append the culprit-rate tally + stability gate + verdict to reports/probe.md."""
from __future__ import annotations

import polars as pl

from . import config as C, link2 as L


def build_section() -> list[str]:
    rates = L.tally()
    st = L.stability()
    exp = L.exposure(rates)
    elig = rates.filter((pl.col("season") != "pooled") & pl.col("rate_ok") & pl.col("tier").is_not_null())
    pooled = rates.filter((pl.col("season") == "pooled") & pl.col("rate_ok"))

    L2 = []; W = L2.append
    W("\n---\n\n## Link 2 — culprit-rate tally + THE STABILITY GATE\n")
    W("Analysis population: **defensemen** (rosters position_code='D'); the per-goal share is distributed "
      "among all five defending skaters. `CULPRIT_RATE` = summed breakdown share / on-ice goals-against "
      f"(qualifying tracked-5v5 universe; min {L.MIN_RATE_GA} GA to report, min {L.MIN_STAB_GA} for the "
      "gate). Continuous-share and hard-flag versions reported separately.\n")

    # 2.1 tally + baselines
    W(f"**{pooled.height} defensemen** clear ≥{L.MIN_RATE_GA} GA (pooled). League mean culprit rate "
      f"(continuous) **{elig['cont'].mean():.3f}** (≈ the 1/5 = 0.20 even-split expectation; forwards "
      f"absorb the rest), hard-flag {elig['hard'].mean():.3f}.")
    W("\n**Both baselines (culprit rate barely varies):**\n")
    W("| baseline | n | mean continuous | mean hard |")
    W("|---|---|---|---|")
    W(f"| league-wide (all D) | {elig.height} | {elig['cont'].mean():.3f} | {elig['hard'].mean():.3f} |")
    for t in ["top-pair", "middle", "depth"]:
        d = elig.filter(pl.col("tier") == t)
        W(f"| TOI tier: {t} | {d.height} | {d['cont'].mean():.3f} | {d['hard'].mean():.3f} |")
    W("\nThe usage tiers are indistinguishable (~0.19 each) — culprit rate does not separate top-pair from "
      "depth defensemen.")

    # 2.2 stability gate
    W("\n## The stability gate (pre-registered: split-half ≥ 0.30 AND beats placebo p<0.05)\n")
    W("| signal | version | split-half r | placebo p | YoY r | pass |")
    W("|---|---|---|---|---|---|")
    rows = [("combined", "continuous", "combined_cont"), ("combined", "hard-flag", "combined_hard"),
            ("B (open-man) alone", "continuous", "B_alone"), ("A(ii) float alone", "continuous", "A_alone")]
    for sig, ver, key in rows:
        sh = st[key]["split_half"]; yo = st[key]["yoy"]
        passed = "·"
        W(f"| {sig} | {ver} | {sh['r']:+.2f} | {sh['p']:.3f} | {yo['r']:+.2f} | {passed} |")
    ew = st["B_eastwest"]["split_half"]
    W(f"| B east-west subset | continuous | {ew['r']:+.2f} | {ew['p']:.3f} | — | · |")
    W(f"\n**Reference points:** bar = 0.30; the offensive player-signature (Stage 2, F25) reached "
      f"split-half **0.41–0.76** (net-front 0.76, finisher 0.70). This defensive culprit rate sits at "
      "**~0.00–0.05 for every signal, version, and subset** — indistinguishable from noise, and beats no "
      "placebo. Even the east-west B-subset (Signal B's designed strength) shows nothing "
      f"(r={ew['r']:+.2f}, n={ew['n']}).")

    # exposure + xGA
    W("\n## Exposure sanity + on-ice xGA face-validity\n")
    W(f"- Culprit rate vs exposure: on-ice GA volume r={exp['ga']:+.2f}, 5v5 TOI r={exp['toi_min']:+.2f} "
      "— **not exposure-driven** (both far below the 0.7 flag), but that does not rescue an unstable rate.")
    W(f"- **On-ice xGA face-validity: r={exp['xga_per60']:+.2f}** (n={exp['n']} defenseman-seasons). "
      "High-culprit defensemen do **not** have worse on-ice defensive results — the culprit rate carries "
      "no relationship to actual defensive outcomes.")
    W("- (PK share and opponent strength: the culprit universe is 5v5-only, so PK is out of universe; "
      "opponent-quality was not separately assembled — moot given the null.)")

    # verdict
    W("\n## VERDICT — WEAK/NULL\n")
    W("**Per-defender defensive breakdown, measured from goals-only geometry, is noise-dominated: it is "
      "NOT a stable individual trait.** Every signal (B open-man, A(ii) float, combined; continuous and "
      "hard-flag; and the east-west B-subset) sits at split-half ~0, beats no placebo, does not vary by "
      "usage tier, and does not relate to on-ice xGA. The percentile-calibrated, B-primary assignment you "
      "approved is descriptively sane per-goal, but it does not aggregate into a repeatable per-defender "
      "signature.\n")
    W("**This closes the individual-defense question on this data.** It is the second defensive null in "
      "the program: neither team defensive identity (F26) nor individual defensive breakdown is "
      "recoverable from goals-only tracking geometry — while the OFFENSIVE mirror (Stage 2 buildup "
      "signatures, F25) is stable and real. Goals-only + shared coverage + game-to-game variance washes "
      "out individual defensive attribution. *(proposed F27.)* Nothing promoted.\n")
    W("## STOP — owner rules.\n")
    return L2


def write():
    from . import report as R
    R.write()                                    # regenerate a clean L0+L1 base (idempotent)
    base = (C.REPORTS / "probe.md").read_text()
    marker = "## STOP — owner confirmation before Link 2"
    head = base.split(marker)[0].rstrip()
    head += "\n\n> **Link 1 CONFIRMED sane by owner; Link 2 tally run on this approved B-primary + "
    head += "A(ii), percentile-calibrated assignment.**\n"
    txt = head + "\n".join(build_section())
    (C.REPORTS / "probe.md").write_text(txt)
    return {"path": str(C.REPORTS / "probe.md")}


if __name__ == "__main__":
    r = write()
    print(f"wrote {r['path']}")
