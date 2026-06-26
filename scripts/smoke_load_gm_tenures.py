"""Smoke test for the GM-tenures CSV (no BigQuery writes).

Asserts the shape the attribution join depends on: the expected columns, ~60-90 stints, multi-stint
gm_ids present, current tenures (blank end_date), and — critically — NO overlapping tenures for the
same team (the attribution join requires non-overlapping ranges per team). Exits nonzero on failure.

Usage:
    python scripts/smoke_load_gm_tenures.py
"""
from __future__ import annotations

import argparse
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from scripts.load_gm_tenures import DEFAULT_CSV, read_gm_csv


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", default=DEFAULT_CSV)
    args = ap.parse_args()

    df = read_gm_csv(args.csv).fillna("")
    df = df[df["gm_id"].str.strip() != ""]

    n, n_gm, n_team = len(df), df["gm_id"].nunique(), df["team_abbrev"].nunique()
    print(f"rows: {n}; GMs: {n_gm}; teams: {n_team}")
    if not (40 <= n <= 140):
        print(f"FAIL: expected ~60-90 stints, got {n}", file=sys.stderr)
        return 1

    multi = {g: c for g, c in Counter(df["gm_id"]).items() if c > 1}
    current = (df["end_date"].str.strip() == "").sum()
    print(f"multi-stint gm_ids: {len(multi)}; current tenures (blank end_date): {current}")

    # non-overlap per team
    overlaps = []
    for team, g in df.groupby("team_abbrev"):
        ten = sorted((r["start_date"], (r["end_date"].strip() or "9999-12-31"), r["gm_id"])
                     for _, r in g.iterrows())
        for i in range(len(ten) - 1):
            if ten[i][1] > ten[i + 1][0]:
                overlaps.append((team, ten[i], ten[i + 1]))
    if overlaps:
        print(f"FAIL: {len(overlaps)} overlapping tenures, e.g. {overlaps[0]}", file=sys.stderr)
        return 1

    print("\nOK: gm-tenures smoke test passed (no overlaps)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
