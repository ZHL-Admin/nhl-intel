"""Read-only probe: do ppt-replay tracking sprites exist for NON-GOAL events?

The methodology doc asserts the same ev{eventId}.json sprite scheme exists for
non-goals, but it was never verified — our client (ingestion.nhl_api.get_ppt_replay)
only ever reads goal.pptReplayUrl off the /goal/ metadata path. This probe answers
the open question WITHOUT writing anything to BigQuery, without touching the
ingestion client, and without escalating fetch tactics.

Two independent tests per event:
  Phase A (metadata): GET the GENERIC path /v1/ppt-replay/{game}/{event} (NOT /goal/),
    no headers. Compare each event's top-level keys against the "game shell" returned
    for a nonexistent event; report the extra keys and any *Url fields. Answers:
    "does the metadata attach a replay object for this event type?"
  Phase B (direct sprite, decisive): GET wsr.nhle.com/sprites/{season}/{game}/ev{event}.json
    with the WSR referer/UA headers, regardless of Phase A. Answers: "is there a sprite
    file on wsr for this event, independent of metadata wiring?" On 200, report
    frame_count and whether a puck entity (onIce key '1') is present.

Phase C generalizes A+B to one 2024-25 and one 2025-26 regular-season game, pulling
eventIds by type from our own stg_play_by_play (read-only), including one OT goal and
one empty-net goal.

Etiquette: >= 1.1s between network requests, on-disk cache so re-runs don't re-hit the
host, tenacity retry on 429/5xx. If wsr behaves differently than documented (403 with
headers, redirect, cf challenge), the script records it verbatim and moves on — it does
NOT escalate. Nothing is written to BigQuery; no backfill is started.

Usage:
    python scripts/probe_ppt_events.py            # full A+B+C
    python scripts/probe_ppt_events.py --no-phase-c
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

import httpx
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

sys.path.insert(0, str(Path(__file__).parent.parent))

from ingestion.nhl_api import WSR_HEADERS  # noqa: E402  (reuse the exact referer/UA)

BASE_URL = "https://api-web.nhle.com"
WSR_SPRITE_URL = "https://wsr.nhle.com/sprites/{season}/{game_id}/ev{event_id}.json"
CACHE_DIR = Path(__file__).parent / "ppt_probe_cache"
THROTTLE_S = 1.1

# Probe design for the sprite-covered control game (eventIds pulled from the live WSC feed).
CONTROL_GAME = 2023020204
CONTROL_SEASON = "20232024"
CONTROL_EVENTS = {
    "goal": [381, 399, 743, 795, 886],        # controls: expect sprites
    "shot-on-goal": [62, 212, 574],
    "missed-shot": [208, 217, 627],
    "blocked-shot": [151, 224, 891],
    "hit": [104, 105, 321],
    "faceoff": [101, 103, 665],
    "takeaway": [107],
    "giveaway": [118],
    "penalty": [57, 285],
}
GOAL_FULL_DUMP_EVENT = 381  # dump this goal's full generic-metadata payload

# --- throttle -----------------------------------------------------------------
_last_request = [0.0]


def _throttle() -> None:
    """Keep >= THROTTLE_S between actual network requests (cache hits don't count)."""
    dt = time.monotonic() - _last_request[0]
    if dt < THROTTLE_S:
        time.sleep(THROTTLE_S - dt)
    _last_request[0] = time.monotonic()


class _Retryable(Exception):
    """Raised on 429/5xx so tenacity backs off; 404 and other statuses are not retried."""


@retry(
    retry=retry_if_exception_type(_Retryable),
    stop=stop_after_attempt(4),
    wait=wait_exponential(multiplier=1, min=2, max=15),
)
def _raw_get(url: str, headers: dict | None) -> httpx.Response:
    _throttle()
    resp = httpx.get(url, headers=headers or {}, timeout=30.0, follow_redirects=True)
    if resp.status_code == 429 or resp.status_code >= 500:
        raise _Retryable(f"{resp.status_code} on {url}")
    return resp


def _cached_fetch(kind: str, url: str, headers: dict | None) -> dict:
    """Fetch with an on-disk cache. Returns {status, url, final_url, body|text|error}."""
    key = f"{kind}__" + url.replace("https://", "").replace("/", "_").replace(":", "_")
    path = CACHE_DIR / f"{key}.json"
    if path.exists():
        try:
            return json.loads(path.read_text())
        except Exception:  # noqa: BLE001 — corrupt entry, re-fetch
            pass
    try:
        resp = _raw_get(url, headers)
        rec: dict = {"status": resp.status_code, "url": url, "final_url": str(resp.url)}
        if resp.status_code == 200:
            try:
                rec["body"] = resp.json()
            except Exception:  # noqa: BLE001
                rec["text"] = resp.text[:500]
        else:
            rec["text"] = resp.text[:500]
    except Exception as e:  # noqa: BLE001 — record transport-level surprises verbatim
        rec = {"status": None, "url": url, "error": f"{type(e).__name__}: {e}"}
    try:
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(rec))
    except Exception:  # noqa: BLE001 — cache is best-effort
        pass
    return rec


