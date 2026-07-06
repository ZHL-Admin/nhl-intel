"""
Value: Goals/Wins Above Replacement (GAR/WAR) — the goals-REALITY companion to RAPM impact.

RAPM (`nhl_models.player_impact`) measures repeatable play-driving on the xG layer and is
UNTOUCHED by this job. GAR measures ACTUAL goals contributed above a freely-available
replacement player, across all situations, on the goals scale. It therefore inherits shooting
luck BY DESIGN — a labeled feature: GAR = "what happened", RAPM = "what tends to repeat". The
gap between the two (finishing / luck / usage) is the intended product insight.

Components (per player-season-window, on the goals scale):
  ev_offense  ACTUAL 5v5 (goals + 0.7*primary + 0.5*secondary assists) per-60 above the
              replacement 5v5 rate, x 5v5 TOI/60.  <- fully goals-based; finishing lives here.
  pp          ACTUAL PP (goals + assists) per-60 above replacement, x PP TOI/60.
  ev_defense  RAPM def_impact (xGF/60) above the replacement def level, x 5v5 TOI/60.  <- xG-BORROWED
  pk          RAPM pk_impact above the replacement PK level, x PK TOI/60.              <- xG-BORROWED
  penalty     (drawn - taken) x PENALTY_VALUE_GOALS.
  faceoff     centers only: net faceoff wins x FACEOFF_VALUE_GOALS.
So the OFFENSIVE side (where the finishing question lives) is fully actual goals; the DEFENSIVE
side borrows RAPM — GAR is "mostly actual", documented in docs/methodology/value-gar.md.

GAR = sum(components); WAR = GAR / GOALS_PER_WIN. Output nhl_models.player_gar.
Run:  python -m models_ml.compute_gar [--dry-run]
"""

from __future__ import annotations

import argparse

import numpy as np
import pandas as pd

from models_ml import bq, config

CFG = config.GAR_CONFIG
SINGLE_SEASONS = ["2021-22", "2022-23", "2023-24", "2024-25", "2025-26"]
WINDOW = ["2023-24", "2024-25", "2025-26"]
WINDOW_LABEL = "2023-24_2025-26"
COMPONENTS = ["ev_offense", "pp", "ev_defense", "pk", "penalty", "faceoff"]
PA = CFG["PRIMARY_ASSIST_VALUE"]
SA = CFG["SECONDARY_ASSIST_VALUE"]

