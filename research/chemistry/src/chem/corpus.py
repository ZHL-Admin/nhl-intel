"""Phase 1 — the pair (and trio) performance corpus, derived from frozen Atlas stints.

5v5, regular season, ice-derived strength, quarantined stints excluded, exactly-5-per-side.
Pair outcomes are computed by a vectorized both-on-ice expansion: each 5v5 stint's 5 same-side
skaters expand to their C(5,2)=10 unordered teammate pairs (a<b) via fixed list indices — no Python
UDF, ~1.4 s/season. Each stint carries a unique row index (`rid`); the stint's own `stint_id` is
only game-local (0..~500) and MUST NOT be used as a join/group key across games.

Grain: pair-team-season (season, team_id, player_a < player_b) — matches mart_player_toi_matrix.
Outcomes during shared TOI: xGF/xGA, CF/CA, GF/GA. Context: OZ-start share, score-state mix,
opponent strength faced (TOI-weighted variant-RAPM of the opposing 5), position pair. Each player's
WITHOUT-partner split is his season on-ice total minus the together portion (WOWY), computed from
the SAME stint source for internal consistency. Every stint source is regular-season-only by
construction (the frozen Atlas stints carry zero playoff stints; the ~is_playoffs filter is a
recorded belt-and-braces guard).
"""
from __future__ import annotations

import itertools

import polars as pl

from . import config

PAIR_DIR = config.PARQUET / "pairs"
ONICE_DIR = config.PARQUET / "player_onice"
TRIO_DIR = config.PARQUET / "trios"
FLOOR_SEC = 3000    # 50 shared minutes (pairs)
TRIO_FLOOR_SEC = 6000   # 100 shared minutes (forward trios)

_PAIR_IDX = list(itertools.combinations(range(5), 2))   # the 10 canonical within-side pairs

# team_id is NOT on the stint table — it is joined from games.parquet by game_id (Atlas convention).
_STINT_COLS = ["game_id", "stint_id", "season_label", "duration_seconds", "home_skater_ids",
               "away_skater_ids", "home_xg", "away_xg", "home_corsi", "away_corsi",
               "home_goals", "away_goals", "score_state", "start_type", "is_quarantined",
               "is_playoffs", "strength_state"]

# per-side selection recipe: (skater_ids, xgf, xga, cf, ca, gf, ga, team, oz, dz, opp_rapm, sign)
# away OZ = home DZ and vice-versa; away score-state = -home score-state.
_SIDES = {
    "home": ("home_skater_ids", "home_xg", "away_xg", "home_corsi", "away_corsi",
             "home_goals", "away_goals", "home_team_id", "home_oz", "home_dz", "away_avg_rapm", 1),
    "away": ("away_skater_ids", "away_xg", "home_xg", "away_corsi", "home_corsi",
             "away_goals", "home_goals", "away_team_id", "home_dz", "home_oz", "home_avg_rapm", -1),
}


def _stints(season: str) -> pl.DataFrame:
    # scan + project + filter (lazy) so only the season's 5v5 stint columns are materialized —
    # avoids holding the full 5.9M-row corpus in memory. team_id joined from games; `rid` is a
    # globally-unique per-row key (stint_id alone is only game-local, 0..~500).
    st = (pl.scan_parquet(config.ATLAS_PARQUET / "stints.parquet")
          .select(_STINT_COLS)
          .filter((pl.col("season_label") == season) & (~pl.col("is_quarantined"))
                  & (~pl.col("is_playoffs"))
                  & (pl.col("strength_state") == "5v5")
                  & (pl.col("home_skater_ids").list.len() == 5)
                  & (pl.col("away_skater_ids").list.len() == 5))
          .collect())
    g = pl.read_parquet(config.ATLAS_PARQUET / "games.parquet",
                        columns=["game_id", "home_team_id", "away_team_id"])
    return st.join(g, on="game_id", how="left").with_row_index("rid")


def _rapm_map(season: str) -> dict:
    r = pl.read_parquet(config.ATLAS_PARQUET / "rapm_variant.parquet").filter(pl.col("season") == season)
    return dict(zip(r["player_id"].to_list(), (r["off_impact"] + r["def_impact"]).to_list()))


def _pos_frame() -> pl.DataFrame:
    """Global most-common F/D per player (skaters only). Position is a slowly-varying attribute;
    the season-invariant modal group is adequate for the pos_pair label. Returns (player_id, pg)."""
    ros = pl.read_parquet(config.ATLAS_PARQUET / "rosters.parquet",
                          columns=["player_id", "position_code", "is_goalie"]).filter(~pl.col("is_goalie"))
    ros = ros.with_columns(pg=pl.when(pl.col("position_code") == "D").then(pl.lit("D")).otherwise(pl.lit("F")))
    return (ros.group_by("player_id", "pg").len().sort("len", descending=True)
            .unique("player_id", keep="first").select("player_id", "pg"))


