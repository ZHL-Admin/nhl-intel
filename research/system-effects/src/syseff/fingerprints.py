"""Phase 2 — system fingerprint metrics per (team, consolidated regime) and (team, season).

Design: build SUMMABLE per-(game, team) primitives once per season (cached), then a
game-set aggregator turns any set of games (a regime, a season, an odd/even split) into
the metric vector by simple summation. This makes regime/season/split-half aggregation
identical and consistent.

SCORE ADJUSTMENT (documented per metric). Attempt-rate and share metrics respond to score
state (a trailing team shoots more, from farther out). Those are computed on SCORE-CLOSE
play only — stint |score_state| <= 1 (within one goal), the ice-derived score differential
from the Atlas stints — which is the standard score adjustment for attempt/location shares.
Deployment metrics: close_game_shortening is score-defined (kept as-is); top-6 share and
zone-start polarization are not score-sensitive (computed on all 5v5).

Sequence shares reuse the frozen `sequence.py` reimplementation of int_shot_sequence.
"""
from __future__ import annotations

import polars as pl

from . import config, sequence as S

PRIM_DIR = config.PARQUET / "prim"
SEQ_FOR = ["rush", "cycle", "forecheck", "point_shot", "rebound", "other"]


def _games(season: str) -> pl.DataFrame:
    return pl.read_parquet(config.ATLAS_PARQUET / "games.parquet",
                           columns=["game_id", "season_label", "home_team_id", "away_team_id"]
                           ).filter(pl.col("season_label") == season)


def _shot_context(season: str) -> pl.DataFrame:
    """Seq shots + stint-attributed score_state, strength, shooter side, PP flag."""
    seq = pl.read_parquet(S.SEQ_DIR / f"{season.replace('-', '_')}.parquet")
    st = (pl.read_parquet(config.ATLAS_PARQUET / "stints.parquet")
          .filter((pl.col("season_label") == season) & (~pl.col("is_quarantined")))
          .select("game_id", "start_seconds", "end_seconds", "strength_state", "score_state")
          .sort(["game_id", "start_seconds"]))
    seq = seq.sort(["game_id", "s_sec"])
    j = seq.join_asof(st, left_on="s_sec", right_on="start_seconds",
                      by="game_id", strategy="backward")
    g = _games(season)
    j = j.join(g.select("game_id", "home_team_id", "away_team_id"), on="game_id", how="left")
    j = j.with_columns(
        shooter_is_home=pl.col("team_id") == pl.col("home_team_id"),
        is_close=pl.col("score_state").abs() <= 1,
        home_sk=pl.col("strength_state").str.extract(r"^(\d+)v").cast(pl.Int32),
        away_sk=pl.col("strength_state").str.extract(r"v(\d+)$").cast(pl.Int32),
    ).with_columns(
        is_pp_for=pl.when(pl.col("shooter_is_home")).then(pl.col("home_sk") > pl.col("away_sk"))
        .otherwise(pl.col("away_sk") > pl.col("home_sk")),
        loc_bin=pl.when(pl.col("seq_point_shot")).then(pl.lit("point"))
        .when(pl.col("s_y").abs() <= 9).then(pl.lit("inner")).otherwise(pl.lit("outer")),
    )
    return j


