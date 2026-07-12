"""Phase 3 primitives — multi-season player context + on-ice xG, from frozen stints.

Phase 0/1 recorded that Atlas `player_context` and the coach fingerprints are
materialized for 2024-25 ONLY. This module is the accepted build-the-delta: re-derive
per-player-season context for all 16 seasons from the frozen stints, matching the Atlas
formulas, and VALIDATE the re-derivation against the one materialized Atlas season
(`player_context_2024-25.parquet`) — rule 7b.

Grain and outputs (all cached under data/parquet/, gitignored):
  pctx/{season}.parquet   per (player, team, season): 5v5 TOI, PP/PK seconds, OZ/DZ
                          starts. Team-level PP/PK time is carried so PP/PK *shares of
                          own team* reconcile with Atlas.
  onice/{season}.parquet  per (game, team, player): 5v5 on-ice xGF/xGA (all + score-
                          close) and 5v5 TOI — the workhorse for on-ice xG share over an
                          arbitrary game set (Design A regime split; Design B checks).

Strength is ICE-DERIVED from the stint strength_state "HvA" (never situationCode); the
753 Atlas-quarantined stints stay excluded, per standing rules.
"""
from __future__ import annotations

import polars as pl

from . import config

PCTX_DIR = config.PARQUET / "pctx"
ONICE_DIR = config.PARQUET / "onice"


def _stints(season: str, only_5v5: bool = False) -> pl.DataFrame:
    st = pl.read_parquet(config.ATLAS_PARQUET / "stints.parquet").filter(
        (pl.col("season_label") == season) & (~pl.col("is_quarantined"))
    )
    if only_5v5:
        st = st.filter(pl.col("strength_state") == "5v5")
    return st


def _games(season: str) -> pl.DataFrame:
    return pl.read_parquet(
        config.ATLAS_PARQUET / "games.parquet",
        columns=["game_id", "season_label", "home_team_id", "away_team_id"],
    ).filter(pl.col("season_label") == season)


# ---------------------------------------------------------------- player context
def build_context(season: str, write: bool = True) -> pl.DataFrame:
    """Per (player, team, season): 5v5 TOI, PP/PK seconds, OZ/DZ starts (5v5), and the
    team's PP/PK time (so PP/PK share-of-own reconciles with Atlas)."""
    st = _stints(season)
    g = _games(season)
    st = st.join(g.select("game_id", "home_team_id", "away_team_id"), on="game_id", how="left")
    st = st.with_columns(
        h_sk=pl.col("strength_state").str.extract(r"^(\d+)v").cast(pl.Int32),
        a_sk=pl.col("strength_state").str.extract(r"v(\d+)$").cast(pl.Int32),
        both_g=pl.col("home_goalie_id").is_not_null() & pl.col("away_goalie_id").is_not_null(),
    ).with_columns(
        is_5v5=(pl.col("h_sk") == 5) & (pl.col("a_sk") == 5),
        # man advantage requires both goalies on ice (excludes pulled-goalie 6v5/5v6)
        home_up=(pl.col("h_sk") > pl.col("a_sk")) & pl.col("both_g"),
        away_up=(pl.col("a_sk") > pl.col("h_sk")) & pl.col("both_g"),
    )

    def side(prefix_ids, team_col, up_flag, dn_flag, oz_flag):
        return st.select(
            "game_id", "duration_seconds", "is_5v5",
            pl.col(team_col).alias("team_id"),
            pl.col(prefix_ids).alias("pid"),
            pp=up_flag, pk=dn_flag,
            oz=(pl.col("start_type") == oz_flag) & pl.col("is_5v5"),
            dz=(pl.col("start_type") == ("DZ" if oz_flag == "OZ" else "OZ")) & pl.col("is_5v5"),
        ).explode("pid")

    home = side("home_skater_ids", "home_team_id", pl.col("home_up"), pl.col("away_up"), "OZ")
    away = side("away_skater_ids", "away_team_id", pl.col("away_up"), pl.col("home_up"), "DZ")
    long = pl.concat([home, away])
    pl_agg = long.group_by("player_id" if False else "pid", "team_id").agg(
        toi_5v5_s=pl.col("duration_seconds").filter(pl.col("is_5v5")).sum(),
        pp_s=pl.col("duration_seconds").filter(pl.col("pp")).sum(),
        pk_s=pl.col("duration_seconds").filter(pl.col("pk")).sum(),
        oz_starts=pl.col("oz").sum(), dz_starts=pl.col("dz").sum(),
    ).rename({"pid": "player_id"})

    # team-level PP/PK time (denominator for share-of-own-team): unique stints per team
    team_home = st.select("game_id", "stint_id", "duration_seconds",
                          pl.col("home_team_id").alias("team_id"),
                          pp=pl.col("home_up"), pk=pl.col("away_up"))
    team_away = st.select("game_id", "stint_id", "duration_seconds",
                          pl.col("away_team_id").alias("team_id"),
                          pp=pl.col("away_up"), pk=pl.col("home_up"))
    team = pl.concat([team_home, team_away]).group_by("team_id").agg(
        team_pp_s=pl.col("duration_seconds").filter(pl.col("pp")).sum(),
        team_pk_s=pl.col("duration_seconds").filter(pl.col("pk")).sum())

    out = pl_agg.join(team, on="team_id", how="left").with_columns(
        season_label=pl.lit(season),
        oz_start_share=pl.when(pl.col("oz_starts") + pl.col("dz_starts") > 0)
        .then(pl.col("oz_starts") / (pl.col("oz_starts") + pl.col("dz_starts"))).otherwise(None),
        pp_share_of_own=pl.when(pl.col("team_pp_s") > 0).then(pl.col("pp_s") / pl.col("team_pp_s")).otherwise(0.0),
        pk_share_of_own=pl.when(pl.col("team_pk_s") > 0).then(pl.col("pk_s") / pl.col("team_pk_s")).otherwise(0.0),
    )
    if write:
        PCTX_DIR.mkdir(parents=True, exist_ok=True)
        out.write_parquet(PCTX_DIR / f"{season.replace('-', '_')}.parquet")
    return out


