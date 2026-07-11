"""Frozen reimplementation of production `int_shot_sequence` seq_type classification.

REUSED DEFINITIONS (verbatim rules from dbt/models/intermediate/int_shot_sequence.sql,
window vars from dbt_project.yml) — we reimplement, we do not reinvent:
  shots        = type_desc_key in {shot-on-goal, missed-shot, goal}, x/y non-null
  zone re-expr = zone_code is owner-relative; flip O<->D when prior event owned by opp
  seq_rebound  = same-team unblocked attempt within 3s prior
  seq_rush     = D/N-zone (shooter-relative) event within 4s prior, AFTER every faceoff
                 in the window (no intervening faceoff)
  seq_forecheck= shooter recovers puck in OZ (own takeaway | opp giveaway) within 5s
  seq_cross_ice= same-team event on opposite y-half within 2s (|y|>=10 both)
  seq_cycle    = sustained OZ presence: no D/N event (either team) within 10s AND >=1 OZ
  seq_point_shot = |x|<=40 and zone_code='O' (shot property)
  seq_type precedence: rebound > rush > forecheck > cycle > point_shot > other

STRENGTH is ice-derived from FROZEN Atlas stints (not production segments): each shot is
attributed to the stint covering its event_second; 5v5 == stint.strength_state=='5v5'
with quarantined stints excluded (standing rule). This is the one deliberate deviation
from production (which reads the rebuilt segment backbone) — required to stay on frozen
assets; validated against production in reports/phase2.md §2.0.
"""
from __future__ import annotations

import polars as pl

from . import config

REBOUND_W, RUSH_W, FORECHECK_W, CROSS_ICE_W = 3, 4, 5, 2
CYCLE_W, FLAG_LOOKBACK = 10, 12
SHOT_TYPES = ["shot-on-goal", "missed-shot", "goal"]
SEQ_DIR = config.PARQUET / "seq"


def _events(season: str) -> pl.DataFrame:
    e = pl.read_parquet(config.ATLAS_PARQUET / "events.parquet").filter(
        pl.col("season_label") == season)
    return e.select(
        "game_id", "event_id", "sort_order", "event_second", "type_desc_key",
        "x_coord", "y_coord", "zone_code", "event_owner_team_id", "goalie_in_net_id")


def _strength_5v5(shots: pl.DataFrame, season: str) -> pl.DataFrame:
    """Attach ice-derived 5v5 flag by attributing each shot to its frozen stint."""
    st = (pl.read_parquet(config.ATLAS_PARQUET / "stints.parquet")
          .filter((pl.col("season_label") == season) & (~pl.col("is_quarantined")))
          .select("game_id", "start_seconds", "end_seconds", "strength_state")
          .sort(["game_id", "start_seconds"]))
    shots = shots.sort(["game_id", "event_second"])
    j = shots.join_asof(st, left_on="event_second", right_on="start_seconds",
                        by="game_id", strategy="backward")
    j = j.with_columns(
        is_5v5=((pl.col("strength_state") == "5v5")
                & (pl.col("event_second") < pl.col("end_seconds"))).fill_null(False)
    )
    return j.select("game_id", "event_id", "is_5v5")


