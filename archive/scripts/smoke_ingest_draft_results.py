"""Smoke test for historical draft-results ingestion (no BigQuery writes).

Fetches one draft year, flattens it through the ingest path, and asserts the shape the staging model
and the never-NHL=0 denominator depend on: a full draft (~200+ picks), dense overall pick 1..N with no
gaps, no null overall, rounds within 1..9. Exits nonzero on failure.

Usage:
    python scripts/smoke_ingest_draft_results.py --year 2015
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from scripts.ingest_draft_results import fetch_year


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--year", type=int, default=2015, help="Completed draft year")
    args = ap.parse_args()

    try:
        rows = fetch_year(args.year)
    except Exception as e:  # noqa: BLE001
        print(f"FAIL: request error: {e}", file=sys.stderr)
        return 1

    print(f"draft {args.year}: {len(rows)} picks")
    if len(rows) < 180:
        print(f"FAIL: expected ~200+ picks for a 7-round draft, got {len(rows)}", file=sys.stderr)
        return 1

    overalls = [r["overall_pick"] for r in rows]
    if any(o is None for o in overalls):
        print("FAIL: null overall_pick present", file=sys.stderr)
        return 1
    overalls_sorted = sorted(overalls)
    if overalls_sorted != list(range(1, len(overalls) + 1)):
        gaps = set(range(1, len(overalls) + 1)) - set(overalls)
        print(f"FAIL: overall_pick not dense 1..{len(overalls)} (gaps: {sorted(gaps)[:10]})", file=sys.stderr)
        return 1

    rounds = sorted({r["round"] for r in rows})
    if rounds[0] < 1 or rounds[-1] > 9:
        print(f"FAIL: rounds out of 1..9: {rounds}", file=sys.stderr)
        return 1

    if len(set(overalls)) != len(overalls):
        print("FAIL: duplicate overall_pick", file=sys.stderr)
        return 1

    first = rows[0]
    print(f"  #1 overall: {first['full_name']} ({first['position_code']}, {first['team_abbrev']})")
    print(f"  rounds: {rounds}; overall dense 1..{len(overalls)}")
    print("\nOK: draft-results smoke test passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
