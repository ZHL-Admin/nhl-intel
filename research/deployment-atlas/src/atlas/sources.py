"""Read-only adapters that assemble the Atlas corpus from NIR's BigQuery.

Standing rule 7b (audit, validate, extend): NIR already ingests the shift feed,
play-by-play, and boxscores. This module READS the production staging views /
raw tables and materializes the Atlas's own Parquet tables under
``data/parquet/``. **Production is never written.** The only network fetches are
the two play-by-play games missing from BigQuery (approved gap), through the
Phase 0 client under the preamble's cache/rate rules.

Source of every output column is documented in the SQL and in COLUMN_PROVENANCE.

Scope: regular season (game type 02), season-start years 2010..2025
(= seasons 2010-11 .. 2025-26). 2015-16+ is primary modeling scope; 2010-11..
2014-15 are admitted flagged (`is_primary_scope=false`) pending 1.4 integrity.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import polars as pl

from . import config, fetch, parse
from .client import AtlasClient

BQ_PROJECT = "nhl-intel-498216"
SA_KEYFILE = config.PROJECT_ROOT.parents[1] / "secrets" / "nhl-intel-sa.json"

SCOPE_MIN_YEAR = 2010          # season-start year (2010-11)
SCOPE_MAX_YEAR = 2025          # season-start year (2025-26)
PRIMARY_MIN_YEAR = 2015        # 2015-16 is the primary modeling floor
REGULAR_SEASON = "02"

# Play-by-play games present in boxscore+shifts but missing pbp in BigQuery
# (identified in Phase 1.2). Fetched fresh through the Phase 0 client.
PBP_GAP_GAMES = ["2023020651", "2024020147"]

SHIFTS_PARQUET = config.PARQUET_DIR / "shifts.parquet"
EVENTS_PARQUET = config.PARQUET_DIR / "events.parquet"
BOXSCORE_TOI_PARQUET = config.PARQUET_DIR / "boxscore_toi.parquet"
PENALTY_LEDGER_PARQUET = config.PARQUET_DIR / "penalty_ledger.parquet"
ROSTERS_PARQUET = config.PARQUET_DIR / "rosters.parquet"
GAMES_PARQUET = config.PARQUET_DIR / "games.parquet"


def season_label(year: int) -> str:
    return f"{year}-{str(year + 1)[2:]}"


def _existing(path) -> dict[str, Any] | None:
    """If the Parquet already exists, summarize it without re-querying BigQuery."""
    from pathlib import Path
    p = Path(path)
    if not p.exists():
        return None
    df = pl.read_parquet(p, columns=["game_id"])
    return {"path": str(p), "rows": df.height, "games": df["game_id"].n_unique(),
            "reused": True}


# ---------------------------------------------------------------------------
# BigQuery access (read-only)
# ---------------------------------------------------------------------------
def bq_client():
    from google.cloud import bigquery
    return bigquery.Client.from_service_account_json(str(SA_KEYFILE), project=BQ_PROJECT)


def _read_bq(sql: str) -> pl.DataFrame:
    """Run a read-only query and return a polars frame (via Arrow).

    Prefers the BigQuery Storage Read API (fast Arrow streaming). If the service
    account lacks `bigquery.readsessions.create`, transparently falls back to the
    slower REST download so the pipeline still runs on viewer/jobUser roles.
    """
    from google.api_core.exceptions import Forbidden, PermissionDenied

    client = bq_client()
    try:
        rows = client.query(sql).result()
        try:
            tbl = rows.to_arrow(create_bqstorage_client=True)
        except (PermissionDenied, Forbidden):
            tbl = rows.to_arrow(create_bqstorage_client=False)
    finally:
        client.close()
    return pl.from_arrow(tbl)


_SCOPE_WHERE = (
    f"substr(cast(game_id as string), 5, 2) = '{REGULAR_SEASON}' "
    f"and safe_cast(substr(cast(game_id as string), 1, 4) as int64) "
    f"between {SCOPE_MIN_YEAR} and {SCOPE_MAX_YEAR}"
)


def _add_scope_flags(df: pl.DataFrame) -> pl.DataFrame:
    yr = pl.col("season_start_year")
    return df.with_columns(
        season_start_year=pl.col("game_id").cast(pl.Utf8).str.slice(0, 4).cast(pl.Int64),
    ).with_columns(
        season_label=yr.cast(pl.Utf8) + "-" + ((yr + 1) % 100).cast(pl.Utf8).str.zfill(2),
        is_primary_scope=yr >= PRIMARY_MIN_YEAR,
    )


def _mmss_expr(col: str) -> pl.Expr:
    """MM:SS -> seconds as an Int64 expression (null-safe)."""
    parts = pl.col(col).str.split(":")
    return (parts.list.get(0).cast(pl.Int64) * 60 + parts.list.get(1).cast(pl.Int64)).alias(col + "_s")


# ---------------------------------------------------------------------------
# shifts
# ---------------------------------------------------------------------------
def materialize_shifts(force: bool = False) -> dict[str, Any]:
    if not force and (ex := _existing(SHIFTS_PARQUET)):
        return ex
    # Reuses stg_shifts's exact transformation (517-via-null-duration filter,
    # (period-1)*1200 offset, 1..1200s validity), but reads raw_shift_charts
    # directly with SAFE_CAST/SAFE_OFFSET. The production view uses hard CAST on
    # JSON-string fields and THROWS "Bad int64 value" on malformed pre-2015 rows
    # (never hit by prod marts, which run 2021-26). Hardening drops those rows
    # instead of crashing; for 2015-26 the output is identical to stg_shifts.
    sql = f"""
    with raw as (
      select game_id, data,
        row_number() over (partition by game_id order by ingestion_date desc) as rn
      from `{BQ_PROJECT}.nhl_raw.raw_shift_charts`
      where {_SCOPE_WHERE}
    ),
    latest as (select game_id, data from raw where rn = 1),
    shifts as (
      select
        l.game_id,
        safe_cast(json_extract_scalar(shift, '$.playerId') as int64) as player_id,
        safe_cast(json_extract_scalar(shift, '$.teamId') as int64) as team_id,
        safe_cast(json_extract_scalar(shift, '$.period') as int64) as period,
        safe_cast(json_extract_scalar(shift, '$.shiftNumber') as int64) as shift_number,
        json_extract_scalar(shift, '$.startTime') as start_mmss,
        json_extract_scalar(shift, '$.endTime') as end_mmss,
        json_extract_scalar(shift, '$.duration') as duration_mmss
      from latest l, unnest(json_extract_array(l.data)) as shift
    ),
    parsed as (
      select
        game_id, player_id, team_id, period, shift_number,
        (period - 1) * 1200
          + safe_cast(split(start_mmss, ':')[safe_offset(0)] as int64) * 60
          + safe_cast(split(start_mmss, ':')[safe_offset(1)] as int64) as shift_start_seconds,
        (period - 1) * 1200
          + safe_cast(split(end_mmss, ':')[safe_offset(0)] as int64) * 60
          + safe_cast(split(end_mmss, ':')[safe_offset(1)] as int64) as shift_end_seconds,
        safe_cast(split(duration_mmss, ':')[safe_offset(0)] as int64) * 60
          + safe_cast(split(duration_mmss, ':')[safe_offset(1)] as int64) as duration_seconds
      from shifts
      where duration_mmss is not null and duration_mmss != ''
    )
    select game_id, player_id, team_id, period, shift_number,
           shift_start_seconds, shift_end_seconds, duration_seconds
    from parsed
    where player_id is not null and duration_seconds between 1 and 1200
    -- Atlas correction (rule 7b, extend): drop exact-duplicate shift rows. The
    -- raw NHL shift array repeats some (player, start, end) entries verbatim
    -- (~0.1% of rows, 2020-25); production stg_shifts inherits them, inflating
    -- TOI and creating phantom overlaps. A player cannot have two identical
    -- shifts, so this is an unambiguous, non-destructive de-dup. Documented in
    -- the Phase 1 report; production is untouched.
    qualify row_number() over (
      partition by game_id, player_id, shift_start_seconds, shift_end_seconds
      order by shift_number) = 1
    """
    df = _add_scope_flags(_read_bq(sql))
    df = df.select(
        "game_id", "season_start_year", "season_label", "is_primary_scope",
        "player_id", "team_id", "period", "shift_number",
        "shift_start_seconds", "shift_end_seconds", "duration_seconds",
    ).sort("game_id", "player_id", "shift_start_seconds")
    df.write_parquet(SHIFTS_PARQUET)
    return {"path": str(SHIFTS_PARQUET), "rows": df.height,
            "games": df["game_id"].n_unique()}


# ---------------------------------------------------------------------------
# events (BigQuery + 2 gap games from the Phase 0 client)
# ---------------------------------------------------------------------------
EVENT_COLUMNS = [
    "game_id", "season_start_year", "season_label", "is_primary_scope",
    "event_id", "sort_order", "period_number", "period_type",
    "time_in_period_s", "event_second", "situation_code", "home_team_defending_side",
    "type_code", "type_desc_key", "x_coord", "y_coord", "zone_code", "shot_type",
    "shooting_player_id", "scoring_player_id", "goalie_in_net_id",
    "assist1_player_id", "assist2_player_id", "event_owner_team_id",
    "home_score", "away_score", "source",
]

# Explicit schema for the gap-fetch frame so all-null-then-int columns (e.g.
# scoring_player_id) don't break polars' first-N-rows schema inference.
_EVENT_SCHEMA: dict[str, Any] = {
    "game_id": pl.Int64, "season_start_year": pl.Int64, "season_label": pl.Utf8,
    "is_primary_scope": pl.Boolean, "event_id": pl.Int64, "sort_order": pl.Int64,
    "period_number": pl.Int64, "period_type": pl.Utf8, "time_in_period_s": pl.Int64,
    "event_second": pl.Int64, "situation_code": pl.Utf8, "home_team_defending_side": pl.Utf8,
    "type_code": pl.Int64, "type_desc_key": pl.Utf8, "x_coord": pl.Int64, "y_coord": pl.Int64,
    "zone_code": pl.Utf8, "shot_type": pl.Utf8, "shooting_player_id": pl.Int64,
    "scoring_player_id": pl.Int64, "goalie_in_net_id": pl.Int64, "assist1_player_id": pl.Int64,
    "assist2_player_id": pl.Int64, "event_owner_team_id": pl.Int64, "home_score": pl.Int64,
    "away_score": pl.Int64, "source": pl.Utf8,
}


def materialize_events(client: AtlasClient | None = None, force: bool = False) -> dict[str, Any]:
    if not force and (ex := _existing(EVENTS_PARQUET)):
        return ex
    sql = f"""
    select
      game_id, season, event_id, sort_order, period_number, period_type,
      time_in_period, situation_code, home_team_defending_side,
      type_code, type_desc_key, x_coord, y_coord, zone_code, shot_type,
      shooting_player_id, scoring_player_id, goalie_in_net_id,
      assist1_player_id, assist2_player_id, event_owner_team_id,
      home_score, away_score
    from `{BQ_PROJECT}.nhl_staging.stg_play_by_play`
    where {_SCOPE_WHERE}
    """
    df = _add_scope_flags(_read_bq(sql))
    df = df.with_columns(_mmss_expr("time_in_period")).with_columns(
        event_second=(pl.col("period_number") - 1) * config.REGULATION_PERIOD_SECONDS
        + pl.col("time_in_period_s"),
        source=pl.lit("bq:stg_play_by_play"),
    ).select(EVENT_COLUMNS)

    # Approved gap fetch: 2 pbp games missing from BigQuery.
    gap_frames = [_fetch_gap_pbp(gid, client) for gid in PBP_GAP_GAMES]
    gap_frames = [g for g in gap_frames if g is not None and g.height > 0]
    combined = pl.concat([df, *gap_frames], how="vertical_relaxed") if gap_frames else df
    combined = combined.sort("game_id", "sort_order")
    combined.write_parquet(EVENTS_PARQUET)
    return {"path": str(EVENTS_PARQUET), "rows": combined.height,
            "games": combined["game_id"].n_unique(),
            "gap_games_added": [g for g in PBP_GAP_GAMES]}


def _fetch_gap_pbp(game_id: str, client: AtlasClient | None) -> pl.DataFrame | None:
    """Fetch one missing pbp game via the Phase 0 client and shape it to the
    events schema (mirrors stg_play_by_play's field selection)."""
    own = client is None
    client = client or AtlasClient()
    try:
        payload = fetch.pbp(client, game_id)
    finally:
        if own:
            client.close()
    plays = payload.get("plays", []) if isinstance(payload, dict) else []
    yr = int(str(game_id)[:4])
    rows: list[dict[str, Any]] = []
    for p in plays:
        d = p.get("details") if isinstance(p.get("details"), dict) else {}
        pd = p.get("periodDescriptor") or {}
        tip = parse.mmss_to_seconds(p.get("timeInPeriod"))
        rows.append({
            "game_id": int(payload.get("id")),
            "season_start_year": yr,
            "season_label": season_label(yr),
            "is_primary_scope": yr >= PRIMARY_MIN_YEAR,
            "event_id": p.get("eventId"),
            "sort_order": p.get("sortOrder"),
            "period_number": pd.get("number"),
            "period_type": pd.get("periodType"),
            "time_in_period_s": tip,
            "event_second": ((pd.get("number") or 1) - 1) * config.REGULATION_PERIOD_SECONDS
            + (tip or 0),
            "situation_code": p.get("situationCode"),
            "home_team_defending_side": p.get("homeTeamDefendingSide"),
            "type_code": p.get("typeCode"),
            "type_desc_key": p.get("typeDescKey"),
            "x_coord": d.get("xCoord"), "y_coord": d.get("yCoord"),
            "zone_code": d.get("zoneCode"), "shot_type": d.get("shotType"),
            "shooting_player_id": d.get("shootingPlayerId"),
            "scoring_player_id": d.get("scoringPlayerId"),
            "goalie_in_net_id": d.get("goalieInNetId"),
            "assist1_player_id": d.get("assist1PlayerId"),
            "assist2_player_id": d.get("assist2PlayerId"),
            "event_owner_team_id": d.get("eventOwnerTeamId"),
            "home_score": d.get("homeScore"), "away_score": d.get("awayScore"),
            "source": "api:gap_fetch",
        })
    if not rows:
        return None
    return pl.DataFrame(rows, schema=_EVENT_SCHEMA).select(EVENT_COLUMNS)


# ---------------------------------------------------------------------------
# boxscore per-player TOI (zero-fetch re-parse of raw_boxscores)
# ---------------------------------------------------------------------------
def materialize_boxscore_toi(force: bool = False) -> dict[str, Any]:
    if not force and (ex := _existing(BOXSCORE_TOI_PARQUET)):
        return ex
    sql = f"""
    with latest as (
      select game_id, playerByGameStats as pg,
        row_number() over (partition by game_id order by ingestion_date desc) as rn
      from `{BQ_PROJECT}.nhl_raw.raw_boxscores`
      where {_SCOPE_WHERE}
    ),
    b as (select game_id, pg from latest where rn = 1),
    exploded as (
      select game_id, 'away' as side, 'F' as grp, s.playerId as player_id,
             s.position as position, s.toi as toi_mmss, s.shifts as shifts_ct
      from b, unnest(pg.awayTeam.forwards) s
      union all
      select game_id, 'away', 'D', s.playerId, s.position, s.toi, s.shifts
      from b, unnest(pg.awayTeam.defense) s
      union all
      select game_id, 'away', 'G', s.playerId, s.position, s.toi, cast(null as int64)
      from b, unnest(pg.awayTeam.goalies) s
      union all
      select game_id, 'home', 'F', s.playerId, s.position, s.toi, s.shifts
      from b, unnest(pg.homeTeam.forwards) s
      union all
      select game_id, 'home', 'D', s.playerId, s.position, s.toi, s.shifts
      from b, unnest(pg.homeTeam.defense) s
      union all
      select game_id, 'home', 'G', s.playerId, s.position, s.toi, cast(null as int64)
      from b, unnest(pg.homeTeam.goalies) s
    )
    select * from exploded
    """
    df = _add_scope_flags(_read_bq(sql))
    df = df.with_columns(_mmss_expr("toi_mmss")).rename({"toi_mmss_s": "toi_seconds"})
    df = df.select(
        "game_id", "season_start_year", "season_label", "is_primary_scope",
        "player_id", "side", "grp", "position", "toi_seconds", "shifts_ct",
    ).sort("game_id", "player_id")
    df.write_parquet(BOXSCORE_TOI_PARQUET)
    return {"path": str(BOXSCORE_TOI_PARQUET), "rows": df.height,
            "games": df["game_id"].n_unique()}


# ---------------------------------------------------------------------------
# penalty ledger (zero-fetch re-parse of raw_play_by_play; incl descKey+severity)
# ---------------------------------------------------------------------------
def materialize_penalty_ledger(force: bool = False) -> dict[str, Any]:
    if not force and (ex := _existing(PENALTY_LEDGER_PARQUET)):
        return ex
    sql = f"""
    with pens as (
      select
        cast(game_id as int64) as game_id,
        ingestion_date,
        play.eventId as event_id,
        play.periodDescriptor.number as period,
        play.timeInPeriod as time_in_period,
        play.details.committedByPlayerId as committed_by_player_id,
        play.details.drawnByPlayerId as drawn_by_player_id,
        play.details.eventOwnerTeamId as team_id,
        play.details.descKey as desc_key,
        play.details.typeCode as severity_type_code,
        play.details.duration as duration_minutes
      from `{BQ_PROJECT}.nhl_raw.raw_play_by_play`,
        unnest(plays) as play
      where play.typeDescKey = 'penalty'
        and {_SCOPE_WHERE}
    ),
    dedup as (
      select *, row_number() over (partition by game_id, event_id
                                    order by ingestion_date desc) as rn
      from pens
    )
    select game_id, event_id, period, time_in_period, committed_by_player_id,
           drawn_by_player_id, team_id, desc_key, severity_type_code, duration_minutes
    from dedup where rn = 1
    """
    df = _add_scope_flags(_read_bq(sql))
    df = df.with_columns(_mmss_expr("time_in_period")).with_columns(
        start_second=(pl.col("period") - 1) * config.REGULATION_PERIOD_SECONDS
        + pl.col("time_in_period_s"),
    ).select(
        "game_id", "season_start_year", "season_label", "is_primary_scope",
        "event_id", "period", "start_second", "committed_by_player_id",
        "drawn_by_player_id", "team_id", "desc_key", "severity_type_code", "duration_minutes",
    ).sort("game_id", "start_second")
    df.write_parquet(PENALTY_LEDGER_PARQUET)
    return {"path": str(PENALTY_LEDGER_PARQUET), "rows": df.height,
            "games": df["game_id"].n_unique()}


# ---------------------------------------------------------------------------
# Column provenance (documented source of every output column)
# ---------------------------------------------------------------------------
COLUMN_PROVENANCE: dict[str, dict[str, str]] = {
    "shifts.parquet": {
        "game_id/player_id/team_id/period/shift_number": "nhl_staging.stg_shifts (from raw_shift_charts, 517-filtered)",
        "shift_start_seconds/shift_end_seconds/duration_seconds": "stg_shifts, (period-1)*1200 + mm:ss",
        "season_start_year/season_label/is_primary_scope": "derived from game_id digits 1-4",
    },
    "events.parquet": {
        "coords/zone/situation/type/players/scores": "nhl_staging.stg_play_by_play (from raw_play_by_play)",
        "event_second": "derived: (period-1)*1200 + time_in_period",
        "source": "'bq:stg_play_by_play' or 'api:gap_fetch' (2 games)",
    },
    "boxscore_toi.parquet": {
        "player_id/position/toi_seconds/shifts_ct": "raw_boxscores.playerByGameStats.{team}.{grp}[] (zero-fetch re-parse)",
    },
    "penalty_ledger.parquet": {
        "committed_by/drawn_by/team/desc_key/severity_type_code/duration_minutes/start_second":
            "raw_play_by_play.plays.details (zero-fetch re-parse; descKey+severity added per Amendment A)",
    },
}


def materialize_rosters(force: bool = False) -> dict[str, Any]:
    """Per (game, player): team, position, goalie flag — from raw_play_by_play
    rosterSpots (STRUCT; safe on all seasons). Needed for stint personnel."""
    if not force and (ex := _existing(ROSTERS_PARQUET)):
        return ex
    sql = f"""
    with latest as (
      select game_id, rosterSpots,
        row_number() over (partition by game_id order by ingestion_date desc) as rn
      from `{BQ_PROJECT}.nhl_raw.raw_play_by_play`
      where {_SCOPE_WHERE})
    select l.game_id, rs.playerId as player_id, rs.teamId as team_id,
           rs.positionCode as position_code
    from latest l, unnest(l.rosterSpots) rs
    where l.rn = 1
    """
    df = _add_scope_flags(_read_bq(sql))
    df = df.with_columns(is_goalie=(pl.col("position_code") == "G")).select(
        "game_id", "season_start_year", "player_id", "team_id",
        "position_code", "is_goalie").unique().sort("game_id", "player_id")
    df.write_parquet(ROSTERS_PARQUET)
    return {"path": str(ROSTERS_PARQUET), "rows": df.height, "games": df["game_id"].n_unique()}


def materialize_games(force: bool = False) -> dict[str, Any]:
    """Per game: home/away team id + playoff flag — from raw_play_by_play."""
    if not force and (ex := _existing(GAMES_PARQUET)):
        return ex
    sql = f"""
    with latest as (
      select game_id, homeTeam.id as home_team_id, awayTeam.id as away_team_id,
        row_number() over (partition by game_id order by ingestion_date desc) as rn
      from `{BQ_PROJECT}.nhl_raw.raw_play_by_play`
      where {_SCOPE_WHERE})
    select game_id, home_team_id, away_team_id from latest where rn = 1
    """
    df = _add_scope_flags(_read_bq(sql))
    df = df.with_columns(
        is_playoffs=pl.col("game_id").cast(pl.Utf8).str.slice(4, 2) == "03",
    ).select("game_id", "season_start_year", "season_label", "home_team_id",
             "away_team_id", "is_playoffs").sort("game_id")
    df.write_parquet(GAMES_PARQUET)
    return {"path": str(GAMES_PARQUET), "rows": df.height, "games": df["game_id"].n_unique()}


def materialize_all(client: AtlasClient | None = None) -> dict[str, Any]:
    return {
        "shifts": materialize_shifts(),
        "events": materialize_events(client),
        "boxscore_toi": materialize_boxscore_toi(),
        "penalty_ledger": materialize_penalty_ledger(),
        "rosters": materialize_rosters(),
        "games": materialize_games(),
    }
