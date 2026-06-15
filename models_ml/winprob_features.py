"""
Shared feature engineering for the win-probability model (Phase 2.4).

State backbone is int_segment_context: every segment carries the running score, skater
counts, and goalie counts, and segments tile [0, game_end]. We expand each segment to a
10-second grid so the time feature is smooth while inheriting the segment's game state —
this gives "a row per sampled game-second plus every state change" without a separate
score/strength join.

Features (logistic regression):
  - a 30-bin (regulation seconds remaining) x score-diff[-3..3] one-hot interaction, so the
    value of a lead depends on how much time is left (the key nonlinearity),
  - strength differential (home - away skaters), home/away goalie-pulled flags,
  - in-OT flag and OT seconds remaining,
  - pregame team-strength prior (RATING_SOURCE: interim = season-to-date score-adjusted
    xGF% difference; swapped to the power rating in Phase 3).
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from scipy import sparse
from sklearn.preprocessing import OneHotEncoder

from models_ml import config

TIME_BINS = 30                # regulation seconds-remaining buckets
REG_SECONDS = 3600
OT_END = 3900                 # regular-season 5-min OT period end
SCORE_CLIP = 3

CONTINUOUS = [
    "strength_diff", "home_pulled", "away_pulled",
    "in_ot", "ot_sec_remaining_scaled", "pregame_rating_diff",
]

# Pull is built from int_segment_context (state) + boxscore outcome + season-to-date rating.
PULL_SQL = """
with seg as (
    select c.game_id, c.season, c.home_team_id, c.away_team_id,
        c.segment_start_seconds, c.segment_end_seconds,
        c.home_score, c.away_score, c.home_skaters, c.away_skaters,
        c.home_goalies, c.away_goalies
    from `{project}.nhl_staging.int_segment_context` c
    where 1 = 1 {where}
),
grid as (
    select seg.* except(segment_start_seconds, segment_end_seconds), t as elapsed
    from seg,
         unnest(generate_array(segment_start_seconds,
                               greatest(segment_end_seconds - 1, segment_start_seconds), {step})) t
),
rating as (
    select game_id, team_id,
        avg(xgf_pct_score_adj) over (
            partition by team_id, season order by game_date
            rows between unbounded preceding and 1 preceding) as td
    from `{project}.nhl_mart.mart_team_game_stats`
),
games as (
    select game_id, game_date,
        case when home_team_score > away_team_score then 1 else 0 end as home_won
    from `{project}.nhl_staging.stg_boxscores`
    where game_state in ('OFF', 'FINAL')
)
select
    g.game_id, g.season, gm.game_date, g.elapsed,
    g.home_score, g.away_score, g.home_skaters, g.away_skaters,
    g.home_goalies, g.away_goalies,
    gm.home_won,
    coalesce(rh.td, 0.5) - coalesce(ra.td, 0.5) as pregame_rating_diff
from grid g
join games gm on g.game_id = gm.game_id
left join rating rh on g.game_id = rh.game_id and rh.team_id = g.home_team_id
left join rating ra on g.game_id = ra.game_id and ra.team_id = g.away_team_id
"""


def build_pull_sql(project: str, where: str = "", step: int = 10) -> str:
    return PULL_SQL.format(project=project, where=where, step=step)


def add_state_features(df: pd.DataFrame) -> pd.DataFrame:
    """Derive model state columns from the raw grid pull."""
    out = df.copy()
    for c in ["home_score", "away_score", "home_skaters", "away_skaters",
              "home_goalies", "away_goalies", "elapsed"]:
        out[c] = pd.to_numeric(out[c]).astype("float64")
    out["score_diff"] = (out["home_score"] - out["away_score"]).astype("int64")
    out["strength_diff"] = (out["home_skaters"] - out["away_skaters"]).astype("float64")
    out["home_pulled"] = (out["home_goalies"] == 0).astype("float64")
    out["away_pulled"] = (out["away_goalies"] == 0).astype("float64")
    out["in_ot"] = (out["elapsed"] >= REG_SECONDS).astype("float64")
    out["ot_sec_remaining_scaled"] = np.where(
        out["elapsed"] >= REG_SECONDS, np.maximum(OT_END - out["elapsed"], 0) / 300.0, 0.0)
    out["pregame_rating_diff"] = pd.to_numeric(out["pregame_rating_diff"]).astype("float64")
    if "home_won" in out.columns:
        out["home_won"] = pd.to_numeric(out["home_won"]).astype("int64")
    return _add_interaction_keys(out)


SCORE_LEVELS = 2 * SCORE_CLIP + 1   # 7
INTERACTION_LEVELS = TIME_BINS * SCORE_LEVELS  # 30 x 7 = 210


def _add_interaction_keys(out: pd.DataFrame) -> pd.DataFrame:
    sec_remaining = np.maximum(REG_SECONDS - out["elapsed"], 0)
    bin_width = REG_SECONDS / TIME_BINS
    out["time_bin"] = np.minimum((sec_remaining // bin_width).astype("int64"), TIME_BINS - 1)
    out["score_diff_clip"] = out["score_diff"].clip(-SCORE_CLIP, SCORE_CLIP).astype("int64")
    # single key for the time x score INTERACTION (the key nonlinearity: a lead's value
    # depends on how much time is left)
    out["tb_sd"] = out["time_bin"] * SCORE_LEVELS + (out["score_diff_clip"] + SCORE_CLIP)
    return out


def _encoder() -> OneHotEncoder:
    enc = OneHotEncoder(categories=[list(range(INTERACTION_LEVELS))],
                        sparse_output=True, handle_unknown="ignore")
    enc.fit(np.array(range(INTERACTION_LEVELS)).reshape(-1, 1))
    return enc


_ENC = _encoder()


def make_design(df: pd.DataFrame) -> sparse.csr_matrix:
    """Sparse design matrix: (time_bin x score_diff) interaction one-hot + continuous.
    df must already have add_state_features() columns."""
    onehot = _ENC.transform(df[["tb_sd"]].to_numpy())
    cont = sparse.csr_matrix(np.nan_to_num(df[CONTINUOUS].to_numpy(dtype="float64"), nan=0.0))
    return sparse.hstack([onehot, cont]).tocsr()


def shift_score(df: pd.DataFrame, delta_home: int) -> pd.DataFrame:
    """Return a copy with the home score shifted by delta_home (for leverage): recompute
    score_diff and the interaction keys. delta_home=+1 => one more home goal."""
    out = df.copy()
    out["score_diff"] = out["score_diff"] + delta_home
    return _add_interaction_keys(out)