def player_season_context(season: str) -> pl.DataFrame:
    """Aggregate the (player, team) context to one row per (player, season): TOI-weighted
    OZ/PP/PK, primary team = max 5v5 TOI. For clustering + matching."""
    d = pl.read_parquet(PCTX_DIR / f"{season.replace('-', '_')}.parquet")
    prim = d.sort("toi_5v5_s", descending=True).unique("player_id", keep="first").select(
        "player_id", pl.col("team_id").alias("primary_team_id"))
    agg = d.group_by("player_id").agg(
        toi_5v5_s=pl.col("toi_5v5_s").sum(), pp_s=pl.col("pp_s").sum(), pk_s=pl.col("pk_s").sum(),
        oz_starts=pl.col("oz_starts").sum(), dz_starts=pl.col("dz_starts").sum(),
        # TOI-weighted share-of-own across teams (handles mid-season trades)
        pp_share_of_own=(pl.col("pp_share_of_own") * pl.col("toi_5v5_s")).sum() / pl.col("toi_5v5_s").sum(),
        pk_share_of_own=(pl.col("pk_share_of_own") * pl.col("toi_5v5_s")).sum() / pl.col("toi_5v5_s").sum(),
    ).with_columns(
        season_label=pl.lit(season),
        toi_5v5_min=pl.col("toi_5v5_s") / 60.0,
        oz_start_share=pl.when(pl.col("oz_starts") + pl.col("dz_starts") > 0)
        .then(pl.col("oz_starts") / (pl.col("oz_starts") + pl.col("dz_starts"))).otherwise(None),
        pp_frac=pl.col("pp_s") / (pl.col("toi_5v5_s") + pl.col("pp_s") + pl.col("pk_s")),
        pk_frac=pl.col("pk_s") / (pl.col("toi_5v5_s") + pl.col("pp_s") + pl.col("pk_s")),
    )
    return agg.join(prim, on="player_id", how="left")


DEPFULL_DIR = config.PARQUET / "depfull"