# Per (player, season): actual 5v5/PP production (goals + weighted assists, from pbp goal
# events classified by situation_code), strength TOI (from segments), penalties (pbp),
# faceoffs (mart), plus ixG/shots/games (mart) for the gap context. game types 02/03 only
# (excludes preseason + 2026 Olympic/4-Nations national-team games).
PLAYER_SEASON_SQL = """
with goal_events as (
  select pbp.season,
         pbp.event_owner_team_id as team_id,
         pbp.situation_code as sc,
         bx.home_team_id, bx.away_team_id,
         pbp.scoring_player_id, pbp.assist1_player_id, pbp.assist2_player_id
  from `{p}.nhl_staging.stg_play_by_play` pbp
  join `{p}.nhl_staging.stg_boxscores` bx on pbp.game_id = bx.game_id
  where pbp.type_desc_key = 'goal'
    and substr(cast(pbp.game_id as string), 5, 2) in ('02', '03')
),
strength_events as (
  select season, scoring_player_id, assist1_player_id, assist2_player_id,
    case
      when sc = '1551' then '5v5'
      when (team_id = home_team_id and cast(substr(sc, 3, 1) as int64) > cast(substr(sc, 2, 1) as int64))
        or (team_id = away_team_id and cast(substr(sc, 2, 1) as int64) > cast(substr(sc, 3, 1) as int64))
        then 'pp'
      else 'other'
    end as strength
  from goal_events
),
roles as (
  select season, strength, scoring_player_id as player_id, 1.0 as g, 0.0 as pa, 0.0 as sa
  from strength_events where scoring_player_id is not null
  union all
  select season, strength, assist1_player_id, 0.0, 1.0, 0.0
  from strength_events where assist1_player_id is not null
  union all
  select season, strength, assist2_player_id, 0.0, 0.0, 1.0
  from strength_events where assist2_player_id is not null
),
prod as (
  select player_id, season,
    sum(if(strength = '5v5', g, 0)) as g5, sum(if(strength = '5v5', pa, 0)) as pa5,
    sum(if(strength = '5v5', sa, 0)) as sa5,
    sum(if(strength = 'pp', g, 0)) as gpp, sum(if(strength = 'pp', pa, 0)) as papp,
    sum(if(strength = 'pp', sa, 0)) as sapp
  from roles group by 1, 2
),
pg as (
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
  select player_id, season, sum(taken) as pen_taken, sum(drawn) as pen_drawn from (
    select committed_by_player_id as player_id, season, count(*) as taken, 0 as drawn
    from `{p}.nhl_staging.stg_play_by_play`
    where type_desc_key = 'penalty' and committed_by_player_id is not null group by 1, 2
    union all
    select drawn_by_player_id, season, 0, count(*)
    from `{p}.nhl_staging.stg_play_by_play`
    where type_desc_key = 'penalty' and drawn_by_player_id is not null group by 1, 2
  ) group by 1, 2
),
fo as (
  select player_id,
    concat(substr(cast(season_id as string), 1, 4), '-', substr(cast(season_id as string), 7, 2)) as season,
    sum(total_faceoff_wins) - sum(total_faceoff_losses) as fo_net
  from `{p}.nhl_mart.mart_player_faceoff_zones`
  where game_type in (2, 3)
  group by 1, 2
)
select pg.player_id, pg.season, pg.position, pg.goals, pg.ixg, pg.shots, pg.games,
       coalesce(prod.g5, 0) as g5, coalesce(prod.pa5, 0) as pa5, coalesce(prod.sa5, 0) as sa5,
       coalesce(prod.gpp, 0) as gpp, coalesce(prod.papp, 0) as papp, coalesce(prod.sapp, 0) as sapp,
       coalesce(toi.toi_5v5, 0) as toi_5v5, coalesce(toi.pp_toi, 0) as pp_toi,
       coalesce(toi.pk_toi, 0) as pk_toi,
       coalesce(pen.pen_taken, 0) as pen_taken, coalesce(pen.pen_drawn, 0) as pen_drawn,
       coalesce(fo.fo_net, 0) as fo_net
from pg
left join prod on pg.player_id = prod.player_id and pg.season = prod.season
left join toi on pg.player_id = toi.player_id and pg.season = toi.season
left join pen on pg.player_id = pen.player_id and pg.season = pen.season
left join fo on pg.player_id = fo.player_id and pg.season = fo.season
"""

# Per (player, season): the player's best (lowest) 5v5-TOI rank on any team he dressed for.
# Drives the replacement pool (depth players: F ranked > 9, D ranked > 6 on their team).
DEPTH_SQL = """
with team_toi as (
  select s.player_id, s.season, s.team_id,
         sum(if(c.strength_state = '5v5', s.segment_duration, 0)) / 60.0 as toi_5v5,
         any_value(s.position_code) as position
  from `{p}.nhl_staging.int_shift_segments` s
  join `{p}.nhl_staging.int_segment_context` c
    on s.game_id = c.game_id and s.segment_index = c.segment_index
  where s.is_goalie = 0
  group by 1, 2, 3
),
ranked as (
  select player_id, season, position, toi_5v5,
         row_number() over (partition by team_id, season,
           case when position = 'D' then 'D' else 'F' end
           order by toi_5v5 desc) as team_rank
  from team_toi
)
select player_id, season, min(team_rank) as best_rank from ranked group by 1, 2
"""

