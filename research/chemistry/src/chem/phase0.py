"""Phase 0 — scaffold, frozen-asset audit, and derivation feasibility (reproducer).

Reproduces the LIGHT parts of the Phase 0 audit from the frozen inputs (asset table + api
importability). The heavy one-time items — the production pair/fit inventory (BigQuery) and the
stint->pair derivation timing probe — are recorded in reports/phase0.md and NOT re-run here (the
probe is an ~80s in-memory measurement, nothing was written). Seeded (config.SEED)."""
from __future__ import annotations

import os
from datetime import datetime

import polars as pl

from . import config

ATLAS = [("stints.parquet", "stints"), ("events.parquet", "events"),
         ("player_5v5.parquet", "player_5v5"), ("rapm_variant.parquet", "rapm_variant"),
         ("movers_eval.parquet", "movers_eval")]
SYSEFF = [("player_types.parquet", "player_types"), ("team_season_fp.parquet", "fingerprints (team_season_fp)"),
          ("regime_ledger.parquet", "regime_ledger_raw"),
          ("regime_ledger_consolidated.parquet", "regime_ledger_consolidated")]


def _row(path, label):
    if not os.path.exists(path):
        return f"  MISSING  {label:34s} -> {path}"
    ts = datetime.fromtimestamp(os.path.getmtime(path)).strftime("%Y-%m-%d %H:%M:%S")
    df = pl.read_parquet(path)
    span = ""
    for c in ("season_label", "season"):
        if c in df.columns:
            u = sorted(df[c].unique().to_list()); span = f"{u[0]}..{u[-1]} ({len(u)})"; break
    return f"  {label:34s} rows={df.height:>9,}  span={span:22s}  mtime={ts}"


def run():
    print("=== Deployment Atlas (frozen read-only) ===")
    for f, l in ATLAS:
        print(_row(str(config.ATLAS_PARQUET / f), l))
    print("  api.py importable:", (config.ATLAS_SRC / "atlas" / "api.py").exists())
    print("=== System Effects (frozen read-only) ===")
    for f, l in SYSEFF:
        print(_row(str(config.SYSEFF_PARQUET / f), l))
    print("  api.py importable:", (config.SYSEFF_SRC / "syseff" / "api.py").exists())
    print("\nSee reports/phase0.md for the production pair/fit inventory and derivation cost probe.")


if __name__ == "__main__":
    run()
