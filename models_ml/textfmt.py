"""Tiny shared text formatters for server-generated prose (so percentiles/ranks read correctly)."""

from __future__ import annotations


def ordinal(n: int) -> str:
    """1 -> '1st', 2 -> '2nd', 3 -> '3rd', 11/12/13 -> 'th', 21 -> '21st', 92 -> '92nd'."""
    n = int(round(n))
    if 10 <= (n % 100) <= 20:
        suffix = "th"
    else:
        suffix = {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{suffix}"
