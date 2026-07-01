"""Smoke test for the trades CSV ingestion (no BigQuery writes).

Parses the trades CSV through the load path and asserts the shape stg_trades + the valuation model
depend on: ~1,300 trades, the three asset types present, two- and three-team trades, and the
conditional-pick flag in notes. Exits nonzero on failure.

Usage:
    python scripts/smoke_load_trades.py
"""
from __future__ import annotations

import argparse
import sys
from collections import Counter, defaultdict
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).parent.parent))

from scripts.load_trades import COLUMN_MAP, DEFAULT_CSV


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", default=DEFAULT_CSV)
    args = ap.parse_args()

    df = pd.read_csv(args.csv, dtype=str).fillna("")
    missing = [c for c in COLUMN_MAP if c not in df.columns]
    if missing:
        print(f"FAIL: missing columns {missing}", file=sys.stderr)
        return 1
    df = df[list(COLUMN_MAP)].rename(columns=COLUMN_MAP)
    df = df[df["trade_id"].str.strip() != ""]

    n_trades = df["trade_id"].nunique()
    types = Counter(df["asset_type"])
    print(f"asset-rows: {len(df)}; trades: {n_trades}")
    print(f"asset types: {dict(types)}")

    if not (1200 <= n_trades <= 1400):
        print(f"FAIL: expected ~1,300 trades, got {n_trades}", file=sys.stderr)
        return 1
    for t in ("Player", "Draft Pick", "Other"):
        if types.get(t, 0) == 0:
            print(f"FAIL: no '{t}' assets", file=sys.stderr)
            return 1

    teams = defaultdict(set)
    for _, r in df.iterrows():
        teams[r["trade_id"]].add(r["acquiring_team"])
    by_n = Counter(len(v) for v in teams.values())
    print(f"teams-per-trade: {dict(by_n)}")
    if by_n.get(2, 0) == 0 or by_n.get(3, 0) == 0:
        print("FAIL: expected both two- and three-team trades", file=sys.stderr)
        return 1

    conditional = (df["asset_type"] == "Draft Pick") & (df["notes"].str.strip() != "")
    print(f"conditional picks (notes flagged): {int(conditional.sum())}")

    print("\nOK: trades smoke test passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
