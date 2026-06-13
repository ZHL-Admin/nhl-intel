"""Smoke test for ppt-replay goal tracking ingestion (no BigQuery writes).

Fetches one goal's two-hop ppt-replay payload, verifies the wsr referer/UA fetch
works, the sprite schema, and the coordinate sanity (puck + skaters within the rink
after the inches->feet transform). Exits nonzero on failure.

Usage:
    python scripts/smoke_ingest_ppt_replay.py --game-id 2025030414 --event-id 69
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from ingestion.nhl_api import get_ppt_replay


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--game-id", type=int, default=2025030414)
    ap.add_argument("--event-id", type=int, default=69, help="A GOAL eventId")
    args = ap.parse_args()

    try:
        payload = get_ppt_replay(args.game_id, args.event_id, use_cache=False)
    except Exception as e:  # noqa: BLE001
        print(f"FAIL: fetch error (referer/UA or host issue): {e}", file=sys.stderr)
        return 1

    if not payload:
        print(f"FAIL: no sprite for {args.game_id}/{args.event_id} (not a goal?)", file=sys.stderr)
        return 1

    frames = payload["frames"]
    print(f"frame_count: {payload['frame_count']}")
    print(f"goal scorer: {payload['goal_metadata'].get('name')} @ {payload['goal_metadata'].get('timeInPeriod')}")
    f0 = frames[0]
    on_ice = f0["onIce"]
    print(f"frame0 entities: {len(on_ice)} (onIce normalized to a list)")

    puck = [e for e in on_ice if e.get("entityKey") == "1"]
    if not puck:
        print("FAIL: no puck entity (key '1') in frame", file=sys.stderr)
        return 1

    # Coordinate sanity: convert inches->feet center-origin, confirm within the rink.
    bad = 0
    for fr in frames:
        for e in fr["onIce"]:
            x, y = e.get("x"), e.get("y")
            if isinstance(x, (int, float)) and isinstance(y, (int, float)):
                x_std, y_std = x / 12.0 - 100.0, y / 12.0 - 42.5
                if abs(x_std) > 105 or abs(y_std) > 46:
                    bad += 1
    span_s = (frames[-1]["timeStamp"] - frames[0]["timeStamp"]) / 10.0
    print(f"clip span: {span_s:.1f}s (~{payload['frame_count']/max(span_s,1):.1f} fps)")
    print(f"entity-coords outside rink (transform check): {bad}")
    if bad > len(frames):  # allow a little boundary noise, not systematic
        print("FAIL: many coords outside rink — transform/units likely wrong", file=sys.stderr)
        return 1

    print("\nOK: ppt-replay smoke test passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
