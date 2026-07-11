"""Phase 0 driver: ingest fixtures, audit payloads, probe earliest usable season.

Produces reports/phase0_probe.json (machine-readable evidence). The human
narrative in reports/phase0.md is written from this probe.

Run: `make phase0`  (or `python -m atlas.phase0`)
"""

from __future__ import annotations

import json
import platform
import sys
from datetime import datetime, timezone
from typing import Any

from . import config, fetch, paths, probe
from .client import AtlasClient

# Task 0.2: exact fixture games (some old ones may 404 / have empty shifts).
FIXTURE_GAMES = [
    "2023020204",  # modern regular season
    "2023030411",  # modern playoff (OT)
    "2019020500",
    "2015020001",
    "2011020400",
    "2008020300",
]

# Task 0.6: probe one mid-season game per season, walking backward, until two
# consecutive seasons fail. Game number 0500 is ~early-December (mid-season).
PROBE_GAME_NUMBER = "0500"
PROBE_START_SEASON = 2010  # 2010-11; walk downward


def _run_meta() -> dict[str, Any]:
    return {
        "seed": config.SEED,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "python": sys.version.split()[0],
        "platform": platform.platform(),
        "user_agent": config.USER_AGENT,
        "rate_limit_per_sec": config.MAX_REQUESTS_PER_SEC,
        "backoff": {
            "base_s": config.BACKOFF_BASE_SECONDS,
            "max_s": config.BACKOFF_MAX_SECONDS,
            "max_retries": config.MAX_RETRIES,
            "retry_status": sorted(config.RETRY_STATUS_CODES),
        },
    }


# ---------------------------------------------------------------------------
# 0.2 ingest
# ---------------------------------------------------------------------------
def ingest_fixtures(client: AtlasClient) -> list[dict[str, Any]]:
    log: list[dict[str, Any]] = []
    for gid in FIXTURE_GAMES:
        rec: dict[str, Any] = {"game_id": gid, "season": paths.season_for_game(gid),
                               "game_type": paths.game_type(gid)}
        for kind in ("shifts", "pbp", "boxscore"):
            res = fetch.game_resource_result(client, gid, kind)
            entry: dict[str, Any] = {"ok": res.ok, "status": res.status,
                                     "from_cache": res.from_cache, "error": res.error}
            if res.ok and res.data is not None:
                try:
                    obj = json.loads(res.data)
                    entry["bytes"] = len(res.data)
                    if kind == "shifts":
                        data = obj.get("data", []) if isinstance(obj, dict) else []
                        entry["shift_rows_total"] = len(data)
                        entry["shift_rows_517"] = sum(
                            1 for r in data if r.get("typeCode") == config.SHIFT_TYPECODE_SHIFT)
                    elif kind == "pbp":
                        entry["play_count"] = len(obj.get("plays", [])) if isinstance(obj, dict) else 0
                    elif kind == "boxscore":
                        entry["has_playerByGameStats"] = (
                            isinstance(obj, dict) and "playerByGameStats" in obj)
                except json.JSONDecodeError as exc:
                    entry["parse_error"] = str(exc)
            rec[kind] = entry
        log.append(rec)
    return log


# ---------------------------------------------------------------------------
# 0.3 shifts audit
# ---------------------------------------------------------------------------
def audit_shifts(client: AtlasClient, game_id: str) -> dict[str, Any]:
    payload = fetch.shifts(client, game_id)
    rows = payload.get("data", []) if isinstance(payload, dict) else []
    fields = ["id", "playerId", "teamId", "teamAbbrev", "teamName", "period",
              "startTime", "endTime", "duration", "typeCode", "detailCode",
              "eventNumber", "shiftNumber", "hexValue", "firstName", "lastName",
              "gameId", "eventDescription", "eventDetails"]
    shifts_only = [r for r in rows if r.get("typeCode") == config.SHIFT_TYPECODE_SHIFT]
    goalie_pos = _positions_for_players(client, game_id)
    shift_pids = {r.get("playerId") for r in shifts_only}
    goalie_pids_in_shifts = sorted(
        pid for pid in shift_pids if goalie_pos.get(pid) == "G")
    return {
        "total_field": payload.get("total") if isinstance(payload, dict) else None,
        "row_count": len(rows),
        "shift_rows_517": len(shifts_only),
        "typeCode_distribution": probe.distribution(rows, "typeCode"),
        "detailCode_distribution": probe.distribution(rows, "detailCode"),
        "fields": probe.field_report(rows, fields),
        "fields_on_517_only": probe.field_report(shifts_only, fields),
        "max_period": max((r.get("period") or 0 for r in rows), default=0),
        "period_distribution": probe.distribution(rows, "period"),
        "goalies_in_shifts_count": len(goalie_pids_in_shifts),
        "goalies_in_shifts_sample": goalie_pids_in_shifts[:6],
        "example_row_517": next((r for r in shifts_only), None),
        "example_row_505": next((r for r in rows
                                 if r.get("typeCode") == config.SHIFT_TYPECODE_GOAL), None),
    }


