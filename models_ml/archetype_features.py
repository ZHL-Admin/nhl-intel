"""
Shared player-season feature assembly for archetypes (Phase 4.2) and reused by Phase 4.4.

Builds one standardized-ready feature row per (player_id, season) for skaters with >= the
minutes floor, from the marts + sequence layer + segments + Edge + RAPM impact. Edge features
(burst rate, o-zone time) exist only for the tracking era and are mean-imputed within position
group when absent.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from models_ml import bq, config

# feature column -> human label for the labeling report
FEATURES = {
    "rush_share": "rush attempt share",
    "rebound_share": "rebound attempt share",
    "forecheck_share": "forecheck attempt share",
    "cycle_share": "cycle attempt share",
    "point_share": "point-shot attempt share",
    "mean_shot_distance": "mean shot distance (ft)",
    "slot_share": "slot-shot share",
    "off_impact": "RAPM offence",
    "def_impact": "RAPM defence",
    "pp_toi_share": "PP TOI share",
    "pk_toi_share": "PK TOI share",
    "oz_start_share": "o-zone faceoff-start share",
    "pen_drawn_per60": "penalties drawn /60",
    "edge_burst_per60": "Edge 22+ mph bursts /60",
    "edge_oz_pct": "Edge o-zone time %",
}

BASE_SQL = """
with pg as (
  select player_id, season, any_value(position_code) as position, count(*) as games,
    sum(individual_shot_attempts) as shots, sum(individual_goals) as goals, sum(ixg) as ixg,
    sum(seq_rush_attempts) as rush, sum(seq_rebound_attempts) as rebound,
    sum(seq_forecheck_attempts) as forecheck, sum(seq_cycle_attempts) as cycle,
    sum(seq_point_shot_attempts) as point, sum(seq_other_attempts) as other_seq
  from `{p}.nhl_mart.mart_player_game_stats`
  where substr(cast(game_id as string), 5, 2) in ('02', '03')
  group by 1, 2
),
shotloc as (
  select shooter_id as player_id, season,
    avg(sqrt(pow(89 - abs(x_coord), 2) + pow(y_coord, 2))) as mean_shot_distance,
    avg(if(abs(x_coord) >= {hx} and abs(y_coord) <= {hy}, 1.0, 0.0)) as slot_share
  from `{p}.nhl_staging.int_shot_sequence`
  where shooter_id is not null and x_coord is not null
  group by 1, 2
),
toi as (
  select s.player_id, s.season,
    sum(if(c.strength_state = '5v5', s.segment_duration, 0)) / 60.0 as toi_5v5,
    sum(if(s.team_skater_count > (case when s.team_id = c.home_team_id then c.away_skaters
                                       else c.home_skaters end), s.segment_duration, 0)) / 60.0 as pp_toi,
    sum(if(s.team_skater_count < (case when s.team_id = c.home_team_id then c.away_skaters
                                       else c.home_skaters end), s.segment_duration, 0)) / 60.0 as pk_toi
  from `{p}.nhl_staging.int_shift_segments` s
  join `{p}.nhl_staging.int_segment_context` c
    on s.game_id = c.game_id and s.segment_index = c.segment_index
  where s.is_goalie = 0
  group by 1, 2
),
zstart as (
  select s.player_id, s.season,
    countif(c.zone_start_code = 'O') as oz_starts,
    countif(c.zone_start_code = 'D') as dz_starts
  from `{p}.nhl_staging.int_shift_segments` s
  join `{p}.nhl_staging.int_segment_context` c
    on s.game_id = c.game_id and s.segment_index = c.segment_index
  where s.is_goalie = 0 and c.is_zone_start and c.strength_state = '5v5'
  group by 1, 2
),
pen as (
  select drawn_by_player_id as player_id, season, count(*) as drawn
  from `{p}.nhl_staging.stg_play_by_play`
  where type_desc_key = 'penalty' and drawn_by_player_id is not null
  group by 1, 2
),
edge as (
  select player_id, season_id, bursts_22_plus_per60 as edge_burst_per60,
         oz_time_pct_es as edge_oz_pct
  from `{p}.nhl_mart.mart_edge_player_profile`
)
select pg.*, sl.mean_shot_distance, sl.slot_share,
  coalesce(t.toi_5v5, 0) as toi_5v5, coalesce(t.pp_toi, 0) as pp_toi, coalesce(t.pk_toi, 0) as pk_toi,
  coalesce(z.oz_starts, 0) as oz_starts, coalesce(z.dz_starts, 0) as dz_starts,
  coalesce(pen.drawn, 0) as pen_drawn,
  e.edge_burst_per60, e.edge_oz_pct
