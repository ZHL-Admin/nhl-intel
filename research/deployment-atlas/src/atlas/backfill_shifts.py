"""Backfill shift data for games the stats-REST shiftcharts endpoint left empty.

Recovers the 563 games (2024-26 + 1 in 2013-14) whose ``raw_shift_charts.data``
is an empty array, from the NHL HTML shift reports (parser validated byte-for-
byte against the JSON feed on a dual-source game). Normalizes into the exact
``raw_shift_charts`` element shape (typeCode 517) and loads to PRODUCTION
idempotently (delete-then-insert per game_id, so re-runs never duplicate).

Run: `python -m atlas.backfill_shifts`  (writes to production BigQuery)
"""

from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx
from google.cloud import bigquery

from . import config, shift_report, sources

RAW_TABLE = f"{sources.BQ_PROJECT}.nhl_raw.raw_shift_charts"
PBP_TABLE = f"{sources.BQ_PROJECT}.nhl_raw.raw_play_by_play"
REPORT_CACHE = config.RAW_DIR / "_shiftreports"
UA = {"User-Agent": "deployment-atlas/0.1 (research; HTML shift-report backfill)"}
RATE_SLEEP = 0.2  # ~5 req/s


def _mmss(sec: int) -> str:
    return f"{sec // 60:02d}:{sec % 60:02d}"


def season_label(gid: int) -> str:
    y = int(str(gid)[:4])
    return f"{y}-{str(y + 1)[2:]}"


# ---------------------------------------------------------------------------
# discovery + roster resolution (from BigQuery)
# ---------------------------------------------------------------------------
def empty_shift_games(client: bigquery.Client) -> list[int]:
    sql = f"""
    with latest as (
      select game_id, data,
        row_number() over (partition by game_id order by ingestion_date desc) as rn
      from `{RAW_TABLE}`
      where {sources._SCOPE_WHERE})
    select game_id from latest
    where rn = 1 and array_length(json_extract_array(data)) = 0
    order by game_id
    """
    return [r["game_id"] for r in client.query(sql).result()]


def game_rosters(client: bigquery.Client, game_ids: list[int]) -> dict[int, dict[str, Any]]:
    """Per game: home/away team id + {(team_id, sweater): (playerId, first, last)}."""
    ids = ",".join(str(g) for g in game_ids)
    sql = f"""
    with latest as (
      select game_id, homeTeam.id as home_id, awayTeam.id as away_id, rosterSpots,
        row_number() over (partition by game_id order by ingestion_date desc) as rn
      from `{PBP_TABLE}` where game_id in ({ids}))
    select l.game_id, l.home_id, l.away_id,
      rs.playerId as player_id, rs.teamId as team_id, rs.sweaterNumber as sweater,
      rs.firstName.default as first_name, rs.lastName.default as last_name
    from latest l, unnest(l.rosterSpots) rs
    where l.rn = 1
    """
    out: dict[int, dict[str, Any]] = {}
    for r in client.query(sql).result():
        g = out.setdefault(r["game_id"], {"home_id": r["home_id"], "away_id": r["away_id"],
                                          "map": {}})
        g["map"][(r["team_id"], r["sweater"])] = (
            r["player_id"], r["first_name"], r["last_name"])
    return out


# ---------------------------------------------------------------------------
# fetch + parse + normalize
# ---------------------------------------------------------------------------
def _fetch_report(http: httpx.Client, gid: int, side: str) -> str:
    REPORT_CACHE.mkdir(parents=True, exist_ok=True)
    cache = REPORT_CACHE / f"{gid}_{side}.HTM"
    if cache.exists():
        return cache.read_text(encoding="utf-8", errors="replace")
    url = shift_report.report_url(str(gid), side)
    for attempt in range(4):
        r = http.get(url)
        if r.status_code == 200:
            cache.write_text(r.text, encoding="utf-8")
            time.sleep(RATE_SLEEP)
            return r.text
        time.sleep(min(2 ** attempt, 30))
    raise RuntimeError(f"failed to fetch {url}: {r.status_code}")


def build_shift_array(gid: int, roster: dict[str, Any],
                      http: httpx.Client) -> tuple[list[dict], list[str]]:
    """Return (shift element list matching raw_shift_charts, unresolved warnings)."""
    home_id, away_id = roster["home_id"], roster["away_id"]
    rmap = roster["map"]
    elements: list[dict] = []
    warnings: list[str] = []
    for side, team_id in (("H", home_id), ("V", away_id)):
        html = _fetch_report(http, gid, side)
        for sh in shift_report.parse_report(html):
            key = (team_id, sh.sweater_number)
            if key not in rmap:
                warnings.append(f"{gid} {side} sweater {sh.sweater_number} unresolved")
                continue
            pid, fn, ln = rmap[key]
            elements.append({
                "playerId": pid, "teamId": team_id,
                "period": sh.period, "shiftNumber": sh.shift_number,
                "startTime": _mmss(sh.start_elapsed_s), "endTime": _mmss(sh.end_elapsed_s),
                "duration": _mmss(sh.duration_s),
                "typeCode": 517, "detailCode": 0,
                "firstName": fn, "lastName": ln, "gameId": gid,
                "eventDescription": None, "eventDetails": None,
                "teamAbbrev": None, "teamName": None, "hexValue": None,
                "eventNumber": None, "id": None,
                "_source": "html_shift_report",  # provenance marker
            })
    return elements, warnings