def _pos_map() -> dict:
    pf = _pos_frame()
    return dict(zip(pf["player_id"].to_list(), pf["pg"].to_list()))


def _opp_rapm_per_stint(st: pl.DataFrame, rmap: dict) -> pl.DataFrame:
    """Per stint (keyed by rid): mean variant-RAPM of each side's 5 skaters (the opponent faces
    the other side)."""
    def side_mean(ids, alias):
        d = st.select("rid", pl.col(ids).alias("sk")).explode("sk").with_columns(
            q=pl.col("sk").replace_strict(rmap, default=0.0, return_dtype=pl.Float64))
        return d.group_by("rid").agg(pl.col("q").mean().alias(alias))
    return (st.select("rid")
            .join(side_mean("home_skater_ids", "home_avg_rapm"), on="rid", how="left")
            .join(side_mean("away_skater_ids", "away_avg_rapm"), on="rid", how="left"))


# ---------------------------------------------------------------- player-season on-ice (5v5)
def build_player_onice(season: str, write: bool = True, st: pl.DataFrame | None = None) -> pl.DataFrame:
    if st is None:
        st = _stints(season)

    def side(ids, xgf, xga, cf, ca, gf, ga, team):
        return st.select(pl.col(ids).alias("pid"), pl.col(team).alias("team_id"),
                         dur=pl.col("duration_seconds"), xgf=pl.col(xgf), xga=pl.col(xga),
                         cf=pl.col(cf), ca=pl.col(ca), gf=pl.col(gf), ga=pl.col(ga)).explode("pid")
    home = side("home_skater_ids", "home_xg", "away_xg", "home_corsi", "away_corsi", "home_goals", "away_goals", "home_team_id")
    away = side("away_skater_ids", "away_xg", "home_xg", "away_corsi", "home_corsi", "away_goals", "home_goals", "away_team_id")
    out = pl.concat([home, away]).group_by("pid", "team_id").agg(
        toi=pl.col("dur").sum(), xgf=pl.col("xgf").sum(), xga=pl.col("xga").sum(),
        cf=pl.col("cf").sum(), ca=pl.col("ca").sum(), gf=pl.col("gf").sum(), ga=pl.col("ga").sum())
    # collapse to player-season (sum across teams) for WOWY 'without' arithmetic
    ps = out.group_by("pid").agg(pl.col(["toi", "xgf", "xga", "cf", "ca", "gf", "ga"]).sum()).with_columns(
        season_label=pl.lit(season)).rename({"pid": "player_id"})
    if write:
        ONICE_DIR.mkdir(parents=True, exist_ok=True)
        ps.write_parquet(ONICE_DIR / f"{season.replace('-', '_')}.parquet")
    return ps


# ---------------------------------------------------------------- pair corpus
def _side_pairs(st: pl.DataFrame, side: str) -> pl.DataFrame:
    """Per-side both-on-ice expansion via fixed list indices, keyed on the unique row id `rid`:
    build the 10 canonical (a<b) key rows, then attach the stint's outcomes/context once by joining
    the one-row-per-rid metrics frame (rid is unique, so the join is exactly 10 rows per stint)."""
    ids, xgf, xga, cf, ca, gf, ga, team, oz, dz, opp, sign = _SIDES[side]
    base = st.select(
        rid=pl.col("rid"), sk=pl.col(ids), team_id=pl.col(team),
        dur=pl.col("duration_seconds"), xgf=pl.col(xgf), xga=pl.col(xga),
        cf=pl.col(cf), ca=pl.col(ca), gf=pl.col(gf), ga=pl.col(ga),
        oz=pl.col(oz), dz=pl.col(dz), opp_rapm=pl.col(opp),
        rel_score=pl.col("score_state") * sign)
    keys = pl.concat([
        base.select("rid",
                    a=pl.min_horizontal(pl.col("sk").list.get(i), pl.col("sk").list.get(j)),
                    b=pl.max_horizontal(pl.col("sk").list.get(i), pl.col("sk").list.get(j)))
        for i, j in _PAIR_IDX])
    return keys.join(base.drop("sk"), on="rid")