def classify_season(season: str, write: bool = True) -> pl.DataFrame:
    ev = _events(season)
    shots = ev.filter(
        pl.col("type_desc_key").is_in(SHOT_TYPES)
        & pl.col("x_coord").is_not_null() & pl.col("y_coord").is_not_null()
    ).rename({"event_owner_team_id": "team_id", "event_second": "s_sec",
              "sort_order": "s_sort", "y_coord": "s_y", "x_coord": "s_x",
              "zone_code": "s_zone", "goalie_in_net_id": "s_goalie"})

    # prior events within the 12s flag window (bounded theta-join on game_id)
    prior = ev.select(
        "game_id", pl.col("sort_order").alias("e_sort"),
        pl.col("event_second").alias("e_sec"), pl.col("type_desc_key").alias("e_type"),
        pl.col("y_coord").alias("e_y"), pl.col("zone_code").alias("e_zone"),
        pl.col("event_owner_team_id").alias("e_team"))
    pairs = shots.join_where(
        prior,
        pl.col("game_id") == pl.col("game_id_right"),
        pl.col("e_sort") < pl.col("s_sort"),
        (pl.col("s_sec") - pl.col("e_sec")) <= FLAG_LOOKBACK,
        (pl.col("s_sec") - pl.col("e_sec")) >= 0,
    )
    pairs = pairs.with_columns(
        dt=pl.col("s_sec") - pl.col("e_sec"),
        e_same=pl.col("e_team") == pl.col("team_id"),
        # zone of prior event re-expressed relative to the SHOOTING team
        e_zone_rel=pl.when(pl.col("e_team") == pl.col("team_id")).then(pl.col("e_zone"))
        .when(pl.col("e_zone") == "O").then(pl.lit("D"))
        .when(pl.col("e_zone") == "D").then(pl.lit("O"))
        .otherwise(pl.lit("N")),
    )
    # most-recent faceoff sort within window (for the no-intervening-faceoff rush rule)
    pairs = pairs.with_columns(
        fo_sort=pl.when(pl.col("e_type") == "faceoff").then(pl.col("e_sort"))
        .otherwise(None).max().over("game_id", "event_id"))

    flags = pairs.group_by("game_id", "event_id").agg(
        seq_rebound=(pl.col("e_type").is_in(SHOT_TYPES) & pl.col("e_same")
                     & (pl.col("dt") <= REBOUND_W)).any(),
        seq_rush=(pl.col("e_zone_rel").is_in(["D", "N"]) & (pl.col("dt") <= RUSH_W)
                  & (pl.col("fo_sort").is_null() | (pl.col("e_sort") > pl.col("fo_sort")))).any(),
        seq_forecheck=((pl.col("e_zone_rel") == "O") & (pl.col("dt") <= FORECHECK_W)
                       & (((pl.col("e_type") == "takeaway") & pl.col("e_same"))
                          | ((pl.col("e_type") == "giveaway") & ~pl.col("e_same")))).any(),
        seq_cross_ice=(pl.col("e_same") & (pl.col("dt") <= CROSS_ICE_W)
                       & (pl.col("e_y").sign() != pl.col("s_y").sign())
                       & (pl.col("e_y").abs() >= 10) & (pl.col("s_y").abs() >= 10)).any(),
        dn_cycle=((pl.col("e_zone_rel").is_in(["D", "N"])) & (pl.col("dt") <= CYCLE_W)).sum(),
        oz_cycle=((pl.col("e_zone_rel") == "O") & (pl.col("dt") <= CYCLE_W)).sum(),
    )

    out = shots.join(flags, on=["game_id", "event_id"], how="left").with_columns(
        seq_rebound=pl.col("seq_rebound").fill_null(False),
        seq_rush=pl.col("seq_rush").fill_null(False),
        seq_forecheck=pl.col("seq_forecheck").fill_null(False),
        seq_cycle=((pl.col("dn_cycle").fill_null(0) == 0) & (pl.col("oz_cycle").fill_null(0) >= 1)),
        seq_point_shot=((pl.col("s_x").abs() <= 40) & (pl.col("s_zone") == "O")),
    ).with_columns(
        seq_type=pl.when(pl.col("seq_rebound")).then(pl.lit("rebound"))
        .when(pl.col("seq_rush")).then(pl.lit("rush"))
        .when(pl.col("seq_forecheck")).then(pl.lit("forecheck"))
        .when(pl.col("seq_cycle")).then(pl.lit("cycle"))
        .when(pl.col("seq_point_shot")).then(pl.lit("point_shot"))
        .otherwise(pl.lit("other"))
    )
    strength = _strength_5v5(
        shots.select("game_id", "event_id", pl.col("s_sec").alias("event_second")), season)
    out = out.join(strength, on=["game_id", "event_id"], how="left")
    out = out.select(
        "game_id", "event_id", "team_id", "s_sec", "s_x", "s_y", "s_zone",
        "is_5v5", "seq_type", "seq_point_shot",
        pl.col("type_desc_key").alias("shot_type"))
    if write:
        SEQ_DIR.mkdir(parents=True, exist_ok=True)
        out.write_parquet(SEQ_DIR / f"{season.replace('-', '_')}.parquet")
    return out


if __name__ == "__main__":
    import sys
    seasons = sys.argv[1:] or config.SEASONS_ALL
    for s in seasons:
        fp = SEQ_DIR / f"{s.replace('-', '_')}.parquet"
        if fp.exists():
            print(s, "cached", flush=True)
            continue
        df = classify_season(s)
        print(s, df.height, "shots done", flush=True)