def build_deploy_full(season: str, write: bool = True) -> pl.DataFrame:
    """Per (game, team, player) full deployment primitive: 5v5 TOI + PP/PK seconds +
    OZ/DZ starts. Summable over any game set (a regime, a within-season split), so Design A
    deployment deltas aggregate by summation. Same both-goalie man-advantage rule as
    build_context."""
    st = _stints(season)
    g = _games(season)
    st = st.join(g.select("game_id", "home_team_id", "away_team_id"), on="game_id", how="left")
    st = st.with_columns(
        h_sk=pl.col("strength_state").str.extract(r"^(\d+)v").cast(pl.Int32),
        a_sk=pl.col("strength_state").str.extract(r"v(\d+)$").cast(pl.Int32),
        both_g=pl.col("home_goalie_id").is_not_null() & pl.col("away_goalie_id").is_not_null(),
    ).with_columns(
        is_5v5=(pl.col("h_sk") == 5) & (pl.col("a_sk") == 5),
        home_up=(pl.col("h_sk") > pl.col("a_sk")) & pl.col("both_g"),
        away_up=(pl.col("a_sk") > pl.col("h_sk")) & pl.col("both_g"),
    )

    def side(ids, team, up, dn, oz_flag):
        return st.select(
            "game_id", "duration_seconds", "is_5v5",
            pl.col(team).alias("team_id"), pl.col(ids).alias("pid"),
            pp=up, pk=dn,
            oz=(pl.col("start_type") == oz_flag) & pl.col("is_5v5"),
            dz=(pl.col("start_type") == ("DZ" if oz_flag == "OZ" else "OZ")) & pl.col("is_5v5"),
        ).explode("pid")

    home = side("home_skater_ids", "home_team_id", pl.col("home_up"), pl.col("away_up"), "OZ")
    away = side("away_skater_ids", "away_team_id", pl.col("away_up"), pl.col("home_up"), "DZ")
    long = pl.concat([home, away])
    out = long.group_by("game_id", "team_id", "pid").agg(
        toi_5v5_s=pl.col("duration_seconds").filter(pl.col("is_5v5")).sum(),
        pp_s=pl.col("duration_seconds").filter(pl.col("pp")).sum(),
        pk_s=pl.col("duration_seconds").filter(pl.col("pk")).sum(),
        oz_starts=pl.col("oz").sum(), dz_starts=pl.col("dz").sum(),
    ).rename({"pid": "player_id"}).with_columns(season_label=pl.lit(season))
    if write:
        DEPFULL_DIR.mkdir(parents=True, exist_ok=True)
        out.write_parquet(DEPFULL_DIR / f"{season.replace('-', '_')}.parquet")
    return out


# ---------------------------------------------------------------- experience proxy (age band)
def experience_table() -> pl.DataFrame:
    """No birthdate exists in any frozen Atlas asset (verified Phase 3 audit). Age-band
    matching (spec 3.2) therefore uses an EXPERIENCE proxy: seasons since a player's first
    appearance in the frozen rosters. Documented as a proxy, not true age."""
    ros = pl.read_parquet(config.ATLAS_PARQUET / "rosters.parquet",
                          columns=["player_id", "season_start_year"])
    first = ros.group_by("player_id").agg(first_syear=pl.col("season_start_year").min())
    return first