def build_pairs(season: str, write: bool = True) -> pl.DataFrame:
    st = _stints(season).with_columns(
        home_oz=(pl.col("start_type") == "OZ"), home_dz=(pl.col("start_type") == "DZ"))
    rmap = _rapm_map(season)
    st = st.join(_opp_rapm_per_stint(st, rmap), on="rid", how="left")

    allp = pl.concat([_side_pairs(st, "home"), _side_pairs(st, "away")])
    agg = allp.group_by("a", "b", "team_id").agg(
        toi=pl.col("dur").sum(), xgf=pl.col("xgf").sum(), xga=pl.col("xga").sum(),
        cf=pl.col("cf").sum(), ca=pl.col("ca").sum(), gf=pl.col("gf").sum(), ga=pl.col("ga").sum(),
        oz_starts=pl.col("oz").sum(), dz_starts=pl.col("dz").sum(),
        opp_rapm=(pl.col("opp_rapm") * pl.col("dur")).sum() / pl.col("dur").sum(),
        toi_lead=pl.col("dur").filter(pl.col("rel_score") > 0).sum(),
        toi_tied=pl.col("dur").filter(pl.col("rel_score") == 0).sum(),
        toi_trail=pl.col("dur").filter(pl.col("rel_score") < 0).sum())
    agg = agg.filter(pl.col("toi") >= FLOOR_SEC).with_columns(
        season_label=pl.lit(season),
        oz_start_share=pl.when(pl.col("oz_starts") + pl.col("dz_starts") > 0)
        .then(pl.col("oz_starts") / (pl.col("oz_starts") + pl.col("dz_starts"))).otherwise(None),
        xg_share=pl.col("xgf") / (pl.col("xgf") + pl.col("xga")),
        share_lead=pl.col("toi_lead") / pl.col("toi"), share_tied=pl.col("toi_tied") / pl.col("toi"),
        share_trail=pl.col("toi_trail") / pl.col("toi"),
        tier=pl.when(pl.col("toi") >= 12000).then(200).when(pl.col("toi") >= 6000).then(100).otherwise(50))

    # WOWY 'without' splits (vectorized): player season on-ice total minus the together portion.
    ps = build_player_onice(season, write=True, st=st)
    for who in ("a", "b"):
        agg = agg.join(ps.select(pl.col("player_id"), pl.col("toi").alias(f"{who}_tot_toi"),
                                 pl.col("xgf").alias(f"{who}_tot_xgf"), pl.col("xga").alias(f"{who}_tot_xga")),
                       left_on=who, right_on="player_id", how="left")
        wf = pl.col(f"{who}_tot_xgf") - pl.col("xgf"); wa = pl.col(f"{who}_tot_xga") - pl.col("xga")
        agg = agg.with_columns(
            **{f"{who}_without_toi": pl.col(f"{who}_tot_toi") - pl.col("toi"),
               f"{who}_without_xg_share": pl.when((wf + wa) > 0).then(wf / (wf + wa)).otherwise(None)}
        ).drop(f"{who}_tot_toi", f"{who}_tot_xgf", f"{who}_tot_xga")

    # position pair (D-D / D-F / F-F) from the global modal F/D map
    pf = _pos_frame()
    for who in ("a", "b"):
        agg = agg.join(pf.rename({"player_id": who, "pg": f"{who}_pg"}), on=who, how="left")
    agg = agg.with_columns(
        pos_pair=pl.when(pl.col("a_pg").fill_null("F") <= pl.col("b_pg").fill_null("F"))
        .then(pl.col("a_pg").fill_null("F") + "-" + pl.col("b_pg").fill_null("F"))
        .otherwise(pl.col("b_pg").fill_null("F") + "-" + pl.col("a_pg").fill_null("F"))
    ).drop("a_pg", "b_pg")

    if write:
        PAIR_DIR.mkdir(parents=True, exist_ok=True)
        agg.write_parquet(PAIR_DIR / f"{season.replace('-', '_')}.parquet")
    return agg


