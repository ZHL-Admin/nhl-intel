"""
Ingest player bio (birthDate / height / weight / shoots) for every player in stg_rosters
(Phase 4.4 prerequisite). NHL boxscore rosterSpots carry no bio, but aging curves need age and
twins need height/weight. Source: /v1/player/{id}/landing.

Lands flat typed rows into nhl_raw.raw_player_bio (one row per player). Resumable: skips players
already present unless --refresh. Threaded fetch with a small pool (bio is immutable enough).

Run:  python -m scripts.ingest_player_bio [--refresh] [--workers 12]
"""

from __future__ import annotations

import argparse
import datetime as _dt
from concurrent.futures import ThreadPoolExecutor, as_completed

from google.cloud import bigquery

from ingestion.nhl_api import get_player_landing
from models_ml import bq

TABLE = "raw_player_bio"


def _raw_table_id() -> str:
    return f"{bq.project()}.nhl_raw.{TABLE}"


def existing_player_ids() -> set[int]:
    try:
        df = bq.query_df(f"select distinct player_id from `{_raw_table_id()}`")
        return set(int(x) for x in df["player_id"])
    except Exception:
        return set()


def all_player_ids() -> list[int]:
    df = bq.query_df(
        f"select distinct player_id from `{bq.project()}.nhl_staging.stg_rosters`")
    return sorted(int(x) for x in df["player_id"])


def fetch_one(pid: int) -> dict | None:
    try:
        r = get_player_landing(str(pid))
    except Exception as e:  # 404 for a stale id, etc. — skip cleanly
        print(f"  {pid}: skip ({str(e)[:50]})")
        return None
    return {
        "player_id": int(r.get("playerId", pid)),
        "birth_date": r.get("birthDate"),
        "height_in": r.get("heightInInches"),
        "weight_lb": r.get("weightInPounds"),
        "shoots": r.get("shootsCatches"),
        "position": r.get("position"),
        "ingestion_date": _dt.date.today().isoformat(),
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--refresh", action="store_true", help="re-fetch all (ignore existing)")
    ap.add_argument("--workers", type=int, default=12)
    args = ap.parse_args()

    ids = all_player_ids()
    if not args.refresh:
        have = existing_player_ids()
        ids = [p for p in ids if p not in have]
    print(f"Fetching bio for {len(ids):,} players (workers={args.workers}) ...")

    rows = []
    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        futs = {ex.submit(fetch_one, p): p for p in ids}
        for i, f in enumerate(as_completed(futs), 1):
            r = f.result()
            if r:
                rows.append(r)
            if i % 500 == 0:
                print(f"  {i}/{len(ids)} fetched")
    if not rows:
        print("Nothing to write.")
        return

    schema = [
        bigquery.SchemaField("player_id", "INTEGER"),
        bigquery.SchemaField("birth_date", "DATE"),
        bigquery.SchemaField("height_in", "INTEGER"),
        bigquery.SchemaField("weight_lb", "INTEGER"),
        bigquery.SchemaField("shoots", "STRING"),
        bigquery.SchemaField("position", "STRING"),
        bigquery.SchemaField("ingestion_date", "DATE"),
    ]
    cli = bq.client()
    disp = "WRITE_TRUNCATE" if args.refresh else "WRITE_APPEND"
    job = cli.load_table_from_json(
        rows, _raw_table_id(),
        job_config=bigquery.LoadJobConfig(schema=schema, write_disposition=disp))
    job.result()
    print(f"Wrote {len(rows):,} rows to {_raw_table_id()} ({disp}).")


if __name__ == "__main__":
    main()
