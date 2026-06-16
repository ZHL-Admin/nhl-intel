"""
Coach-trust signals (Phase 4.3, blueprint 4.4).

How a coach deploys a player, independent of results — the "eye-test usage" side of the
reconciliation layer. Three signals from the shift/segment layer, z-scored within position and
combined (config.COACH_TRUST_WEIGHTS):

  pk_share          = penalty-kill TOI / total TOI
  protect_lead_rate = TOI in the last 2 minutes of regulation while leading / total TOI
  road_home_ratio   = (road TOI/road GP) / (home TOI/home GP)  -- play them without last change

(The blueprint's DZ-faceoff-start and post-icing signals are omitted: the available
zone_start_code is not team-relative, so a team-relative defensive-zone-start share can't be
computed cleanly from it. Documented in docs/methodology/reconciliation.md.)

Output: nhl_models.player_coach_trust (player_id, season_window, the three raw signals, and
trust_score = weighted sum of within-position z-scores).

Run:  python -m models_ml.compute_coach_trust [--dry-run]
"""

from __future__ import annotations

import argparse

import numpy as np
import pandas as pd

from models_ml import bq, config

SINGLE_SEASONS = ["2021-22", "2022-23", "2023-24", "2024-25", "2025-26"]
WINDOW = ["2023-24", "2024-25", "2025-26"]
WINDOW_LABEL = "2023-24_2025-26"
MIN_TOI = 200  # minutes

PULL_SQL = """
select s.player_id, s.season, any_value(s.position_code) as position,
  sum(s.segment_duration) / 60.0 as total_toi,
  sum(if(s.team_skater_count < (case when s.team_id = c.home_team_id then c.away_skaters
                                     else c.home_skaters end), s.segment_duration, 0)) / 60.0 as pk_toi,
  sum(if(c.segment_start_seconds >= 3480 and c.segment_start_seconds < 3600
         and ((s.team_id = c.home_team_id and c.home_score_state = 'leading')
              or (s.team_id = c.away_team_id and c.home_score_state = 'trailing')),
         s.segment_duration, 0)) / 60.0 as protect_lead_toi,
  sum(if(s.team_id = c.away_team_id, s.segment_duration, 0)) / 60.0 as road_toi,
  sum(if(s.team_id = c.home_team_id, s.segment_duration, 0)) / 60.0 as home_toi,
  count(distinct if(s.team_id = c.away_team_id, s.game_id, null)) as road_gp,
  count(distinct if(s.team_id = c.home_team_id, s.game_id, null)) as home_gp
from `{p}.nhl_staging.int_shift_segments` s
join `{p}.nhl_staging.int_segment_context` c
  on s.game_id = c.game_id and s.segment_index = c.segment_index
where s.is_goalie = 0 and substr(cast(s.game_id as string), 5, 2) in ('02', '03')
  and s.season in ({seasons})
group by 1, 2
"""


# Defensive-zone faceoff deployment. pbp zone_code is owner-relative (D = the faceoff
# winner's defensive zone), so a player is taking a d-zone draw when his team won the draw
# and zone_code='D', or lost it and zone_code='O'. on_ice_for = winner's skaters.
FACEOFF_SQL = """
with fo as (
  select e.game_id, e.on_ice_for, e.on_ice_against, p.zone_code
  from `{p}.nhl_staging.int_on_ice_events` e
  join `{p}.nhl_staging.stg_play_by_play` p
    on e.game_id = p.game_id and e.event_id = p.event_id
  where e.type_desc_key = 'faceoff' and p.zone_code in ('O', 'D', 'N')
    and substr(cast(e.game_id as string), 5, 2) in ('02', '03')
),
g as (select game_id, season from `{p}.nhl_staging.stg_games`
      where season in ({seasons})),
winner as (
  select g.season, pid as player_id, fo.zone_code = 'D' as is_dz
  from fo join g using (game_id), unnest(fo.on_ice_for) as pid
),
loser as (
  select g.season, pid as player_id, fo.zone_code = 'O' as is_dz
  from fo join g using (game_id), unnest(fo.on_ice_against) as pid
)
select player_id, season, count(*) as total_fo, countif(is_dz) as dz_fo
from (select * from winner union all select * from loser)
group by 1, 2
"""


