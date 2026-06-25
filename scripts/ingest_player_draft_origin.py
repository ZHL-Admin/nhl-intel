"""Ingest each NHL player's DRAFT ORIGIN — the authoritative (draft_year, overall_pick) map used to
resolve historical draft results to player_ids (Handoff 5, Phase A).

The draft-results endpoint carries no player_id (see scripts/DRAFT_RESULTS_FINDINGS.md), and name
matching produces false zeros (it cannot tell a true bust from a roster-coverage gap). The reliable
resolver is each player's own landing draftDetails: (year, round, overallPick, teamAbbrev). We fetch it
for the PRODUCING universe — every player with rows in mart_player_game_stats (~3,834, 2010-11..2025-26)
— and stg_draft_results joins raw_draft_results on (draft_year, overall_pick) to attach resolved_player_id.

Output: nhl_raw.raw_player_draft_origin (one row per player; undrafted players kept with null draft
fields so we know they were checked, not skipped). full_name is stored for the join cross-check only.

Resumable + crash-safe: skips players already present unless --refresh, and appends in checkpoint
batches so an interrupted run resumes from where it stopped.

Run (env: set -a && source .env && set +a):
    python -m scripts.ingest_player_draft_origin                 # incremental (new players only)
    python -m scripts.ingest_player_draft_origin --refresh       # re-fetch all
    python -m scripts.ingest_player_draft_origin --sample 50     # slice-verify
"""
from __future__ import annotations

import argparse
import datetime as _dt
from concurrent.futures import ThreadPoolExecutor, as_completed

from google.cloud import bigquery

from ingestion.nhl_api import get_player_landing
from models_ml import bq

TABLE = "raw_player_draft_origin"
SCHEMA = [
    bigquery.SchemaField("player_id", "INTEGER"),
    bigquery.SchemaField("draft_year", "INTEGER"),
    bigquery.SchemaField("draft_round", "INTEGER"),
    bigquery.SchemaField("draft_overall", "INTEGER"),
    bigquery.SchemaField("draft_team_abbrev", "STRING"),
    bigquery.SchemaField("full_name", "STRING"),
    bigquery.SchemaField("is_undrafted", "BOOL"),
    bigquery.SchemaField("ingestion_date", "DATE"),
]


def _raw_table_id() -> str:
    return f"{bq.project()}.nhl_raw.{TABLE}"


def existing_player_ids() -> set[int]:
    try:
        df = bq.query_df(f"select distinct player_id from `{_raw_table_id()}`")
        return set(int(x) for x in df["player_id"])
    except Exception:
        return set()


def producing_player_ids() -> list[int]:
    """Every player with realized production in our data — the universe that can have non-zero value."""
    df = bq.query_df(
        f"select distinct player_id from `{bq.project()}.nhl_mart.mart_player_game_stats` "
        f"where player_id is not null")
    return sorted(int(x) for x in df["player_id"])


def _default(d) -> str | None:
    return d.get("default") if isinstance(d, dict) else d


def fetch_one(pid: int) -> dict | None:
    try:
        r = get_player_landing(str(pid))
    except Exception as e:  # stale/404 id — skip cleanly
        print(f"  {pid}: skip ({str(e)[:50]})")
        return None
    dd = r.get("draftDetails") or {}
    first = _default(r.get("firstName"))
    last = _default(r.get("lastName"))
    full = " ".join(x for x in (first, last) if x) or None
    return {
        "player_id": int(r.get("playerId", pid)),
        "draft_year": dd.get("year"),
        "draft_round": dd.get("round"),
        "draft_overall": dd.get("overallPick"),
        "draft_team_abbrev": dd.get("teamAbbrev"),
        "full_name": full,
        "is_undrafted": not bool(dd),
        "ingestion_date": _dt.date.today().isoformat(),
    }


def _append(rows: list[dict], disp: str) -> None:
    cli = bq.client()
    cli.load_table_from_json(
        rows, _raw_table_id(),
        job_config=bigquery.LoadJobConfig(schema=SCHEMA, write_disposition=disp)).result()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--refresh", action="store_true", help="re-fetch all (truncate)")
    ap.add_argument("--workers", type=int, default=12)
    ap.add_argument("--batch", type=int, default=400, help="checkpoint flush size (crash-safe)")
    ap.add_argument("--sample", type=int, default=0, help="only fetch the first N (slice-verify)")
    args = ap.parse_args()

    ids = producing_player_ids()
    if not args.refresh:
        have = existing_player_ids()
        ids = [p for p in ids if p not in have]
    if args.sample:
        ids = ids[: args.sample]
    print(f"Fetching draft origin for {len(ids):,} players (workers={args.workers}, batch={args.batch}) ...")
    if not ids:
        print("Nothing to fetch — all present.")
        return

    # First flush of a --refresh truncates; everything else appends (so it's resumable).
    disp = "WRITE_TRUNCATE" if args.refresh else "WRITE_APPEND"
    buf: list[dict] = []
    n_written = n_drafted = 0
    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        futs = {ex.submit(fetch_one, p): p for p in ids}
        for i, f in enumerate(as_completed(futs), 1):
            r = f.result()
            if r:
                buf.append(r)
                n_drafted += 0 if r["is_undrafted"] else 1
            if len(buf) >= args.batch:
                _append(buf, disp)
                n_written += len(buf)
                disp = "WRITE_APPEND"
                buf = []
                print(f"  checkpoint: {n_written} written ({i}/{len(ids)} fetched)")
    if buf:
        _append(buf, disp)
        n_written += len(buf)
    print(f"Wrote {n_written:,} rows to {_raw_table_id()} ({n_drafted:,} drafted, "
          f"{n_written - n_drafted:,} undrafted).")


if __name__ == "__main__":
    main()
