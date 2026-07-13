"""Step 0 — frozen-input timestamps + event-primitive inventory (reproducer).

Reproduces the light Step-0 audit: asset timestamps, the per-season player-attributed shot inventory,
and the player-attribution check that decides which action primitives are usable for the role model.
The narrative + reliability flags are in reports/probe.md §0.
"""
from __future__ import annotations

import datetime as dt
import os

import polars as pl

from . import config

FROZEN = [
    ("atlas/stints", config.ATLAS_PARQUET / "stints.parquet"),
    ("atlas/events", config.ATLAS_PARQUET / "events.parquet"),
    ("atlas/player_5v5", config.ATLAS_PARQUET / "player_5v5.parquet"),
    ("atlas/rapm_variant", config.ATLAS_PARQUET / "rapm_variant.parquet"),
    ("atlas/shot_xg", config.ATLAS_PARQUET / "shot_xg.parquet"),
    ("atlas/rosters", config.ATLAS_PARQUET / "rosters.parquet"),
    ("chem/pairs_corpus", config.CHEM_PARQUET / "frozen" / "pairs_corpus.parquet"),
    ("syseff/player_types", config.SYSEFF_PARQUET / "player_types.parquet"),
    ("syseff/team_season_fp", config.SYSEFF_PARQUET / "team_season_fp.parquet"),
]
HUSTLE = ["hit", "takeaway", "giveaway", "faceoff"]
SHOTS = ["shot-on-goal", "missed-shot", "blocked-shot", "goal"]


def _ts(p):
    return dt.datetime.fromtimestamp(os.path.getmtime(p)).strftime("%Y-%m-%d %H:%M:%S") if os.path.exists(p) else "MISSING"


def run():
    print("=== frozen inputs ===")
    for label, p in FROZEN:
        n = pl.scan_parquet(str(p)).select(pl.len()).collect().item() if os.path.exists(p) else "-"
        print(f"  {label:22s} {_ts(p)}  rows={n}")

    ev = pl.scan_parquet(config.ATLAS_PARQUET / "events.parquet")
    print("\n=== player attribution by event type (does an individual player attach?) ===")
    for et in HUSTLE + ["blocked-shot", "shot-on-goal", "goal"]:
        r = ev.filter(pl.col("type_desc_key") == et).select(
            n=pl.len(), shooter=pl.col("shooting_player_id").is_not_null().sum(),
            scorer=pl.col("scoring_player_id").is_not_null().sum()).collect().to_dicts()[0]
        print(f"  {et:14s} n={r['n']:>9,}  shooter_attr={r['shooter']:>9,}  scorer_attr={r['scorer']:>9,}")

    print("\n=== usable player-attributed shot events, 5v5 (situation 1551), per season ===")
    shots = ev.filter(pl.col("type_desc_key").is_in(SHOTS) & (pl.col("situation_code") == "1551")
                      & pl.col("is_primary_scope"))
    d = shots.group_by("season_label").agg(
        shots=pl.len(), xy_cov=pl.col("x_coord").is_not_null().mean()).sort("season_label").collect()
    for r in d.iter_rows(named=True):
        print(f"  {r['season_label']}  shots={r['shots']:>7,}  xy_cov={r['xy_cov']:.3f}")


if __name__ == "__main__":
    run()
