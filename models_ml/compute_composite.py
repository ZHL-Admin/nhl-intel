"""
Composite stack (Phase 4.2, blueprint 4.3).

Per player-season (and the 3-season window), decompose total value into components on a common
GOALS scale, each with an uncertainty:

  ev_offense   = off_impact (RAPM, xGF/60) x 5v5 TOI/60
  ev_defense   = def_impact x 5v5 TOI/60
  pp           = pp_impact x PP TOI/60
  pk           = pk_impact x PK TOI/60
  finishing    = (goals - ixG) shrunk toward 0 by individual shot volume (PLAYER_FINISHING_SHRINKAGE_K)
  penalty_diff = (penalties drawn - taken) x PP_GOAL_VALUE
  goalie_gsax  = season GSAx (goalies only)

total = sum of components; total_sd = component sds combined in quadrature. The product RULE:
components are ALWAYS returned, never a total-only shape.

Output nhl_models.player_composite (player_id, season_window, every component + *_sd, total,
total_sd, position, games/TOI denominators). Windows mirror nhl_models.player_impact.

Run:  python -m models_ml.compute_composite [--dry-run]
"""

from __future__ import annotations

import argparse

import numpy as np
import pandas as pd

from models_ml import bq, config

SINGLE_SEASONS = ["2021-22", "2022-23", "2023-24", "2024-25", "2025-26"]
WINDOW = ["2023-24", "2024-25", "2025-26"]
WINDOW_LABEL = "2023-24_2025-26"
COMPONENTS = ["ev_offense", "ev_defense", "pp", "pk", "finishing", "penalty_diff", "goalie_gsax"]

# Per (player, season) skater aggregates: goals, ixG, shots, position, and strength TOI.
PLAYER_SEASON_SQL = """
with pg as (
  select player_id, season, any_value(position_code) as position,
         sum(individual_goals) as goals, sum(ixg) as ixg,
         sum(individual_shot_attempts) as shots, count(*) as games
  from `{p}.nhl_mart.mart_player_game_stats`
  where substr(cast(game_id as string), 5, 2) in ('02', '03')
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
pen as (
  select player_id, season, sum(taken) as taken, sum(drawn) as drawn
  from (
    select committed_by_player_id as player_id, season, count(*) as taken, 0 as drawn
    from `{p}.nhl_staging.stg_play_by_play`
    where type_desc_key = 'penalty' and committed_by_player_id is not null
    group by 1, 2
    union all
    select drawn_by_player_id as player_id, season, 0 as taken, count(*) as drawn
    from `{p}.nhl_staging.stg_play_by_play`
    where type_desc_key = 'penalty' and drawn_by_player_id is not null
    group by 1, 2
  )
  group by 1, 2
)
select pg.player_id, pg.season, pg.position, pg.goals, pg.ixg, pg.shots, pg.games,
       coalesce(toi.toi_5v5, 0) as toi_5v5, coalesce(toi.pp_toi, 0) as pp_toi,
       coalesce(toi.pk_toi, 0) as pk_toi,
       coalesce(pen.taken, 0) as pen_taken, coalesce(pen.drawn, 0) as pen_drawn
from pg
left join toi on pg.player_id = toi.player_id and pg.season = toi.season
left join pen on pg.player_id = pen.player_id and pg.season = pen.season
"""


def pull_player_seasons() -> pd.DataFrame:
    df = bq.query_df(PLAYER_SEASON_SQL.format(p=bq.project()))
    for c in ["goals", "ixg", "shots", "games", "toi_5v5", "pp_toi", "pk_toi",
              "pen_taken", "pen_drawn"]:
        df[c] = pd.to_numeric(df[c]).astype("float64")
    return df


def goalie_gsax() -> pd.DataFrame:
    df = bq.query_df(f"""
        select goalie_id as player_id, season, sum(gsax) as gsax
        from `{bq.project()}.nhl_mart.mart_goalie_game_stats`
        where substr(cast(game_id as string), 5, 2) in ('02', '03')
        group by 1, 2
    """)
    df["gsax"] = pd.to_numeric(df["gsax"]).astype("float64")
    return df


def aggregate_window(ps: pd.DataFrame, seasons: list[str]) -> pd.DataFrame:
    sub = ps[ps["season"].isin(seasons)]
    agg = sub.groupby("player_id").agg(
        position=("position", "last"),
        goals=("goals", "sum"), ixg=("ixg", "sum"), shots=("shots", "sum"),
        games=("games", "sum"), toi_5v5=("toi_5v5", "sum"), pp_toi=("pp_toi", "sum"),
        pk_toi=("pk_toi", "sum"), pen_taken=("pen_taken", "sum"),
        pen_drawn=("pen_drawn", "sum")).reset_index()
    return agg