NUM = ["goals", "ixg", "shots", "games", "g5", "pa5", "sa5", "gpp", "papp", "sapp",
       "toi_5v5", "pp_toi", "pk_toi", "pen_taken", "pen_drawn", "fo_net"]


def pull() -> tuple[pd.DataFrame, pd.DataFrame]:
    ps = bq.query_df(PLAYER_SEASON_SQL.format(p=bq.project()))
    for c in NUM:
        ps[c] = pd.to_numeric(ps[c]).astype("float64")
    depth = bq.query_df(DEPTH_SQL.format(p=bq.project()))
    depth["best_rank"] = pd.to_numeric(depth["best_rank"]).astype("float64")
    return ps, depth


def aggregate_window(ps: pd.DataFrame, depth: pd.DataFrame, seasons: list[str]) -> pd.DataFrame:
    sub = ps[ps["season"].isin(seasons)]
    agg = sub.groupby("player_id").agg(
        position=("position", "last"),
        **{c: (c, "sum") for c in NUM}).reset_index()
    # depth rank for the window = best (lowest) team rank across the window's seasons
    d = depth[depth["season"].isin(seasons)].groupby("player_id")["best_rank"].min().reset_index()
    return agg.merge(d, on="player_id", how="left")


def _pos_group(pos: pd.Series) -> pd.Series:
    return np.where(pos == "D", "D", "F")


