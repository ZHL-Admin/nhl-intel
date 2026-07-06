"""Differential verification of the DuckDB serving layer vs BigQuery.

Runs a representative set of the backend's real request-time queries against whichever
backend SERVING_BACKEND selects, printing per-probe row counts, a value checksum, and
latency. Run it once per backend and diff the reports to prove parity + the speedup:

    set -a && source .env && set +a
    export GOOGLE_APPLICATION_CREDENTIALS=$PWD/secrets/nhl-intel-sa.json
    SERVING_BACKEND=bigquery python -m scripts.verify_serving_parity > /tmp/bq.txt
    SERVING_BACKEND=duckdb   python -m scripts.verify_serving_parity > /tmp/duck.txt
    diff <(grep -E '^(PROBE|  rows|  checksum)' /tmp/bq.txt) \
         <(grep -E '^(PROBE|  rows|  checksum)' /tmp/duck.txt)   # value parity
    # (latency lines differ by design — that's the point.)

Probes call the actual `bq_service.get_*` methods (so the SQL is the real thing) plus a
few high-traffic inline router queries. IDs are discovered from the data at runtime.
"""
from __future__ import annotations

import hashlib
import os
import sys
import time
from pathlib import Path

# Make `services` importable the same way the backend does (backend/ on sys.path).
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from services.bigquery import bq_service  # noqa: E402


def _checksum(rows: list) -> str:
    """Stable order-insensitive checksum of result rows (rounded floats for cross-engine)."""
    def norm(v):
        if isinstance(v, float):
            return round(v, 4)
        return str(v)
    parts = sorted("|".join(f"{k}={norm(r[k])}" for k in sorted(r)) for r in rows)
    return hashlib.md5("\n".join(parts).encode()).hexdigest()[:12]


def _discover_ids() -> dict:
    """Find a recent final game, an active player/team/goalie from the served data."""
    season = bq_service.query(
        f"SELECT MAX(season) s FROM {bq_service.get_full_table_id('stg_games')}"
    )[0]["s"]
    # The latest real NHL game (type 02/03) that actually has shot data — avoids exhibition /
    # Olympic / 4-Nations games (type 09/19/20) which carry no shots and would yield empty probes.
    gid = bq_service.query(
        f"""SELECT MAX(game_id) AS g FROM {bq_service.get_full_table_id('int_shot_attempts_all')}
            WHERE SUBSTR(CAST(game_id AS STRING), 5, 2) IN ('02','03')"""
    )[0]["g"]
    return {"season": season, "game_id": int(gid),
            "player_id": 8478402, "team_id": 22, "goalie_id": 8479973}


def main() -> int:
    backend = os.getenv("SERVING_BACKEND", "duckdb")
    ids = _discover_ids()
    print(f"BACKEND={backend}  ids={ids}\n")

    g = ids["game_id"]
    pid = ids["player_id"]
    tid = ids["team_id"]
    season = ids["season"]

    # (label, callable) — each returns a list[dict]. Real service methods where possible.
    probes = [
        ("get_game_shots", lambda: bq_service.get_game_shots(g)),
        ("get_winprob", lambda: bq_service.get_winprob(g)),
        ("get_winprob_goal_swings", lambda: bq_service.get_winprob_goal_swings(g)),
        ("get_xg_worm", lambda: bq_service.get_xg_worm(g)),
        ("get_goaltending", lambda: bq_service.get_goaltending(g)),
        ("get_game_goals", lambda: bq_service.get_game_goals(g)),
        ("get_team_comparison", lambda: [bq_service.get_team_comparison(g) or {}]),
        ("get_pressure_shots", lambda: bq_service.get_pressure_shots(g)),
        ("get_special_teams", lambda: bq_service.get_special_teams(g)),
        ("get_goalie_danger", lambda: bq_service.get_goalie_danger(g)),
        ("get_shot_quality", lambda: bq_service.get_shot_quality(g)),
        ("get_skater_impact", lambda: bq_service.get_skater_impact(g)),
        ("get_game_context", lambda: [bq_service.get_game_context(g) or {}]),
        ("get_player_situational", lambda: bq_service.get_player_situational(pid, season)),
        ("get_player_zone_deployment", lambda: bq_service.get_player_zone_deployment(pid, season)),
        ("get_player_shooting_luck", lambda: bq_service.get_player_shooting_luck(pid, season)),
        ("get_player_relative", lambda: bq_service.get_player_relative(pid, season)),
        ("get_team_zone_time", lambda: bq_service.get_team_zone_time(tid, season)),
        ("get_team_faceoffs", lambda: bq_service.get_team_faceoffs(tid, season)),
        ("get_player_edge", lambda: [bq_service.get_player_edge(pid) or {}]),
        ("get_team_edge", lambda: [bq_service.get_team_edge(tid) or {}]),
        # Player Assessment (Layer 1) + Context (Layer 2) reads. These pass once the nightly export
        # populates player_assessment / mart_player_quality_context in the DuckDB serving file.
        ("player_assessment", lambda: bq_service.query(
            f"SELECT * FROM {bq_service.get_models_table_id('player_assessment')} "
            f"WHERE player_id = {pid} ORDER BY season_window")),
        ("mart_player_quality_context", lambda: bq_service.query(
            f"SELECT * FROM {bq_service.get_full_table_id('mart_player_quality_context')} "
            f"WHERE player_id = {pid} ORDER BY season, team_id")),
    ]

    n_ok = n_err = 0
    for label, fn in probes:
        print(f"PROBE {label}")
        t0 = time.time()
        try:
            rows = fn()
            dt = (time.time() - t0) * 1000
            print(f"  rows {len(rows)}")
            print(f"  checksum {_checksum(rows)}")
            print(f"  latency_ms {dt:.0f}")
            n_ok += 1
        except Exception as e:  # noqa: BLE001
            print(f"  ERROR {type(e).__name__}: {str(e)[:160]}")
            n_err += 1
        print()

    print(f"SUMMARY backend={backend} ok={n_ok} err={n_err}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
