"""Export the site's serving data from BigQuery into a single local DuckDB file.

BigQuery stays the nightly COMPUTE engine + system of record. This job materializes
everything the FastAPI backend READS at request time into one DuckDB file, so the backend
serves interactive reads in milliseconds with no BigQuery client on the request path.

Driven entirely by `serving_tables.yml` (the single source of truth). For each table:
  - `kind: source`      -> copied AS-IS from BigQuery.
  - `kind: precompute`  -> copied once `built: true` (built by its models_ml/dbt job).
Big per-event tables (`cap: recent`) are limited to the most recent N seasons by the
game_id season prefix; everything else is exported in full.

The DuckDB file is built ATOMICALLY: a fresh temp file is populated, then swapped into
place (the previous file is kept as <path>.bak), so the backend never reads a half-written
file. The export is idempotent and fully RE-RUNNABLE: delete the file, run this, done.

Usage (env: set -a && source .env && set +a && export GOOGLE_APPLICATION_CREDENTIALS=...):
    python -m scripts.export_to_duckdb                  # full export
    python -m scripts.export_to_duckdb --only stg_rosters,mart_team_game_stats
    python -m scripts.export_to_duckdb --dry-run        # print the plan, fetch nothing
    python -m scripts.export_to_duckdb --recent-seasons 4
"""
from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path
from typing import Any

import duckdb
import yaml
from google.cloud import bigquery

REPO_ROOT = Path(__file__).resolve().parent.parent
MANIFEST = REPO_ROOT / "serving_tables.yml"


def _load_manifest() -> dict:
    with open(MANIFEST) as f:
        return yaml.safe_load(f)


def _project() -> str:
    proj = os.getenv("GCP_PROJECT_ID")
    if not proj:
        sys.exit("GCP_PROJECT_ID not set (source .env first).")
    return proj


def _dataset(meta: dict, key: str) -> str:
    return meta[f"{key}_dataset"]


def _recent_start_year(client: bigquery.Client, recent_seasons: int) -> int:
    """Start year for the recent-season cap, from the latest season in stg_games.

    Seasons look like '2025-26'; the start year is the first 4 chars. The cap keeps the
    latest `recent_seasons` seasons, i.e. start_year >= latest_start - (recent_seasons-1).
    """
    proj = _project()
    row = list(
        client.query(
            f"SELECT MAX(season) AS s FROM `{proj}.nhl_staging.stg_games`"
        ).result()
    )[0]
    latest_start = int(str(row.s)[:4])
    return latest_start - (recent_seasons - 1)


def _select_sql(proj: str, dataset: str, table: str, cap: str, start_year: int) -> str:
    src = f"`{proj}.{dataset}.{table}`"
    if cap == "recent":
        # Uniform cap by game_id season prefix (every capped table carries game_id).
        return (
            f"SELECT * FROM {src} "
            f"WHERE CAST(SUBSTR(CAST(game_id AS STRING), 1, 4) AS INT64) >= {start_year}"
        )
    return f"SELECT * FROM {src}"


def _fetch_arrow(client: bigquery.Client, sql: str):
    """Pull a query result as a pyarrow.Table, preferring the BQ Storage API."""
    job = client.query(sql)
    try:
        return job.result().to_arrow(create_bqstorage_client=True)
    except Exception:
        return job.result().to_arrow(create_bqstorage_client=False)


