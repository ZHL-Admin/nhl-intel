"""Link 0 · universe + possession window. Read-only over the goal-tracking fused corpus.

STRENGTH FILTER (fixed): even-strength 5v5 only. The universe is 5v5, reconstruction_ok, with a valid
attack direction. n_def=5 (exactly five defending skaters tracked) is enforced later in tracks.py where
frame occupancy is known. The possession window runs from the attacking team's last clean zone entry (or,
when no in-window entry exists, a capped final-approach fallback) up to the shot release.
"""
from __future__ import annotations

import polars as pl

from . import config as C

MAX_FR = int(C.MAX_WINDOW_S * C.HZ)
MIN_FR = int(C.MIN_WINDOW_S * C.HZ)


def universe() -> pl.DataFrame:
    """5v5 tracked goals-against with defending team, defending net, goalies, and the possession window."""
    f = pl.read_parquet(C.GT_FUSED).filter(
        (pl.col("strength_state") == "5v5") & pl.col("reconstruction_ok") & pl.col("attack_sign").is_not_null()
        & pl.col("release_frame").is_not_null())
    defending = pl.when(pl.col("scoring_team_id") == pl.col("home_team_id")).then(pl.col("away_team_id")).otherwise(pl.col("home_team_id"))
    f = f.with_columns(
        defending_team_id=defending,
        def_goalie_id=pl.when(defending == pl.col("home_team_id")).then(pl.col("home_goalie_id")).otherwise(pl.col("away_goalie_id")),
        net_x=pl.col("attack_sign") * C.NET_X,
        goal_frame=pl.col("release_frame"))
    # window start: use a real in-window entry when present and sane; else capped final-approach fallback.
    has_entry = pl.col("entry_frame").is_not_null() & (pl.col("entry_frame") < pl.col("goal_frame"))
    entry_len = pl.col("goal_frame") - pl.col("entry_frame")
    f = f.with_columns(
        start_frame=pl.when(has_entry & (entry_len <= MAX_FR)).then(pl.col("entry_frame"))
        .otherwise(pl.max_horizontal(pl.lit(0), pl.col("goal_frame") - MAX_FR)).cast(pl.Int64),
        clean_entry=has_entry & (entry_len >= MIN_FR) & (entry_len <= MAX_FR))
    f = f.with_columns(
        win_frames=pl.col("goal_frame") - pl.col("start_frame"),
        win_len_s=(pl.col("goal_frame") - pl.col("start_frame")) / C.HZ)
    f = f.with_columns(short_window=pl.col("win_len_s") < C.MIN_WINDOW_S)
    return f.select(
        "game_id", "event_id", "season", "game_date", "scoring_team_id", "defending_team_id",
        "def_goalie_id", "home_goalie_id", "away_goalie_id", "attack_sign", "net_x",
        "entry_type", "entry_frame", "start_frame", "goal_frame", "arrival_frame", "n_frames",
        "win_frames", "win_len_s", "clean_entry", "short_window",
        "scorer_id", "assist1_id", "assist2_id", "shot_type")


def counts(u: pl.DataFrame) -> dict:
    """Strength-filter accounting for the report (how many goals the 5v5 filter removes)."""
    allg = pl.read_parquet(C.GT_FUSED)
    return {
        "all_tracked_goals": int(allg.filter(pl.col("reconstruction_ok")).height),
        "strength_breakdown": allg["strength_state"].value_counts().sort("count", descending=True).head(10).to_dicts(),
        "kept_5v5_tracked": u.height,
        "removed_non_5v5": int(allg.filter(pl.col("reconstruction_ok")).height) - u.height,
        "with_clean_entry": int(u["clean_entry"].sum()),
        "no_clean_entry": int((~u["clean_entry"]).sum()),
        "short_window": int(u["short_window"].sum()),
    }


if __name__ == "__main__":
    u = universe()
    C.PARQUET.mkdir(parents=True, exist_ok=True)
    u.write_parquet(C.PARQUET / "universe.parquet")
    c = counts(u)
    print(f"5v5 tracked universe: {c['kept_5v5_tracked']:,} goals "
          f"(removed non-5v5: {c['removed_non_5v5']:,} of {c['all_tracked_goals']:,} tracked)")
    print(f"clean entry: {c['with_clean_entry']:,} | no clean entry (fallback window): {c['no_clean_entry']:,} "
          f"| short window flagged: {c['short_window']:,}")
    print("window length s:", {k: round(float(u["win_len_s"].quantile(q)), 2) for k, q in
                                [("p10", .1), ("p25", .25), ("med", .5), ("p75", .75), ("p90", .9)]})
