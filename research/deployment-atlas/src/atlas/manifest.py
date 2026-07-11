"""Resumable fetch manifest.

Every successfully cached resource gets one manifest entry keyed by its logical
cache key (e.g. ``2023020204/pbp``). A re-run consults the manifest + the file
on disk; if both agree the resource is present, no network call is made. The
manifest is written atomically so an interrupted run never corrupts it.
"""

from __future__ import annotations

import json
import os
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass(frozen=True)
class ManifestEntry:
    key: str
    url: str
    path: str          # relative to the manifest's directory
    status: int
    bytes: int
    sha256: str
    fetched_at: str    # ISO-8601 UTC; supplied by caller (no hidden clock)
    from_cache: bool


class Manifest:
    def __init__(self, path: Path):
        self.path = Path(path)
        self._entries: dict[str, ManifestEntry] = {}
        if self.path.exists():
            self._load()

    def _load(self) -> None:
        raw = json.loads(self.path.read_text())
        for key, fields in raw.get("entries", {}).items():
            self._entries[key] = ManifestEntry(**fields)

    def get(self, key: str) -> ManifestEntry | None:
        return self._entries.get(key)

    def has(self, key: str) -> bool:
        """True only if the manifest records the key AND the file still exists."""
        entry = self._entries.get(key)
        if entry is None:
            return False
        return (self.path.parent / entry.path).exists()

    def record(self, entry: ManifestEntry) -> None:
        self._entries[entry.key] = entry

    def entries(self) -> dict[str, ManifestEntry]:
        return dict(self._entries)

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "version": 1,
            "entries": {k: asdict(v) for k, v in sorted(self._entries.items())},
        }
        fd, tmp = tempfile.mkstemp(dir=self.path.parent, suffix=".tmp")
        try:
            with os.fdopen(fd, "w") as fh:
                json.dump(payload, fh, indent=2, sort_keys=True)
            os.replace(tmp, self.path)
        finally:
            if os.path.exists(tmp):
                os.remove(tmp)
