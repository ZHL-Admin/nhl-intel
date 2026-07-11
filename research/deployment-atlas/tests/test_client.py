"""Client tests: cache-before-parse, cache reuse, backoff on 429/5xx, 404
surfaced as a finding, rate-limit spacing. All offline via MockTransport."""

from __future__ import annotations

import httpx
import pytest

from atlas.client import AtlasClient, FetchError, RateLimiter
from atlas.manifest import Manifest


def _client(handler, tmp_path, sleep=None):
    calls = []
    sleep = sleep or (lambda d: calls.append(d))
    http = httpx.Client(transport=httpx.MockTransport(handler))
    manifest = Manifest(tmp_path / "manifest.json")
    client = AtlasClient(http=http, manifest=manifest, sleep=sleep,
                         rate_limiter=RateLimiter(5.0, sleep=lambda d: None,
                                                  monotonic=lambda: 0.0),
                         clock=lambda: "2026-07-10T00:00:00+00:00")
    return client, calls


def test_fetch_caches_before_parse(tmp_path):
    hits = {"n": 0}

    def handler(request):
        hits["n"] += 1
        return httpx.Response(200, json={"ok": True})

    client, _ = _client(handler, tmp_path)
    cache = tmp_path / "g" / "pbp.json"
    data = client.fetch("http://x/pbp", cache, key="g/pbp")
    assert cache.exists()
    assert b"ok" in data
    assert hits["n"] == 1


def test_cache_hit_skips_network(tmp_path):
    hits = {"n": 0}

    def handler(request):
        hits["n"] += 1
        return httpx.Response(200, json={"v": 1})

    client, _ = _client(handler, tmp_path)
    cache = tmp_path / "g" / "pbp.json"
    client.fetch("http://x/pbp", cache, key="g/pbp")
    client.fetch("http://x/pbp", cache, key="g/pbp")  # second call: cache hit
    assert hits["n"] == 1


def test_backoff_retries_then_succeeds(tmp_path):
    seq = [429, 503, 200]

    def handler(request):
        code = seq.pop(0)
        if code == 200:
            return httpx.Response(200, json={"done": True})
        return httpx.Response(code)

    client, sleeps = _client(handler, tmp_path)
    data = client.fetch("http://x/pbp", tmp_path / "g" / "pbp.json", key="g/pbp")
    assert b"done" in data
    # Two retries -> two backoff sleeps, exponentially increasing (base 2s + jitter).
    assert len(sleeps) == 2
    assert sleeps[0] < sleeps[1]
    assert 2.0 <= sleeps[0] < 3.0
    assert 4.0 <= sleeps[1] < 5.0


def test_404_is_finding_not_crash(tmp_path):
    def handler(request):
        return httpx.Response(404)

    client, _ = _client(handler, tmp_path)
    res = client.fetch_result("http://x/shifts", tmp_path / "g" / "shifts.json", key="g/shifts")
    assert res.ok is False
    assert res.status == 404
    assert res.data is None


def test_404_raises_in_strict_fetch(tmp_path):
    def handler(request):
        return httpx.Response(404)

    client, _ = _client(handler, tmp_path)
    with pytest.raises(FetchError) as exc:
        client.fetch("http://x/shifts", tmp_path / "g" / "shifts.json", key="g/shifts")
    assert exc.value.status == 404


def test_rate_limiter_spacing():
    slept = []
    t = {"now": 0.0}
    rl = RateLimiter(5.0, sleep=lambda d: slept.append(d), monotonic=lambda: t["now"])
    rl.wait()          # first call: no wait
    rl.wait()          # immediately after: must wait ~0.2s
    assert slept and abs(slept[0] - 0.2) < 1e-9