# ---------------------------------------------------------------- forward-trio corpus
def build_trios(season: str, write: bool = True) -> pl.DataFrame:
    """Forward trios: a stint 'belongs to' a trio when EXACTLY 3 of a side's 5 skaters are forwards
    (matches int_line_seasons' F3 definition). 100-shared-minute floor. Outcomes + OZ/opp context.
    Grouping is on the unique row id `rid`, never the game-local stint_id."""
    st = _stints(season).with_columns(
        home_oz=(pl.col("start_type") == "OZ"), home_dz=(pl.col("start_type") == "DZ"))
    rmap = _rapm_map(season)
    st = st.join(_opp_rapm_per_stint(st, rmap), on="rid", how="left")
    pf = _pos_frame()

    def side(ids, xgf, xga, cf, ca, gf, ga, team, oz, dz, opp):
        d = st.select("rid", pl.col(ids).alias("sk"), pl.col(team).alias("team_id"),
                      dur=pl.col("duration_seconds"), xgf=pl.col(xgf), xga=pl.col(xga),
                      cf=pl.col(cf), ca=pl.col(ca), gf=pl.col(gf), ga=pl.col(ga),
                      oz=pl.col(oz), dz=pl.col(dz), opp_rapm=pl.col(opp))
        ex = (d.select("rid", "sk").explode("sk")
              .join(pf.rename({"player_id": "sk"}), on="sk", how="left")
              .with_columns(pg=pl.col("pg").fill_null("F")))
        fwd = ex.filter(pl.col("pg") == "F").group_by("rid").agg(
            fwds=pl.col("sk").sort(), nf=pl.len()).filter(pl.col("nf") == 3)
        return d.join(fwd, on="rid", how="inner").with_columns(
            f1=pl.col("fwds").list.get(0), f2=pl.col("fwds").list.get(1), f3=pl.col("fwds").list.get(2))

    home = side("home_skater_ids", "home_xg", "away_xg", "home_corsi", "away_corsi", "home_goals", "away_goals", "home_team_id", "home_oz", "home_dz", "away_avg_rapm")
    away = side("away_skater_ids", "away_xg", "home_xg", "away_corsi", "home_corsi", "away_goals", "home_goals", "away_team_id", "home_dz", "home_oz", "home_avg_rapm")
    allt = pl.concat([home, away])
    agg = allt.group_by("f1", "f2", "f3", "team_id").agg(
        toi=pl.col("dur").sum(), xgf=pl.col("xgf").sum(), xga=pl.col("xga").sum(),
        cf=pl.col("cf").sum(), ca=pl.col("ca").sum(), gf=pl.col("gf").sum(), ga=pl.col("ga").sum(),
        oz_starts=pl.col("oz").sum(), dz_starts=pl.col("dz").sum(),
        opp_rapm=(pl.col("opp_rapm") * pl.col("dur")).sum() / pl.col("dur").sum(),
    ).filter(pl.col("toi") >= TRIO_FLOOR_SEC).with_columns(
        season_label=pl.lit(season), xg_share=pl.col("xgf") / (pl.col("xgf") + pl.col("xga")),
        oz_start_share=pl.when(pl.col("oz_starts") + pl.col("dz_starts") > 0)
        .then(pl.col("oz_starts") / (pl.col("oz_starts") + pl.col("dz_starts"))).otherwise(None))
    if write:
        TRIO_DIR.mkdir(parents=True, exist_ok=True)
        agg.write_parquet(TRIO_DIR / f"{season.replace('-', '_')}.parquet")
    return agg


# ---------------------------------------------------------------- integrity helpers
def partner_toi_long(season: str, st: pl.DataFrame | None = None) -> pl.DataFrame:
    """UNFLOORED per (player, partner) shared 5v5 TOI (symmetric long form). Serves the conservation
    identity and the pair-locking distribution (no 50-min floor). Keyed on the unique `rid`."""
    if st is None:
        st = _stints(season)

    def side_pairs(ids):
        base = st.select(rid=pl.col("rid"), sk=pl.col(ids), dur=pl.col("duration_seconds"))
        keys = pl.concat([
            base.select("rid",
                        a=pl.min_horizontal(pl.col("sk").list.get(i), pl.col("sk").list.get(j)),
                        b=pl.max_horizontal(pl.col("sk").list.get(i), pl.col("sk").list.get(j)))
            for i, j in _PAIR_IDX])
        return keys.join(base.select("rid", "dur"), on="rid")
    pairs = pl.concat([side_pairs("home_skater_ids"), side_pairs("away_skater_ids")]).group_by(
        "a", "b").agg(toi=pl.col("dur").sum())
    return pl.concat([pairs.select(pid="a", partner="b", toi="toi"),
                      pairs.select(pid="b", partner="a", toi="toi")])


def conservation(season: str, st: pl.DataFrame | None = None) -> pl.DataFrame:
    """Integrity 1.3(b): each player's UNFLOORED summed shared TOI across partners must equal
    (skaters-on-ice − 1) × his 5v5 on-ice TOI = 4 × player_toi (each stint puts him in 4 pairs)."""
    if st is None:
        st = _stints(season)
    per = partner_toi_long(season, st).group_by("pid").agg(partner_toi=pl.col("toi").sum())
    po = build_player_onice(season, write=False, st=st).rename({"player_id": "pid"})
    return per.join(po.select("pid", "toi"), on="pid", how="inner").with_columns(
        ratio=pl.col("partner_toi") / pl.col("toi"), season_label=pl.lit(season))


if __name__ == "__main__":
    import sys
    import time
    seasons = sys.argv[1:] or config.SEASONS_ALL
    for s in seasons:
        t0 = time.time()
        p = build_pairs(s)
        t = build_trios(s)
        print(f"{s}: pairs>=50min={p.height:,}  fwd_trios>=100min={t.height:,}  ({time.time()-t0:.1f}s)",
              flush=True)
