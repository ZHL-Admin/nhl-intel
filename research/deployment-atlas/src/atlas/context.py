"""Phase 4.4 Atlas context layer: WITH/AGAINST matrices, per-player descriptive
context (QoC/QoT/OZ/strictness/ST shares), and coach deployment fingerprints.

Derived from the clean Atlas stint corpus (the production WOWY marts are stale —
modified 2026-07-02, before the backfill+dedup — and lack an AGAINST relation).
"""

from __future__ import annotations

from typing import Any

import numpy as np
import polars as pl

from . import config, sources, stints as stints_mod


def _is5(df: pl.DataFrame) -> pl.Expr:
    return ((df["home_skater_ids"].list.len() == 5) & (df["away_skater_ids"].list.len() == 5)
            & df["home_goalie_id"].is_not_null() & df["away_goalie_id"].is_not_null())


def _positions() -> dict[int, str]:
    ros = pl.read_parquet(sources.ROSTERS_PARQUET).filter(~pl.col("is_goalie")).with_columns(
        pg=pl.when(pl.col("position_code") == "D").then(pl.lit("D")).otherwise(pl.lit("F")))
    m = ros.group_by("player_id", "pg").len().sort("len", descending=True).unique("player_id", keep="first")
    return dict(zip(m["player_id"], m["pg"]))


def _season_5v5(season: str) -> pl.DataFrame:
    st = pl.read_parquet(stints_mod.STINTS_PARQUET)
    return st.filter(_is5(st) & ~pl.col("is_quarantined") & (pl.col("season_label") == season))


def _player_rows(st: pl.DataFrame) -> pl.DataFrame:
    """One row per (player, stint) with side, teammates, opponents, dur, zone-from-player."""
    h = st.select("game_id", "stint_id", "duration_seconds", "start_type",
                  pl.col("home_skater_ids").alias("team"), pl.col("away_skater_ids").alias("opps"),
                  pl.lit(True).alias("is_home")).explode("team").rename({"team": "player_id"})
    a = st.select("game_id", "stint_id", "duration_seconds", "start_type",
                  pl.col("away_skater_ids").alias("team"), pl.col("home_skater_ids").alias("opps"),
                  pl.lit(False).alias("is_home")).explode("team").rename({"team": "player_id"})
    # teammates = same-side others; add for QoT
    hm = st.select("game_id", "stint_id", pl.col("home_skater_ids").alias("mates"))
    am = st.select("game_id", "stint_id", pl.col("away_skater_ids").alias("mates"))
    h = h.join(hm, on=["game_id", "stint_id"]); a = a.join(am, on=["game_id", "stint_id"])
    return pl.concat([h, a])


def oz_and_st_shares(season: str) -> pl.DataFrame:
    st = _season_5v5(season)
    pr = _player_rows(st).with_columns(
        oz=pl.when(pl.col("is_home")).then(pl.col("start_type") == "OZ").otherwise(pl.col("start_type") == "DZ"),
        dz=pl.when(pl.col("is_home")).then(pl.col("start_type") == "DZ").otherwise(pl.col("start_type") == "OZ"))
    oz = pr.group_by("player_id").agg(
        toi_5v5_s=pl.col("duration_seconds").sum(),
        oz_starts=pl.col("oz").sum(), dz_starts=pl.col("dz").sum())
    oz = oz.with_columns(oz_start_share=pl.col("oz_starts") / (pl.col("oz_starts") + pl.col("dz_starts")))
    # PP/PK: 5v4 (home PP) / 4v5 stints
    allst = pl.read_parquet(stints_mod.STINTS_PARQUET).filter(
        (pl.col("season_label") == season) & ~pl.col("is_quarantined"))
    def side_toi(strength, side_ids, team_key):
        s = allst.filter(pl.col("strength_state") == strength).select(
            pl.col(side_ids).alias("ids"), "duration_seconds").explode("ids").rename({"ids": "player_id"})
        return s.group_by("player_id").agg(pl.col("duration_seconds").sum().alias(team_key))
    pp = pl.concat([side_toi("5v4", "home_skater_ids", "pp_s"), side_toi("4v5", "away_skater_ids", "pp_s")]).group_by("player_id").agg(pl.col("pp_s").sum())
    pk = pl.concat([side_toi("5v4", "away_skater_ids", "pk_s"), side_toi("4v5", "home_skater_ids", "pk_s")]).group_by("player_id").agg(pl.col("pk_s").sum())
    return oz.join(pp, on="player_id", how="left").join(pk, on="player_id", how="left").with_columns(
        pp_s=pl.col("pp_s").fill_null(0), pk_s=pl.col("pk_s").fill_null(0))


