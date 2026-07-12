"""One-time backfill loader (System Effects Phase 7.1c).

Loads the CACHED right-rail payloads for 2010-11..2023-24 (16,526 games) that the System Effects
research project already fetched — into nhl_raw.raw_game_right_rail via the NORMAL loader. We do
NOT refetch: the raw payloads are on disk under the research cache, so this reads them and loads
them through the same `load_json_to_bigquery` path as the daily flow, idempotent (delete-then-
insert per game_id) and provenance-marked (`_source="right_rail_backfill_2010_24"`).

This is a one-time operation, not part of the DAG. It reads from the research cache directory
purely as a data source for the load; it imports no research code. Run once, after which the
regime ledger (stg_syseff_game_coaches → mart_syseff_regime_ledger) covers the full 2010-26 span.

Usage:
    python -m ingestion.backfill_coach_loader --cache-dir <path> [--dry-run] [--batch 500]

Default cache dir: research/system-effects/data/cache/right_rail/{season}/{game_id}.json
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from ingestion.loaders import load_json_to_bigquery, delete_rows_by_game_id

DEFAULT_CACHE = Path(__file__).resolve().parents[1] / "research/system-effects/data/cache/right_rail"
SOURCE_TAG = "right_rail_backfill_2010_24"


def _iter_payloads(cache_dir: Path):
    for season_dir in sorted(p for p in cache_dir.iterdir() if p.is_dir()):
        season = season_dir.name  # "2010-11"
        for jf in sorted(season_dir.glob("*.json")):
            try:
                payload = json.loads(jf.read_text())
            except Exception:
                continue
            gid = int(jf.stem)
            payload["id"] = gid
            payload["game_id"] = gid
            payload["_source"] = SOURCE_TAG
            payload["_game_final"] = True   # historical games are settled
            yield season, gid, payload


def run(cache_dir: Path, project_id: str, dataset: str = "nhl_raw",
        batch: int = 500, dry_run: bool = False) -> int:
    by_season: dict[str, list] = {}
    for season, gid, payload in _iter_payloads(cache_dir):
        by_season.setdefault(season, []).append(payload)
    total = sum(len(v) for v in by_season.values())
    print(f"Found {total} cached right-rail payloads across {len(by_season)} seasons in {cache_dir}")
    if dry_run:
        for s, rows in sorted(by_season.items()):
            print(f"  {s}: {len(rows)} games")
        return total
    loaded = 0
    for season, rows in sorted(by_season.items()):
        for i in range(0, len(rows), batch):
            chunk = rows[i:i + batch]
            gids = [r["game_id"] for r in chunk]
            delete_rows_by_game_id(project_id, dataset, "raw_game_right_rail", gids)
            load_json_to_bigquery(project_id, dataset, "raw_game_right_rail", chunk, season)
            loaded += len(chunk)
        print(f"  loaded {season}: {len(rows)} games (idempotent)")
    print(f"Backfill complete: {loaded} right-rail rows loaded via the normal loader (no refetch).")
    return loaded


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--cache-dir", default=str(DEFAULT_CACHE))
    ap.add_argument("--project-id", default=os.environ.get("GCP_PROJECT_ID"))
    ap.add_argument("--dataset", default="nhl_raw")
    ap.add_argument("--batch", type=int, default=500)
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    run(Path(a.cache_dir), a.project_id, a.dataset, a.batch, a.dry_run)
