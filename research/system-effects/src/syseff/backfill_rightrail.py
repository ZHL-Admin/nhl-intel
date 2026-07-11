"""Gate A — historical right-rail coach backfill (Phase 0 approved, full corpus).

Fetches gamecenter right-rail for every regular-season game 2010-11 … 2023-24
(enumerated from the frozen Atlas games.parquet — the authoritative game list),
caching each raw payload to disk BEFORE parsing, resumable via a manifest,
rate-limited to <=5 req/s with exponential backoff.

Captures coaches + referees + linesmen + scratches in the one pass (all free in
the same payload; serves the officials / healthy-scratch catalog items later).

Research acquisition only — payloads live under research/system-effects/data/,
NOT the warehouse. Promoting right-rail to the daily DAG is a Phase 7 item.

  make: python -m syseff.backfill_rightrail            # fetch (resumable)
        python -m syseff.backfill_rightrail --parse    # build parquet from cache
"""
from __future__ import annotations

import asyncio
import json
import sys
import time
from pathlib import Path

import httpx
import polars as pl

from . import config

RAIL_DIR = config.CACHE / "right_rail"
MANIFEST = RAIL_DIR / "_manifest.json"
OUT_PARQUET = config.PARQUET / "game_coaches.parquet"
URL = "https://api-web.nhle.com/v1/gamecenter/{gid}/right-rail"

# Backfill span: everything NOT already warehoused (2024-25/2025-26 come from BQ).
BACKFILL_SEASONS = [f"{y}-{str(y + 1)[2:]}" for y in range(2010, 2024)]  # 2010-11..2023-24

MAX_INFLIGHT = 5          # <=5 concurrent
MIN_INTERVAL = 0.21       # >=0.21s between request starts => <=~4.8 req/s
CHECKPOINT_EVERY = 200


def worklist() -> list[tuple[int, str]]:
    g = pl.read_parquet(config.ATLAS_PARQUET / "games.parquet",
                        columns=["game_id", "season_label"])
    g = g.filter(pl.col("season_label").is_in(BACKFILL_SEASONS)).unique().sort("game_id")
    return [(int(r[0]), r[1]) for r in g.iter_rows()]


def load_manifest() -> dict:
    if MANIFEST.exists():
        return json.loads(MANIFEST.read_text())
    return {}


def save_manifest(m: dict) -> None:
    MANIFEST.parent.mkdir(parents=True, exist_ok=True)
    MANIFEST.write_text(json.dumps(m))


def cache_path(season: str, gid: int) -> Path:
    return RAIL_DIR / season / f"{gid}.json"


class Throttle:
    """Serialises request-start times to >=MIN_INTERVAL apart (token bucket)."""
    def __init__(self, interval: float):
        self.interval = interval
        self._next = 0.0
        self._lock = asyncio.Lock()

    async def wait(self):
        async with self._lock:
            now = time.monotonic()
            if now < self._next:
                await asyncio.sleep(self._next - now)
                now = time.monotonic()
            self._next = now + self.interval


async def fetch_one(client, throttle, sem, gid, season, manifest):
    fp = cache_path(season, gid)
    if fp.exists():
        manifest[str(gid)] = "cached"
        return "cached"
    async with sem:
        delay = 0.5
        for attempt in range(6):
            await throttle.wait()
            try:
                r = await client.get(URL.format(gid=gid), timeout=30,
                                     headers={"User-Agent": "syseff-backfill/0.1"})
                if r.status_code == 200:
                    fp.parent.mkdir(parents=True, exist_ok=True)
                    fp.write_text(r.text)
                    manifest[str(gid)] = "ok"
                    return "ok"
                if r.status_code == 404:
                    manifest[str(gid)] = "404"
                    return "404"
                # 429/5xx -> backoff
            except Exception:
                pass
            if attempt < 5:
                await asyncio.sleep(delay)
                delay = min(delay * 2, 16)
        manifest[str(gid)] = "error"
        return "error"


async def run():
    work = worklist()
    manifest = load_manifest()
    todo = [(g, s) for g, s in work if manifest.get(str(g)) not in ("ok", "cached", "404")]
    print(f"backfill: {len(work)} games in span, {len(work) - len(todo)} already done, "
          f"{len(todo)} to fetch", flush=True)
    throttle = Throttle(MIN_INTERVAL)
    sem = asyncio.Semaphore(MAX_INFLIGHT)
    done = 0
    t0 = time.monotonic()
    async with httpx.AsyncClient(http2=False) as client:
        tasks = [asyncio.create_task(fetch_one(client, throttle, sem, g, s, manifest))
                 for g, s in todo]
        for fut in asyncio.as_completed(tasks):
            await fut
            done += 1
            if done % CHECKPOINT_EVERY == 0:
                save_manifest(manifest)
                rate = done / max(time.monotonic() - t0, 1e-9)
                print(f"  {done}/{len(todo)}  {rate:.1f} req/s", flush=True)
    save_manifest(manifest)
    from collections import Counter
    print("done. statuses:", dict(Counter(manifest.values())), flush=True)


def _officials(gi: dict, key: str) -> list[str]:
    return [o.get("default") for o in (gi.get(key) or []) if isinstance(o, dict)]


def _scratches(team: dict) -> list[dict]:
    out = []
    for s in (team.get("scratches") or []):
        out.append({
            "player_id": s.get("id"),
            "name": ((s.get("firstName") or {}).get("default", "") + " "
                     + (s.get("lastName") or {}).get("default", "")).strip(),
        })
    return out


def parse():
    """Build game_coaches.parquet from cached raw payloads (span seasons)."""
    rows = []
    for season in BACKFILL_SEASONS:
        d = RAIL_DIR / season
        if not d.exists():
            continue
        for fp in d.glob("*.json"):
            try:
                payload = json.loads(fp.read_text())
            except Exception:
                continue
            gi = payload.get("gameInfo") or {}
            home = gi.get("homeTeam") or {}
            away = gi.get("awayTeam") or {}
            rows.append({
                "game_id": int(fp.stem),
                "season_label": season,
                "home_head_coach": (home.get("headCoach") or {}).get("default"),
                "away_head_coach": (away.get("headCoach") or {}).get("default"),
                "referees": _officials(gi, "referees"),
                "linesmen": _officials(gi, "linesmen"),
                "home_scratches": json.dumps(_scratches(home)),
                "away_scratches": json.dumps(_scratches(away)),
                "source": "right_rail_backfill",
            })
    df = pl.DataFrame(rows).sort("game_id")
    OUT_PARQUET.parent.mkdir(parents=True, exist_ok=True)
    df.write_parquet(OUT_PARQUET)
    n_missing_coach = df.filter(pl.col("home_head_coach").is_null()
                                | pl.col("away_head_coach").is_null()).height
    print(f"parsed {df.height} games -> {OUT_PARQUET.name}; "
          f"{n_missing_coach} with a null coach", flush=True)
    return df


if __name__ == "__main__":
    if "--parse" in sys.argv:
        parse()
    else:
        asyncio.run(run())
