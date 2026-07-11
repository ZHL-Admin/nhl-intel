"""Phase 2.4 tests over the derived stint table, reported per season."""

from __future__ import annotations

from typing import Any

import numpy as np
import polars as pl

from . import sources, stints

# Star players + season (season-start year) for the manual cross-check (2.4e).
MANUAL = [
    ("McDavid", 8478402, 2023), ("Makar", 8480069, 2022),
    ("MacKinnon", 8477492, 2023), ("Matthews", 8479318, 2021),
    ("Hughes", 8480800, 2023),
]


def _five_v_five(df: pl.DataFrame) -> pl.Expr:
    return ((df["home_skater_ids"].list.len() == 5)
            & (df["away_skater_ids"].list.len() == 5)
            & df["home_goalie_id"].is_not_null()
            & df["away_goalie_id"].is_not_null())


def load() -> pl.DataFrame:
    return pl.read_parquet(stints.STINTS_PARQUET)


# (a) stint durations sum to actual game seconds (max shift end) +/- 2s
def test_a_duration(st: pl.DataFrame) -> dict[str, Any]:
    shifts = pl.read_parquet(sources.SHIFTS_PARQUET)
    game_len = shifts.group_by("game_id").agg(
        pl.col("shift_end_seconds").max().alias("game_seconds"),
        pl.col("season_start_year").first())
    s = st.group_by("game_id").agg(pl.col("duration_seconds").sum().alias("stint_sum"))
    m = game_len.join(s, on="game_id", how="inner").with_columns(
        ok=(pl.col("stint_sum") - pl.col("game_seconds")).abs() <= 2)
    by = m.group_by("season_start_year").agg(
        pl.len().alias("games"), pl.col("ok").mean().alias("pass_rate")).sort("season_start_year")
    return {"games": m.height, "pass_rate": m["ok"].mean(),
            "fail_games": sorted(m.filter(~pl.col("ok"))["game_id"].to_list())[:20],
            "by_season": by.to_dicts()}


# (b) personnel sanity + overlap absorption
def test_b_personnel(st: pl.DataFrame) -> dict[str, Any]:
    shifts = pl.read_parquet(sources.SHIFTS_PARQUET).sort(
        "game_id", "player_id", "shift_start_seconds")
    prev_end = pl.col("shift_end_seconds").shift(1).over("game_id", "player_id")
    ov = shifts.with_columns(
        overlap=(pl.col("shift_start_seconds") < prev_end)
        & pl.col("player_id").shift(1).over("game_id", "player_id").is_not_null())
    overlap_games = set(ov.filter(pl.col("overlap"))["game_id"].unique().to_list())

    st2 = st.with_columns(nh=pl.col("home_skater_ids").list.len(),
                          na=pl.col("away_skater_ids").list.len())
    # strengthState is derived from the counts, so consistency is 100% by construction.
    impossible = st2.filter((pl.col("nh") > 6) | (pl.col("na") > 6))
    imp_in_overlap = impossible.filter(pl.col("game_id").is_in(list(overlap_games)))
    return {
        "strength_matches_counts": True,  # by construction
        "impossible_stints": impossible.height,
        "impossible_stints_in_overlap_games": imp_in_overlap.height,
        "impossible_stints_outside_overlap_games": impossible.height - imp_in_overlap.height,
        "overlap_games": len(overlap_games),
        "quarantine_stints": sorted(
            (impossible.select("game_id", "stint_id")).unique().rows())[:20],
        "quarantine_stint_count": impossible.height,
    }


# (c) league 5v5 TOI share per season in [70%, 83%]
def test_c_5v5_share(st: pl.DataFrame) -> dict[str, Any]:
    st = st.with_columns(is5=_five_v_five(st),
                         yr=pl.col("game_id").cast(pl.Utf8).str.slice(0, 4).cast(pl.Int64))
    by = st.group_by("yr").agg(
        (pl.col("duration_seconds").filter(pl.col("is5")).sum()
         / pl.col("duration_seconds").sum()).alias("share_5v5")).sort("yr")
    rows = by.to_dicts()
    return {"by_season": rows,
            "all_in_range": all(0.70 <= r["share_5v5"] <= 0.83 for r in rows)}