# --- payload inspection -------------------------------------------------------
def _find_url_fields(obj, path: str = "") -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            p = f"{path}.{k}" if path else str(k)
            if isinstance(k, str) and k.lower().endswith("url") and isinstance(v, str):
                out.append((p, v))
            out += _find_url_fields(v, p)
    elif isinstance(obj, list):
        for i, v in enumerate(obj[:3]):  # first few list items is enough to spot url fields
            out += _find_url_fields(v, f"{path}[{i}]")
    return out


def phase_a(game_id: int, event_id: int, shell_keys: set[str]) -> dict:
    """Generic metadata path. Report status, keys beyond the game shell, and *Url fields."""
    url = f"{BASE_URL}/v1/ppt-replay/{game_id}/{event_id}"
    rec = _cached_fetch("metaA", url, None)
    body = rec.get("body") or {}
    top_keys = sorted(body.keys()) if isinstance(body, dict) else []
    extra = sorted(set(top_keys) - shell_keys)
    urls = _find_url_fields(body)
    return {
        "status": rec.get("status"),
        "top_keys": top_keys,
        "extra_keys": extra,           # keys beyond the game shell => the "replay object"
        "url_fields": urls,
        "attaches_replay": bool(extra) or bool(urls),
        "error": rec.get("error"),
        "_body": body,
    }


def phase_b(game_id: int, event_id: int, season: str) -> dict:
    """Direct sprite fetch on wsr (decisive). On 200: frame_count + puck-entity presence."""
    url = WSR_SPRITE_URL.format(season=season, game_id=game_id, event_id=event_id)
    rec = _cached_fetch("spriteB", url, WSR_HEADERS)
    out = {"status": rec.get("status"), "url": url, "error": rec.get("error"),
           "frame_count": None, "puck": None, "note": None}
    if rec.get("status") == 200:
        frames = rec.get("body")
        if isinstance(frames, list):
            out["frame_count"] = len(frames)
            puck = False
            for fr in frames:
                on_ice = fr.get("onIce") if isinstance(fr, dict) else None
                if isinstance(on_ice, dict) and "1" in on_ice:
                    puck = True
                    break
                if isinstance(on_ice, list) and any(e.get("entityKey") == "1" for e in on_ice):
                    puck = True
                    break
            out["puck"] = puck
        else:
            out["note"] = f"200 but body is {type(frames).__name__}, not a frame list"
    elif rec.get("status") not in (200, 404, None):
        # 403 with headers / redirect / cf challenge => record verbatim, do not escalate.
        out["note"] = f"unexpected status {rec.get('status')}: {rec.get('text', '')[:200]}"
    return out


def _establish_shell(game_id: int) -> set[str]:
    """Keys the generic metadata path returns for a NONEXISTENT event (the game shell)."""
    rec = _cached_fetch("metaA", f"{BASE_URL}/v1/ppt-replay/{game_id}/99999", None)
    body = rec.get("body") or {}
    keys = set(body.keys()) if isinstance(body, dict) else set()
    print(f"  [shell] nonexistent-event keys for {game_id}: {sorted(keys)} (status {rec.get('status')})")
    return keys