def pull(seasons: list[str]) -> pd.DataFrame:
    df = bq.query_df(PULL_SQL.format(p=bq.project(), seasons=", ".join(f"'{s}'" for s in seasons)))
    for c in ["total_toi", "pk_toi", "protect_lead_toi", "road_toi", "home_toi",
              "road_gp", "home_gp"]:
        df[c] = pd.to_numeric(df[c]).astype("float64")
    fo = bq.query_df(FACEOFF_SQL.format(p=bq.project(), seasons=", ".join(f"'{s}'" for s in seasons)))
    for c in ["total_fo", "dz_fo"]:
        fo[c] = pd.to_numeric(fo[c]).astype("float64")
    return df.merge(fo, on=["player_id", "season"], how="left")


def compute(df: pd.DataFrame, label: str) -> pd.DataFrame:
    # the pull groups by (player, season); for a multi-season window, sum across seasons so
    # there is exactly one row per player.
    df = (df.groupby("player_id")
          .agg(position=("position", "last"),
               total_toi=("total_toi", "sum"), pk_toi=("pk_toi", "sum"),
               protect_lead_toi=("protect_lead_toi", "sum"), road_toi=("road_toi", "sum"),
               home_toi=("home_toi", "sum"), road_gp=("road_gp", "sum"),
               home_gp=("home_gp", "sum"),
               total_fo=("total_fo", "sum"), dz_fo=("dz_fo", "sum"))
          .reset_index())
    df = df[df["total_toi"] >= MIN_TOI].copy()
    df["pos_group"] = np.where(df["position"] == "D", "D", "F")
    df["pk_share"] = df["pk_toi"] / df["total_toi"]
    df["dz_faceoff_share"] = (df["dz_fo"] / df["total_fo"].replace(0, np.nan)).fillna(0.0)
    df["protect_lead_rate"] = df["protect_lead_toi"] / df["total_toi"]
    road_pg = df["road_toi"] / df["road_gp"].replace(0, np.nan)
    home_pg = df["home_toi"] / df["home_gp"].replace(0, np.nan)
    df["road_home_ratio"] = (road_pg / home_pg).clip(0.5, 2.0).fillna(1.0)

    def z(col):
        m = df.groupby("pos_group")[col].transform("mean")
        sd = df.groupby("pos_group")[col].transform("std").replace(0, 1.0)
        return (df[col] - m) / sd

    df["trust_score"] = sum(w * z(sig) for sig, w in config.COACH_TRUST_WEIGHTS.items())
    df["season_window"] = label
    return df


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    frames = [compute(pull([s]), s) for s in SINGLE_SEASONS]
    frames.append(compute(pull(WINDOW), WINDOW_LABEL))
    out = pd.concat(frames, ignore_index=True)

    w = out[out["season_window"] == WINDOW_LABEL]
    names = _names(w["player_id"].tolist())
    print("Most coach-trusted forwards (window):")
    for _, r in w[w.pos_group == "F"].sort_values("trust_score", ascending=False).head(8).iterrows():
        print(f"  {names.get(r['player_id'], r['player_id']):22s} trust {r['trust_score']:+.2f} "
              f"(PK {r['pk_share']:.0%}, DZdraw {r['dz_faceoff_share']:.0%}, "
              f"protectLead {r['protect_lead_rate']:.1%}, road/home {r['road_home_ratio']:.2f})")

    if args.dry_run:
        print(f"\n[dry-run] {len(out):,} rows not written")
        return
    cols = ["player_id", "season_window", "pos_group", "trust_score", "pk_share",
            "dz_faceoff_share", "protect_lead_rate", "road_home_ratio", "total_toi"]
    out = out[cols].copy()
    out["player_id"] = out["player_id"].astype("int64")
    out["model_version"] = "coach_trust_v1"
    bq.write_df(out, "player_coach_trust", write_disposition="WRITE_TRUNCATE",
                clustering_fields=["season_window", "player_id"])
    print(f"\nWrote {len(out):,} rows to nhl_models.player_coach_trust.")


def _names(ids):
    ids = [int(i) for i in ids]
    if not ids:
        return {}
    df = bq.query_df(f"""select player_id, any_value(first_name||' '||last_name) as name
                         from `{bq.project()}.nhl_staging.stg_rosters`
                         where player_id in ({", ".join(str(i) for i in ids)}) group by 1""")
    return dict(zip(df["player_id"], df["name"]))


if __name__ == "__main__":
    main()
