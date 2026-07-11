"""Derive the Atlas stint table from the deduplicated shifts corpus (Phase 2.2).

DERIVE decision (see reports/phase2.md): production int_shift_segments is a stale
materialized table (missing all 563 backfilled games), built on undeduplicated
stg_shifts, with no goal cut-points. We reuse its proven conventions (boundary-
union of shift start/end, strength from on-ice counts, goalie via positionCode G,
(period-1)*1200 absolute seconds) but derive from the clean Atlas corpus and add
goal cut-points (Amendment A) so score state is constant within every stint.

A STINT is a maximal interval during which the on-ice personnel AND the score are
unchanged. Boundaries = union of every shift start/end and every (non-shootout)
goal second. A player is on ice for a stint if their shift spans it. Shootouts
have no shifts and are excluded. OT length is never assumed: boundaries come from
actual shift/goal seconds.

Output columns (2.2 spec): gameId, season, stintId, startSeconds, endSeconds,
durationSeconds, homeSkaterIds, awaySkaterIds, homeGoalieId, awayGoalieId,
strengthState, homeScore, awayScore, scoreState (-3..+3), startType
(OZ/NZ/DZ/OTF), isPlayoffs.
"""

from __future__ import annotations

from typing import Any

import numpy as np
import polars as pl

from . import config, sources

STINTS_PARQUET = config.PARQUET_DIR / "stints.parquet"

STINT_SCHEMA: dict[str, Any] = {
    "game_id": pl.Int64, "season_label": pl.Utf8, "stint_id": pl.Int64,
    "start_seconds": pl.Int64, "end_seconds": pl.Int64, "duration_seconds": pl.Int64,
    "home_skater_ids": pl.List(pl.Int64), "away_skater_ids": pl.List(pl.Int64),
    "home_goalie_id": pl.Int64, "away_goalie_id": pl.Int64,
    "strength_state": pl.Utf8, "home_score": pl.Int64, "away_score": pl.Int64,
    "score_state": pl.Int64, "start_type": pl.Utf8, "is_playoffs": pl.Boolean,
}


def _zone_from_home(zone_code: str | None, owner_is_home: bool) -> str:
    """Faceoff zoneCode (relative to event owner) -> home-perspective start type."""
    if zone_code == "N":
        return "NZ"
    if zone_code == "O":
        return "OZ" if owner_is_home else "DZ"
    if zone_code == "D":
        return "DZ" if owner_is_home else "OZ"
    return "OTF"