def build_primitives(season: str, write: bool = True) -> pl.DataFrame:
    j = _shot_context(season)
    j5 = j.filter(pl.col("is_5v5"))

    def _for_counts(df, suffix, closed):
        d = df.filter(pl.col("is_close")) if closed else df
        agg = d.group_by("game_id", "team_id").agg(
            att=pl.len(),
            **{f"{t}": (pl.col("seq_type") == t).sum() for t in SEQ_FOR},
            inner=(pl.col("loc_bin") == "inner").sum(),
            outer=(pl.col("loc_bin") == "outer").sum(),
            point=(pl.col("loc_bin") == "point").sum(),
        )
        return agg.rename({c: f"{c}_{suffix}" for c in agg.columns
                           if c not in ("game_id", "team_id")})

    fc_all = _for_counts(j5, "for", False)
    fc_close = _for_counts(j5, "forc", True)     # 'forc' = for, score-close

    # PP location (for)
    pp = j.filter(pl.col("is_pp_for")).group_by("game_id", "team_id").agg(
        att_pp=pl.len(), inner_pp=(pl.col("loc_bin") == "inner").sum(),
        outer_pp=(pl.col("loc_bin") == "outer").sum(),
        point_pp=(pl.col("loc_bin") == "point").sum())

    # stint primitives: toi, corsi for/against, at 5v5, all + score-close
    st = (pl.read_parquet(config.ATLAS_PARQUET / "stints.parquet")
          .filter((pl.col("season_label") == season) & (~pl.col("is_quarantined"))
                  & (pl.col("strength_state") == "5v5"))
          .select("game_id", "home_team_id" if False else "duration_seconds",
                  "home_corsi", "away_corsi", "score_state"))
    g = _games(season)
    st = st.join(g, on="game_id", how="left")
    home = st.select("game_id", pl.col("home_team_id").alias("team_id"), "duration_seconds",
                     pl.col("home_corsi").alias("cf"), pl.col("away_corsi").alias("ca"), "score_state")
    away = st.select("game_id", pl.col("away_team_id").alias("team_id"), "duration_seconds",
                     pl.col("away_corsi").alias("cf"), pl.col("home_corsi").alias("ca"), "score_state")
    tg = pl.concat([home, away]).with_columns(is_close=pl.col("score_state").abs() <= 1)
    stp = tg.group_by("game_id", "team_id").agg(
        toi_sec=pl.col("duration_seconds").sum(),
        cf=pl.col("cf").sum(), ca=pl.col("ca").sum(),
        toi_sec_close=pl.col("duration_seconds").filter(pl.col("is_close")).sum(),
        cf_close=pl.col("cf").filter(pl.col("is_close")).sum(),
        ca_close=pl.col("ca").filter(pl.col("is_close")).sum())

    # forecheck events (5v5): OZ takeaway by team + DZ giveaway by opponent
    prim = (_games(season).select("game_id", "home_team_id", "away_team_id"))
    fk = _forecheck_primitives(season)

    # assemble: universe = (game, team) for all teams that played
    teams = pl.concat([
        g.select("game_id", pl.col("home_team_id").alias("team_id"), pl.col("away_team_id").alias("opp_id")),
        g.select("game_id", pl.col("away_team_id").alias("team_id"), pl.col("home_team_id").alias("opp_id")),
    ])
    out = teams
    for f in (fc_all, fc_close, pp, stp, fk):
        out = out.join(f, on=["game_id", "team_id"], how="left")
    # AGAINST = opponent's FOR (join fc_all/fc_close by opp)
    ag = fc_all.rename({c: c.replace("_for", "_against") for c in fc_all.columns
                        if c.endswith("_for")}).rename({"team_id": "opp_id"})
    agc = fc_close.rename({c: c.replace("_forc", "_againstc") for c in fc_close.columns
                           if c.endswith("_forc")}).rename({"team_id": "opp_id"})
    out = out.join(ag, on=["game_id", "opp_id"], how="left").join(agc, on=["game_id", "opp_id"], how="left")
    out = out.fill_null(0).with_columns(season_label=pl.lit(season))
    if write:
        PRIM_DIR.mkdir(parents=True, exist_ok=True)
        out.write_parquet(PRIM_DIR / f"{season.replace('-', '_')}.parquet")
    return out


def _forecheck_primitives(season: str) -> pl.DataFrame:
    """5v5 forecheck pressure primitives per (game, team)."""
    ev = pl.read_parquet(config.ATLAS_PARQUET / "events.parquet").filter(
        (pl.col("season_label") == season)
        & pl.col("type_desc_key").is_in(["takeaway", "giveaway"])
    ).select("game_id", "event_second", "type_desc_key", "zone_code", "event_owner_team_id")
    st = (pl.read_parquet(config.ATLAS_PARQUET / "stints.parquet")
          .filter((pl.col("season_label") == season) & (~pl.col("is_quarantined")))
          .select("game_id", "start_seconds", "end_seconds", "strength_state").sort(["game_id", "start_seconds"]))
    ev = ev.sort(["game_id", "event_second"]).join_asof(
        st, left_on="event_second", right_on="start_seconds", by="game_id", strategy="backward")
    ev = ev.filter((pl.col("strength_state") == "5v5") & (pl.col("event_second") < pl.col("end_seconds")))
    g = _games(season)
    ev = ev.join(g, on="game_id", how="left")
    # OZ takeaway credited to the owner team; DZ giveaway credits the OPPONENT team's forecheck
    oz_take = ev.filter((pl.col("type_desc_key") == "takeaway") & (pl.col("zone_code") == "O")).select(
        "game_id", pl.col("event_owner_team_id").alias("team_id")).group_by("game_id", "team_id").agg(oz_take=pl.len())
    dz_give = ev.filter((pl.col("type_desc_key") == "giveaway") & (pl.col("zone_code") == "D")).with_columns(
        forecheck_team=pl.when(pl.col("event_owner_team_id") == pl.col("home_team_id"))
        .then(pl.col("away_team_id")).otherwise(pl.col("home_team_id"))).select(
        "game_id", pl.col("forecheck_team").alias("team_id")).group_by("game_id", "team_id").agg(forced_give=pl.len())
    return oz_take.join(dz_give, on=["game_id", "team_id"], how="full", coalesce=True).fill_null(0)