# ---------------------------------------------------------------- on-ice xG primitive
def build_onice(season: str, write: bool = True) -> pl.DataFrame:
    """Per (game, team, player) 5v5 on-ice xGF/xGA (all + score-close) and TOI. Lets us
    compute any player's on-ice 5v5 xG share over an arbitrary game set by summation."""
    st = _stints(season, only_5v5=True).select(
        "game_id", "duration_seconds", "score_state", "home_team_id" if False else "home_skater_ids",
        "away_skater_ids", "home_xg", "away_xg")
    g = _games(season)
    st = st.join(g.select("game_id", "home_team_id", "away_team_id"), on="game_id", how="left")
    st = st.with_columns(is_close=pl.col("score_state").abs() <= 1)
    home = st.select(
        "game_id", "duration_seconds", "is_close",
        pl.col("home_team_id").alias("team_id"),
        pl.col("home_skater_ids").alias("pid"),
        xgf=pl.col("home_xg"), xga=pl.col("away_xg")).explode("pid")
    away = st.select(
        "game_id", "duration_seconds", "is_close",
        pl.col("away_team_id").alias("team_id"),
        pl.col("away_skater_ids").alias("pid"),
        xgf=pl.col("away_xg"), xga=pl.col("home_xg")).explode("pid")
    long = pl.concat([home, away])
    out = long.group_by("game_id", "team_id", "pid").agg(
        toi_5v5_s=pl.col("duration_seconds").sum(),
        xgf=pl.col("xgf").sum(), xga=pl.col("xga").sum(),
        xgf_close=pl.col("xgf").filter(pl.col("is_close")).sum(),
        xga_close=pl.col("xga").filter(pl.col("is_close")).sum(),
    ).rename({"pid": "player_id"}).with_columns(season_label=pl.lit(season))
    if write:
        ONICE_DIR.mkdir(parents=True, exist_ok=True)
        out.write_parquet(ONICE_DIR / f"{season.replace('-', '_')}.parquet")
    return out


def onice_share(onice: pl.DataFrame, game_ids, player_id: int, team_id: int, close: bool = False) -> dict:
    """A player's on-ice 5v5 xG share over a game set (optionally score-close)."""
    d = onice.filter(pl.col("game_id").is_in(list(game_ids))
                     & (pl.col("player_id") == player_id) & (pl.col("team_id") == team_id))
    if d.height == 0:
        return {"xgf": 0.0, "xga": 0.0, "xg_share": None, "toi_min": 0.0}
    s = d.sum()
    f = float(s["xgf_close"][0] if close else s["xgf"][0])
    a = float(s["xga_close"][0] if close else s["xga"][0])
    toi = float(s["toi_5v5_s"][0]) / 60.0
    return {"xgf": f, "xga": a, "xg_share": f / (f + a) if (f + a) > 0 else None, "toi_min": toi}


# ---------------------------------------------------------------- team-game 5v5 xG (opponent track)
def build_team_game_xg(season: str) -> pl.DataFrame:
    """Per (game, team) 5v5 xGF/xGA (all + score-close) + opponent id — the opponent-track
    unit for 5v5 xG share between two teams in a game."""
    st = _stints(season, only_5v5=True).select(
        "game_id", "duration_seconds", "score_state", "home_xg", "away_xg")
    g = _games(season)
    st = st.join(g, on="game_id", how="left").with_columns(is_close=pl.col("score_state").abs() <= 1)
    home = st.select("game_id", pl.col("home_team_id").alias("team_id"),
                     pl.col("away_team_id").alias("opp_id"), "duration_seconds", "is_close",
                     xgf=pl.col("home_xg"), xga=pl.col("away_xg"))
    away = st.select("game_id", pl.col("away_team_id").alias("team_id"),
                     pl.col("home_team_id").alias("opp_id"), "duration_seconds", "is_close",
                     xgf=pl.col("away_xg"), xga=pl.col("home_xg"))
    long = pl.concat([home, away])
    return long.group_by("game_id", "team_id", "opp_id").agg(
        toi_5v5_s=pl.col("duration_seconds").sum(),
        xgf=pl.col("xgf").sum(), xga=pl.col("xga").sum(),
        xgf_close=pl.col("xgf").filter(pl.col("is_close")).sum(),
        xga_close=pl.col("xga").filter(pl.col("is_close")).sum(),
    ).with_columns(season_label=pl.lit(season))


if __name__ == "__main__":
    import sys
    seasons = sys.argv[1:] or config.SEASONS_ALL
    for s in seasons:
        cp = PCTX_DIR / f"{s.replace('-', '_')}.parquet"
        op = ONICE_DIR / f"{s.replace('-', '_')}.parquet"
        dfp = DEPFULL_DIR / f"{s.replace('-', '_')}.parquet"
        if not cp.exists():
            build_context(s)
        if not op.exists():
            build_onice(s)
        if not dfp.exists():
            build_deploy_full(s)
        print(s, "done", flush=True)