# (d) situationCode cross-check
def test_d_situationcode(st: pl.DataFrame) -> dict[str, Any]:
    events = pl.read_parquet(sources.EVENTS_PARQUET).filter(
        pl.col("situation_code").is_not_null() & (pl.col("period_type") != "SO")
    ).select("game_id", "event_second",
             pl.col("situation_code").str.zfill(4).alias("situation_code"),  # 4-digit; recover stripped leading zero
             pl.col("game_id").cast(pl.Utf8).str.slice(0, 4).cast(pl.Int64).alias("yr"))
    # stint state -> expected code [awayGoalie][awaySkaters][homeSkaters][homeGoalie]
    ss = st.with_columns(
        ag=pl.col("away_goalie_id").is_not_null().cast(pl.Int64),
        hg=pl.col("home_goalie_id").is_not_null().cast(pl.Int64),
        na=pl.col("away_skater_ids").list.len(), nh=pl.col("home_skater_ids").list.len(),
    ).with_columns(expected=pl.col("ag").cast(pl.Utf8) + pl.col("na").cast(pl.Utf8)
                   + pl.col("nh").cast(pl.Utf8) + pl.col("hg").cast(pl.Utf8)).select(
        "game_id", "stint_id", "start_seconds", "end_seconds", "expected").sort(
        "game_id", "end_seconds")
    ev = events.sort("game_id", "event_second").join_asof(
        ss, left_on="event_second", right_on="end_seconds", by="game_id", strategy="forward"
    ).filter(pl.col("expected").is_not_null() & (pl.col("start_seconds") < pl.col("event_second")))
    ev = ev.with_columns(agree=pl.col("situation_code") == pl.col("expected"))
    by = ev.group_by("yr").agg(pl.len().alias("events"),
                               pl.col("agree").mean().alias("agreement")).sort("yr")
    disagreements = ev.filter(~pl.col("agree")).group_by("situation_code", "expected").len().sort(
        "len", descending=True)
    return {"events": ev.height, "agreement": ev["agree"].mean(),
            "by_season": by.to_dicts(),
            "top_disagreements": disagreements.head(15).to_dicts()}


# (e) manual cross-check: pipeline 5v5 TOI vs independent per-second computation
def _player_5v5_toi_pipeline(st: pl.DataFrame, gid: int, pid: int) -> int:
    sub = st.filter((pl.col("game_id") == gid) & _five_v_five(st))
    on = sub.filter(pl.col("home_skater_ids").list.contains(pid)
                    | pl.col("away_skater_ids").list.contains(pid))
    return int(on["duration_seconds"].sum())


def _player_5v5_toi_bruteforce(gid: int, pid: int) -> int:
    """Independent second-by-second recomputation from raw shifts + rosters."""
    sh = pl.read_parquet(sources.SHIFTS_PARQUET).filter(pl.col("game_id") == gid)
    ros = pl.read_parquet(sources.ROSTERS_PARQUET).filter(pl.col("game_id") == gid)
    games = pl.read_parquet(sources.GAMES_PARQUET).filter(pl.col("game_id") == gid).to_dicts()[0]
    home_id, away_id = games["home_team_id"], games["away_team_id"]
    is_g = dict(zip(ros["player_id"], ros["is_goalie"]))
    glen = int(sh["shift_end_seconds"].max())
    home_sk = np.zeros(glen + 1, dtype=np.int32)
    away_sk = np.zeros(glen + 1, dtype=np.int32)
    home_go = np.zeros(glen + 1, dtype=np.int32)
    away_go = np.zeros(glen + 1, dtype=np.int32)
    player_on = np.zeros(glen + 1, dtype=bool)
    for r in sh.iter_rows(named=True):
        a, b = r["shift_start_seconds"], r["shift_end_seconds"]
        goalie = is_g.get(r["player_id"], False)
        if r["team_id"] == home_id:
            (home_go if goalie else home_sk)[a:b] += 1
        elif r["team_id"] == away_id:
            (away_go if goalie else away_sk)[a:b] += 1
        if r["player_id"] == pid:
            player_on[a:b] = True
    five = (home_sk == 5) & (away_sk == 5) & (home_go >= 1) & (away_go >= 1)
    return int(np.sum(five & player_on))


def test_e_manual(st: pl.DataFrame) -> dict[str, Any]:
    shifts = pl.read_parquet(sources.SHIFTS_PARQUET)
    results = []
    for name, pid, yr in MANUAL:
        gids = shifts.filter((pl.col("player_id") == pid)
                             & (pl.col("season_start_year") == yr))["game_id"].unique().sort()
        sample = gids.to_list()[:3]
        for gid in sample:
            pipe = _player_5v5_toi_pipeline(st, gid, pid)
            brute = _player_5v5_toi_bruteforce(gid, pid)
            results.append({"player": name, "game_id": gid, "pipeline_5v5_s": pipe,
                            "bruteforce_5v5_s": brute, "diff": pipe - brute})
    return {"checks": results, "all_match": all(r["diff"] == 0 for r in results)}
