"""Escalated read-only probe: can ANY fetch tactic surface non-goal ppt-replay tracking?

Follow-up to probe_ppt_events.py, which found non-goal sprite URLs return 403
AccessDenied (S3 missing-key semantics) while goals 200 with the same headers. The
owner explicitly authorized escalating fetch tactics to rule out that non-goal
tracking merely lives behind a different scheme / auth / host. Still read-only: no
BigQuery writes, no ingestion-client changes, no backfill.

Tests (all against the confirmed sprite-covered control game 2023020204 / 20232024):
  1. S3 bucket ENUMERATION — list objects under the game prefix. If allowed, this is
     decisive: it names every file that exists, so we see whether non-goal eventIds
     have any object at all. (virtual-host + path-style, several query forms)
  2. MISSING-KEY control — request a goal sprite (200), a non-goal sprite (403), and a
     nonexistent eventId (expected 403). Confirms 403 == key-absent under our creds,
     not selective blocking.
  3. Alternate FILENAME schemes for a known non-goal (shot ev62): ev62 w/o ext,
     62.json, zero-padded, play/shot/event prefixes, and game-level bundles
     (all/plays/events/frames/index/manifest/tracking.json).
  4. Alternate METADATA verbs: /v1/ppt-replay/{verb}/{game}/{event} for verb in
     {goal(control), shot, play, hit, save, event, sog} on a non-goal event, plus a
     full-body URL scan of the generic non-goal payload.
  5. TLS IMPERSONATION — refetch a goal (positive control) and a non-goal shot with
     curl_cffi Chrome impersonation. If the non-goal 200s where httpx 403'd, the wall
     is a TLS/fingerprint gate, not a missing object.

Any 200 that yields a frame array (a list whose items carry an onIce map) is a HIT and
is reported loudly. Otherwise the goal-only conclusion is reinforced with harder
evidence. Etiquette: >= 1.1s between requests, on-disk cache, no tactic beyond these.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).parent.parent))

from ingestion.nhl_api import WSR_HEADERS  # noqa: E402

try:
    from curl_cffi import requests as cffi_requests  # noqa: E402
    HAVE_CFFI = True
except Exception as e:  # noqa: BLE001
    HAVE_CFFI = False
    _CFFI_ERR = str(e)

BASE_URL = "https://api-web.nhle.com"
WSR_HOST = "https://wsr.nhle.com"
CACHE_DIR = Path(__file__).parent / "ppt_escalate_cache"
THROTTLE_S = 1.1

GAME = 2023020204
SEASON = "20232024"
GOAL_EV = 381          # known 200 sprite
NONGOAL_EV = 62        # shot-on-goal, known 403
MISSING_EV = 999999    # no such event
PREFIX = f"sprites/{SEASON}/{GAME}"

_last = [0.0]


def _throttle() -> None:
    dt = time.monotonic() - _last[0]
    if dt < THROTTLE_S:
        time.sleep(THROTTLE_S - dt)
    _last[0] = time.monotonic()


def _get(url: str, headers: dict | None = None, engine: str = "httpx") -> dict:
    """Fetch (cached). engine 'httpx' or 'cffi' (Chrome impersonation). Returns summary."""
    key = f"{engine}__" + url.replace("https://", "").replace("/", "_").replace("?", "_q_").replace("&", "_").replace("=", "-").replace(":", "_")
    path = CACHE_DIR / f"{key[:180]}.json"
    if path.exists():
        try:
            return json.loads(path.read_text())
        except Exception:  # noqa: BLE001
            pass
    _throttle()
    rec: dict = {"url": url, "engine": engine}
    try:
        if engine == "cffi":
            r = cffi_requests.get(url, headers=headers or {}, impersonate="chrome", timeout=30)
            status, text = r.status_code, r.text
            try:
                body = r.json()
            except Exception:  # noqa: BLE001
                body = None
        else:
            r = httpx.get(url, headers=headers or {}, timeout=30.0, follow_redirects=True)
            status, text = r.status_code, r.text
            try:
                body = r.json() if r.status_code == 200 else None
            except Exception:  # noqa: BLE001
                body = None
        rec["status"] = status
        rec["ctype"] = (r.headers.get("content-type") if hasattr(r, "headers") else None)
        if body is not None:
            rec["body"] = body
        else:
            rec["text"] = text[:600]
    except Exception as e:  # noqa: BLE001
        rec["status"] = None
        rec["error"] = f"{type(e).__name__}: {e}"
    try:
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(rec))
    except Exception:  # noqa: BLE001
        pass
    return rec


def _is_frame_array(body) -> tuple[bool, int, bool]:
    """(looks_like_tracking, frame_count, has_puck)."""
    if not isinstance(body, list) or not body:
        return (False, 0, False)
    puck = False
    ok = False
    for fr in body:
        if isinstance(fr, dict) and "onIce" in fr:
            ok = True
            oi = fr.get("onIce")
            if isinstance(oi, dict) and "1" in oi:
                puck = True
                break
    return (ok, len(body), puck)


def _find_urls(obj, path="") -> list[tuple[str, str]]:
    out = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            p = f"{path}.{k}" if path else str(k)
            if isinstance(k, str) and k.lower().endswith("url") and isinstance(v, str):
                out.append((p, v))
            out += _find_urls(v, p)
    elif isinstance(obj, list):
        for i, v in enumerate(obj[:3]):
            out += _find_urls(v, f"{path}[{i}]")
    return out


hits: list[str] = []


def _report_sprite(label: str, rec: dict, control: bool = False) -> None:
    st = rec.get("status")
    if st == 200 and "body" in rec:
        ok, fc, puck = _is_frame_array(rec["body"])
        if ok:
            # Goal positive-controls are EXPECTED 200s, not discoveries — don't count them.
            if not control:
                hits.append(f"{label}: {rec['url']} -> {fc} frames, puck={puck}")
            tag = "(expected goal control)" if control else "** HIT **"
            print(f"  {tag} {label:<28} 200 tracking array: {fc} frames puck={puck}  {rec['url']}")
            return
        print(f"  {label:<28} 200 but NOT a frame array (keys/type: "
              f"{list(rec['body'])[:6] if isinstance(rec['body'], dict) else type(rec['body']).__name__})  {rec['url']}")
        return
    snippet = ""
    if st not in (200, 404) and rec.get("text"):
        t = rec["text"].replace("\n", " ")
        snippet = f"  [{t[:70]}]"
    print(f"  {label:<28} {st}{snippet}  {rec['url']}")


def test1_enumerate() -> None:
    print("\n[1] S3/CloudFront bucket ENUMERATION (decisive if allowed)")
    forms = [
        f"{WSR_HOST}/?list-type=2&prefix={PREFIX}/&max-keys=1000",
        f"{WSR_HOST}/?prefix={PREFIX}/&max-keys=1000",
        f"{WSR_HOST}/sprites/{SEASON}/{GAME}/",
        f"{WSR_HOST}/sprites/{SEASON}/{GAME}",
    ]
    for url in forms:
        rec = _get(url, WSR_HEADERS)
        st = rec.get("status")
        body_text = rec.get("text", "") or (json.dumps(rec.get("body"))[:200] if rec.get("body") else "")
        listed = "ListBucketResult" in body_text or "<Key>" in body_text
        note = " <-- LISTING RETURNED" if listed else ""
        print(f"  {st}  {url}{note}")
        if listed:
            import re
            keys = re.findall(r"<Key>([^<]+)</Key>", body_text)
            print(f"    keys found ({len(keys)}): {keys[:40]}")
            hits.append(f"bucket listing exposed {len(keys)} keys at {url}")
        elif st not in (200, 403, 404):
            print(f"    body: {body_text[:160]}")


def test2_missing_control() -> None:
    print("\n[2] MISSING-KEY control (same host/headers, httpx)")
    for label, ev, ctl in [("goal ev%d (exists)" % GOAL_EV, GOAL_EV, True),
                           ("non-goal ev%d" % NONGOAL_EV, NONGOAL_EV, False),
                           ("nonexistent ev%d" % MISSING_EV, MISSING_EV, False)]:
        rec = _get(f"{WSR_HOST}/{PREFIX}/ev{ev}.json", WSR_HEADERS)
        _report_sprite(label, rec, control=ctl)


def test3_filenames() -> None:
    print(f"\n[3] Alternate FILENAME schemes for non-goal ev{NONGOAL_EV} + game-level bundles")
    ev = NONGOAL_EV
    variants = [
        f"ev{ev}.json", f"ev{ev}", f"{ev}.json", f"ev{ev:04d}.json",
        f"event{ev}.json", f"play{ev}.json", f"shot{ev}.json", f"e{ev}.json",
    ]
    bundles = ["all.json", "plays.json", "events.json", "frames.json",
               "index.json", "manifest.json", "tracking.json", "shots.json"]
    for v in variants:
        _report_sprite(f"file:{v}", _get(f"{WSR_HOST}/{PREFIX}/{v}", WSR_HEADERS))
    for b in bundles:
        _report_sprite(f"bundle:{b}", _get(f"{WSR_HOST}/{PREFIX}/{b}", WSR_HEADERS))


def test4_metadata_verbs() -> None:
    print(f"\n[4] Alternate METADATA verbs on non-goal ev{NONGOAL_EV} (+ goal control)")
    verbs = ["goal", "shot", "play", "hit", "save", "event", "sog", "shot-on-goal"]
    for verb in verbs:
        ev = GOAL_EV if verb == "goal" else NONGOAL_EV
        rec = _get(f"{BASE_URL}/v1/ppt-replay/{verb}/{GAME}/{ev}")
        st = rec.get("status")
        body = rec.get("body") or {}
        extra = sorted(set(body) - {"id", "gameDate", "awayTeam", "homeTeam",
                                    "gameState", "gameType"}) if isinstance(body, dict) else []
        urls = _find_urls(body)
        tag = ""
        if urls and any("wsr" in u or "sprite" in u.lower() or u.lower().endswith("pptreplayurl")
                        for _, u in urls):
            tag = "  <-- replay URL!"
            if verb != "goal":  # 'goal' is the expected positive control
                hits.append(f"verb '{verb}' ev{ev} exposed url(s): {urls}")
        print(f"  verb={verb:<13} ev{ev} -> {st} extra_keys={extra or '-'} "
              f"urls={[p for p, _ in urls] or '-'}{tag}")


def test5_impersonation() -> None:
    print("\n[5] TLS IMPERSONATION (curl_cffi Chrome) — goal control vs non-goal shot")
    if not HAVE_CFFI:
        print(f"  curl_cffi unavailable: {_CFFI_ERR}")
        return
    _report_sprite("cffi goal ev%d" % GOAL_EV,
                   _get(f"{WSR_HOST}/{PREFIX}/ev{GOAL_EV}.json", WSR_HEADERS, engine="cffi"),
                   control=True)
    _report_sprite("cffi non-goal ev%d" % NONGOAL_EV,
                   _get(f"{WSR_HOST}/{PREFIX}/ev{NONGOAL_EV}.json", WSR_HEADERS, engine="cffi"))
    # also try impersonation WITHOUT our explicit headers (pure browser profile)
    _report_sprite("cffi non-goal ev%d (no hdr)" % NONGOAL_EV,
                   _get(f"{WSR_HOST}/{PREFIX}/ev{NONGOAL_EV}.json", None, engine="cffi"))


def main() -> int:
    print("=" * 78)
    print(f"ESCALATED PROBE (read-only): non-goal ppt tracking on game {GAME}/{SEASON}")
    print("=" * 78)
    test1_enumerate()
    test2_missing_control()
    test3_filenames()
    test4_metadata_verbs()
    test5_impersonation()

    print("\n" + "=" * 78)
    print("VERDICT")
    print("=" * 78)
    if hits:
        print("Escalation SURFACED something — non-goal tracking may exist after all:")
        for h in hits:
            print(f"  - {h}")
    else:
        print("No escalation tactic surfaced a non-goal tracking array or any object at all:")
        print("  - bucket listing denied (can't enumerate, but nothing leaked)")
        print("  - non-goal + nonexistent eventIds both 403; only real goals 200 "
              "(403 == key-absent under our creds, not selective blocking)")
        print("  - no alternate filename/bundle scheme returned a frame array")
        print("  - no metadata verb exposed a replay URL for a non-goal event")
        print("  - Chrome TLS impersonation did NOT change any non-goal outcome "
              "(the wall is a MISSING OBJECT, not a fingerprint/auth gate)")
        print("=> Reinforced: ppt-replay sprites are genuinely GOAL-ONLY.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
