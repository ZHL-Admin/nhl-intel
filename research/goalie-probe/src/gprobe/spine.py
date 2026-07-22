"""G1.1/G1.2 — the shot spine: one row per unblocked on-goal shot (SOG + goals) with buckets.

THE DENOMINATOR: this is shots FACED (saves + goals), the denominator for every save-performance figure.
Buckets are computable on saves too (that is the whole point); tracking-only buckets are excluded.
Dropped, flagged: rush-vs-in-zone (pbp has no zone-entry sequence; would be fabricated) and one-timer
(not carried by pbp). Kept: shot_type, danger tier (xG), region (location), rebound (spine sequence).
"""
from __future__ import annotations

import duckdb
import polars as pl

from . import bq, config

SPINE = config.PARQUET / "shot_spine.parquet"


def _pull_pbp() -> pl.DataFrame:
    ev = "','".join(config.SHOT_EVENTS)
    seas = "','".join(config.TRACKING_SEASONS)
    return bq.cached_query("pbp_shots", f"""
        select game_id, event_id, season, game_date, period_number, time_in_period, situation_code,
               type_desc_key, x_coord, y_coord, shot_type, goalie_in_net_id, event_owner_team_id,
               coalesce(shooting_player_id, scoring_player_id) as shooter_id,
               home_score, away_score
        from `{config.BQ_PROJECT}.{config.STAGING}.stg_play_by_play`
        where type_desc_key in ('{ev}') and season in ('{seas}')
    """)


def full_span() -> dict:
    ev = "','".join(config.SHOT_EVENTS)
    r = bq.cached_query("pbp_shots_span", f"""
        select min(season) mn, max(season) mx, count(*) n
        from `{config.BQ_PROJECT}.{config.STAGING}.stg_play_by_play`
        where type_desc_key in ('{ev}')""")
    return {"min_season": r["mn"][0], "max_season": r["mx"][0], "n_shots_all_span": int(r["n"][0])}


def _danger(xg):
    for name, lo, hi in config.DANGER_BANDS:
        if xg is not None and lo <= xg < hi:
            return name
    return None


def _region(d):
    for name, lo, hi in config.REGION_BANDS:
        if lo <= d < hi:
            return name
    return None


def build(from_cache: bool = True) -> dict:
    pbp = _pull_pbp().with_columns(
        abs_s=(pl.col("period_number") - 1) * 1200
        + pl.col("time_in_period").str.split(":").list.get(0).cast(pl.Int64) * 60
        + pl.col("time_in_period").str.split(":").list.get(1).cast(pl.Int64),
        is_goal=(pl.col("type_desc_key") == "goal").cast(pl.Int64))
    # xG join
    xg = pl.read_parquet(config.SHOT_XG, columns=["game_id", "event_id", "xg"])
    pbp = pbp.join(xg, on=["game_id", "event_id"], how="left")
    # distance to nearer net, region, danger, shot_type bucket
    pbp = pbp.with_columns(
        dist=((89.0 - pl.col("x_coord").abs()) ** 2 + pl.col("y_coord") ** 2).sqrt())
    pbp = pbp.with_columns(
        region=pl.col("dist").map_elements(_region, return_dtype=pl.Utf8),
        danger=pl.col("xg").map_elements(_danger, return_dtype=pl.Utf8),
        shot_bucket=pl.col("shot_type").replace_strict(config.SHOT_TYPE_MAP, default="other"))
    # rebound: an on-goal shot by the same team within REBOUND_SECONDS of a prior on-goal shot
    pbp = pbp.sort(["game_id", "event_owner_team_id", "abs_s", "event_id"])
    pbp = pbp.with_columns(
        prev_s=pl.col("abs_s").shift(1).over(["game_id", "event_owner_team_id"]))
    pbp = pbp.with_columns(
        rebound=((pl.col("abs_s") - pl.col("prev_s")) <= config.REBOUND_SECONDS)
        & ((pl.col("abs_s") - pl.col("prev_s")) >= 0) & pl.col("prev_s").is_not_null())

    # ice-derived strength via stint interval join (fallback: situationCode)
    st = pl.read_parquet(config.STINTS, columns=["game_id", "start_seconds", "end_seconds", "strength_state"])
    con = duckdb.connect()
    con.register("shots", pbp.select("game_id", "event_id", "abs_s"))
    con.register("st", st)
    cov = con.execute("""
        select s.game_id, s.event_id, any_value(t.strength_state) strength_ice
        from shots s left join st t
          on s.game_id=t.game_id and s.abs_s >= t.start_seconds and s.abs_s < t.end_seconds
        group by 1,2""").pl()
    con.close()
    pbp = pbp.join(cov, on=["game_id", "event_id"], how="left").with_columns(
        strength=pl.coalesce([pl.col("strength_ice"), pl.col("situation_code")]),
        strength_source=pl.when(pl.col("strength_ice").is_not_null()).then(pl.lit("stint")).otherwise(pl.lit("situationCode")))

    spine = pbp.select(
        "game_id", "event_id", "season", "game_date", "goalie_id" if False else pl.col("goalie_in_net_id").alias("goalie_id"),
        "shooter_id", "event_owner_team_id", "x_coord", "y_coord", "dist", "shot_type", "shot_bucket",
        "xg", "danger", "region", "rebound", "is_goal", "abs_s", "strength", "strength_source",
        "home_score", "away_score").with_columns(saved=1 - pl.col("is_goal"))
    config.PARQUET.mkdir(parents=True, exist_ok=True)
    spine.write_parquet(SPINE)

    span = full_span()
    return {"n_shots": spine.height, "n_goalies": spine["goalie_id"].n_unique(),
            "xg_coverage": float(spine["xg"].drop_nulls().len() / spine.height),
            "n_goals": int(spine["is_goal"].sum()), "n_saves": int(spine["saved"].sum()),
            "strength_stint_frac": float((spine["strength_source"] == "stint").mean()),
            "rebound_frac": float(spine["rebound"].mean()),
            "by_season": spine.group_by("season").len().sort("season").to_dicts(),
            "full_span": span}


if __name__ == "__main__":
    import time
    t = time.time()
    r = build()
    print(f"spine: {r['n_shots']:,} shots faced ({r['n_saves']:,} saves + {r['n_goals']:,} goals) "
          f"over {r['n_goalies']} goalies in {time.time()-t:.0f}s")
    print(f"  xG coverage {r['xg_coverage']*100:.1f}% | strength ice-derived {r['strength_stint_frac']*100:.1f}% | rebound {r['rebound_frac']*100:.1f}%")
    print(f"  full shot-data span: {r['full_span']['min_season']}..{r['full_span']['max_season']} "
          f"({r['full_span']['n_shots_all_span']:,} SOG+goals); G1 runs on {config.TRACKING_SEASONS}")
    print("  by season:", r["by_season"])
