"""Phase 0.3(c) era probe: does gamecenter right-rail carry headCoach across eras?
Fetches ONE regular-season game per era, caches to disk, reports populated blocks.
Rate-limited <=5 req/s with exponential backoff. Six requests total."""
from __future__ import annotations
import json, time, sys
from pathlib import Path
import httpx

CACHE = Path(__file__).resolve().parents[2] / "data/cache/probe/right_rail"
CACHE.mkdir(parents=True, exist_ok=True)
GAMES = {  # era -> a mid-season regular game id (SSSS02XXXX)
    "2010": 2010020500, "2013": 2013020500, "2016": 2016020500,
    "2019": 2019020500, "2022": 2022020500, "2024": 2024020500,
}
URL = "https://api-web.nhle.com/v1/gamecenter/{gid}/right-rail"

def fetch(gid: int) -> dict:
    fp = CACHE / f"{gid}.json"
    if fp.exists():
        return json.loads(fp.read_text())
    delay = 0.25
    for attempt in range(5):
        try:
            r = httpx.get(URL.format(gid=gid), timeout=30,
                          headers={"User-Agent": "syseff-probe/0.1"})
            if r.status_code == 200:
                fp.write_text(r.text)
                time.sleep(0.25)  # <=5 req/s
                return r.json()
            if r.status_code == 404:
                return {"__status__": 404}
            raise httpx.HTTPStatusError(f"{r.status_code}", request=r.request, response=r)
        except Exception as e:
            if attempt == 4:
                return {"__error__": str(e)}
            time.sleep(delay); delay *= 2
    return {"__error__": "exhausted"}

def probe():
    out = {}
    for era, gid in GAMES.items():
        d = fetch(gid)
        gi = d.get("gameInfo", {}) if isinstance(d, dict) else {}
        rec = {
            "game_id": gid,
            "status": d.get("__status__") or d.get("__error__") or 200,
            "home_coach": (gi.get("homeTeam", {}) or {}).get("headCoach", {}).get("default") if gi else None,
            "away_coach": (gi.get("awayTeam", {}) or {}).get("headCoach", {}).get("default") if gi else None,
            "has_referees": bool(gi.get("referees")) if gi else False,
            "has_linesmen": bool(gi.get("linesmen")) if gi else False,
            "home_scratches_n": len((gi.get("homeTeam", {}) or {}).get("scratches", []) or []) if gi else 0,
            "away_scratches_n": len((gi.get("awayTeam", {}) or {}).get("scratches", []) or []) if gi else 0,
            "top_keys": sorted(d.keys())[:12] if isinstance(d, dict) else None,
        }
        out[era] = rec
        print(f"[{era}] g={gid} status={rec['status']} "
              f"home_coach={rec['home_coach']!r} away_coach={rec['away_coach']!r} "
              f"refs={rec['has_referees']} lines={rec['has_linesmen']} "
              f"scratch(h/a)={rec['home_scratches_n']}/{rec['away_scratches_n']}")
    (CACHE / "_probe_summary.json").write_text(json.dumps(out, indent=2))
    return out

if __name__ == "__main__":
    probe()
