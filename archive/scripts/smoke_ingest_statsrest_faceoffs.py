"""Smoke test for stats-REST faceoff ingestion (no BigQuery writes).

Fetches one page of skater/faceoffwins for a season, verifies the zone + strength
split fields are present, and prints a sample record. Exits nonzero on failure.

Usage:
    python scripts/smoke_ingest_statsrest_faceoffs.py --season 20242025
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from ingestion.nhl_api import _get_statsrest_page


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--season", default="20242025", help="Season YYYYYYYY")
    ap.add_argument("--game-type", type=int, default=2)
    args = ap.parse_args()

    try:
        page = _get_statsrest_page("faceoffwins", args.season, args.game_type, 5, 0)
    except Exception as e:  # noqa: BLE001
        print(f"FAIL: request error: {e}", file=sys.stderr)
        return 1

    data = page.get("data", [])
    print(f"season total players: {page.get('total')}")
    print(f"page rows: {len(data)}")
    if not data:
        print("FAIL: empty faceoff data", file=sys.stderr)
        return 1

    required = {
        "playerId", "offensiveZoneFaceoffWins", "neutralZoneFaceoffWins",
        "defensiveZoneFaceoffWins", "evFaceoffsWon", "ppFaceoffsWon",
        "shFaceoffsWon", "totalFaceoffs",
    }
    missing = required - set(data[0].keys())
    if missing:
        print(f"FAIL: missing fields: {missing}", file=sys.stderr)
        return 1

    sample = max(data, key=lambda r: r.get("totalFaceoffs") or 0)
    print("\nsample record (highest-volume of page):")
    print(json.dumps({k: sample[k] for k in sorted(required)}, indent=2))
    print("\nOK: statsrest faceoffs smoke test passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
