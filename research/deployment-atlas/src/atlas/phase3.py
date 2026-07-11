"""Phase 3.4: fill stint xGF/xGA from adopted shot_xg, reclassify strength to the
ice, compute per-player 5v5 on-ice rates, reconcile the 3 no-pbp games."""

from __future__ import annotations

import json
from typing import Any

import polars as pl

from . import config, sources, stints

SHOT_XG_PARQUET = config.PARQUET_DIR / "shot_xg.parquet"
PLAYER_5V5_PARQUET = config.PARQUET_DIR / "player_5v5.parquet"
MIN_TOI_PUBLISH_S = 200 * 60   # 200 minutes


def _is5(df: pl.DataFrame) -> pl.Expr:
    return ((df["home_skater_ids"].list.len() == 5) & (df["away_skater_ids"].list.len() == 5)
            & df["home_goalie_id"].is_not_null() & df["away_goalie_id"].is_not_null())


def fill_stint_xg() -> dict[str, Any]:
    """Attribute shot_xg to stints via (start, end] and fill home_xg/away_xg. Also
    report strength reclassifications: shots whose situationCode strength ('1551'
    = 5v5) disagrees with the Atlas stint (shift-derived) strength."""
    st = pl.read_parquet(stints.STINTS_PARQUET)
    games = pl.read_parquet(sources.GAMES_PARQUET).select("game_id", "home_team_id", "away_team_id")
    xg = pl.read_parquet(SHOT_XG_PARQUET).join(games, on="game_id", how="inner").with_columns(
        is_home=pl.col("event_owner_team_id") == pl.col("home_team_id"),
        sit=pl.col("situation_code").str.zfill(4))

    stsel = st.select("game_id", "stint_id", "start_seconds", "end_seconds",
                      "home_skater_ids", "away_skater_ids", "home_goalie_id",
                      "away_goalie_id").sort("game_id", "end_seconds")
    xg = xg.sort("game_id", "event_second").join_asof(
        stsel, left_on="event_second", right_on="end_seconds", by="game_id", strategy="forward"
    ).filter(pl.col("stint_id").is_not_null() & (pl.col("start_seconds") < pl.col("event_second")))

    # strength reclassification: stint 5v5 vs situationCode 5v5
    xg = xg.with_columns(stint_5v5=_is5(xg), sit_5v5=pl.col("sit") == "1551")
    reclass = xg.with_columns(disagree=pl.col("stint_5v5") != pl.col("sit_5v5"))
    reclass_by_season = reclass.group_by("season_start_year").agg(
        pl.len().alias("shots"), pl.col("disagree").sum().alias("reclassified"),
        pl.col("disagree").mean().alias("reclass_rate")).sort("season_start_year")
    # direction
    to_5v5 = reclass.filter(pl.col("stint_5v5") & ~pl.col("sit_5v5")).height   # ice says 5v5, sit says not
    from_5v5 = reclass.filter(~pl.col("stint_5v5") & pl.col("sit_5v5")).height  # sit says 5v5, ice says not

    agg = xg.group_by("game_id", "stint_id").agg(
        pl.col("xg").filter(pl.col("is_home")).sum().alias("home_xg"),
        pl.col("xg").filter(~pl.col("is_home")).sum().alias("away_xg"))
    out = st.drop("home_xg", "away_xg").join(agg, on=["game_id", "stint_id"], how="left").with_columns(
        home_xg=pl.col("home_xg").fill_null(0.0), away_xg=pl.col("away_xg").fill_null(0.0))
    out.write_parquet(stints.STINTS_PARQUET)

    return {
        "total_reclassified": int(reclass["disagree"].sum()),
        "total_shots": reclass.height,
        "reclass_rate": float(reclass["disagree"].mean()),
        "ice_5v5_sit_not": to_5v5, "sit_5v5_ice_not": from_5v5,
        "by_season": reclass_by_season.to_dicts(),
        "total_xg_attributed": float(out["home_xg"].sum() + out["away_xg"].sum()),
    }