def _build_game(gid: int, season: str, home_id: int, away_id: int, is_po: bool,
                shifts: pl.DataFrame, goals: pl.DataFrame,
                faceoffs: pl.DataFrame, pos: dict[int, bool]) -> list[dict]:
    ss = shifts["shift_start_seconds"].to_numpy()
    se = shifts["shift_end_seconds"].to_numpy()
    pid = shifts["player_id"].to_numpy()
    tid = shifts["team_id"].to_numpy()

    goal_secs = goals["event_second"].to_numpy() if goals.height else np.array([], dtype=np.int64)
    goal_home = (goals["event_owner_team_id"].to_numpy() == home_id) if goals.height else np.array([], dtype=bool)

    # boundary-union: shift starts/ends + goal seconds
    bounds = np.unique(np.concatenate([ss, se, goal_secs]).astype(np.int64))
    if bounds.size < 2:
        return []

    n_stints = bounds.size - 1
    # per-stint accumulators
    home_sk: list[list[int]] = [[] for _ in range(n_stints)]
    away_sk: list[list[int]] = [[] for _ in range(n_stints)]
    home_g: list[int | None] = [None] * n_stints
    away_g: list[int | None] = [None] * n_stints

    # each shift covers stints [lo, hi): bounds[lo]==start, bounds[hi]==end
    lo = np.searchsorted(bounds, ss)
    hi = np.searchsorted(bounds, se)
    for k in range(len(pid)):
        p, t, is_g = int(pid[k]), int(tid[k]), pos.get(int(pid[k]), False)
        for i in range(lo[k], hi[k]):
            if t == home_id:
                if is_g:
                    home_g[i] = p
                else:
                    home_sk[i].append(p)
            elif t == away_id:
                if is_g:
                    away_g[i] = p
                else:
                    away_sk[i].append(p)

    # score at each stint start (goals strictly before the stint start; because we
    # cut at goal seconds, a goal at start belongs to this stint's score)
    gs_sorted_idx = np.argsort(goal_secs, kind="stable") if goal_secs.size else np.array([], dtype=int)
    gsec = goal_secs[gs_sorted_idx]
    ghome = goal_home[gs_sorted_idx]
    cum_home = np.cumsum(ghome.astype(np.int64)) if gsec.size else np.array([], dtype=np.int64)
    cum_away = np.cumsum((~ghome).astype(np.int64)) if gsec.size else np.array([], dtype=np.int64)

    # faceoffs for start type
    fsec = faceoffs["event_second"].to_numpy() if faceoffs.height else np.array([], dtype=np.int64)
    fzone = faceoffs["zone_code"].to_list() if faceoffs.height else []
    fowner_home = (faceoffs["event_owner_team_id"].to_numpy() == home_id) if faceoffs.height else np.array([], dtype=bool)
    forder = np.argsort(fsec, kind="stable") if fsec.size else np.array([], dtype=int)
    fsec_s = fsec[forder]

    rows: list[dict] = []
    for i in range(n_stints):
        a, b = int(bounds[i]), int(bounds[i + 1])
        if b <= a:
            continue
        hsk, ask = sorted(home_sk[i]), sorted(away_sk[i])
        # score: goals with sec <= a
        if gsec.size:
            j = int(np.searchsorted(gsec, a, side="right"))
            hs = int(cum_home[j - 1]) if j > 0 else 0
            as_ = int(cum_away[j - 1]) if j > 0 else 0
        else:
            hs = as_ = 0
        # start type: latest faceoff in [a-2, a]
        st = "OTF"
        if fsec_s.size:
            r = int(np.searchsorted(fsec_s, a, side="right")) - 1
            if r >= 0 and fsec_s[r] >= a - 2:
                oi = int(forder[r])
                st = _zone_from_home(fzone[oi], bool(fowner_home[oi]))
        rows.append({
            "game_id": gid, "season_label": season, "stint_id": i,
            "start_seconds": a, "end_seconds": b, "duration_seconds": b - a,
            "home_skater_ids": hsk, "away_skater_ids": ask,
            "home_goalie_id": home_g[i], "away_goalie_id": away_g[i],
            "strength_state": f"{len(hsk)}v{len(ask)}",
            "home_score": hs, "away_score": as_,
            "score_state": max(-3, min(3, hs - as_)),
            "start_type": st, "is_playoffs": is_po,
        })
    return rows


def build_stints(force: bool = False) -> dict[str, Any]:
    if not force and STINTS_PARQUET.exists():
        df = pl.read_parquet(STINTS_PARQUET, columns=["game_id"])
        return {"path": str(STINTS_PARQUET), "rows": df.height,
                "games": df["game_id"].n_unique(), "reused": True}

    shifts = pl.read_parquet(sources.SHIFTS_PARQUET)
    rosters = pl.read_parquet(sources.ROSTERS_PARQUET)
    games = pl.read_parquet(sources.GAMES_PARQUET)
    events = pl.read_parquet(sources.EVENTS_PARQUET)

    goals = events.filter((pl.col("type_desc_key") == "goal")
                          & (pl.col("period_type") != "SO")).select(
        "game_id", "event_second", "event_owner_team_id")
    faceoffs = events.filter(pl.col("type_desc_key") == "faceoff").select(
        "game_id", "event_second", "event_owner_team_id", "zone_code")

    game_meta = {r["game_id"]: r for r in games.to_dicts()}
    pos_by_game = {
        (g[0] if isinstance(g, tuple) else g): dict(zip(sub["player_id"], sub["is_goalie"]))
        for g, sub in rosters.group_by("game_id")
    }
    shifts_by_game = dict(iter(shifts.partition_by("game_id", as_dict=True).items()))
    goals_by_game = dict(iter(goals.partition_by("game_id", as_dict=True).items()))
    fo_by_game = dict(iter(faceoffs.partition_by("game_id", as_dict=True).items()))

    empty = pl.DataFrame(schema={"event_second": pl.Int64, "event_owner_team_id": pl.Int64,
                                 "zone_code": pl.Utf8})
    all_rows: list[dict] = []
    skipped = 0
    gids = sorted(shifts_by_game.keys(), key=lambda k: k[0] if isinstance(k, tuple) else k)
    for i, key in enumerate(gids):
        gid = key[0] if isinstance(key, tuple) else key
        meta = game_meta.get(gid)
        if meta is None:
            skipped += 1
            continue
        all_rows.extend(_build_game(
            gid, meta["season_label"], meta["home_team_id"], meta["away_team_id"],
            meta["is_playoffs"], shifts_by_game[key],
            goals_by_game.get(key, empty), fo_by_game.get(key, empty),
            pos_by_game.get(gid, {}),
        ))
        if (i + 1) % 2000 == 0:
            print(f"  ...{i+1}/{len(gids)} games, {len(all_rows)} stints", flush=True)

    df = pl.DataFrame(all_rows, schema=STINT_SCHEMA).sort("game_id", "stint_id")
    df.write_parquet(STINTS_PARQUET)
    return {"path": str(STINTS_PARQUET), "rows": df.height,
            "games": df["game_id"].n_unique(), "skipped_no_meta": skipped}


