"""Smoke test for glossary ingestion (no BigQuery writes).

Fetches the stats-REST glossary and verifies term records. Exits nonzero on failure.

Usage:
    python scripts/smoke_ingest_glossary.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from ingestion.nhl_api import get_glossary


def main() -> int:
    try:
        payload = get_glossary()
    except Exception as e:  # noqa: BLE001
        print(f"FAIL: request error: {e}", file=sys.stderr)
        return 1

    data = payload.get("data", [])
    print(f"glossary terms: {len(data)}")
    if not data:
        print("FAIL: empty glossary", file=sys.stderr)
        return 1

    required = {"id", "abbreviation", "definition"}
    missing = required - set(data[0].keys())
    if missing:
        print(f"FAIL: missing fields: {missing}", file=sys.stderr)
        return 1

    print("sample term:", json.dumps(data[0], indent=2)[:300])
    print("\nOK: glossary smoke test passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
