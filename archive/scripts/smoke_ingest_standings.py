"""Smoke test for standings-by-date ingestion (no BigQuery writes).

Fetches standings for one date, verifies the fields stg_standings parses (ranks,
record, last-10), and prints the league leader. Exits nonzero on failure.
Defaults to an in-season date (offseason dates return zero rows).

Usage:
    python scripts/smoke_ingest_standings.py --date 2026-01-15
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from ingestion.nhl_api import get_standings_by_date


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default="2026-01-15", help="In-season date YYYY-MM-DD")
    args = ap.parse_args()

    try:
        payload = get_standings_by_date(args.date)
    except Exception as e:  # noqa: BLE001
        print(f"FAIL: request error: {e}", file=sys.stderr)
        return 1

    rows = payload.get("standings", [])
    print(f"standings rows for {args.date}: {len(rows)}")
    if not rows:
        print(f"FAIL: no standings for {args.date} (offseason date?)", file=sys.stderr)
        return 1

    required = {"teamAbbrev", "points", "wins", "losses", "otLosses",
                "leagueSequence", "conferenceSequence", "divisionSequence", "l10Wins"}
    missing = required - set(rows[0].keys())
    if missing:
        print(f"FAIL: missing fields: {missing}", file=sys.stderr)
        return 1

    leader = min(rows, key=lambda r: r.get("leagueSequence") or 999)
    print("league leader:", json.dumps({
        "team": leader.get("teamAbbrev", {}).get("default"),
        "points": leader.get("points"),
        "record": f"{leader.get('wins')}-{leader.get('losses')}-{leader.get('otLosses')}",
        "l10": f"{leader.get('l10Wins')}-{leader.get('l10Losses')}-{leader.get('l10OtLosses')}",
    }, indent=2))
    print("\nOK: standings smoke test passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