CORSI_TYPES = ["shot-on-goal", "goal", "missed-shot", "blocked-shot"]
FENWICK_TYPES = ["shot-on-goal", "goal", "missed-shot"]
SOG_TYPES = ["shot-on-goal", "goal"]


def attach_outcomes() -> dict[str, Any]:
    """Phase 2.3: attribute shot attempts to stints via (start, end] and count
    for/against from the home perspective. xG stays null until Phase 3.
    Attribution reuses int_on_ice_events' (start, end] convention (event credited
    to the line on the ice through that second)."""
    stints = pl.read_parquet(STINTS_PARQUET)
    games = pl.read_parquet(sources.GAMES_PARQUET).select("game_id", "home_team_id", "away_team_id")
    ev = pl.read_parquet(sources.EVENTS_PARQUET).filter(
        pl.col("type_desc_key").is_in(CORSI_TYPES)
        & (pl.col("period_type") != "SO")
        & pl.col("event_owner_team_id").is_not_null()
    ).select("game_id", "event_second", "type_desc_key", "event_owner_team_id")
    ev = ev.join(games, on="game_id", how="inner").with_columns(
        is_home=pl.col("event_owner_team_id") == pl.col("home_team_id"))

    # attribute each event to the stint with the smallest end_seconds >= event_second
    st = stints.select("game_id", "stint_id", "start_seconds", "end_seconds").sort(
        "game_id", "end_seconds")
    ev = ev.sort("game_id", "event_second")
    ev = ev.join_asof(st, left_on="event_second", right_on="end_seconds", by="game_id",
                      strategy="forward").filter(
        pl.col("stint_id").is_not_null() & (pl.col("start_seconds") < pl.col("event_second")))

    def cnt(types, home):
        return (pl.col("type_desc_key").is_in(types) & (pl.col("is_home") == home)).sum()

    agg = ev.group_by("game_id", "stint_id").agg(
        cnt(CORSI_TYPES, True).alias("home_corsi"), cnt(CORSI_TYPES, False).alias("away_corsi"),
        cnt(FENWICK_TYPES, True).alias("home_fenwick"), cnt(FENWICK_TYPES, False).alias("away_fenwick"),
        cnt(SOG_TYPES, True).alias("home_sog"), cnt(SOG_TYPES, False).alias("away_sog"),
        cnt(["goal"], True).alias("home_goals"), cnt(["goal"], False).alias("away_goals"),
    )
    out = stints.join(agg, on=["game_id", "stint_id"], how="left").with_columns([
        pl.col(c).fill_null(0) for c in ["home_corsi", "away_corsi", "home_fenwick",
        "away_fenwick", "home_sog", "away_sog", "home_goals", "away_goals"]
    ]).with_columns(home_xg=pl.lit(None, dtype=pl.Float64), away_xg=pl.lit(None, dtype=pl.Float64))
    out.write_parquet(STINTS_PARQUET)
    return {"path": str(STINTS_PARQUET), "rows": out.height,
            "total_goals_attributed": int(out["home_goals"].sum() + out["away_goals"].sum())}


if __name__ == "__main__":
    import sys
    if "--outcomes" in sys.argv:
        print(attach_outcomes())
    else:
        print(build_stints(force=True))