# ---------------------------------------------------------------- aggregation
def aggregate(prim: pl.DataFrame, game_ids: list[int], team_id: int) -> dict:
    d = prim.filter(pl.col("game_id").is_in(game_ids) & (pl.col("team_id") == team_id))
    if d.height == 0:
        return {}
    s = d.sum()
    def g(c): return float(s[c][0]) if c in s.columns else 0.0
    att_c, atta_c = g("att_forc"), g("att_againstc")   # score-close for/against
    att_f, atta_f = g("att_for"), g("att_against")
    toi_c = g("toi_sec_close"); toi = g("toi_sec")
    m = {"n_games": d.height, "att_for_close": att_c, "toi_min_close": toi_c / 60.0}
    # pace (score-close): combined attempts/60
    m["pace"] = (g("cf_close") + g("ca_close")) / toi_c * 3600 if toi_c else None
    # seq shares FOR (score-close)
    for t in ("rush", "cycle", "forecheck", "point_shot"):
        m[f"{t}_share_for"] = g(f"{t}_forc") / att_c if att_c else None
    # seq shares AGAINST (score-close)
    for t in ("rush", "cycle"):
        m[f"{t}_share_against"] = g(f"{t}_againstc") / atta_c if atta_c else None
    # shot-location-against profile (score-close)
    for b in ("inner", "outer", "point"):
        m[f"loc_{b}_against"] = g(f"{b}_againstc") / atta_c if atta_c else None
    # attack-origin-against: rush vs in-zone
    m["rush_against"] = g("rush_againstc") / atta_c if atta_c else None
    m["inzone_against"] = 1 - m["rush_against"] if m["rush_against"] is not None else None
    # forecheck pressure per 60 (all-5v5; a rate, score-adj via denominator TOI)
    m["forecheck_pressure_per60"] = (g("oz_take") + g("forced_give")) / toi * 3600 if toi else None
    # PP shot-location-for profile
    att_pp = g("att_pp")
    for b in ("inner", "outer", "point"):
        m[f"pp_loc_{b}_for"] = g(f"{b}_pp") / att_pp if att_pp else None
    return m


DEPLOY_DIR = config.PARQUET / "deploy"
PK_DIR = config.PARQUET / "pk"


def build_pk(season: str, write: bool = True) -> pl.DataFrame:
    """Per (game, DEFENDING team) PK shot-location-against primitive: location bins of
    unblocked attempts conceded while shorthanded. Strength ice-derived (is_pp_for on the
    shooting side => the shooter's OPPONENT is the shorthanded/defending team)."""
    j = _shot_context(season).filter(pl.col("is_pp_for"))
    g = _games(season).select("game_id", "home_team_id", "away_team_id")
    j = j.with_columns(
        def_team=pl.when(pl.col("shooter_is_home")).then(pl.col("away_team_id"))
        .otherwise(pl.col("home_team_id")))
    out = j.group_by("game_id", pl.col("def_team").alias("team_id")).agg(
        att_pk_against=pl.len(),
        inner_pk_against=(pl.col("loc_bin") == "inner").sum(),
        outer_pk_against=(pl.col("loc_bin") == "outer").sum(),
        point_pk_against=(pl.col("loc_bin") == "point").sum())
    if write:
        PK_DIR.mkdir(parents=True, exist_ok=True)
        out.write_parquet(PK_DIR / f"{season.replace('-', '_')}.parquet")
    return out


def pk_location(pk: pl.DataFrame, game_ids: list[int], team_id: int) -> dict:
    d = pk.filter(pl.col("game_id").is_in(game_ids) & (pl.col("team_id") == team_id))
    if d.height == 0:
        return {"pk_loc_inner_against": None, "pk_loc_outer_against": None,
                "pk_loc_point_against": None, "att_pk_against": 0}
    s = d.sum(); att = float(s["att_pk_against"][0])
    return {"att_pk_against": att,
            "pk_loc_inner_against": float(s["inner_pk_against"][0]) / att if att else None,
            "pk_loc_outer_against": float(s["outer_pk_against"][0]) / att if att else None,
            "pk_loc_point_against": float(s["point_pk_against"][0]) / att if att else None}


