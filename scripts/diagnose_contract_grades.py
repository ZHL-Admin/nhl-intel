"""Contract-grade regression diagnostics — PRINT ONLY, changes nothing.

Three checks the grading work depends on:
  1. ROUND-TRIP — does Step-3 invert (share -> effective WAR) reproduce under Step-6 reprice
     (effective WAR -> share)? Exact below the knee == invert and reprice share one curve.
  2. BASKET — do consensus contracts (steals / fair / albatrosses) land in their expected band?
  3. DISTRIBUTION — leaguewide surplus-to-cost ratio + grade histogram across signed contracts.
     A calibrated model centers near C (fair); a heavy A/B or D/F skew flags the Step-4 quantile.

Run:  python -m scripts.diagnose_contract_grades   (uses SERVING_BACKEND env; bigquery or duckdb)
"""
from __future__ import annotations

import sys
from collections import Counter
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "backend"))

import numpy as np  # noqa: E402

SEASON = "2025-26"

BASKET = [
    ("celebrini",      0.975e6, 2, "steal",     {"A", "B"}),
    ("makar",          9.0e6,   6, "steal",     {"A", "B"}),
    ("kucherov",       9.5e6,   3, "steal",     {"A", "B"}),
    ("barzal",         9.15e6,  6, "fair",      {"B", "C", "D"}),
    ("seth jones",     9.5e6,   4, "fair",      {"B", "C", "D"}),
    ("huberdeau",     10.5e6,   6, "albatross", {"D", "F"}),
    ("darnell nurse",  9.25e6,  5, "albatross", {"D", "F"}),
    ("erik karlsson", 11.5e6,   2, "albatross", {"D", "F"}),
]


def main() -> int:
    from services import contract_grade as cg
    from services.contract_grade import grade_contract, grade_from_surplus
    from services.bigquery import bq_service
    from models_ml.compute_contract_value import market_cap_share, inverse_market_share
    from models_ml import config

    # ---------------------------------------------------------------- 1. round-trip
    print("=" * 70)
    print("1. ROUND-TRIP  market_cap_share(inverse_market_share(s)) - s")
    m = cg._market_for(SEASON)
    cap = config.CAP_UPPER_LIMIT_BY_SEASON[SEASON]
    for pg in ("F", "D", "G"):
        knee, ceil = m["knee"][pg], m["ceil"][pg]      # per-position soft-cap
        below = np.linspace(0.01, knee * 0.98, 10)
        above = np.linspace(knee * 1.02, ceil * 0.99, 6)
        eb = max(abs(market_cap_share(m, pg, inverse_market_share(m, pg, s)) - s) for s in below)
        ea = max(abs(market_cap_share(m, pg, inverse_market_share(m, pg, s)) - s) for s in above)
        print(f"   {pg}: knee ${knee*cap/1e6:.1f}M ceil ${ceil*cap/1e6:.1f}M | "
              f"max|err| below knee = {eb:.2e}   above knee = {ea:.4f} (intended soft-cap)")

    # ---------------------------------------------------------------- 2. basket
    print("=" * 70)
    print("2. VALIDATION BASKET (consensus deals -> expected band)")
    ros = bq_service.get_models_table_id("dim_current_roster")
    print(f"   {'player':16}{'cap$M':>6}{'yr':>3}{'kind':>10}{'grade':>6}{'ratio':>8}  expect  result")
    npass = 0
    for nm, cap, term, kind, allowed in BASKET:
        rows = bq_service.query(f"SELECT player_id FROM {ros} WHERE name_lower LIKE '%{nm}%' LIMIT 1")
        if not rows:
            print(f"   {nm:16} NOT FOUND"); continue
        g = grade_contract(rows[0]["player_id"], cap, term, SEASON)
        ratio = g["total_discounted_surplus"] / g["cost_dollars"] if g["cost_dollars"] else 0.0
        ok = g["grade"] in allowed
        npass += ok
        print(f"   {nm[:15]:16}{cap/1e6:6.2f}{term:3}{kind:>10}{g['grade']:>6}{ratio:+8.2f}"
              f"  {''.join(sorted(allowed)):>5}  {'PASS' if ok else 'FAIL'}")
    print(f"   basket: {npass}/{len(BASKET)} in expected band")

    # ---------------------------------------------------------------- 3. distribution
    print("=" * 70)
    print("3. DISTRIBUTION (signed contracts) — calibrated on the NON-ELC market population")
    pcv = bq_service.get_models_table_id("player_contract_value")
    mart = bq_service.get_full_table_id("mart_player_contracts")
    rows = bq_service.query(f"""
        SELECT v.total_discounted_surplus s, v.cost_dollars c, v.surplus_flat_dollars flat, mc.is_elc
        FROM {pcv} v JOIN {mart} mc ON v.player_id = mc.player_id AND v.as_of_date = mc.as_of_date
        WHERE mc.contract_status = 'signed' AND v.cost_dollars > 0""")
    R = [dict(r) for r in rows]

    def line(label, rs):
        h = Counter(grade_from_surplus(r["s"], r["c"])["grade"] for r in rs)
        n = len(rs)
        med = float(np.median([r["s"] / r["c"] for r in rs]))
        band = grade_from_surplus(med, 1.0)["grade"]
        print(f"   {label} (n={n}): " + " ".join(f"{k}:{100*h[k]/n:.0f}%" for k in "ABCDF")
              + f"   median={med:+.3f} -> {band}")

    non_elc = [r for r in R if not r["is_elc"]]
    elc = [r for r in R if r["is_elc"]]
    line("NON-ELC (market, the calibration target)", non_elc)
    line("ELC (CBA-capped, reported separately) ", elc)
    line("FULL signed population                ", R)
    # player-skill surplus = total - cap-growth = the frozen-cap (flat) surplus; this is the calibration
    # target (Gate 2 read on player skill), since cap-growth is real value kept in the grade but separate.
    capg = float(np.median([(r["s"] - r["flat"]) / r["c"] for r in non_elc]))
    skill = float(np.median([r["flat"] / r["c"] for r in non_elc]))
    print(f"   median cap-growth contribution (non-ELC) = {capg:+.3f}  (real asset value, decomposed not stripped)")
    print(f"   non-ELC PLAYER-SKILL median (cap frozen) = {skill:+.3f} -> {grade_from_surplus(skill, 1.0)['grade']}  "
          "(the calibration read: fair on skill; the total-median residual is the cap-growth bonus)")
    print(f"   curve fit: two-anchor pivot  LO={config.CONTRACT_VALUE.get('MARKET_ANCHOR_LO')} "
          f"HI={config.CONTRACT_VALUE.get('MARKET_ANCHOR_HI')}  (bands A>=+0.30 B>=+0.12 C>=-0.12 D>=-0.30 F<-0.30)")
    print("   target: non-ELC median in the C band; ELCs ~100% A by construction; full stays A-heavy "
          "(many NHL deals are genuinely cheap) — that is the honest result.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