def qoc_qot_strictness(season: str, prior_rating: dict[int, float]) -> pl.DataFrame:
    """QoC/QoT = shared-TOI-weighted mean opponent/teammate prior rating.
    Matchup strictness = Herfindahl of the player's opponent-FORWARD TOI distribution."""
    pos = _positions()
    st = _season_5v5(season)
    pr = _player_rows(st)
    # AGAINST pairs (opponents)
    opp = pr.select("player_id", "duration_seconds", "opps").explode("opps").rename({"opps": "opp_id"})
    opp = opp.with_columns(
        opp_rating=pl.col("opp_id").replace_strict(prior_rating, default=None, return_dtype=pl.Float64),
        opp_is_fwd=pl.col("opp_id").replace_strict({k: (v == "F") for k, v in pos.items()}, default=False, return_dtype=pl.Boolean))
    # QoC: TOI-weighted mean opponent rating (over opponents with a rating)
    qoc = opp.filter(pl.col("opp_rating").is_not_null()).group_by("player_id").agg(
        qoc=(pl.col("opp_rating") * pl.col("duration_seconds")).sum() / pl.col("duration_seconds").sum())
    # matchup strictness: HHI over opponent forwards' TOI shares
    fwd = opp.filter(pl.col("opp_is_fwd")).group_by("player_id", "opp_id").agg(
        toi=pl.col("duration_seconds").sum())
    tot = fwd.group_by("player_id").agg(pl.col("toi").sum().alias("tot"))
    hhi = fwd.join(tot, on="player_id").with_columns(sh2=(pl.col("toi") / pl.col("tot")) ** 2).group_by(
        "player_id").agg(strictness=pl.col("sh2").sum())
    # WITH pairs (teammates, exclude self)
    mate = pr.select("player_id", "duration_seconds", "mates").explode("mates").rename({"mates": "mate_id"}).filter(
        pl.col("player_id") != pl.col("mate_id"))
    mate = mate.with_columns(mate_rating=pl.col("mate_id").replace_strict(prior_rating, default=None, return_dtype=pl.Float64))
    qot = mate.filter(pl.col("mate_rating").is_not_null()).group_by("player_id").agg(
        qot=(pl.col("mate_rating") * pl.col("duration_seconds")).sum() / pl.col("duration_seconds").sum())
    return qoc.join(qot, on="player_id", how="outer_coalesce").join(hhi, on="player_id", how="left")


def player_context(season: str, prior_rating: dict[int, float], min_toi_min: int = 200) -> pl.DataFrame:
    oz = oz_and_st_shares(season)
    qq = qoc_qot_strictness(season, prior_rating)
    df = oz.join(qq, on="player_id", how="left").with_columns(
        toi_5v5_min=pl.col("toi_5v5_s") / 60.0,
        pp_share_of_own=pl.col("pp_s") / (pl.col("toi_5v5_s") + pl.col("pp_s") + pl.col("pk_s")),
        pk_share_of_own=pl.col("pk_s") / (pl.col("toi_5v5_s") + pl.col("pp_s") + pl.col("pk_s")),
    ).filter(pl.col("toi_5v5_s") >= min_toi_min * 60)
    df.write_parquet(config.PARQUET_DIR / f"player_context_{season}.parquet")
    return df