# ---------------------------------------------------------------------------
# idempotent production load
# ---------------------------------------------------------------------------
_LOAD_SCHEMA = [
    bigquery.SchemaField("game_id", "INTEGER"),
    bigquery.SchemaField("season", "STRING"),
    bigquery.SchemaField("data", "STRING"),
    bigquery.SchemaField("ingestion_date", "DATE"),
    bigquery.SchemaField("id", "INTEGER"),
]


def load_to_production(client: bigquery.Client, rows: list[dict], game_ids: list[int]) -> None:
    """Delete existing rows for these game_ids, then insert the recovered rows.
    Delete-then-insert => idempotent, no duplication (re-runs converge)."""
    ids = ",".join(str(g) for g in game_ids)
    client.query(f"DELETE FROM `{RAW_TABLE}` WHERE game_id IN ({ids})").result()
    job = client.load_table_from_json(
        rows, RAW_TABLE,
        job_config=bigquery.LoadJobConfig(
            schema=_LOAD_SCHEMA, write_disposition="WRITE_APPEND"),
    )
    job.result()


def main() -> int:
    client = bigquery.Client.from_service_account_json(str(sources.SA_KEYFILE),
                                                       project=sources.BQ_PROJECT)
    today = datetime.now(timezone.utc).date().isoformat()
    try:
        # Authoritative target: the games we identified as missing shift data and
        # confirmed have HTML reports (data/html_report_availability.json), UNION
        # any currently-empty arrays. The availability manifest is the stable
        # source of truth even after a prior backfill filled the rows (so a re-run
        # to fix e.g. OT parsing still targets them).
        target = set()
        avail = config.DATA_DIR / "html_report_availability.json"
        if avail.exists():
            target |= {int(g) for g in json.loads(avail.read_text())["per_game"]}
        integ = config.REPORTS_DIR / "phase1_integrity.json"
        if integ.exists():
            target |= set(json.loads(integ.read_text())["coverage"]["no_shift_games"])
        target |= set(empty_shift_games(client))
        games = sorted(target)
        print(f"games to backfill: {len(games)}")
        if not games:
            print("nothing to backfill.")
            return 0
        rosters = game_rosters(client, games)

        rows: list[dict] = []
        all_warnings: list[str] = []
        total_shifts = 0
        with httpx.Client(timeout=30, headers=UA, follow_redirects=True) as http:
            for i, gid in enumerate(games):
                roster = rosters.get(gid)
                if roster is None:
                    all_warnings.append(f"{gid} no roster (pbp missing)")
                    continue
                elements, warns = build_shift_array(gid, roster, http)
                all_warnings.extend(warns)
                total_shifts += len(elements)
                rows.append({
                    "game_id": gid, "season": season_label(gid),
                    "data": json.dumps(elements), "ingestion_date": today, "id": None,
                })
                if (i + 1) % 50 == 0:
                    print(f"  ...{i+1}/{len(games)} games, {total_shifts} shifts, "
                          f"{len(all_warnings)} warnings", flush=True)

        print(f"built {len(rows)} game rows, {total_shifts} shift elements, "
              f"{len(all_warnings)} unresolved warnings")
        if all_warnings[:10]:
            print("sample warnings:", all_warnings[:10])

        # sanity gate before touching production
        empty_built = [r["game_id"] for r in rows if r["data"] == "[]"]
        if empty_built:
            print(f"ABORT: {len(empty_built)} games produced empty arrays: {empty_built[:10]}")
            return 1

        print(f"writing {len(rows)} rows to PRODUCTION {RAW_TABLE} (delete-then-insert)...")
        load_to_production(client, rows, [r["game_id"] for r in rows])
        print("load complete.")

        # verify: re-check emptiness for these games
        remaining = empty_shift_games(client)
        still_empty = sorted(set(games) & set(remaining))
        print(f"post-load empty-shift games remaining: {len(still_empty)}")
        (config.RAW_DIR / "backfill_summary.json").write_text(json.dumps({
            "backfilled_games": len(rows), "total_shift_elements": total_shifts,
            "warnings": len(all_warnings), "still_empty_after": still_empty,
            "loaded_at": today,
        }, indent=2))
    finally:
        client.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
