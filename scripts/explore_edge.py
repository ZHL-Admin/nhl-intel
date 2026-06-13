"""Exploration tool for the NHL Edge data API (Phase 1.2).

The finalization plan assumed endpoints of the form
    /v1/edge/skater-detail/{playerId}/{season}
on api-web.nhle.com. As of this writing those return 404 (see EDGE_FINDINGS.md),
so the real endpoint must be discovered from the edge.nhl.com app's network calls.

This script:
  1. Re-tests the plan's candidate endpoints (documents the 404s).
  2. Accepts a --url template once the REAL endpoint is captured from the browser,
     fetches one example per entity, prints top-level keys, and saves the full
     payloads to scripts/edge_samples/*.json (gitignored) for schema decisions.

No BigQuery writes. Exits nonzero if no working endpoint is found/provided.

Usage:
    # just re-test the (dead) plan candidates:
    python scripts/explore_edge.py

    # once you capture the real URL from edge.nhl.com DevTools -> Network:
    python scripts/explore_edge.py \\
        --url 'https://<real-host>/<path>/{id}/{season}' \\
        --skater 8478402 --goalie 8479979 --team 10 --season 20252026
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import httpx

SAMPLE_DIR = Path(__file__).parent / "edge_samples"

# The plan's assumed endpoints (kept so the script documents that they are dead).
PLAN_CANDIDATES = [
    "https://api-web.nhle.com/v1/edge/skater-detail/{id}/{season}",
    "https://api-web.nhle.com/v1/edge/goalie-detail/{id}/{season}",
    "https://api-web.nhle.com/v1/edge/team-detail/{id}/{season}",
]


def _probe(url: str) -> tuple[int, str]:
    try:
        r = httpx.get(url, timeout=15.0, follow_redirects=True)
        ct = r.headers.get("content-type", "")
        return r.status_code, ct
    except Exception as e:  # noqa: BLE001
        return -1, str(e)[:60]


def _fetch_and_save(url: str, label: str) -> bool:
    code, ct = _probe(url)
    print(f"  {label:16s} {code} {ct[:24]:24s} {url[:70]}")
    if code != 200 or "json" not in ct:
        return False
    payload = httpx.get(url, timeout=15.0, follow_redirects=True).json()
    SAMPLE_DIR.mkdir(exist_ok=True)
    (SAMPLE_DIR / f"{label}.json").write_text(json.dumps(payload, indent=2)[:200000])
    keys = list(payload.keys()) if isinstance(payload, dict) else f"list[{len(payload)}]"
    print(f"    -> saved edge_samples/{label}.json  top-level keys: {keys}")
    return True


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", help="Real endpoint template with {id} and {season} placeholders")
    ap.add_argument("--skater", default="8478402")
    ap.add_argument("--goalie", default="8479979")
    ap.add_argument("--team", default="10")
    ap.add_argument("--season", default="20252026")
    args = ap.parse_args()

    print("Re-testing the plan's assumed Edge endpoints (expected 404):")
    for tmpl in PLAN_CANDIDATES:
        code, ct = _probe(tmpl.format(id=args.skater, season=args.season))
        print(f"  {code} {ct[:24]:24s} {tmpl}")

    if not args.url:
        print(
            "\nNo --url provided. The plan's endpoints are dead; capture the real one"
            "\nfrom edge.nhl.com (DevTools -> Network -> click a skater) and re-run with"
            "\n--url '<template with {id} and {season}>'. See EDGE_FINDINGS.md.",
            file=sys.stderr,
        )
        return 1

    print(f"\nTesting provided endpoint template: {args.url}")
    any_ok = False
    any_ok |= _fetch_and_save(args.url.format(id=args.skater, season=args.season), "skater")
    any_ok |= _fetch_and_save(args.url.format(id=args.goalie, season=args.season), "goalie")
    any_ok |= _fetch_and_save(args.url.format(id=args.team, season=args.season), "team")

    if not any_ok:
        print("FAIL: provided endpoint returned no JSON for any entity.", file=sys.stderr)
        return 1
    print("\nOK: saved real Edge payloads to scripts/edge_samples/ for schema decisions.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
