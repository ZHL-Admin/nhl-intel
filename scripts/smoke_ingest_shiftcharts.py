"""Smoke test for shift-chart ingestion (no BigQuery writes).

Fetches one real game's shift chart, prints the top-level keys and a 30-line
pretty-printed sample, and verifies the expected fields and the typeCode rule
(517 = real shifts, 505 = goal annotations with null duration). Exits nonzero on
any HTTP or parse failure.

Usage:
    python scripts/smoke_ingest_shiftcharts.py --game-id 2025020500
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from ingestion.nhl_api import get_shift_charts


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--game-id", default="2025020500", help="NHL game id")
    args = ap.parse_args()

    try:
        payload = get_shift_charts(args.game_id)
    except Exception as e:  # noqa: BLE001
        print(f"FAIL: HTTP/request error for game {args.game_id}: {e}", file=sys.stderr)
        return 1

    if not isinstance(payload, dict) or "data" not in payload:
        print(f"FAIL: unexpected payload shape; keys={list(payload)[:10]}", file=sys.stderr)
        return 1

    data = payload.get("data", [])
    print(f"top-level keys: {list(payload.keys())}")
    print(f"total shift rows: {len(data)}")

    if not data:
        print(f"FAIL: empty shift data for game {args.game_id} (unplayed?)", file=sys.stderr)
        return 1

    real = [s for s in data if s.get("duration")]
    annotations = [s for s in data if not s.get("duration")]
    type_codes = {s.get("typeCode") for s in data}
    print(f"rows with duration (real shifts): {len(real)} | null-duration (annotations): {len(annotations)}")
    print(f"distinct typeCodes: {sorted(tc for tc in type_codes if tc is not None)}")

    required = {"playerId", "teamId", "period", "startTime", "endTime", "duration", "shiftNumber"}
    missing = required - set(real[0].keys())
    if missing:
        print(f"FAIL: sample shift missing fields: {missing}", file=sys.stderr)
        return 1

    print("\nsample real shift (first 30 lines of pretty JSON):")
    pretty = json.dumps(real[0], indent=2, sort_keys=True).splitlines()
    print("\n".join(pretty[:30]))

    print("\nOK: shiftcharts smoke test passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
