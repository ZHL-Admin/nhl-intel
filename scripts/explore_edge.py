"""Exploration tool for the NHL Edge data API (Phase 1.2).

The real endpoint family (see EDGE_FINDINGS.md) is per-metric with a gameType segment:
    GET /v1/edge/{entity}-{category}-detail/{id}/{season}/{gameType}

This script fetches every confirmed category for a sample skater/goalie/team,
prints top-level keys, saves full payloads to scripts/edge_samples/*.json
(gitignored), and records which seasons return data. No BigQuery writes. Exits
nonzero if nothing returns JSON.

Usage:
    python scripts/explore_edge.py --season 20242025
    python scripts/explore_edge.py --skater 8478402 --goalie 8479979 --team 10 --season 20252026
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from ingestion.nhl_api import (
    get_edge_detail,
    EDGE_SKATER_REPORTS,
    EDGE_GOALIE_REPORTS,
    EDGE_TEAM_REPORTS,
)

SAMPLE_DIR = Path(__file__).parent / "edge_samples"


def _fetch(entity: str, eid: str, season: str, game_type: int, report: str) -> bool:
    label = f"{entity}_{report}".replace("-", "_")
    try:
        payload = get_edge_detail(entity, eid, season, game_type, report)
    except Exception as e:  # noqa: BLE001
        print(f"  {entity:7s} {report:18s} FAIL: {str(e)[:50]}")
        return False
    SAMPLE_DIR.mkdir(exist_ok=True)
    (SAMPLE_DIR / f"{label}.json").write_text(json.dumps(payload, indent=2)[:300000])
    keys = list(payload.keys()) if isinstance(payload, dict) else f"list[{len(payload)}]"
    print(f"  {entity:7s} {report:18s} OK  keys={keys}")
    return True


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--skater", default="8482116")  # Tim Stützle
    ap.add_argument("--goalie", default="8479979")
    ap.add_argument("--team", default="10")  # Toronto
    ap.add_argument("--season", default="20242025")
    ap.add_argument("--game-type", type=int, default=2)
    args = ap.parse_args()

    print(f"NHL Edge exploration — season {args.season}, gameType {args.game_type}")
    any_ok = False
    for rep in EDGE_SKATER_REPORTS:
        any_ok |= _fetch("skater", args.skater, args.season, args.game_type, rep)
    for rep in EDGE_GOALIE_REPORTS:
        any_ok |= _fetch("goalie", args.goalie, args.season, args.game_type, rep)
    for rep in EDGE_TEAM_REPORTS:
        any_ok |= _fetch("team", args.team, args.season, args.game_type, rep)

    if not any_ok:
        print(f"FAIL: no Edge data for season {args.season} (pre-tracking era?)", file=sys.stderr)
        return 1
    print(f"\nOK: saved payloads to {SAMPLE_DIR}/ for schema decisions.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
