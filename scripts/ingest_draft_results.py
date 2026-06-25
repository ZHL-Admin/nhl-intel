"""Ingest historical draft RESULTS — who was actually selected at each pick (Handoff 5, Phase A).

Source: /v1/draft/picks/{year}/all. One row per pick into nhl_raw.raw_draft_results with an EXPLICIT
schema (loaders.DRAFT_RESULTS_SCHEMA). This is the complete evaluation universe / denominator for the
Draft Value tool: every pick is kept, including players who never reached the NHL (never-NHL = value 0
downstream, NOT missing).

This is SEPARATE from raw_draft_picks (future pick OWNERSHIP, scripts/ingest_futures.py). Do not merge.

The payload carries no player_id (verified; see scripts/DRAFT_RESULTS_FINDINGS.md). player_id is
resolved downstream in stg_draft_results by joining (draft_year, overall_pick) to each player's landing
draftDetails (nhl_models.player_draft_origin, scripts/ingest_player_draft_origin.py).

Idempotent per year (delete-then-append). Resumable over a year range: skips years already present
unless --force. Drafts are annual — backfill once, then refresh the latest year yearly.

Usage (env: set -a && source .env && set +a):
    python -m scripts.ingest_draft_results --year 2024            # single year
    python -m scripts.ingest_draft_results --start 2005 --end 2025   # backfill (handoff floor)
    python -m scripts.ingest_draft_results --year 2024 --dry-run  # fetch + print shape, no write
"""
from __future__ import annotations

import argparse
import logging
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from ingestion.nhl_api import get_draft_picks
from ingestion.loaders import load_draft_results_to_bigquery
from google.cloud import bigquery

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

PROJECT = os.environ["GCP_PROJECT_ID"]
DATASET_RAW = os.environ.get("GCP_DATASET_RAW", "nhl_raw")


def _default(d: dict | None) -> str | None:
    """Pull the 'default' string from a localized {default, fr} object, or pass through."""
    if isinstance(d, dict):
        return d.get("default")
    return d


def flatten_pick(p: dict) -> dict:
    """Map one API pick to the explicit DRAFT_RESULTS_SCHEMA columns."""
    first = _default(p.get("firstName"))
    last = _default(p.get("lastName"))
    full = " ".join(x for x in (first, last) if x)
    return {
        "draft_year": None,  # stamped by caller (the payload's draftYear)
        "round": p.get("round"),
        "pick_in_round": p.get("pickInRound"),
        "overall_pick": p.get("overallPick"),
        "team_id": p.get("teamId"),
        "team_abbrev": p.get("teamAbbrev"),
        "full_name": full or None,
        "first_name": first,
        "last_name": last,
        "position_code": p.get("positionCode"),
        "country_code": p.get("countryCode"),
        "height_in": p.get("height"),
        "weight_lb": p.get("weight"),
        "amateur_league": p.get("amateurLeague"),
        "amateur_club": p.get("amateurClubName"),
    }


def fetch_year(year: int) -> list[dict]:
    payload = get_draft_picks(year, "all")
    if str(payload.get("state")) != "over":
        logger.warning("draft %d state=%s (not 'over') — skipping incomplete draft", year, payload.get("state"))
        return []
    picks = payload.get("picks") or []
    rows = []
    for p in picks:
        r = flatten_pick(p)
        r["draft_year"] = year
        rows.append(r)
    return rows


def existing_years(client: bigquery.Client) -> set[int]:
    try:
        sql = f"SELECT DISTINCT draft_year FROM `{PROJECT}.{DATASET_RAW}.raw_draft_results`"
        return {int(r.draft_year) for r in client.query(sql).result()}
    except Exception:
        return set()


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--year", type=int, help="Single draft year")
    ap.add_argument("--start", type=int, help="Range start year")
    ap.add_argument("--end", type=int, help="Range end year")
    ap.add_argument("--sleep-ms", type=int, default=120)
    ap.add_argument("--force", action="store_true", help="Re-ingest years already present")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    if args.year:
        years = [args.year]
    elif args.start and args.end:
        years = list(range(args.start, args.end + 1))
    else:
        ap.error("provide --year or --start/--end")

    client = None if args.dry_run else bigquery.Client(project=PROJECT)
    done = set() if (args.force or args.dry_run) else existing_years(client)

    total_rows = 0
    for y in years:
        if y in done:
            logger.info("draft %d already present — skip (use --force to re-ingest)", y)
            continue
        rows = fetch_year(y)
        if not rows:
            continue
        overalls = sorted(r["overall_pick"] for r in rows if r["overall_pick"] is not None)
        dense = overalls == list(range(1, len(overalls) + 1))
        rounds = sorted({r["round"] for r in rows})
        logger.info("draft %d: %d picks, rounds %s, overall dense 1..%d = %s",
                    y, len(rows), rounds, len(overalls), dense)
        if args.dry_run:
            sample = rows[0]
            logger.info("  sample: #%s %s (%s, %s)", sample["overall_pick"], sample["full_name"],
                        sample["position_code"], sample["team_abbrev"])
        else:
            load_draft_results_to_bigquery(PROJECT, DATASET_RAW, rows, y)
            total_rows += len(rows)
        time.sleep(args.sleep_ms / 1000.0)

    if args.dry_run:
        logger.info("[dry-run] not written")
    else:
        logger.info("Done. Loaded %d rows across %d year(s).", total_rows, len(years))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