def compute(agg: pd.DataFrame, impact: pd.DataFrame, gsax: pd.DataFrame,
            window_label: str) -> pd.DataFrame:
    m = agg.merge(impact, on="player_id", how="left")
    k = config.PLAYER_FINISHING_SHRINKAGE_K
    shrink = m["shots"] / (m["shots"] + k)
    m["ev_offense"] = m["off_impact"].fillna(0) * m["toi_5v5"] / 60.0
    m["ev_defense"] = m["def_impact"].fillna(0) * m["toi_5v5"] / 60.0
    m["pp"] = m["pp_impact"].fillna(0) * m["pp_toi"] / 60.0
    m["pk"] = m["pk_impact"].fillna(0) * m["pk_toi"] / 60.0
    m["finishing"] = (m["goals"] - m["ixg"]) * shrink
    m["penalty_diff"] = (m["pen_drawn"] - m["pen_taken"]) * config.PP_GOAL_VALUE
    # goalies
    g = gsax.rename(columns={"gsax": "goalie_gsax"})
    m = m.merge(g, on="player_id", how="left")
    m["goalie_gsax"] = m["goalie_gsax"].fillna(0.0)
    is_goalie = m["position"] == "G"
    for c in ["ev_offense", "ev_defense", "pp", "pk", "finishing"]:
        m.loc[is_goalie, c] = 0.0

    m["total"] = m[COMPONENTS].sum(axis=1)
    # uncertainty: scale RAPM sds by TOI; finishing ~ Poisson(goals) shrunk; others small
    m["ev_offense_sd"] = m["off_sd"].fillna(0) * m["toi_5v5"] / 60.0
    m["ev_defense_sd"] = m["def_sd"].fillna(0) * m["toi_5v5"] / 60.0
    m["pp_sd_c"] = m["pp_sd"].fillna(0) * m["pp_toi"] / 60.0
    m["pk_sd_c"] = m["pk_sd"].fillna(0) * m["pk_toi"] / 60.0
    m["finishing_sd"] = np.sqrt(m["goals"].clip(lower=0)) * shrink
    m["total_sd"] = np.sqrt(m["ev_offense_sd"] ** 2 + m["ev_defense_sd"] ** 2
                            + m["pp_sd_c"] ** 2 + m["pk_sd_c"] ** 2 + m["finishing_sd"] ** 2)
    m["season_window"] = window_label
    return m


OUT_COLS = (["player_id", "season_window", "position", "total", "total_sd"]
            + COMPONENTS + ["ev_offense_sd", "ev_defense_sd", "finishing_sd",
                            "toi_5v5", "pp_toi", "pk_toi", "games"])


def report(df: pd.DataFrame, label: str) -> None:
    names = _names(df["player_id"].tolist())
    top = df[df["toi_5v5"] >= 200].sort_values("total", ascending=False).head(20)
    print(f"\n=== Composite top-20 ({label}) ===")
    for _, r in top.iterrows():
        print(f"  {names.get(r['player_id'], r['player_id']):22s} {r['total']:+6.1f} "
              f"(O {r['ev_offense']:+.1f} D {r['ev_defense']:+.1f} PP {r['pp']:+.1f} "
              f"PK {r['pk']:+.1f} fin {r['finishing']:+.1f}) ±{r['total_sd']:.1f}")


def _names(ids):
    ids = [int(i) for i in ids if pd.notna(i)]
    if not ids:
        return {}
    df = bq.query_df(f"""
        select player_id, any_value(first_name || ' ' || last_name) as name
        from `{bq.project()}.nhl_staging.stg_rosters`
        where player_id in ({", ".join(str(i) for i in ids)}) group by 1""")
    return dict(zip(df["player_id"], df["name"]))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    ps = pull_player_seasons()
    gsx_all = goalie_gsax()
    impact = bq.query_df(f"select * from `{bq.project()}.nhl_models.player_impact`")
    frames = []
    # single seasons
    for s in SINGLE_SEASONS:
        agg = aggregate_window(ps, [s])
        imp = impact[impact["season_window"] == s]
        gsx = gsx_all[gsx_all["season"] == s]
        frames.append(compute(agg, imp, gsx, s))
    # 3-season window
    aggw = aggregate_window(ps, WINDOW)
    impw = impact[impact["season_window"] == WINDOW_LABEL]
    gsxw = gsx_all[gsx_all["season"].isin(WINDOW)].groupby("player_id", as_index=False)["gsax"].sum()
    frames.append(compute(aggw, impw, gsxw, WINDOW_LABEL))

    report(frames[-1], WINDOW_LABEL)
    out = pd.concat(frames, ignore_index=True)[OUT_COLS]
    out["player_id"] = out["player_id"].astype("int64")
    out["model_version"] = "composite_v1"
    if args.dry_run:
        print(f"\n[dry-run] {len(out):,} rows not written")
        return
    bq.write_df(out, "player_composite", write_disposition="WRITE_TRUNCATE",
                clustering_fields=["season_window", "player_id"])
    print(f"\nWrote {len(out):,} rows to nhl_models.player_composite.")


if __name__ == "__main__":
    main()