def _positions_for_players(client: AtlasClient, game_id: str) -> dict[int, str]:
    pbp = fetch.pbp(client, game_id)
    out: dict[int, str] = {}
    for r in (pbp.get("rosterSpots", []) if isinstance(pbp, dict) else []):
        out[r.get("playerId")] = r.get("positionCode")
    return out


# ---------------------------------------------------------------------------
# 0.4 pbp audit
# ---------------------------------------------------------------------------
def audit_pbp(client: AtlasClient, game_id: str) -> dict[str, Any]:
    payload = fetch.pbp(client, game_id)
    plays = payload.get("plays", []) if isinstance(payload, dict) else []
    details_by_type: dict[str, list[str]] = {}
    for p in plays:
        k = p.get("typeDescKey", "?")
        if k not in details_by_type and isinstance(p.get("details"), dict):
            details_by_type[k] = sorted(p["details"].keys())

    # Empty-net evidence: goals where the scored-on goalie is absent
    # (goalieInNetId missing) and/or situationCode shows a pulled goalie.
    goal_situations = []
    for p in plays:
        if p.get("typeDescKey") == "goal":
            d = p.get("details", {}) if isinstance(p.get("details"), dict) else {}
            goal_situations.append({
                "eventId": p.get("eventId"),
                "situationCode": p.get("situationCode"),
                "goalieInNetId": d.get("goalieInNetId"),
                "eventOwnerTeamId": d.get("eventOwnerTeamId"),
                "empty_net_inferred": d.get("goalieInNetId") is None,
            })

    penalty_examples = [p for p in plays if p.get("typeDescKey") == "penalty"][:3]
    return {
        "play_count": len(plays),
        "top_level_keys": list(payload.keys()) if isinstance(payload, dict) else [],
        "has_onice_player_lists": _detect_onice_lists(plays),
        "typeDescKey_distribution": probe.distribution(plays, "typeDescKey"),
        "situationCode_distribution": probe.distribution(plays, "situationCode"),
        "details_keys_by_type": details_by_type,
        "coordinate_location": "details.xCoord / details.yCoord (and details.zoneCode)",
        "penalty_examples": [p.get("details") | {"timeInPeriod": p.get("timeInPeriod"),
                             "period": (p.get("periodDescriptor") or {}).get("number")}
                             for p in penalty_examples],
        "goal_situations": goal_situations,
        "rosterSpots_count": len(payload.get("rosterSpots", [])) if isinstance(payload, dict) else 0,
    }


def _detect_onice_lists(plays: list[Any]) -> dict[str, Any]:
    hits: dict[str, int] = {}
    for p in plays:
        if not isinstance(p, dict):
            continue
        for scope, obj in (("play", p), ("details", p.get("details", {}))):
            if not isinstance(obj, dict):
                continue
            for k, v in obj.items():
                if isinstance(v, list) and len(v) >= 3 and all(isinstance(x, int) for x in v):
                    hits[f"{scope}.{k}"] = hits.get(f"{scope}.{k}", 0) + 1
    return {"onice_list_fields_found": hits}


