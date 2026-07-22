"""Stage 0.1 — input audit. Records (path, timestamp, rowcount) for every rule-4 input, verifies the
two views return the expected shapes, and names the DAG task that ingests raw_ppt_replay.

Results cache to data/cache/audit.json so ``make stage0`` reproduces offline after the first run.
"""
from __future__ import annotations

import datetime as dt
import json
import sys
from pathlib import Path

import pyarrow.parquet as pq

from . import bq, config

DAG_FILE = config.NIR / "dags" / "nhl_daily.py"
AUDIT_JSON = config.CACHE / "audit.json"


def _pq_meta(path: Path) -> dict:
    p = Path(path)
    if not p.exists():
        return {"path": str(p), "exists": False}
    md = pq.read_metadata(p)
    ts = dt.datetime.fromtimestamp(p.stat().st_mtime).isoformat(timespec="seconds")
    return {"path": str(p), "exists": True, "timestamp": ts, "rows": md.num_rows}


def _bq_count(tbl: str) -> int:
    return int(list(bq.client().query(f"select count(*) n from `{tbl}`").result())[0].n)


def _dag_task() -> dict:
    text = DAG_FILE.read_text().splitlines()
    task = None
    for i, line in enumerate(text):
        if "raw_ppt_replay" in line and "table_id" in line:
            # walk upward to the enclosing def
            for j in range(i, -1, -1):
                s = text[j].strip()
                if s.startswith("def "):
                    task = s.split("def ")[1].split("(")[0]
                    break
            break
    return {"file": str(DAG_FILE), "ingest_task": task,
            "note": "raw_ppt_replay is loaded inline in this task via load_json_to_bigquery(table_id='raw_ppt_replay')"}


def run(refresh: bool = False) -> dict:
    if AUDIT_JSON.exists() and not refresh:
        return json.loads(AUDIT_JSON.read_text())
    P = config.BQ_PROJECT
    # view shapes
    fr = list(bq.client().query(f"""
        select season, count(*) n_rows, count(distinct concat(cast(game_id as string),'-',cast(event_id as string))) goals
        from `{P}.{config.STAGING}.stg_ppt_tracking_frames` group by season order by season""").result())
    frames = {r.season: {"rows": int(r.n_rows), "goals": int(r.goals)} for r in fr}
    frames_total = sum(v["rows"] for v in frames.values())
    goals_total = sum(v["goals"] for v in frames.values())
    rel = list(bq.client().query(f"""
        select count(distinct concat(cast(game_id as string),'-',cast(event_id as string))) goals, count(*) n
        from `{P}.{config.STAGING}.int_goal_release_frame`""").result())[0]

    # expected-vs-actual (mismatch beyond newly-ingested 2025-26 rows => STOP)
    checks = {}
    for s, exp in config.EXPECTED_GOALS_BY_SEASON.items():
        got = frames.get(s, {}).get("goals", 0)
        checks[s] = {"expected_goals": exp, "actual_goals": got, "match": got == exp}
    frame_rows_match = frames_total == config.EXPECTED_FRAME_ROWS
    stop = any(not c["match"] for s, c in checks.items() if s != "2025-26") or \
        (goals_total < config.EXPECTED_GOALS)

    audit = {
        "generated": dt.datetime.now().isoformat(timespec="seconds"),
        "views": {
            "stg_ppt_tracking_frames": {"rows": frames_total, "goals": goals_total, "by_season": frames,
                                        "expected_rows": config.EXPECTED_FRAME_ROWS, "rows_match": frame_rows_match},
            "int_goal_release_frame": {"goals": int(rel.goals), "rows": int(rel.n),
                                       "expected_goals": config.EXPECTED_GOALS, "expected_rows": config.EXPECTED_RELEASE_ROWS},
        },
        "season_goal_checks": checks,
        "bq_tables": {
            "nhl_raw.raw_ppt_replay": {"rows": _bq_count(f"{P}.{config.RAW}.raw_ppt_replay")},
            "nhl_staging.stg_play_by_play": {"rows": _bq_count(f"{P}.{config.STAGING}.stg_play_by_play")},
        },
        "frozen_inputs": {
            "atlas_stints": _pq_meta(config.STINTS),
            "atlas_player_5v5": _pq_meta(config.PLAYER_5V5),
            "atlas_rapm_variant": _pq_meta(config.RAPM_VARIANT),
            "sysfx_team_season_fp": _pq_meta(config.TEAM_SEASON_FP),
            "sysfx_regime_ledger": _pq_meta(config.REGIME_LEDGER),
        },
        "dag": _dag_task(),
        "STOP": bool(stop),
    }
    config.CACHE.mkdir(parents=True, exist_ok=True)
    AUDIT_JSON.write_text(json.dumps(audit, indent=1, default=str))
    return audit


if __name__ == "__main__":
    # refresh=False so `make stage0` reproduces offline after the first cache-populating run;
    # pass `--refresh` to re-verify the live BigQuery view shapes.
    a = run(refresh="--refresh" in sys.argv)
    print(json.dumps(a, indent=1, default=str))
