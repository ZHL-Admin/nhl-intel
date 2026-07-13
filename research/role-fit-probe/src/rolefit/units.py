"""Link 2.1 — unit corpus from the frozen stints (reused Chemistry expansion).

Primary unit = forward TRIO (a stint 'belongs to' a trio when exactly 3 of a side's 5 skaters are
forwards; matches int_line_seasons' F3 definition and the Chemistry trio corpus). Built per
(trio, team, game) so odd/even split-halves reuse one path, with full-season + half aggregates and
context (OZ-start share, score-state mix, opponent strength). The five-man distribution is reported
to settle 'do fivesomes recur within a season' with data.
"""
from __future__ import annotations

import polars as pl

from . import config
import chem.corpus as cc

UNIT_DIR = config.PARQUET / "units"
TRIO_FLOOR_SEC = 6000        # 100 shared 5v5 minutes


def _prep(season):
    st = cc._stints(season).with_columns(
        home_oz=(pl.col("start_type") == "OZ"), home_dz=(pl.col("start_type") == "DZ"))
    st = st.join(cc._opp_rapm_per_stint(st, cc._rapm_map(season)), on="rid", how="left")
    pf = cc._pos_frame()
    return st, pf


def build_trio_units(season: str, write: bool = True) -> pl.DataFrame:
    st, pf = _prep(season)

    def side(name):
        ids, xgf, xga, cf, ca, gf, ga, team, oz, dz, opp, sign = cc._SIDES[name]
        d = st.select("rid", "game_id", sk=pl.col(ids), team_id=pl.col(team),
                      dur="duration_seconds", xgf=pl.col(xgf), xga=pl.col(xga),
                      oz=pl.col(oz), dz=pl.col(dz), opp_rapm=pl.col(opp),
                      rel_score=pl.col("score_state") * sign)
        ex = (d.select("rid", "sk").explode("sk")
              .join(pf.rename({"player_id": "sk"}), on="sk", how="left")
              .with_columns(pg=pl.col("pg").fill_null("F")))
        fwd = (ex.filter(pl.col("pg") == "F").group_by("rid")
               .agg(fwds=pl.col("sk").sort(), nf=pl.len()).filter(pl.col("nf") == 3))
        return d.join(fwd, on="rid", how="inner").with_columns(
            f1=pl.col("fwds").list.get(0), f2=pl.col("fwds").list.get(1), f3=pl.col("fwds").list.get(2))

    allt = pl.concat([side("home"), side("away")])
    # half = parity of game rank within the trio-team-season
    games = (allt.select("f1", "f2", "f3", "team_id", "game_id").unique()
             .with_columns(rank=pl.col("game_id").rank("dense").over("f1", "f2", "f3", "team_id"))
             .with_columns(half=(pl.col("rank") % 2)))
    allt = allt.join(games.select("f1", "f2", "f3", "team_id", "game_id", "half"),
                     on=["f1", "f2", "f3", "team_id", "game_id"], how="left")

    def agg(df, suffix):
        a = df.group_by("f1", "f2", "f3", "team_id").agg(
            toi=pl.col("dur").sum(), xgf=pl.col("xgf").sum(), xga=pl.col("xga").sum(),
            oz_starts=pl.col("oz").sum(), dz_starts=pl.col("dz").sum(),
            opp_rapm=(pl.col("opp_rapm") * pl.col("dur")).sum() / pl.col("dur").sum(),
            toi_lead=pl.col("dur").filter(pl.col("rel_score") > 0).sum(),
            toi_trail=pl.col("dur").filter(pl.col("rel_score") < 0).sum(),
            n_games=pl.col("game_id").n_unique()).with_columns(
            xg_share=pl.col("xgf") / (pl.col("xgf") + pl.col("xga")),
            oz_start_share=pl.when(pl.col("oz_starts") + pl.col("dz_starts") > 0)
            .then(pl.col("oz_starts") / (pl.col("oz_starts") + pl.col("dz_starts"))).otherwise(None),
            share_lead=pl.col("toi_lead") / pl.col("toi"), share_trail=pl.col("toi_trail") / pl.col("toi"))
        keep = ["f1", "f2", "f3", "team_id", "toi", "xgf", "xga", "xg_share", "oz_start_share",
                "opp_rapm", "share_lead", "share_trail", "n_games"]
        return a.select(keep).rename({c: f"{c}{suffix}" for c in
                                      ["toi", "xgf", "xga", "xg_share", "oz_start_share", "opp_rapm",
                                       "share_lead", "share_trail", "n_games"]})

    full = agg(allt, "")
    odd = agg(allt.filter(pl.col("half") == 1), "_odd")
    even = agg(allt.filter(pl.col("half") == 0), "_even")
    out = (full.join(odd, on=["f1", "f2", "f3", "team_id"], how="left")
           .join(even, on=["f1", "f2", "f3", "team_id"], how="left")
           .with_columns(season_label=pl.lit(season)))
    if write:
        UNIT_DIR.mkdir(parents=True, exist_ok=True)
        out.write_parquet(UNIT_DIR / f"trio_{season.replace('-', '_')}.parquet")
    return out


def five_man_distribution(season: str) -> dict:
    """Settle 'do fivesomes recur within a season': the exact 5-skater set's shared-TOI distribution."""
    st = cc._stints(season)

    def side(ids, team):
        return st.select(team_id=pl.col(team), dur="duration_seconds",
                         five=pl.col(ids).list.sort().cast(pl.List(pl.Int64)))
    allf = pl.concat([side("home_skater_ids", "home_team_id"), side("away_skater_ids", "away_team_id")])
    grp = allf.group_by("team_id", "five").agg(toi=pl.col("dur").sum())
    toi_min = grp["toi"] / 60.0
    return {"season": season, "n_five_units": grp.height,
            "ge_100min": int((toi_min >= 100).sum()), "ge_200min": int((toi_min >= 200).sum()),
            "ge_50min": int((toi_min >= 50).sum()),
            "toi_min_p50": float(toi_min.median()), "toi_min_p90": float(toi_min.quantile(0.9)),
            "toi_min_max": float(toi_min.max())}


if __name__ == "__main__":
    import sys
    for s in sys.argv[1:] or config.SEASONS_PRIMARY:
        u = build_trio_units(s)
        fm = five_man_distribution(s)
        floored = u.filter(pl.col("toi") >= TRIO_FLOOR_SEC).height
        print(f"{s}: trios>=100min={floored:,} (all {u.height:,}) | 5-man units>=100min={fm['ge_100min']} "
              f"(>=50min={fm['ge_50min']}, max={fm['toi_min_max']:.0f}min)", flush=True)
