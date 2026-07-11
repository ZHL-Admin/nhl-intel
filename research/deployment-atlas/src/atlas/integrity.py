"""Phase 1.4 integrity tests over the assembled Atlas Parquet tables.

Operates on the local Parquet corpus (no BigQuery) except test (d), which
refetches raw payloads for a few games through the Phase 0 client and diffs them
against the production-derived rows.

A shift-coverage gate runs first: games that have a boxscore but ZERO shift rows
(the empty-shift-array games, concentrated in 2024-25/2025-26) are separated out
so they are reported explicitly rather than silently dropped by inner joins.
Tests a/b/c then run over games that actually have shifts.
"""

from __future__ import annotations

from typing import Any

import polars as pl

from . import fetch, parse, sources
from .client import AtlasClient

TOI_TOLERANCE_S = 30
GOAL_ONICE_TOLERANCE_S = 2


def _load(path) -> pl.DataFrame:
    return pl.read_parquet(path)


# ---------------------------------------------------------------------------
# coverage gate: which boxscore games have no shift data?
# ---------------------------------------------------------------------------
def shift_coverage() -> dict[str, Any]:
    shifts = _load(sources.SHIFTS_PARQUET)
    toi = _load(sources.BOXSCORE_TOI_PARQUET)
    shift_games = set(shifts["game_id"].unique().to_list())
    box = toi.select("game_id", "season_label", "season_start_year").unique()
    box = box.with_columns(has_shifts=pl.col("game_id").is_in(list(shift_games)))
    no_shift = box.filter(~pl.col("has_shifts"))
    by_season = box.group_by("season_label").agg(
        pl.len().alias("box_games"),
        pl.col("has_shifts").sum().alias("with_shifts"),
        (~pl.col("has_shifts")).sum().alias("no_shift_games"),
        pl.col("season_start_year").first(),
    ).sort("season_label")
    return {
        "box_games": box.height,
        "no_shift_count": no_shift.height,
        "no_shift_games": sorted(no_shift["game_id"].to_list()),
        "by_season": by_season.to_dicts(),
        "shift_games_set": shift_games,
    }


# ---------------------------------------------------------------------------
# a) shift-duration sum vs boxscore TOI (>=98% within 30s), games-with-shifts
# ---------------------------------------------------------------------------
def test_toi_reconciliation() -> dict[str, Any]:
    shifts = _load(sources.SHIFTS_PARQUET)
    toi = _load(sources.BOXSCORE_TOI_PARQUET)

    shift_sum = shifts.group_by("game_id", "player_id").agg(
        pl.col("duration_seconds").sum().alias("shift_sum_s"),
        pl.col("season_label").first(),
    )
    merged = shift_sum.join(
        toi.select("game_id", "player_id", "toi_seconds", "grp"),
        on=["game_id", "player_id"], how="inner",
    ).with_columns(delta=(pl.col("shift_sum_s") - pl.col("toi_seconds")))
    merged = merged.with_columns(within=pl.col("delta").abs() <= TOI_TOLERANCE_S)
    n = merged.height
    pass_rate = merged["within"].mean() if n else None
    by_season = merged.group_by("season_label").agg(
        pl.len().alias("player_games"),
        pl.col("within").mean().alias("pass_rate"),
        pl.col("delta").abs().median().alias("median_abs_delta"),
    ).sort("season_label")
    by_grp = merged.group_by("grp").agg(
        pl.len().alias("player_games"), pl.col("within").mean().alias("pass_rate"),
    ).sort("grp")
    return {
        "player_games": n, "pass_rate": pass_rate,
        "passed": bool(pass_rate is not None and pass_rate >= 0.98),
        "threshold": 0.98, "tolerance_s": TOI_TOLERANCE_S,
        "by_season": by_season.to_dicts(), "by_group": by_grp.to_dicts(),
        "delta_series": merged.select("delta", "grp", "season_label", "game_id"),
    }


# ---------------------------------------------------------------------------
# b) no overlapping shifts for the same player in the same game
# ---------------------------------------------------------------------------
def test_no_overlaps() -> dict[str, Any]:
    shifts = _load(sources.SHIFTS_PARQUET).sort(
        "game_id", "player_id", "shift_start_seconds")
    prev_end = pl.col("shift_end_seconds").shift(1).over("game_id", "player_id")
    prev_exists = pl.col("player_id").shift(1).over("game_id", "player_id").is_not_null()
    flagged = shifts.with_columns(
        overlap=(pl.col("shift_start_seconds") < prev_end) & prev_exists,
        overlap_s=(prev_end - pl.col("shift_start_seconds")),
    )
    overlaps = flagged.filter(pl.col("overlap"))
    bad_games = sorted(overlaps["game_id"].unique().to_list())
    return {
        "overlap_rows": overlaps.height,
        "games_with_overlap": len(bad_games),
        "bad_games": bad_games,
        "median_overlap_s": (overlaps["overlap_s"].median() if overlaps.height else None),
        "passed": overlaps.height == 0,
    }