def compute(agg: pd.DataFrame, impact: pd.DataFrame, window_label: str) -> pd.DataFrame:
    m = agg.merge(impact[["player_id", "def_impact", "def_sd", "pk_impact", "pk_sd"]],
                  on="player_id", how="left")
    m["pos_group"] = _pos_group(m["position"])
    is_skater = m["position"].isin(["C", "L", "R", "D"])

    # per-60 production rates (actual goals + weighted assists)
    m["ev_off_per60"] = np.where(m["toi_5v5"] > 0,
        (m["g5"] + PA * m["pa5"] + SA * m["sa5"]) / (m["toi_5v5"] / 60.0), 0.0)
    m["pp_per60"] = np.where(m["pp_toi"] > 0,
        (m["gpp"] + PA * m["papp"] + SA * m["sapp"]) / (m["pp_toi"] / 60.0), 0.0)
    m["def_impact"] = m["def_impact"].fillna(0.0)
    m["pk_impact"] = m["pk_impact"].fillna(0.0)

    # The assist values (0.7 / 0.5) are RELATIVE weights. Summing goals + weighted assists
    # credits ~2.2 units per goal (scorer + two assisters), which would inflate offensive GAR.
    # Normalize so total offensive credit ties to ACTUAL goals scored: scale = league goals /
    # league weighted-credit, per strength. This makes ev_offense/pp read as "goals' worth of
    # actual scoring involvement above replacement" — fully goals-based, no triple-count.
    sk = m[is_skater]
    ev_credit = (sk["g5"] + PA * sk["pa5"] + SA * sk["sa5"]).sum()
    pp_credit = (sk["gpp"] + PA * sk["papp"] + SA * sk["sapp"]).sum()
    ev_scale = float(sk["g5"].sum() / ev_credit) if ev_credit > 0 else 1.0
    pp_scale = float(sk["gpp"].sum() / pp_credit) if pp_credit > 0 else 1.0

    # replacement pool: depth skaters (F rank > threshold, D rank > threshold) with enough TOI
    fr, dr = CFG["REPLACEMENT_DEPTH_RANK"]["F"], CFG["REPLACEMENT_DEPTH_RANK"]["D"]
    depth_rank = np.where(m["pos_group"] == "D", dr, fr)
    is_repl = is_skater & (m["best_rank"] > depth_rank) & (m["toi_5v5"] >= CFG["REPLACEMENT_MIN_TOI_5V5"])
    m["is_replacement"] = is_repl

    repl = {}
    for grp in ["F", "D"]:
        pool = m[is_repl & (m["pos_group"] == grp)]
        if len(pool) < CFG["REPLACEMENT_MIN_POOL"]:
            pool = m[is_skater & (m["pos_group"] == grp) & (m["best_rank"] > (dr if grp == "D" else fr))]
        # TOI-weighted means so a 60-min call-up doesn't dominate
        def w(col, wt):
            x, weights = pool[col], pool[wt]
            return float(np.average(x, weights=weights)) if weights.sum() > 0 else 0.0
        repl[grp] = {
            "ev_off": w("ev_off_per60", "toi_5v5"),
            "pp": w("pp_per60", "pp_toi") if pool["pp_toi"].sum() > 0 else 0.0,
            "def": w("def_impact", "toi_5v5"),
            "pk": w("pk_impact", "pk_toi") if pool["pk_toi"].sum() > 0 else 0.0,
        }
    rg = m["pos_group"].map(lambda g: repl[g])
    m["repl_ev_off"] = [r["ev_off"] for r in rg]
    m["repl_pp"] = [r["pp"] for r in rg]
    m["repl_def"] = [r["def"] for r in rg]
    m["repl_pk"] = [r["pk"] for r in rg]

    # components (goals above replacement, scaled by the player's TOI in that state)
    m["ev_offense"] = (m["ev_off_per60"] - m["repl_ev_off"]) * (m["toi_5v5"] / 60.0) * ev_scale
    m["pp"] = (m["pp_per60"] - m["repl_pp"]) * (m["pp_toi"] / 60.0) * pp_scale
    m["ev_defense"] = (m["def_impact"] - m["repl_def"]) * (m["toi_5v5"] / 60.0)
    m["pk"] = (m["pk_impact"] - m["repl_pk"]) * (m["pk_toi"] / 60.0)
    m["penalty"] = (m["pen_drawn"] - m["pen_taken"]) * CFG["PENALTY_VALUE_GOALS"]
    m["faceoff"] = np.where(m["position"] == "C", m["fo_net"] * CFG["FACEOFF_VALUE_GOALS"], 0.0)

    for c in COMPONENTS:
        m.loc[~is_skater, c] = 0.0
    m["gar"] = m[COMPONENTS].sum(axis=1)
    m["war"] = m["gar"] / CFG["GOALS_PER_WIN"]

    # uncertainty band: EV-defense + PK borrow RAPM sd (scaled by TOI); EV-offense carries a
    # shooting-variance term (binomial on goals given shot volume, converted to goals).
    def_sd = m["def_sd"].fillna(0.0) * (m["toi_5v5"] / 60.0)
    pk_sd = m["pk_sd"].fillna(0.0) * (m["pk_toi"] / 60.0)
    shoot_sd = np.sqrt((m["g5"] + m["gpp"]).clip(lower=0)) * ev_scale   # ~Poisson on actual goals
    m["gar_sd"] = np.sqrt(def_sd ** 2 + pk_sd ** 2 + shoot_sd ** 2)
    m["war_sd"] = m["gar_sd"] / CFG["GOALS_PER_WIN"]

    m["season_window"] = window_label
    m["repl_level_meta"] = (f"depth>F{fr}/D{dr}, min{CFG['REPLACEMENT_MIN_TOI_5V5']:.0f}m5v5, "
                            f"poolF={int(is_repl[m['pos_group']=='F'].sum())} "
                            f"poolD={int(is_repl[m['pos_group']=='D'].sum())}, "
                            f"evScale={ev_scale:.3f} ppScale={pp_scale:.3f}")
    return m[m["position"].isin(["C", "L", "R", "D"])].copy()


OUT_COLS = (["player_id", "season_window", "position", "gar", "war", "gar_sd", "war_sd"]
            + COMPONENTS + ["toi_5v5", "pp_toi", "pk_toi", "games", "goals", "ixg",
                            "is_replacement", "repl_level_meta"])


