"""Smoke test for live-roster ingestion (no BigQuery writes).

Fetches ONE real team's CURRENT roster via get_roster() (which resolves "current" as
max(/roster-season) -> /roster/{TEAM}/{season8}; the planned /current path is a 307 we
don't use — see scripts/ROSTER_FINDINGS.md), verifies the fields stg_roster_current
parses, and prints the top-level keys + ~30 lines of pretty JSON. Exits nonzero on any
HTTP/parse failure or missing field. Optionally cross-checks the stats-REST currentTeamId
source (best-effort; never part of the refresh path). No BigQuery writes.

Usage:
    python scripts/smoke_ingest_roster.py --team TOR --team-id 10
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from ingestion.nhl_api import api8_to_season, get_players_by_current_team, get_roster


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--team", default="TOR", help="Team abbrev")
    ap.add_argument("--team-id", type=int, default=10, help="Numeric team id for the stats cross-check (TOR=10)")
    args = ap.parse_args()

    try:
        payload = get_roster(args.team)
    except Exception as e:  # noqa: BLE001
        print(f"FAIL: get_roster({args.team}) error: {e}", file=sys.stderr)
        return 1

    keys = list(payload.keys())
    print(f"team {args.team}: top-level keys = {keys}")
    print(f"resolved season = {api8_to_season(payload['season8'])} (season8={payload['season8']})")

    groups = ("forwards", "defensemen", "goalies")
    missing_groups = [g for g in groups if g not in payload]
    if missing_groups:
        print(f"FAIL: payload missing position arrays: {missing_groups}", file=sys.stderr)
        return 1
    counts = {g: len(payload[g]) for g in groups}
    print(f"counts = {counts}")
    if sum(counts.values()) == 0:
        print("FAIL: roster is empty", file=sys.stderr)
        return 1

    # Validate the fields stg_roster_current extracts from each player object.
    sample = payload["forwards"][0] if payload["forwards"] else payload["defensemen"][0]
    required = {"id", "firstName", "lastName", "positionCode"}
    missing = required - set(sample.keys())
    if missing:
        print(f"FAIL: player object missing fields {missing}; keys={list(sample.keys())}", file=sys.stderr)
        return 1
    if not isinstance(sample.get("firstName"), dict) or "default" not in sample["firstName"]:
        print(f"FAIL: firstName is not the expected localized object: {sample.get('firstName')!r}", file=sys.stderr)
        return 1

    print("--- first ~30 lines of pretty JSON (forwards[0]) ---")
    print("\n".join(json.dumps(sample, indent=2).splitlines()[:30]))

    # Best-effort cross-check (second source of truth; not used in the refresh path).
    try:
        stats = get_players_by_current_team(args.team_id)
        n = len(stats.get("data", []))
        has_field = bool(stats.get("data")) and "currentTeamId" in stats["data"][0]
        print(f"\n(cross-check) stats-REST currentTeamId={args.team_id}: {n} players, carries currentTeamId={has_field}")
    except Exception as e:  # noqa: BLE001
        print(f"\n(cross-check) stats-REST unavailable: {e}")

    print("\nOK: roster smoke test passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