def _create_indexes(con: duckdb.DuckDBPyConnection, table: str, indexes: list) -> None:
    for i, spec in enumerate(indexes or []):
        cols = spec if isinstance(spec, list) else [spec]
        col_sql = ", ".join(f'"{c}"' for c in cols)
        idx_name = f"idx_{table}_{i}"
        try:
            con.execute(f'DROP INDEX IF EXISTS "{idx_name}"')
            con.execute(f'CREATE INDEX "{idx_name}" ON "{table}" ({col_sql})')
        except Exception as e:  # noqa: BLE001 — a bad index spec must not waste the data pull
            print(f"    ! index {idx_name} ({col_sql}) skipped: {str(e)[:100]}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--duckdb-path", help="override meta.duckdb_path")
    ap.add_argument("--only", help="comma-separated subset of table names to export")
    ap.add_argument("--recent-seasons", type=int, help="override meta.recent_seasons")
    ap.add_argument("--dry-run", action="store_true", help="print the plan, fetch nothing")
    ap.add_argument(
        "--into-existing",
        action="store_true",
        help="update the targeted tables in-place in the existing DuckDB file (no atomic "
        "swap). Implied by --only. Use for dev iteration / incremental refresh of small tables.",
    )
    ap.add_argument(
        "--skip-missing",
        action="store_true",
        default=True,
        help="skip tables that error (e.g. precompute not built yet); on by default",
    )
    args = ap.parse_args()

    manifest = _load_manifest()
    meta = manifest["meta"]
    recent_seasons = args.recent_seasons or int(meta.get("recent_seasons", 3))
    duckdb_path = REPO_ROOT / (args.duckdb_path or meta["duckdb_path"])
    duckdb_path.parent.mkdir(parents=True, exist_ok=True)

    only = set(s.strip() for s in args.only.split(",")) if args.only else None

    # Which tables to export: every source, plus precompute tables marked built.
    plan: list[dict] = []
    for t in manifest["tables"]:
        if only and t["name"] not in only:
            continue
        if t["kind"] == "precompute" and not t.get("built", False):
            print(f"  - skip {t['name']} (precompute, not built yet)")
            continue
        plan.append(t)

    proj = _project()
    client = bigquery.Client(project=proj)
    start_year = _recent_start_year(client, recent_seasons)
    print(
        f"Export plan: {len(plan)} tables -> {duckdb_path}\n"
        f"  recent cap = last {recent_seasons} seasons (game_id start year >= {start_year})\n"
    )

    if args.dry_run:
        for t in plan:
            ds = _dataset(meta, t["dataset"])
            print(f"  {ds}.{t['name']:30s} cap={t['cap']:6s} idx={t.get('indexes')}")
        return 0

    into_existing = args.into_existing or bool(only)
    if into_existing:
        # Patch targeted tables in-place in the existing file (no swap). Dev / incremental.
        if not duckdb_path.exists():
            sys.exit(f"--into-existing needs an existing file at {duckdb_path}; run a full export first.")
        build_path = duckdb_path
        print("  (in-place update of the existing serving file; no atomic swap)")
    else:
        # Build a fresh temp file, then atomically swap.
        build_path = duckdb_path.with_suffix(f".tmp-{os.getpid()}")
        # Clean any leftover temp files from a previously aborted run.
        for stale in duckdb_path.parent.glob(f"{duckdb_path.stem}.tmp-*"):
            stale.unlink()

    summary: list[tuple[str, int, float]] = []
    con = duckdb.connect(str(build_path))
    try:
        for t in plan:
            name = t["name"]
            ds = _dataset(meta, t["dataset"])
            sql = _select_sql(proj, ds, name, t["cap"], start_year)
            t0 = time.time()
            try:
                arrow_tbl = _fetch_arrow(client, sql)
            except Exception as e:  # noqa: BLE001
                if args.skip_missing:
                    print(f"  ! skip {name}: {str(e)[:120]}")
                    continue
                raise
            con.register("_src", arrow_tbl)
            con.execute(f'CREATE OR REPLACE TABLE "{name}" AS SELECT * FROM _src')
            con.unregister("_src")
            n = con.execute(f'SELECT COUNT(*) FROM "{name}"').fetchone()[0]
            _create_indexes(con, name, t.get("indexes"))
            dt = time.time() - t0
            summary.append((name, n, dt))
            print(f"  ok {name:32s} {n:>12,} rows  {dt:6.1f}s")
        con.execute("CHECKPOINT")
    finally:
        con.close()

    if not into_existing:
        # Atomic swap: keep the previous file as .bak until the new one is in place.
        bak_path = duckdb_path.with_suffix(".duckdb.bak")
        if duckdb_path.exists():
            if bak_path.exists():
                bak_path.unlink()
            os.replace(duckdb_path, bak_path)
        os.replace(build_path, duckdb_path)
    else:
        bak_path = None

    total_rows = sum(n for _, n, _ in summary)
    total_time = sum(dt for _, _, dt in summary)
    size_mb = duckdb_path.stat().st_size / 1e6
    print(
        f"\nDONE: {len(summary)} tables, {total_rows:,} rows, "
        f"{size_mb:.1f} MB, {total_time:.1f}s -> {duckdb_path}"
    )
    if bak_path and bak_path.exists():
        print(f"  (previous file kept at {bak_path})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
