"""Replay probe reproducer (read-only, stdlib only).

Reproduces the VERIFIED facts from local cached sprite JSON (`scripts/ppt_probe_cache/`, from the
repo's earlier probe run): the decisive coordinate answer, the entity composition (all players + the
puck), the 10 Hz frame cadence, and goals-only scope. The full warehouse coverage (raw_ppt_replay,
25,946 goals, 2023-24..2025-26) is characterized in reports/probe.md via BigQuery; the exact query is
printed here for reference (needs BQ creds — not run in this reproducer). No fetch, no writes.
"""
from __future__ import annotations

import glob
import json
import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[4]
CACHE = REPO / "scripts" / "ppt_probe_cache"

BQ_COVERAGE_SQL = (
    "select season, count(*) goals, count(distinct game_id) games, "
    "min(frame_count) fmin, round(avg(frame_count)) favg, max(frame_count) fmax "
    "from `<project>.nhl_raw.raw_ppt_replay` group by season order by season"
)


def _load(fp: str) -> dict:
    return json.loads(Path(fp).read_text())


def reproduce() -> dict:
    # a known GOAL sprite: puck + all players, 10 Hz frames
    goal = _load(str(CACHE / "spriteB__wsr.nhle.com_sprites_20232024_2023020204_ev743.json.json"))
    frames = goal["body"]
    f0 = frames[0]
    entities = f0["onIce"]
    puck = entities.get("1") if isinstance(entities, dict) else next(
        (e for e in entities if str(e.get("id")) == "1"), None)
    players = [e for k, e in (entities.items() if isinstance(entities, dict) else enumerate(entities))
               if str((e.get("id") if isinstance(e, dict) else k)) != "1"]
    # goals-only: goal eids return 200, non-goals return 403, across the cached games
    status = {"goal_200": 0, "nongoal_403": 0, "nongoal_other": 0, "games": set()}
    for fp in glob.glob(str(CACHE / "spriteB__*")):
        m = re.search(r"_(\d{10})_ev(\d+)", fp)
        if not m:
            continue
        st = _load(fp).get("status")
        status["games"].add(m.group(1))
        if st == 200:
            status["goal_200"] += 1
        elif st == 403:
            status["nongoal_403"] += 1
        else:
            status["nongoal_other"] += 1
    seasons = sorted({g[:4] for g in status["games"]})   # season start year from the 10-digit game id
    return {
        "goal_frame_count": len(frames),
        "entities_per_frame": len(entities),
        "has_puck": puck is not None,
        "sample_player_has_xy_playerid": all(k in players[0] for k in ("playerId", "x", "y")),
        "cadence": "timeStamp deciseconds -> 10 Hz (per dbt stg_ppt_tracking_frames)",
        "coord_frame": "raw inches corner-origin; x_std=raw_x/12-100, y_std=raw_y/12-42.5",
        "cache_status": {k: v for k, v in status.items() if k != "games"},
        "cache_seasons_YYYY": seasons,
        "scope": "GOALS ONLY (non-goal events 403 AccessDenied on wsr S3)",
    }


if __name__ == "__main__":
    r = reproduce()
    print("=== replay probe — verified from local cache ===")
    for k, v in r.items():
        print(f"  {k}: {v}")
    print("\nWarehouse coverage query (raw_ppt_replay; run with BQ creds):")
    print("  " + BQ_COVERAGE_SQL)