def _names(ids):
    ids = [int(i) for i in ids if pd.notna(i)]
    if not ids:
        return {}
    df = bq.query_df(f"""
        select player_id, any_value(first_name || ' ' || last_name) as name
        from `{bq.project()}.nhl_staging.stg_rosters`
        where player_id in ({", ".join(str(i) for i in ids)}) group by 1""")
    return dict(zip(df["player_id"], df["name"]))


def report(df: pd.DataFrame, label: str) -> None:
    names = _names(df["player_id"].tolist())
    floor = CFG["MIN_TOI_5V5_FOR_RANKING"]
    top = df[df["toi_5v5"] >= floor].sort_values("gar", ascending=False).head(25)
    print(f"\n=== GAR top-25 ({label}) ===")
    for i, (_, r) in enumerate(top.iterrows(), 1):
        print(f"  {i:2d}. {names.get(r['player_id'], r['player_id']):22s} GAR {r['gar']:+6.1f} "
              f"WAR {r['war']:+4.1f}  (EVo {r['ev_offense']:+.1f} PP {r['pp']:+.1f} "
              f"EVd {r['ev_defense']:+.1f} PK {r['pk']:+.1f}) ±{r['gar_sd']:.1f}")


def _append_gar(out: pd.DataFrame, seasons: list[str]) -> None:
    """Append-only backfill: delete ONLY the listed season_windows (never existing rows), then
    WRITE_APPEND. Idempotent; never touches the 3yr window or other seasons."""
    if set(out["season_window"]) - set(seasons):
        raise ValueError("_append_gar refuses: rows contain a season_window outside --seasons.")
    cli = bq.client()
    tid = f"{bq.project()}.{config.MODELS_DATASET}.player_gar"
    inlist = ", ".join(f"'{s}'" for s in seasons)
    cli.query(f"DELETE FROM `{tid}` WHERE season_window IN ({inlist})").result()
    bq.write_df(out, "player_gar", write_disposition="WRITE_APPEND",
                clustering_fields=["season_window", "player_id"])
    print(f"\nAppended {len(out):,} rows for {seasons} to nhl_models.player_gar (existing untouched).")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--seasons", default=None,
                    help="comma-separated single seasons to BACKFILL (append-only). Does NOT touch "
                         "the 3yr window or existing rows. Run the RAPM backfill first.")
    args = ap.parse_args()

    ps, depth = pull()
    impact = bq.query_df(f"select * from `{bq.project()}.nhl_models.player_impact`")

    if args.seasons:
        seasons = [s.strip() for s in args.seasons.split(",") if s.strip()]
        frames = [compute(aggregate_window(ps, depth, [s]),
                          impact[impact["season_window"] == s], s) for s in seasons]
        out = pd.concat(frames, ignore_index=True)[OUT_COLS]
        out["player_id"] = out["player_id"].astype("int64")
        out["model_version"] = "gar_v1"
        report(frames[-1], seasons[-1])
        if args.dry_run:
            print(f"\n[dry-run] {len(out):,} rows for {seasons} not written")
            return
        _append_gar(out, seasons)
        return

    frames = []
    for s in SINGLE_SEASONS:
        agg = aggregate_window(ps, depth, [s])
        frames.append(compute(agg, impact[impact["season_window"] == s], s))
    aggw = aggregate_window(ps, depth, WINDOW)
    frames.append(compute(aggw, impact[impact["season_window"] == WINDOW_LABEL], WINDOW_LABEL))

    report(frames[-1], WINDOW_LABEL)
    report(frames[SINGLE_SEASONS.index("2025-26")], "2025-26")
    out = pd.concat(frames, ignore_index=True)[OUT_COLS]
    out["player_id"] = out["player_id"].astype("int64")
    out["model_version"] = "gar_v1"
    if args.dry_run:
        print(f"\n[dry-run] {len(out):,} rows not written")
        return
    bq.write_df(out, "player_gar", write_disposition="WRITE_TRUNCATE",
                clustering_fields=["season_window", "player_id"])
    print(f"\nWrote {len(out):,} rows to nhl_models.player_gar.")


if __name__ == "__main__":
    main()