# ---------------------------------------------------------------------------
# 0.5 boxscore audit
# ---------------------------------------------------------------------------
def audit_boxscore(client: AtlasClient, game_id: str) -> dict[str, Any]:
    box = fetch.boxscore(client, game_id)
    pbgs = box.get("playerByGameStats", {}) if isinstance(box, dict) else {}
    sample_skater = None
    sample_goalie = None
    for team in ("awayTeam", "homeTeam"):
        grp = pbgs.get(team, {})
        if grp.get("forwards"):
            sample_skater = sample_skater or grp["forwards"][0]
        if grp.get("goalies"):
            sample_goalie = sample_goalie or grp["goalies"][0]
    return {
        "playerByGameStats_shape": {
            team: {grp: len(pbgs.get(team, {}).get(grp, []))
                   for grp in ("forwards", "defense", "goalies")}
            for team in ("awayTeam", "homeTeam")
        },
        "toi_location": "playerByGameStats.<team>.<forwards|defense|goalies>[].toi",
        "toi_format_sample": {"skater_toi": (sample_skater or {}).get("toi"),
                              "goalie_toi": (sample_goalie or {}).get("toi")},
        "skater_stat_keys": sorted(sample_skater.keys()) if sample_skater else [],
        "goalie_stat_keys": sorted(sample_goalie.keys()) if sample_goalie else [],
    }


# ---------------------------------------------------------------------------
# 0.6 earliest usable season probe
# ---------------------------------------------------------------------------
def probe_earliest_season(client: AtlasClient) -> dict[str, Any]:
    probed: list[dict[str, Any]] = []
    consecutive_fail = 0
    earliest_usable: str | None = None
    season = PROBE_START_SEASON
    while season >= 1990:  # generous floor; loop exits on 2 consecutive fails
        gid = f"{season}02{PROBE_GAME_NUMBER}"
        res = fetch.game_resource_result(client, gid, "shifts")
        usable = False
        shift_rows = None
        if res.ok and res.data is not None:
            try:
                obj = json.loads(res.data)
                data = obj.get("data", []) if isinstance(obj, dict) else []
                shift_rows = sum(1 for r in data
                                 if r.get("typeCode") == config.SHIFT_TYPECODE_SHIFT)
                usable = shift_rows > 0
            except json.JSONDecodeError:
                usable = False
        probed.append({"season": f"{season}{season+1}", "game_id": gid,
                       "status": res.status, "ok": res.ok,
                       "shift_rows_517": shift_rows, "usable": usable})
        if usable:
            earliest_usable = f"{season}{season+1}"
            consecutive_fail = 0
        else:
            consecutive_fail += 1
            if consecutive_fail >= 2:
                break
        season -= 1
    return {"earliest_usable_season": earliest_usable,
            "consecutive_fail_stop": consecutive_fail >= 2,
            "probed": probed}


# ---------------------------------------------------------------------------
# driver
# ---------------------------------------------------------------------------
def main() -> int:
    config.REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    with AtlasClient() as client:
        fetch_log = ingest_fixtures(client)
        audit = {
            "shifts_2023020204": audit_shifts(client, "2023020204"),
            "pbp_2023020204": audit_pbp(client, "2023020204"),
            "boxscore_2023020204": audit_boxscore(client, "2023020204"),
            "shifts_2023030411": audit_shifts(client, "2023030411"),
        }
        earliest = probe_earliest_season(client)

    result = {"run_meta": _run_meta(), "fetch_log": fetch_log,
              "audit": audit, "earliest_season": earliest}

    (config.REPORTS_DIR / "phase0_probe.json").write_text(json.dumps(result, indent=2, default=str))
    config.FETCH_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    config.FETCH_LOG_PATH.write_text(json.dumps(fetch_log, indent=2))
    config.RUN_META_PATH.write_text(json.dumps(result["run_meta"], indent=2))

    print("Phase 0 probe written to reports/phase0_probe.json")
    for rec in fetch_log:
        s = rec["shifts"]
        print(f"  {rec['game_id']}: shifts status={s.get('status')} "
              f"rows_517={s.get('shift_rows_517')} pbp={rec['pbp'].get('play_count')}")
    print(f"  earliest usable season: {earliest['earliest_usable_season']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