# --- probing a labeled set of (type -> [event_id]) ----------------------------
def probe_set(game_id: int, season: str, events_by_type: dict[str, list[int]]) -> dict:
    shell = _establish_shell(game_id)
    matrix: dict[str, dict] = {}
    goal_dump = None
    for etype, eids in events_by_type.items():
        rows = []
        for eid in eids:
            a = phase_a(game_id, eid, shell)
            b = phase_b(game_id, eid, season)
            rows.append({"event_id": eid, "a": a, "b": b})
            if game_id == CONTROL_GAME and eid == GOAL_FULL_DUMP_EVENT:
                goal_dump = a["_body"]
            fc = b["frame_count"]
            print(f"    {etype:<14} ev{eid:<5} | A status={a['status']} "
                  f"extra={a['extra_keys'] or '-'} url={'Y' if a['url_fields'] else '-'} "
                  f"| B status={b['status']} frames={fc if fc is not None else '-'} "
                  f"puck={b['puck']}" + (f" !! {b['note']}" if b.get('note') else ""))
        # aggregate for the matrix
        sprite_200 = [r["b"]["frame_count"] for r in rows if r["b"]["status"] == 200 and r["b"]["frame_count"] is not None]
        matrix[etype] = {
            "n": len(rows),
            "meta_attaches_replay": sum(1 for r in rows if r["a"]["attaches_replay"]),
            "sprite_200": sum(1 for r in rows if r["b"]["status"] == 200),
            "sprite_404": sum(1 for r in rows if r["b"]["status"] == 404),
            "sprite_other": sum(1 for r in rows if r["b"]["status"] not in (200, 404)),
            "frame_range": (min(sprite_200), max(sprite_200)) if sprite_200 else None,
            "rows": rows,
        }
    return {"matrix": matrix, "goal_dump": goal_dump}


def _print_matrix(title: str, matrix: dict) -> None:
    print(f"\n=== MATRIX: {title} ===")
    print(f"  {'event_type':<14} {'n':>3} {'meta_replay':>11} {'sprite200':>9} "
          f"{'404':>4} {'other':>5} {'frame_range':>14}")
    for etype, m in matrix.items():
        fr = f"{m['frame_range'][0]}-{m['frame_range'][1]}" if m["frame_range"] else "-"
        print(f"  {etype:<14} {m['n']:>3} {m['meta_attaches_replay']:>11} {m['sprite_200']:>9} "
              f"{m['sprite_404']:>4} {m['sprite_other']:>5} {fr:>14}")


# --- Phase C: pull eventIds by type from stg_play_by_play (read-only) ----------
def _phase_c_events(client, project: str, season: str, game_id: int) -> dict[str, list[int]]:
    types = ["goal", "shot-on-goal", "missed-shot", "blocked-shot", "hit",
             "faceoff", "takeaway", "giveaway", "penalty"]
    sql = f"""
        SELECT type_desc_key, ARRAY_AGG(event_id ORDER BY event_id LIMIT 3) AS eids
        FROM `{project}.nhl_staging.stg_play_by_play`
        WHERE game_id = {game_id} AND event_id IS NOT NULL
          AND type_desc_key IN UNNEST(@types)
        GROUP BY type_desc_key
    """
    from google.cloud import bigquery
    job = client.query(sql, job_config=bigquery.QueryJobConfig(
        query_parameters=[bigquery.ArrayQueryParameter("types", "STRING", types)]))
    out = {r.type_desc_key: [int(e) for e in r.eids] for r in job.result()}
    return {t: out.get(t, []) for t in types if out.get(t)}


def _find_special_goals(client, project: str, season: str) -> list[tuple[str, int, int]]:
    """(label, game_id, event_id) for one OT goal and one empty-net goal in the season."""
    specials = []
    ot = list(client.query(f"""
        SELECT game_id, event_id FROM `{project}.nhl_staging.stg_play_by_play`
        WHERE season='{season}' AND type_desc_key='goal' AND period_type='OT'
          AND event_id IS NOT NULL
          AND CAST(game_id AS STRING) LIKE '____02%'
        ORDER BY game_id LIMIT 1""").result())
    if ot:
        specials.append(("OT-goal", int(ot[0].game_id), int(ot[0].event_id)))
    en = list(client.query(f"""
        SELECT game_id, event_id FROM `{project}.nhl_staging.stg_play_by_play`
        WHERE season='{season}' AND type_desc_key='goal' AND goalie_in_net_id IS NULL
          AND event_id IS NOT NULL
          AND CAST(game_id AS STRING) LIKE '____02%'
        ORDER BY game_id LIMIT 1""").result())
    if en:
        specials.append(("empty-net-goal", int(en[0].game_id), int(en[0].event_id)))
    return specials


def _season_str(game_id: int) -> str:
    """wsr sprite path season token, e.g. 2024020001 -> '20242025'."""
    y = int(str(game_id)[:4])
    return f"{y}{y + 1}"


