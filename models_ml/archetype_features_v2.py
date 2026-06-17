"""
Enriched archetype feature vector for the v2 refit (supersedes the v1 vector).

v1 clustered on offense/sequence/shot-location/PP/penalty/deployment/Edge features. Defense was
present only as RAPM def_impact (low variance), so it barely separated clusters — defensive roles
were a display afterthought, not a classification driver. v2 ADDS the stronger defensive/style
signals that postdate v1 and were never used to classify:

  - coach-trust composite + its 4 components (PK role, DZ-faceoff-start share, lead-protection
    usage, road/home matchup usage) from nhl_models.player_coach_trust
  - rink-adjusted hits /60 (mart_player_game_stats.hits_adj — NEVER raw hits)
  - penalty differential (drawn - taken) /60 (stg_play_by_play drawn/committed_by)
  - on-ice xGA /60 at 5v5 (defensive suppression; computed from the attribution backbone
    int_on_ice_events x shot_xg — there is no stored on-ice-xGA column)

These all exist only for the tracking era (2021-22+, same window as player_coach_trust /
player_impact / Edge), which is the v2 fit cohort; pre-2021 seasons get the reduced-feature
historical projection (as in v1). Built on top of archetype_features.build() so the v1 features
are unchanged.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from models_ml import archetype_features, bq

# v1 features (reused verbatim) + the v2 enrichments. label is for the trait audit / report.
EXTRA_FEATURES_V2 = {
    "coach_trust": "coach-trust composite (deployment)",
    "ct_pk_share": "PK deployment share",
    "ct_dz_faceoff_share": "DZ faceoff-start share",
    "ct_protect_lead_rate": "lead-protection usage",
    "ct_road_home_ratio": "road/home matchup usage",
    "hits_adj_per60": "rink-adjusted hits /60",
    "pen_diff_per60": "penalty differential (drawn-taken) /60",
    "onice_xga_per60": "on-ice xGA /60 at 5v5 (suppression)",
}
FEATURES_V2 = {**archetype_features.FEATURES, **EXTRA_FEATURES_V2}

# on-ice 5v5 xGA per (player, season) from the attribution backbone (no stored column)
_ONICE_XGA_SQL = """
with seg5 as (
  select game_id, segment_index, season from `{p}.nhl_staging.int_segment_context`
  where strength_state = '5v5'
),
segp as (
  select s.game_id, s.segment_index, s.season, s.team_id, s.player_id
  from `{p}.nhl_staging.int_shift_segments` s
  join seg5 using (game_id, segment_index)
  where s.is_goalie = 0 and substr(cast(s.game_id as string), 5, 2) in ('02', '03')
),
segx as (
  select o.game_id, o.segment_index, o.event_owner_team_id as team_id, sum(x.xg) as xg
  from `{p}.nhl_staging.int_on_ice_events` o
  join `{p}.nhl_models.shot_xg` x on o.game_id = x.game_id and o.event_id = x.event_id
  group by 1, 2, 3
),
segtot as (select game_id, segment_index, sum(xg) as tot from segx group by 1, 2)
select segp.player_id, segp.season,
  sum(coalesce(st.tot, 0) - coalesce(sx.xg, 0)) as onice_xga
from segp
left join segx sx on sx.game_id = segp.game_id and sx.segment_index = segp.segment_index
  and sx.team_id = segp.team_id
left join segtot st on st.game_id = segp.game_id and st.segment_index = segp.segment_index
group by 1, 2
"""

_PEN_SQL = """
with drawn as (
  select drawn_by_player_id as player_id, season, count(*) as n
  from `{p}.nhl_staging.stg_play_by_play`
  where type_desc_key = 'penalty' and drawn_by_player_id is not null
    and substr(cast(game_id as string), 5, 2) in ('02', '03')
  group by 1, 2
),
taken as (
  select committed_by_player_id as player_id, season, count(*) as n
  from `{p}.nhl_staging.stg_play_by_play`
  where type_desc_key = 'penalty' and committed_by_player_id is not null
    and substr(cast(game_id as string), 5, 2) in ('02', '03')
  group by 1, 2
)
select coalesce(d.player_id, t.player_id) as player_id,
       coalesce(d.season, t.season) as season,
       coalesce(d.n, 0) as drawn, coalesce(t.n, 0) as taken
from drawn d full outer join taken t using (player_id, season)
"""

_HITS_SQL = """
select player_id, season, sum(hits_adj) as hits_adj
from `{p}.nhl_mart.mart_player_game_stats`
where substr(cast(game_id as string), 5, 2) in ('02', '03')
group by 1, 2
"""


def build_v2(seasons: list[str], min_5v5: float | None = None) -> pd.DataFrame:
    """v1 features + the v2 defensive/style enrichments, imputed within position group."""
    df = archetype_features.build(seasons, min_5v5=min_5v5).copy()
    p = bq.project()
    qs = ", ".join(f"'{s}'" for s in seasons)

    trust = bq.query_df(f"""select player_id, season_window as season, trust_score as coach_trust,
        pk_share as ct_pk_share, dz_faceoff_share as ct_dz_faceoff_share,
        protect_lead_rate as ct_protect_lead_rate, road_home_ratio as ct_road_home_ratio
        from `{p}.nhl_models.player_coach_trust` where season_window in ({qs})""")
    hits = bq.query_df(_HITS_SQL.format(p=p))
    pen = bq.query_df(_PEN_SQL.format(p=p))
    xga = bq.query_df(_ONICE_XGA_SQL.format(p=p))

    df = df.merge(trust, on=["player_id", "season"], how="left")
    df = df.merge(hits, on=["player_id", "season"], how="left")
    df = df.merge(pen, on=["player_id", "season"], how="left")
    df = df.merge(xga, on=["player_id", "season"], how="left")

    total_toi = (df["toi_5v5"].fillna(0) + df["pp_toi"].fillna(0) + df["pk_toi"].fillna(0))
    total_toi = total_toi.replace(0, np.nan)
    df["hits_adj_per60"] = pd.to_numeric(df["hits_adj"], errors="coerce") / total_toi * 60.0
    df["pen_diff_per60"] = ((pd.to_numeric(df["drawn"], errors="coerce").fillna(0)
                             - pd.to_numeric(df["taken"], errors="coerce").fillna(0))
                            / total_toi * 60.0)
    df["onice_xga_per60"] = (pd.to_numeric(df["onice_xga"], errors="coerce")
                             / df["toi_5v5"].replace(0, np.nan) * 60.0)
    for c in ["coach_trust", "ct_pk_share", "ct_dz_faceoff_share", "ct_protect_lead_rate",
              "ct_road_home_ratio"]:
        df[c] = pd.to_numeric(df[c], errors="coerce")

    # impute every v2-extra feature within position group, then global mean (matches v1's policy
    # for the v1 features, which build() already imputed)
    for f in EXTRA_FEATURES_V2:
        df[f] = df.groupby("pos_group")[f].transform(lambda s: s.fillna(s.mean()))
        df[f] = df[f].fillna(df[f].mean())
    return df
