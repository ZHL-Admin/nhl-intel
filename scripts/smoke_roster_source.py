"""STEP-0 smoke for the offseason roster-forecast tool: resolve the roster data source.

The forecast needs two roster snapshots per team:
  - BASE  (prior season-end membership): game-derived from stg_rosters (accurate for a COMPLETED
           season) — the latest game per player that season, team-type filter 01/02/03.
  - UPDATED (current membership): the LIVE roster feed this repo already ingests
           (ingestion.nhl_api.get_roster -> max(/roster-season) -> /v1/roster/{TEAM}/{season8};
           the /current path is a 307, see scripts/ROSTER_FINDINGS.md), surfaced through
           stg_roster_current / int_player_current_team / dim_current_roster.

This smoke exercises the UPDATED source (the only one that reflects offseason signings/trades,
since the offseason has no games). It fetches one team's current roster from the repo's real
source, prints the top-level keys + ~30 lines of pretty JSON, and exits nonzero on any HTTP/parse
failure. No BigQuery writes. The BASE source is a BigQuery read (stg_rosters), documented in
docs/methodology/offseason-forecast.md, not re-fetched here.

Usage:
    python scripts/smoke_roster_source.py --team TOR
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from ingestion.nhl_api import api8_to_season, get_roster


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--team", default="TOR", help="Team abbrev")
    args = ap.parse_args()

    try:
        payload = get_roster(args.team)
    except Exception as e:  # noqa: BLE001
        print(f"FAIL: get_roster({args.team}) error: {e}", file=sys.stderr)
        return 1

    print(f"UPDATED roster source = api-web /v1/roster/{args.team}/{{season8}} (live membership)")
    print(f"team {args.team}: top-level keys = {list(payload.keys())}")
    print(f"resolved season = {api8_to_season(payload['season8'])} (season8={payload['season8']})")

    groups = ("forwards", "defensemen", "goalies")
    missing = [g for g in groups if g not in payload]
    if missing:
        print(f"FAIL: payload missing position arrays: {missing}", file=sys.stderr)
        return 1
    counts = {g: len(payload[g]) for g in groups}
    print(f"counts = {counts}")
    if sum(counts.values()) == 0:
        print("FAIL: roster is empty", file=sys.stderr)
        return 1

    # The forecast joins each roster player to value tables by NHL player id.
    sample = (payload["forwards"] or payload["defensemen"] or payload["goalies"])[0]
    if "id" not in sample:
        print(f"FAIL: player object has no id (join key); keys={list(sample.keys())}", file=sys.stderr)
        return 1
    print(f"join key present: player id = {sample['id']} ({sample.get('firstName', {}).get('default')} "
          f"{sample.get('lastName', {}).get('default')}, {sample.get('positionCode')})")

    print("--- first ~30 lines of pretty JSON (forwards[0]) ---")
    print("\n".join(json.dumps(sample, indent=2).splitlines()[:30]))
    print("\nOK: updated-roster source reachable and parseable")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
