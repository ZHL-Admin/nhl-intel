"""Caching, rate-limited, retrying HTTP client.

Policy (from the preamble):
  * at most 5 requests/second,
  * exponential backoff on 429/5xx: base 2s, max 60s, up to 5 retries,
  * every fetch cached to disk as raw bytes before parsing,
  * re-runs never re-fetch a cached resource.

The client is constructed with an ``httpx.Client`` so tests can inject an
``httpx.MockTransport`` and exercise the retry/cache logic with zero network.
Backoff jitter is drawn from a seeded RNG; the seed is recorded in run_meta.

``fetch`` raises on failure (happy path); ``fetch_result`` never raises and is
used by ingestion so that a 404 on an old game is recorded as a finding.
"""

from __future__ import annotations

import hashlib
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from random import Random

import httpx

from . import config
from .manifest import Manifest, ManifestEntry


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class RateLimiter:
    """Enforces a minimum spacing between request starts (<= max/sec)."""

    def __init__(self, max_per_sec: float, sleep: Callable[[float], None] = time.sleep,
                 monotonic: Callable[[], float] = time.monotonic):
        self._min_interval = 1.0 / max_per_sec
        self._sleep = sleep
        self._monotonic = monotonic
        self._last_start: float | None = None

    def wait(self) -> None:
        now = self._monotonic()
        if self._last_start is not None:
            elapsed = now - self._last_start
            if elapsed < self._min_interval:
                self._sleep(self._min_interval - elapsed)
        self._last_start = self._monotonic()


class FetchError(RuntimeError):
    """Raised when a resource cannot be fetched after all retries."""

    def __init__(self, message: str, status: int | None = None):
        super().__init__(message)
        self.status = status


@dataclass
class FetchResult:
    key: str
    url: str
    ok: bool
    status: int | None
    from_cache: bool
    path: str | None
    error: str | None
    data: bytes | None


class AtlasClient:
    def __init__(
        self,
        http: httpx.Client | None = None,
        manifest: Manifest | None = None,
        *,
        seed: int = config.SEED,
        rate_limiter: RateLimiter | None = None,
        sleep: Callable[[float], None] = time.sleep,
        clock: Callable[[], str] = _utcnow_iso,
    ):
        self._http = http or httpx.Client(
            timeout=config.REQUEST_TIMEOUT_SECONDS,
            headers={"User-Agent": config.USER_AGENT},
            follow_redirects=True,
        )
        self.manifest = manifest if manifest is not None else Manifest(config.MANIFEST_PATH)
        self._rng = Random(seed)
        self._rate = rate_limiter or RateLimiter(config.MAX_REQUESTS_PER_SEC, sleep=sleep)
        self._sleep = sleep
        self._clock = clock

    # -- public API --------------------------------------------------------
    def fetch(self, url: str, cache_path: Path, key: str, *, force: bool = False) -> bytes:
        """Return raw bytes for ``url``, using the on-disk cache when possible.

        Raises FetchError on failure. On a cache hit no network request is made.
        """
        cache_path = Path(cache_path)
        if not force and self.manifest.has(key) and cache_path.exists():
            return cache_path.read_bytes()

        data, status = self._get_with_retries(url)
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_bytes(data)

        rel = _relpath(cache_path, self.manifest.path.parent)
        self.manifest.record(ManifestEntry(
            key=key, url=url, path=rel, status=status, bytes=len(data),
            sha256=hashlib.sha256(data).hexdigest(),
            fetched_at=self._clock(), from_cache=False,
        ))
        self.manifest.save()
        return data

    def fetch_result(self, url: str, cache_path: Path, key: str, *,
                     force: bool = False) -> FetchResult:
        """Like ``fetch`` but never raises; failures are returned as findings."""
        cache_path = Path(cache_path)
        if not force and self.manifest.has(key) and cache_path.exists():
            data = cache_path.read_bytes()
            return FetchResult(key, url, True, 200, True,
                               _relpath(cache_path, self.manifest.path.parent),
                               None, data)
        try:
            data = self.fetch(url, cache_path, key, force=force)
        except FetchError as exc:
            return FetchResult(key, url, False, exc.status, False, None, str(exc), None)
        return FetchResult(key, url, True, 200, False,
                           _relpath(cache_path, self.manifest.path.parent), None, data)

    # -- internals ---------------------------------------------------------
    def _get_with_retries(self, url: str) -> tuple[bytes, int]:
        last_exc: Exception | None = None
        for attempt in range(config.MAX_RETRIES + 1):
            self._rate.wait()
            try:
                resp = self._http.get(url)
            except httpx.HTTPError as exc:  # network-level failure
                last_exc = exc
                if attempt < config.MAX_RETRIES:
                    self._sleep(self._backoff_delay(attempt))
                    continue
                raise FetchError(f"network error fetching {url}: {exc}", None) from exc

            if resp.status_code == 200:
                return resp.content, 200

            if resp.status_code in config.RETRY_STATUS_CODES and attempt < config.MAX_RETRIES:
                self._sleep(self._backoff_delay(attempt))
                continue

            raise FetchError(f"{resp.status_code} fetching {url}", resp.status_code)

        raise FetchError(f"exhausted retries fetching {url}: {last_exc}", None)

    def _backoff_delay(self, attempt: int) -> float:
        """Exponential backoff with seeded jitter, capped at BACKOFF_MAX."""
        base = min(config.BACKOFF_BASE_SECONDS * (2 ** attempt), config.BACKOFF_MAX_SECONDS)
        jitter = self._rng.uniform(0.0, 1.0)
        return min(base + jitter, config.BACKOFF_MAX_SECONDS)

    def close(self) -> None:
        self._http.close()

    def __enter__(self) -> "AtlasClient":
        return self

    def __exit__(self, *exc) -> None:
        self.close()


def _relpath(path: Path, start: Path) -> str:
    try:
        return str(path.resolve().relative_to(start.resolve()))
    except ValueError:
        return str(path.resolve())
