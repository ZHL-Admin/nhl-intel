"""Smoke test for partner-odds ingestion (no BigQuery writes).

Fetches the current partner-game snapshot and verifies the envelope. In the
offseason games[] is empty — that is reported, not failed (the surface still
ingests snapshots). INTERNAL CALIBRATION ONLY (blueprint 13.2).

Usage:
    python scripts/smoke_ingest_partner_odds.py --country US
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from ingestion.nhl_api import get_partner_odds


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--country", default="US")
    args = ap.parse_args()

    try:
        payload = get_partner_odds(args.country)
    except Exception as e:  # noqa: BLE001
        print(f"FAIL: request error: {e}", file=sys.stderr)
        return 1

    if "games" not in payload or "bettingPartner" not in payload:
        print(f"FAIL: unexpected envelope; keys={list(payload)}", file=sys.stderr)
        return 1

    games = payload.get("games", [])
    print(f"currentOddsDate: {payload.get('currentOddsDate')}")
    print(f"bettingPartner: {payload.get('bettingPartner', {}).get('name')}")
    print(f"games: {len(games)}")
    if games:
        print("sample game keys:", list(games[0].keys()))
        print(json.dumps(games[0], indent=2)[:600])
    else:
        print("(offseason: no games in snapshot — envelope OK, odds parse pending in-season)")

    print("\nOK: partner odds smoke test passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
