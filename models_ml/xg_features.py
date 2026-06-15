"""
Shared feature engineering for the in-house xG model (Phase 2.2).

Both train_xg.py and score_xg.py import this so training and scoring see identical
features. One unblocked, non-empty-net, non-shootout shot per row. Blocked shots are
excluded upstream (their coords are the block location, not the shot).

Decomposition buckets group the model's features so per-shot pred_contrib can be rolled
up into named, product-facing pieces (location / shot_type / strength / sequence /
game_state). The bucket order is also the order contributions are applied in prob space.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

NET_X = 89.0  # goal line x in standard NHL coords (shots normalised to attack |x|=89)

SHOT_TYPES = ["wrist", "slap", "snap", "backhand", "tip-in", "deflected", "wrap-around", "other"]
STRENGTHS = ["5v5", "PP", "SH", "other"]

# Feature buckets -> ordered list of model feature columns. The dict order is the order
# contributions are sequentially applied to the base rate in probability space.
FEATURE_BUCKETS: dict[str, list[str]] = {
    "location": ["distance", "angle"],
    "shot_type": ["shot_type_clean"],
    "strength": ["strength"],
    "sequence": [
        "seq_rebound", "seq_rush", "seq_forecheck", "seq_cross_ice",
        "time_since_faceoff", "time_since_turnover",
    ],
    "game_state": ["period_number", "shooter_is_home", "score_diff"],
}

CATEGORICAL = ["shot_type_clean", "strength"]


def feature_columns() -> list[str]:
    cols: list[str] = []
    for feats in FEATURE_BUCKETS.values():
        cols.extend(feats)
    return cols


# The pull. {where} is injected (season filter for training, --since for scoring). Running
# pre-shot score is computed over the FULL play-by-play (so empty-net goals still move the
# score) and joined back to the unblocked, non-EN, non-SO shots from int_shot_sequence.
PULL_SQL = """
with running as (
    select
        game_id,
        sort_order,
        coalesce(last_value(home_score ignore nulls) over w, 0) as home_score_pre,
        coalesce(last_value(away_score ignore nulls) over w, 0) as away_score_pre
    from `{project}.nhl_staging.stg_play_by_play`
    window w as (
        partition by game_id order by sort_order
        rows between unbounded preceding and 1 preceding
    )
)
select
    iss.game_id,
    iss.season,
    iss.game_date,
    iss.event_id,
    iss.team_id,
    iss.period_number,
    iss.strength,
    iss.x_coord,
    iss.y_coord,
    cast(iss.is_goal as int64) as is_goal,
    cast(iss.seq_rebound as int64) as seq_rebound,
    cast(iss.seq_rush as int64) as seq_rush,
    cast(iss.seq_forecheck as int64) as seq_forecheck,
    cast(iss.seq_cross_ice as int64) as seq_cross_ice,
    iss.time_since_faceoff,
    iss.time_since_turnover,
    pbp.shot_type,
    cast(iss.team_id = b.home_team_id as int64) as shooter_is_home,
    r.home_score_pre,
    r.away_score_pre
from `{project}.nhl_staging.int_shot_sequence` iss
join `{project}.nhl_staging.stg_play_by_play` pbp
    on iss.game_id = pbp.game_id and iss.event_id = pbp.event_id
join `{project}.nhl_staging.stg_boxscores` b
    on iss.game_id = b.game_id
join running r
    on iss.game_id = r.game_id and iss.sort_order = r.sort_order
where iss.is_empty_net = false
  and pbp.period_type != 'SO'
  and iss.x_coord is not null and iss.y_coord is not null
  {where}
"""


def build_pull_sql(project: str, where: str = "") -> str:
    return PULL_SQL.format(project=project, where=where)


def build_features(df: pd.DataFrame) -> pd.DataFrame:
    """Add the derived model columns to a raw pull. Returns the same frame with feature
    columns present and categoricals typed; callers select feature_columns()."""
    out = df.copy()

    # location: normalise to the |x|=89 net, distance + absolute angle from goal centre
    abs_x = out["x_coord"].abs()
    dx = NET_X - abs_x
    abs_y = out["y_coord"].abs()
    out["distance"] = np.sqrt(dx**2 + out["y_coord"].astype(float) ** 2)
    out["angle"] = np.degrees(np.arctan2(abs_y, dx))

    # game state
    out["score_diff"] = np.where(
        out["shooter_is_home"] == 1,
        out["home_score_pre"] - out["away_score_pre"],
        out["away_score_pre"] - out["home_score_pre"],
    )
    out["score_diff"] = out["score_diff"].clip(-3, 3).astype("int64")

    # categoricals
    out["shot_type_clean"] = (
        out["shot_type"].where(out["shot_type"].isin(SHOT_TYPES[:-1]), "other")
        .astype(pd.CategoricalDtype(categories=SHOT_TYPES))
    )
    out["strength"] = out["strength"].astype(pd.CategoricalDtype(categories=STRENGTHS))

    # Coerce all non-categorical feature columns to plain float64 numpy (BigQuery returns
    # nullable Int64/Float64 arrays that LightGBM rejects); NaNs are kept for timing.
    for c in feature_columns():
        if c not in CATEGORICAL:
            out[c] = pd.to_numeric(out[c], errors="coerce").astype("float64")

    # label as plain int (no nulls)
    if "is_goal" in out.columns:
        out["is_goal"] = pd.to_numeric(out["is_goal"]).astype("int64")

    return out


def feature_frame(df_feat: pd.DataFrame) -> pd.DataFrame:
    """Select just the model feature columns, in canonical order."""
    return df_feat[feature_columns()]
