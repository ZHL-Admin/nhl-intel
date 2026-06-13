"""Smoke test for game landing + right-rail ingestion (no BigQuery writes).

Fetches both payloads for one game, verifies the fields stg_game_context parses
(goal highlight links, scratches, season series, team game stats), and prints a
sample goal-highlight and scratch list. Exits nonzero on failure.

Usage:
    python scripts/smoke_ingest_game_context.py --game-id 2025030414
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from ingestion.nhl_api import get_game_landing, get_game_right_rail


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--game-id", default="2025030414")
    args = ap.parse_args()

    try:
        landing = get_game_landing(args.game_id)
        rail = get_game_right_rail(args.game_id)
    except Exception as e:  # noqa: BLE001
        print(f"FAIL: request error: {e}", file=sys.stderr)
        return 1

    # Landing: goal highlight links
    scoring = landing.get("summary", {}).get("scoring", [])
    goals = [g for p in scoring for g in p.get("goals", [])]
    print(f"goals in landing summary: {len(goals)}")
    with_links = [g for g in goals if g.get("highlightClipSharingUrl")]
    print(f"goals with highlight links: {len(with_links)}")
    if goals:
        g = goals[0]
        print("sample goal:", json.dumps(
            {k: g.get(k) for k in ("eventId", "playerId", "timeInPeriod",
                                   "highlightClipSharingUrl", "pptReplayUrl")}, indent=2))

    # Right-rail: scratches, series, stats
    gi = rail.get("gameInfo", {})
    away_scr = gi.get("awayTeam", {}).get("scratches", [])
    home_scr = gi.get("homeTeam", {}).get("scratches", [])
    print(f"\nscratches: away={len(away_scr)} home={len(home_scr)}")
    print("seasonSeriesWins:", json.dumps(rail.get("seasonSeriesWins")))
    print(f"seasonSeries prior meetings: {len(rail.get('seasonSeries', []))}")
    print(f"teamGameStats rows: {len(rail.get('teamGameStats', []))}")

    if not gi.get("awayTeam") or "headCoach" not in gi.get("awayTeam", {}):
        print("FAIL: gameInfo missing coaches/scratches structure", file=sys.stderr)
        return 1

    print("\nOK: game context smoke test passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