def coach_fingerprints(season: str) -> pl.DataFrame:
    """Per team-season deployment fingerprint (2024-25)."""
    pos = _positions()
    st = _season_5v5(season)
    games = pl.read_parquet(sources.GAMES_PARQUET).select("game_id", "home_team_id", "away_team_id")
    pr = _player_rows(st).join(games, on="game_id", how="left").with_columns(
        team_id=pl.when(pl.col("is_home")).then(pl.col("home_team_id")).otherwise(pl.col("away_team_id")),
        is_fwd=pl.col("player_id").replace_strict({k: (v == "F") for k, v in pos.items()}, default=False, return_dtype=pl.Boolean))

    # per team: TOI concentration = top-6 forward share of team 5v5 TOI
    fwd_toi = pr.filter(pl.col("is_fwd")).group_by("team_id", "player_id").agg(
        toi=pl.col("duration_seconds").sum())
    team_fwd_toi = fwd_toi.group_by("team_id").agg(pl.col("toi").sum().alias("team_fwd_toi"))
    top6 = fwd_toi.sort("toi", descending=True).group_by("team_id").head(6).group_by("team_id").agg(
        pl.col("toi").sum().alias("top6_toi"))
    conc = top6.join(team_fwd_toi, on="team_id").with_columns(top6_fwd_toi_share=pl.col("top6_toi") / pl.col("team_fwd_toi"))

    # zone-start polarization = std dev of OZ start share across roster (>=200 min)
    ozr = oz_and_st_shares(season).filter(pl.col("toi_5v5_s") >= 200 * 60)
    # attach team
    pteam = pr.group_by("player_id").agg(pl.col("team_id").mode().first().alias("team_id"))
    ozp = ozr.join(pteam, on="player_id", how="left")
    polar = ozp.group_by("team_id").agg(zone_start_polarization=pl.col("oz_start_share").std())

    # close-game bench shortening: top-6 F TOI share in 3rd period within 1 goal - overall
    st3 = st.with_columns(
        p3=(pl.col("start_seconds") >= 2400) & (pl.col("start_seconds") < 3600),
        close=pl.col("score_state").abs() <= 1)
    prc = _player_rows(st3.filter(pl.col("p3") & pl.col("close"))).join(games, on="game_id").with_columns(
        team_id=pl.when(pl.col("is_home")).then(pl.col("home_team_id")).otherwise(pl.col("away_team_id")),
        is_fwd=pl.col("player_id").replace_strict({k: (v == "F") for k, v in pos.items()}, default=False, return_dtype=pl.Boolean))
    def top6_share(rows):
        ft = rows.filter(pl.col("is_fwd")).group_by("team_id", "player_id").agg(toi=pl.col("duration_seconds").sum())
        tt = ft.group_by("team_id").agg(pl.col("toi").sum().alias("tt"))
        t6 = ft.sort("toi", descending=True).group_by("team_id").head(6).group_by("team_id").agg(pl.col("toi").sum().alias("t6"))
        return t6.join(tt, on="team_id").with_columns(share=pl.col("t6") / pl.col("tt")).select("team_id", "share")
    close_share = top6_share(prc).rename({"share": "close_top6_share"})
    overall_share = top6_share(pr).rename({"share": "overall_top6_share"})
    shorten = close_share.join(overall_share, on="team_id").with_columns(
        close_game_shortening=pl.col("close_top6_share") - pl.col("overall_top6_share"))

    # home-minus-away matchup strictness for the team's top defensive forwards.
    # strictness = HHI of opponent-forward TOI, split by whether it's a home game
    # (is_home). Top defensive forwards = the team's 3 forwards with the highest
    # overall strictness (they draw the tough matchups). Last change => home > away.
    opp = pr.filter(pl.col("is_fwd")).select(
        "player_id", "team_id", "is_home", "duration_seconds", "opps").explode("opps").rename(
        {"opps": "opp_id"})
    opp = opp.with_columns(opp_fwd=pl.col("opp_id").replace_strict(
        {k: (v == "F") for k, v in pos.items()}, default=False, return_dtype=pl.Boolean)).filter(pl.col("opp_fwd"))

    def hhi(group_cols):
        f = opp.group_by(*group_cols, "opp_id").agg(toi=pl.col("duration_seconds").sum())
        t = f.group_by(*group_cols).agg(pl.col("toi").sum().alias("tot"))
        return f.join(t, on=group_cols).with_columns(s2=(pl.col("toi") / pl.col("tot")) ** 2).group_by(
            *group_cols).agg(hhi=pl.col("s2").sum())

    overall = hhi(["team_id", "player_id"])
    by_venue = hhi(["team_id", "player_id", "is_home"])
    top_def = overall.sort("hhi", descending=True).group_by("team_id").head(3).select("team_id", "player_id")
    venue_w = by_venue.pivot("is_home", index=["team_id", "player_id"], values="hhi")
    cols = venue_w.columns
    hcol = "true" if "true" in cols else ("True" if "True" in cols else cols[-1])
    acol = "false" if "false" in cols else ("False" if "False" in cols else cols[-2])
    venue_w = venue_w.with_columns(home_minus_away=pl.col(hcol) - pl.col(acol))
    ha = top_def.join(venue_w, on=["team_id", "player_id"], how="left").group_by("team_id").agg(
        home_away_strictness=pl.col("home_minus_away").mean())

    fp = conc.select("team_id", "top6_fwd_toi_share").join(
        ha, on="team_id", how="left").join(
        polar, on="team_id", how="left").join(
        shorten.select("team_id", "close_game_shortening"), on="team_id", how="left")
    return fp.sort("team_id")
