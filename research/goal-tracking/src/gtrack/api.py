"""gtrack.api — typed, read-only accessors over the fused goal corpus (Stage 0.5).

THE TWO LAWS govern every use of this data:

LAW 1 · GOALS-ONLY. Every tracked sequence ended in a goal; there is no tracked non-goal in this data.
You may DESCRIBE and ATTRIBUTE what happened on goals and build goal-as-the-unit measurements. You may
NEVER make a predictive or comparative "what causes goals / what wins" claim from this data alone.

LAW 2 · FUSION. Tracking is faithful on position (scorer within stick-reach 88% in validation) and weak
on exact stick attribution in traffic (38%). Attribution NEVER comes from geometry alone: the recorded
scorer/assisters from stg_play_by_play are the anchor; tracking supplies context around those labels.
Cluster-level credit is acceptable; deflection micro-mechanics may remain fuzzy and are labeled as such.

All accessors return polars DataFrames. Data is read from data/parquet (built by Stage 0.2/0.3); nothing
here touches BigQuery or production.
"""
from __future__ import annotations

from functools import lru_cache

import polars as pl

from . import config, fuse, quality

LAW_1 = config.LAW_1
LAW_2 = config.LAW_2


@lru_cache(maxsize=1)
def _goals() -> pl.DataFrame:
    return quality.score_frame(pl.read_parquet(fuse.FUSED))


@lru_cache(maxsize=1)
def _events() -> pl.DataFrame:
    return pl.read_parquet(fuse.EVENTS)


def _apply_quality(df: pl.DataFrame, clean_only: bool, min_quality: float | None) -> pl.DataFrame:
    if clean_only:
        df = df.filter(pl.col("is_clean"))
    if min_quality is not None:
        df = df.filter(pl.col("quality_score") >= min_quality)
    return df


def goal(game_id: int, event_id: int) -> dict:
    """Return one goal's full fused row + its reconstructed events.

    LAW 1 · GOALS-ONLY: this row exists because the sequence ended in a goal; describe/attribute only,
    never infer "what causes goals" from goal-only data. LAW 2 · FUSION: scorer_id/assist*_id/goalie_id
    are the stg_play_by_play anchor; reconstructed carriers, passes and geometry are descriptive context
    around those labels and may be fuzzy in traffic.

    >>> g = goal(2023020097, 119)
    >>> g["fused"]["scorer_id"], g["fused"]["entry_type"]        # doctest: +SKIP
    (8475760, 'carried')
    >>> [e["event_type"] for e in g["events"]][:3]               # doctest: +SKIP
    ['segment', 'segment', 'pass']
    """
    fused = _goals().filter((pl.col("game_id") == game_id) & (pl.col("event_id") == event_id))
    ev = _events().filter((pl.col("game_id") == game_id) & (pl.col("event_id") == event_id))
    if fused.height == 0:
        raise KeyError(f"goal {game_id}-{event_id} not in the fused corpus")
    return {"fused": fused.row(0, named=True), "events": ev.to_dicts()}


def goals(season: str | None = None, team: int | None = None,
          clean_only: bool = False, min_quality: float | None = None) -> pl.DataFrame:
    """Fused goals, optionally filtered by season / team (scoring or conceding) / clip quality.

    >>> goals(season="2024-25", clean_only=True).height          # doctest: +SKIP
    3xxx
    """
    df = _goals()
    if season is not None:
        df = df.filter(pl.col("season") == season)
    if team is not None:
        df = df.filter((pl.col("home_team_id") == team) | (pl.col("away_team_id") == team))
    return _apply_quality(df, clean_only, min_quality)


def player_goals(player_id: int, involvement: str = "any") -> pl.DataFrame:
    """Goals a player was credited on. involvement in {scorer, assister, any} (stg_play_by_play labels)."""
    df = _goals()
    if involvement == "scorer":
        f = pl.col("scorer_id") == player_id
    elif involvement == "assister":
        f = (pl.col("assist1_id") == player_id) | (pl.col("assist2_id") == player_id)
    elif involvement == "any":
        f = ((pl.col("scorer_id") == player_id) | (pl.col("assist1_id") == player_id)
             | (pl.col("assist2_id") == player_id))
    else:
        raise ValueError("involvement must be one of {scorer, assister, any}")
    return df.filter(f)


def goalie_goals_against(goalie_id: int) -> pl.DataFrame:
    """Goals conceded with this goalie in net (stg_play_by_play goalie_in_net_id)."""
    return _goals().filter(pl.col("goalie_id") == goalie_id)


def team_goals(team_id: int, season: str | None = None, side: str = "for") -> pl.DataFrame:
    """Goals for or against a team. side in {for, against}."""
    df = _goals()
    if season is not None:
        df = df.filter(pl.col("season") == season)
    if side == "for":
        f = pl.col("scoring_team_id") == team_id
    elif side == "against":
        f = ((pl.col("home_team_id") == team_id) | (pl.col("away_team_id") == team_id)) & (
            pl.col("scoring_team_id") != team_id)
    else:
        raise ValueError("side must be one of {for, against}")
    return df.filter(f)
