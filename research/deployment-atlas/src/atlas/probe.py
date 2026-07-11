"""Structural probing of raw JSON payloads.

Produces a compact, deterministic description of an arbitrary JSON value:
types, dict keys, list element schemas, sample scalar values, and per-field
null rates. Used in Phase 0 to document API field semantics from real payloads
rather than assumptions.
"""

from __future__ import annotations

from typing import Any


def type_name(v: Any) -> str:
    if v is None:
        return "null"
    if isinstance(v, bool):
        return "bool"
    if isinstance(v, int):
        return "int"
    if isinstance(v, float):
        return "float"
    if isinstance(v, str):
        return "str"
    if isinstance(v, list):
        return "list"
    if isinstance(v, dict):
        return "dict"
    return type(v).__name__


def element_key_union(items: list[Any]) -> list[str]:
    """Union of dict keys across list elements, in first-seen order."""
    seen: dict[str, None] = {}
    for it in items:
        if isinstance(it, dict):
            for k in it:
                seen.setdefault(k, None)
    return list(seen)


def summarize(obj: Any, *, max_depth: int = 4, max_list: int = 3, _depth: int = 0) -> Any:
    """Return a JSON-serializable structural summary of ``obj``."""
    t = type_name(obj)
    if _depth >= max_depth:
        return {"type": t, "truncated": True}

    if isinstance(obj, dict):
        return {
            "type": "dict",
            "keys": {
                k: summarize(v, max_depth=max_depth, max_list=max_list, _depth=_depth + 1)
                for k, v in obj.items()
            },
        }

    if isinstance(obj, list):
        out: dict[str, Any] = {"type": "list", "len": len(obj)}
        if obj:
            out["element_keys"] = element_key_union(obj)
            out["element_schema"] = summarize(
                obj[0], max_depth=max_depth, max_list=max_list, _depth=_depth + 1
            )
        return out

    sample: Any = obj
    if isinstance(obj, str) and len(obj) > 80:
        sample = obj[:80] + "…"
    return {"type": t, "sample": sample}


def field_report(items: list[dict[str, Any]], fields: list[str]) -> dict[str, Any]:
    """Per field across ``items``: presence, null count, observed types, and up
    to 5 distinct sample values. Nails down enum-like fields + null rates."""
    report: dict[str, Any] = {}
    n = len(items)
    for f in fields:
        types: dict[str, None] = {}
        samples: dict[str, None] = {}
        present = 0
        nulls = 0
        for it in items:
            if isinstance(it, dict) and f in it:
                present += 1
                v = it[f]
                if v is None:
                    nulls += 1
                types.setdefault(type_name(v), None)
                if v is not None and len(samples) < 5:
                    samples.setdefault(repr(v), None)
        report[f] = {
            "present": present,
            "of": n,
            "nulls": nulls,
            "null_rate": round(nulls / present, 4) if present else None,
            "types": list(types),
            "samples": list(samples),
        }
    return report


def distribution(items: list[Any], field: str, top: int = 30) -> dict[str, int]:
    counts: dict[str, int] = {}
    for it in items:
        if isinstance(it, dict) and field in it:
            counts[repr(it[field])] = counts.get(repr(it[field]), 0) + 1
    return dict(sorted(counts.items(), key=lambda kv: -kv[1])[:top])