from pg
left join shotloc sl on pg.player_id = sl.player_id and pg.season = sl.season
left join toi t on pg.player_id = t.player_id and pg.season = t.season
left join zstart z on pg.player_id = z.player_id and pg.season = z.season
left join pen on pg.player_id = pen.player_id and pg.season = pen.season
left join edge e on pg.player_id = e.player_id
  and e.season_id = cast(substr(pg.season, 1, 4) || '20' || substr(pg.season, 6, 2) as int64)
"""


def build(seasons: list[str], min_5v5: float | None = None) -> pd.DataFrame:
    min_5v5 = config.ARCHETYPE_MIN_5V5_MIN if min_5v5 is None else min_5v5
    sql = BASE_SQL.format(p=bq.project(), hx=55, hy=22)
    df = bq.query_df(sql)
    df = df[df["season"].isin(seasons)].copy()
    for c in ["games", "shots", "goals", "ixg", "rush", "rebound", "forecheck", "cycle",
              "point", "other_seq", "toi_5v5", "pp_toi", "pk_toi", "oz_starts", "dz_starts",
              "pen_drawn"]:
        df[c] = pd.to_numeric(df[c]).astype("float64")
    df = df[(df["position"] != "G") & (df["toi_5v5"] >= min_5v5)].copy()

    seq_total = (df[["rush", "rebound", "forecheck", "cycle", "point", "other_seq"]]
                 .sum(axis=1)).replace(0, np.nan)
    df["rush_share"] = df["rush"] / seq_total
    df["rebound_share"] = df["rebound"] / seq_total
    df["forecheck_share"] = df["forecheck"] / seq_total
    df["cycle_share"] = df["cycle"] / seq_total
    df["point_share"] = df["point"] / seq_total
    total_toi = df["toi_5v5"] + df["pp_toi"] + df["pk_toi"]
    df["pp_toi_share"] = df["pp_toi"] / total_toi
    df["pk_toi_share"] = df["pk_toi"] / total_toi
    df["oz_start_share"] = df["oz_starts"] / (df["oz_starts"] + df["dz_starts"]).replace(0, np.nan)
    df["pen_drawn_per60"] = df["pen_drawn"] / total_toi.replace(0, np.nan) * 60.0
    df["edge_burst_per60"] = pd.to_numeric(df["edge_burst_per60"], errors="coerce")
    df["edge_oz_pct"] = pd.to_numeric(df["edge_oz_pct"], errors="coerce")

    # RAPM impact (single-season) merged per (player, season)
    impact = bq.query_df(f"""select player_id, season_window as season, off_impact, def_impact
                             from `{bq.project()}.nhl_models.player_impact`
                             where season_window in ({", ".join(f"'{s}'" for s in seasons)})""")
    df = df.merge(impact, on=["player_id", "season"], how="left")

    df["pos_group"] = np.where(df["position"] == "D", "D", "F")
    # impute remaining NaNs by position-group mean (Edge era + missing shotloc/impact)
    for f in FEATURES:
        df[f] = df.groupby("pos_group")[f].transform(lambda s: s.fillna(s.mean()))
        df[f] = df[f].fillna(df[f].mean())
    return df