def build_deploy(season: str, write: bool = True) -> pl.DataFrame:
    """Per (game, team, player) 5v5 TOI + OZ/DZ starts — summable deployment primitive.
    Reuses the Atlas _is5 / start-type convention (start_type OZ/DZ relative to team)."""
    st = pl.read_parquet(config.ATLAS_PARQUET / "stints.parquet").filter(
        (pl.col("season_label") == season) & (~pl.col("is_quarantined"))
        & (pl.col("strength_state") == "5v5"))
    g = _games(season)
    st = st.join(g.select("game_id", "home_team_id", "away_team_id"), on="game_id", how="left")
    home = st.select("game_id", pl.col("home_team_id").alias("team_id"), "duration_seconds",
                     "start_type", pl.col("home_skater_ids").alias("pid"),
                     oz=(pl.col("start_type") == "OZ"), dz=(pl.col("start_type") == "DZ")).explode("pid")
    away = st.select("game_id", pl.col("away_team_id").alias("team_id"), "duration_seconds",
                     "start_type", pl.col("away_skater_ids").alias("pid"),
                     oz=(pl.col("start_type") == "DZ"), dz=(pl.col("start_type") == "OZ")).explode("pid")
    d = pl.concat([home.drop("start_type"), away.drop("start_type")]).group_by("game_id", "team_id", "pid").agg(
        toi_sec=pl.col("duration_seconds").sum(),
        oz_starts=pl.col("oz").sum(), dz_starts=pl.col("dz").sum())
    if write:
        DEPLOY_DIR.mkdir(parents=True, exist_ok=True)
        d.write_parquet(DEPLOY_DIR / f"{season.replace('-', '_')}.parquet")
    return d


_POS_CACHE = {}
_FWD_CACHE = {}
def _positions() -> dict:
    if not _POS_CACHE:
        ros = pl.read_parquet(config.ATLAS_PARQUET / "rosters.parquet")
        pgcol = "is_goalie" if "is_goalie" in ros.columns else None
        if pgcol:
            ros = ros.filter(~pl.col("is_goalie"))
        ros = ros.with_columns(pg=pl.when(pl.col("position_code") == "D").then(pl.lit("D")).otherwise(pl.lit("F")))
        m = ros.group_by("player_id", "pg").len().sort("len", descending=True).unique("player_id", keep="first")
        _POS_CACHE.update(dict(zip(m["player_id"].to_list(), m["pg"].to_list())))
        _FWD_CACHE.update({k: v == "F" for k, v in _POS_CACHE.items()})  # built ONCE
    return _POS_CACHE


def deployment_over(deploy: pl.DataFrame, game_ids: list[int], team_id: int,
                    min_start_toi_min: float = 50.0) -> dict:
    d = deploy.filter(pl.col("game_id").is_in(game_ids) & (pl.col("team_id") == team_id))
    if d.height == 0:
        return {"top6_fwd_toi_share": None, "zone_start_polarization": None}
    pl_agg = d.group_by("pid").agg(toi=pl.col("toi_sec").sum(),
                                   oz=pl.col("oz_starts").sum(), dz=pl.col("dz_starts").sum())
    _positions()  # ensure caches built
    pl_agg = pl_agg.with_columns(
        is_fwd=pl.col("pid").replace_strict(_FWD_CACHE, default=True, return_dtype=pl.Boolean))
    fwd = pl_agg.filter(pl.col("is_fwd")).sort("toi", descending=True)
    top6 = fwd.head(6)["toi"].sum()
    total_fwd = fwd["toi"].sum()
    top6_share = float(top6 / total_fwd) if total_fwd else None
    # zone-start polarization: std of OZ-start share across players with enough starts
    z = pl_agg.with_columns(starts=pl.col("oz") + pl.col("dz")).filter(
        pl.col("toi") >= min_start_toi_min * 60).with_columns(
        oz_share=pl.col("oz") / (pl.col("oz") + pl.col("dz")))
    z = z.filter((pl.col("oz") + pl.col("dz")) > 0)
    pol = float(z["oz_share"].std()) if z.height > 2 else None
    return {"top6_fwd_toi_share": top6_share, "zone_start_polarization": pol}


if __name__ == "__main__":
    import sys
    seasons = sys.argv[1:] or config.SEASONS_ALL
    for s in seasons:
        fp = PRIM_DIR / f"{s.replace('-', '_')}.parquet"
        dp = DEPLOY_DIR / f"{s.replace('-', '_')}.parquet"
        if not fp.exists():
            build_primitives(s)
        if not dp.exists():
            build_deploy(s)
        print(s, "done", flush=True)