def player_5v5_rates() -> dict[str, Any]:
    """Per-player per-season 5v5 on-ice rates (min 200 min for publication)."""
    st = pl.read_parquet(stints.STINTS_PARQUET).filter(_is5(pl.read_parquet(stints.STINTS_PARQUET))
                                                       & ~pl.col("is_quarantined"))
    base = ["game_id", "season_label", "duration_seconds"]

    def side(id_col, xgf, xga, cf, ca, gf, ga):
        return st.select(*base, pl.col(id_col).alias("ids"),
                         pl.col(xgf).alias("xgf"), pl.col(xga).alias("xga"),
                         pl.col(cf).alias("cf"), pl.col(ca).alias("ca"),
                         pl.col(gf).alias("gf"), pl.col(ga).alias("ga")).explode("ids").rename({"ids": "player_id"})

    home = side("home_skater_ids", "home_xg", "away_xg", "home_corsi", "away_corsi", "home_goals", "away_goals")
    away = side("away_skater_ids", "away_xg", "home_xg", "away_corsi", "home_corsi", "away_goals", "home_goals")
    both = pl.concat([home, away]).drop_nulls("player_id")

    agg = both.group_by("player_id", "season_label").agg(
        pl.col("duration_seconds").sum().alias("toi_s"),
        pl.col("xgf").sum(), pl.col("xga").sum(),
        pl.col("cf").sum(), pl.col("ca").sum(),
        pl.col("gf").sum(), pl.col("ga").sum())
    p60 = pl.col("toi_s") / 3600.0
    agg = agg.with_columns(
        toi_min=pl.col("toi_s") / 60.0,
        xgf_per60=pl.col("xgf") / p60, xga_per60=pl.col("xga") / p60,
        xg_share=pl.col("xgf") / (pl.col("xgf") + pl.col("xga")),
        cf_per60=pl.col("cf") / p60, ca_per60=pl.col("ca") / p60,
        gf_per60=pl.col("gf") / p60, ga_per60=pl.col("ga") / p60,
    ).filter(pl.col("toi_s") >= MIN_TOI_PUBLISH_S)
    agg.write_parquet(PLAYER_5V5_PARQUET)
    return {"path": str(PLAYER_5V5_PARQUET), "player_seasons": agg.height,
            "min_toi_min": MIN_TOI_PUBLISH_S / 60}


def reconcile_three_games() -> dict[str, Any]:
    shifts_games = set(pl.read_parquet(sources.SHIFTS_PARQUET)["game_id"].unique().to_list())
    meta_games = set(pl.read_parquet(sources.GAMES_PARQUET)["game_id"].unique().to_list())
    no_meta = sorted(shifts_games - meta_games)
    events = pl.read_parquet(sources.EVENTS_PARQUET)
    gap = ["2023020651", "2024020147"]  # Phase 1's 2 fetched pbp games
    ev_games = set(events["game_id"].unique().to_list())
    return {
        "games_in_shifts_not_meta": no_meta,
        "phase1_gap_games": gap,
        "gap_games_events_present": {g: (int(g) in ev_games) for g in gap},
        "gap_game_event_counts": {g: events.filter(pl.col("game_id") == int(g)).height for g in gap},
        "third_game": sorted(set(no_meta) - {int(g) for g in gap}),
    }


def main() -> int:
    fx = fill_stint_xg()
    pr = player_5v5_rates()
    rc = reconcile_three_games()
    summary = {"fill_xg": fx, "player_5v5": pr, "three_game_reconcile": rc}
    (config.REPORTS_DIR / "phase3_analysis.json").write_text(json.dumps(summary, indent=2, default=str))
    print("reclassified shots:", fx["total_reclassified"], f"({fx['reclass_rate']:.4%})")
    print("  ice=5v5/sit≠5v5:", fx["ice_5v5_sit_not"], " sit=5v5/ice≠5v5:", fx["sit_5v5_ice_not"])
    print("total xG attributed:", round(fx["total_xg_attributed"], 1))
    print("player-seasons (>=200min 5v5):", pr["player_seasons"])
    print("3-game reconcile:", rc["games_in_shifts_not_meta"], "gap events present:", rc["gap_games_events_present"], "third:", rc["third_game"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