# ---------------------------------------------------------------------------
# c) goal scorer on ice at goal second (+/- 2s), over games WITH shifts
# ---------------------------------------------------------------------------
def test_goal_scorer_on_ice(no_shift_games: set[int]) -> dict[str, Any]:
    events = _load(sources.EVENTS_PARQUET)
    shifts = _load(sources.SHIFTS_PARQUET)

    goals_all = events.filter(
        (pl.col("type_desc_key") == "goal")
        & (pl.col("period_type") != "SO")
        & pl.col("scoring_player_id").is_not_null()
    )
    goals = goals_all.filter(~pl.col("game_id").is_in(list(no_shift_games)))

    joined = goals.select(
        "game_id", "event_id", "season_label",
        pl.col("scoring_player_id").alias("player_id"),
        pl.col("event_second").alias("goal_second"),
    ).join(
        shifts.select("game_id", "player_id", "shift_start_seconds", "shift_end_seconds"),
        on=["game_id", "player_id"], how="left",
    ).with_columns(
        covers=(pl.col("shift_start_seconds") <= pl.col("goal_second") + GOAL_ONICE_TOLERANCE_S)
        & (pl.col("shift_end_seconds") >= pl.col("goal_second") - GOAL_ONICE_TOLERANCE_S)
    )
    per_goal = joined.group_by("game_id", "event_id").agg(
        pl.col("covers").fill_null(False).any().alias("on_ice"),
        pl.col("season_label").first(),
    )
    n = per_goal.height
    rate = per_goal["on_ice"].mean() if n else None
    misses = per_goal.filter(~pl.col("on_ice"))
    by_season = per_goal.group_by("season_label").agg(
        pl.len().alias("goals"), pl.col("on_ice").mean().alias("on_ice_rate"),
    ).sort("season_label")
    return {
        "goals_tested": n, "on_ice_rate": rate,
        "passed": bool(rate is not None and rate > 0.99),
        "goals_in_no_shift_games": goals_all.height - n,
        "miss_count": misses.height,
        "miss_games": sorted(misses["game_id"].unique().to_list()),
        "by_season": by_season.to_dicts(),
    }


# ---------------------------------------------------------------------------
# d) freshness spot-check (7 games): refetch raw and diff vs production-derived
# ---------------------------------------------------------------------------
FRESHNESS_GAMES = [
    "2011020400", "2013020500", "2015020001", "2018020500",
    "2021020500", "2023020204", "2025020500",
]


def test_freshness(client: AtlasClient | None = None) -> dict[str, Any]:
    shifts = _load(sources.SHIFTS_PARQUET)
    events = _load(sources.EVENTS_PARQUET)
    own = client is None
    client = client or AtlasClient()
    results = []
    try:
        for gid in FRESHNESS_GAMES:
            gid_int = int(gid)
            fetch.shifts(client, gid)
            fetch.pbp(client, gid)
            fresh_shifts = parse.parse_shifts(gid).filter(
                (pl.col("duration_s") >= 1) & (pl.col("duration_s") <= 1200))
            # apply the same exact-dup removal the corpus applies. parse_shifts
            # start_s/end_s are PERIOD-RELATIVE, so the dedup key must include
            # period (otherwise same-in-period times in different periods collapse).
            fresh_shifts = fresh_shifts.unique(
                subset=["player_id", "period", "start_s", "end_s"], keep="first")
            fresh_pbp = parse.parse_pbp(gid)
            prod_shifts = shifts.filter(pl.col("game_id") == gid_int)
            prod_events = events.filter(pl.col("game_id") == gid_int)
            results.append({
                "game_id": gid,
                "prod_shift_rows": prod_shifts.height,
                "raw_shift_rows": fresh_shifts.height,
                "shift_row_match": prod_shifts.height == fresh_shifts.height,
                "prod_event_rows": prod_events.height,
                "raw_event_rows": fresh_pbp.height,
                "event_row_match": prod_events.height == fresh_pbp.height,
                "prod_toi_sum_s": int(prod_shifts["duration_seconds"].sum()),
                "raw_toi_sum_s": int(fresh_shifts["duration_s"].sum()),
            })
    finally:
        if own:
            client.close()
    all_match = all(r["shift_row_match"] and r["event_row_match"] for r in results)
    return {"games": results, "all_match": all_match}


# ---------------------------------------------------------------------------
# quarantine synthesis (true counts)
# ---------------------------------------------------------------------------
def quarantine(coverage: dict, overlaps: dict, goal_check: dict,
               total_games: int) -> dict[str, Any]:
    no_shift = set(coverage["no_shift_games"])
    ovl = set(overlaps["bad_games"])
    miss = set(goal_check["miss_games"])
    bad = no_shift | ovl | miss
    frac = len(bad) / total_games if total_games else 0.0
    return {
        "total_boxscore_games": total_games,
        "no_shift_games": len(no_shift),
        "genuine_overlap_games": len(ovl),
        "goal_miss_games": len(miss),
        "quarantine_union": len(bad),
        "fraction": frac,
        "under_half_pct": frac < 0.005,
        "sample": sorted(bad)[:50],
    }