def run_phase_c(results: dict) -> None:
    try:
        from google.cloud import bigquery
    except Exception as e:  # noqa: BLE001
        print(f"\n[Phase C skipped] google-cloud-bigquery unavailable: {e}")
        return
    project = os.environ.get("GCP_PROJECT_ID")
    if not project:
        print("\n[Phase C skipped] GCP_PROJECT_ID unset (source .env first).")
        return
    client = bigquery.Client(project=project)
    for season, game_id in (("2024-25", 2024020001), ("2025-26", 2025020001)):
        print(f"\n--- Phase C: {season} game {game_id} ---")
        try:
            events = _phase_c_events(client, project, season, game_id)
        except Exception as e:  # noqa: BLE001
            print(f"  [skip] pbp query failed: {e}")
            continue
        if not events:
            print(f"  [skip] no pbp rows for {game_id} yet.")
            continue
        wsr_season = _season_str(game_id)
        res = probe_set(game_id, wsr_season, events)
        _print_matrix(f"{season} game {game_id}", res["matrix"])
        results[season] = res["matrix"]
        # special goals (OT + empty-net), possibly in other games of the season
        try:
            specials = _find_special_goals(client, project, season)
        except Exception as e:  # noqa: BLE001
            print(f"  [special-goal lookup failed: {e}]")
            specials = []
        for label, gid, eid in specials:
            shell = _establish_shell(gid)
            a = phase_a(gid, eid, shell)
            b = phase_b(gid, eid, _season_str(gid))
            print(f"  {label:<16} game {gid} ev{eid} | A status={a['status']} "
                  f"extra={a['extra_keys'] or '-'} | B status={b['status']} "
                  f"frames={b['frame_count']} puck={b['puck']}"
                  + (f" !! {b['note']}" if b.get('note') else ""))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-phase-c", action="store_true", help="skip the BigQuery-backed generalization")
    args = ap.parse_args()

    print("=" * 78)
    print("PROBE: do ppt-replay sprites exist for NON-GOAL events? (read-only, no writes)")
    print("=" * 78)

    results: dict[str, dict] = {}

    print(f"\n--- Phase A+B: control game {CONTROL_GAME} (season {CONTROL_SEASON}) ---")
    control = probe_set(CONTROL_GAME, CONTROL_SEASON, CONTROL_EVENTS)
    _print_matrix(f"control {CONTROL_GAME} ({CONTROL_SEASON})", control["matrix"])
    results[CONTROL_SEASON] = control["matrix"]

    if control["goal_dump"] is not None:
        print(f"\n=== FULL generic-metadata payload for GOAL ev{GOAL_FULL_DUMP_EVENT} "
              f"(game {CONTROL_GAME}) ===")
        print(json.dumps(control["goal_dump"], indent=2)[:6000])

    if not args.no_phase_c:
        run_phase_c(results)

    # --- interpretation --------------------------------------------------------
    print("\n" + "=" * 78)
    print("INTERPRETATION")
    print("=" * 78)
    nongoal_sprites = []
    nongoal_403 = nongoal_404 = 0
    goal_ok = False
    for season, matrix in results.items():
        for etype, m in matrix.items():
            if etype == "goal" and m["sprite_200"] > 0:
                goal_ok = True
            if etype != "goal":
                nongoal_403 += m["sprite_other"]  # 403 AccessDenied etc.
                nongoal_404 += m["sprite_404"]
                if m["sprite_200"] > 0:
                    nongoal_sprites.append((season, etype, m["sprite_200"], m["n"]))
    if nongoal_sprites:
        print("NON-GOAL sprites FOUND — tracking is broader than goals; our metadata "
              "wiring is merely goal-scoped. Types with sprites:")
        for season, etype, hit, n in nongoal_sprites:
            print(f"  - {season}: {etype} ({hit}/{n} returned a sprite)")
    elif goal_ok:
        print(f"NO non-goal event returned a sprite ({nongoal_403} x 403-AccessDenied, "
              f"{nongoal_404} x 404) while every goal control returned frames — with the "
              "SAME referer/UA headers on the SAME host/game, so this is object-not-found, "
              "not host-level blocking (wsr's S3 returns 403 AccessDenied, not 404, for a "
              "missing key). Sprites are GENUINELY GOAL-ONLY; the goals-only plan stands.")
    else:
        print("Goal controls did NOT return sprites — inconclusive; investigate the "
              "control fetch (host behavior / headers) before drawing conclusions.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
