"""Shared per-(team, season) fingerprint + schedule assembly for Phase 3.3-3.5.

For each team-season: the Phase 2 metric vector (deployment + style) over the team's full
season game set, the games it played, and its opponents (for schedule-average style and the
opponent track). Cached to data/parquet/team_season_fp.parquet.
"""
from __future__ import annotations

import polars as pl

from . import config, fingerprints as F, phase2 as P2

FP_PARQUET = config.PARQUET / "team_season_fp.parquet"

DEPLOY_AXES = ["top6_fwd_toi_share", "zone_start_polarization"]
STYLE_AXES = ["pace", "rush_share_for", "cycle_share_for", "forecheck_share_for",
              "point_shot_share_for", "loc_inner_against", "loc_outer_against", "loc_point_against"]
ALL_AXES = DEPLOY_AXES + STYLE_AXES


def _games(season):
    return pl.read_parquet(config.ATLAS_PARQUET / "games.parquet",
                           columns=["game_id", "season_label", "home_team_id", "away_team_id"]
                           ).filter(pl.col("season_label") == season)


def team_season_games(seasons=None) -> pl.DataFrame:
    """Long (season, team, game_id, opp_id) — every team-game with its opponent."""
    seasons = seasons or config.SEASONS_ALL
    frames = []
    for s in seasons:
        g = _games(s)
        frames.append(g.select("season_label", pl.col("home_team_id").alias("team_id"),
                               "game_id", pl.col("away_team_id").alias("opp_id")))
        frames.append(g.select("season_label", pl.col("away_team_id").alias("team_id"),
                               "game_id", pl.col("home_team_id").alias("opp_id")))
    return pl.concat(frames)


def build(seasons=None, write: bool = True) -> pl.DataFrame:
    seasons = seasons or config.SEASONS_ALL
    prim = P2._load(F.PRIM_DIR, seasons)
    deploy = P2._load(F.DEPLOY_DIR, seasons)
    tsg = team_season_games(seasons)
    rows = []
    for (season, team), sub in tsg.group_by(["season_label", "team_id"]):
        gids = sub["game_id"].unique().to_list()
        v = P2.metric_vector(prim, deploy, gids, team)
        rows.append({"season_label": season, "team_id": team, "n_games": len(gids),
                     **{a: v.get(a) for a in ALL_AXES}})
    out = pl.DataFrame(rows)
    if write:
        out.write_parquet(FP_PARQUET)
    return out


def schedule_avg_style(seasons=None) -> pl.DataFrame:
    """Per (team, season): games-weighted average of OPPONENTS' style vectors (schedule)."""
    fp = pl.read_parquet(FP_PARQUET) if FP_PARQUET.exists() else build(seasons)
    tsg = team_season_games(seasons)
    opp = fp.select("season_label", pl.col("team_id").alias("opp_id"),
                    *[pl.col(a).alias(f"opp_{a}") for a in STYLE_AXES])
    j = tsg.join(opp, on=["season_label", "opp_id"], how="left")
    agg = j.group_by("season_label", "team_id").agg(
        *[pl.col(f"opp_{a}").mean().alias(f"sched_{a}") for a in STYLE_AXES])
    return agg


if __name__ == "__main__":
    out = build()
    print("team_season_fp:", out.shape)
    print(out.head(3).to_dicts())
