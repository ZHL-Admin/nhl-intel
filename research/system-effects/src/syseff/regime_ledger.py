"""Phase 1 — the regime ledger: one row per (team, head coach, contiguous game span).

Game universe is the FROZEN Atlas games.parquet (19,149 regular-season games,
2010-11 … 2025-26). Coaches come from the Phase 0 source:
  - 2010-11 … 2023-24  -> right-rail backfill (data/parquet/game_coaches.parquet)
  - 2024-25 … 2025-26  -> warehouse stg_game_context (cached CSV)
game_date is joined from a deduped game_id->date map (single-valued per game_id).

Ordering for regime detection is by (season_start_year, game_id) — schedule order,
frozen and rebuild-invariant — with game_date attached for reporting only. We do NOT
trust production season labels (stg_games/stg_game_context mislabel a block of
2015-16 games as 2024-25; see upstream-ledger); the join-by-game_id to the Atlas
universe filters that out.
"""
from __future__ import annotations

import unicodedata
from pathlib import Path

import polars as pl

from . import config

BACKFILL_PARQUET = config.PARQUET / "game_coaches.parquet"
WH_COACHES_CSV = config.CACHE / "warehouse" / "game_coaches_wh.csv"
DATES_CSV = config.CACHE / "warehouse" / "game_dates.csv"
OUT_LEDGER = config.PARQUET / "regime_ledger.parquet"
WH_SEASONS = ["2024-25", "2025-26"]


# ---------------------------------------------------------------- name normalization
def normalize_name(name: str | None) -> str | None:
    """Coach-name normalization (documented rules; NO hardcoded alias key):
      1. NFC-normalize unicode (accents kept, canonical form).
      2. Straighten curly apostrophes U+2019 -> ' and strip stray control chars.
      3. Trim ends; collapse internal whitespace to a single space.
      4. Preserve proper-name casing as delivered by the feed.
    Genuine cross-era spelling variants are NOT auto-merged here — they are surfaced
    by validate() (same-lastname / small-edit-distance pairs) for eyeball review, so
    the ledger never bakes in an unverified merge.
    """
    if name is None:
        return None
    s = unicodedata.normalize("NFC", str(name))
    s = s.replace("’", "'").replace("‘", "'")
    s = " ".join(s.split())
    return s or None


# ---------------------------------------------------------------- assembly
def assemble_game_coaches() -> pl.DataFrame:
    """One row per game in the frozen universe, with home/away coach attached."""
    games = pl.read_parquet(
        config.ATLAS_PARQUET / "games.parquet",
        columns=["game_id", "season_start_year", "season_label",
                 "home_team_id", "away_team_id"],
    )
    dates = pl.read_csv(DATES_CSV, schema_overrides={"game_id": pl.Int64}).with_columns(
        pl.col("game_date").str.to_date(strict=False)
    )
    games = games.join(dates, on="game_id", how="left")

    frames = []
    if BACKFILL_PARQUET.exists():
        bf = pl.read_parquet(
            BACKFILL_PARQUET,
            columns=["game_id", "home_head_coach", "away_head_coach"],
        ).with_columns(pl.lit("right_rail_backfill").alias("coach_source"))
        frames.append(bf)
    if WH_COACHES_CSV.exists():
        wh = pl.read_csv(WH_COACHES_CSV, schema_overrides={"game_id": pl.Int64})
        wh = wh.select("game_id", "home_head_coach", "away_head_coach").with_columns(
            pl.lit("warehouse_right_rail").alias("coach_source")
        )
        frames.append(wh)
    coaches = pl.concat(frames, how="vertical").unique(subset=["game_id"], keep="first")

    out = games.join(coaches, on="game_id", how="left")
    out = out.with_columns(
        normalize=pl.col("home_head_coach"),  # placeholder; normalized below via map
    ).drop("normalize")
    # normalize both coach columns
    for col in ("home_head_coach", "away_head_coach"):
        out = out.with_columns(
            pl.col(col).map_elements(normalize_name, return_dtype=pl.Utf8).alias(col)
        )
    return out.sort(["season_start_year", "game_id"])


def to_team_games(gc: pl.DataFrame) -> pl.DataFrame:
    """Long form: one row per (game, team) with that team's coach + home flag."""
    home = gc.select(
        "game_id", "season_start_year", "season_label", "game_date",
        pl.col("home_team_id").alias("team_id"),
        pl.col("home_head_coach").alias("coach"),
        pl.lit(True).alias("is_home"), "coach_source",
    )
    away = gc.select(
        "game_id", "season_start_year", "season_label", "game_date",
        pl.col("away_team_id").alias("team_id"),
        pl.col("away_head_coach").alias("coach"),
        pl.lit(False).alias("is_home"), "coach_source",
    )
    return pl.concat([home, away]).sort(["team_id", "season_start_year", "game_id"])


# ---------------------------------------------------------------- ledger
def annotate_regimes(team_games: pl.DataFrame) -> pl.DataFrame:
    """Tag each team-game with a globally-unique regime_seq (contiguous same-coach
    run within a team, schedule-ordered). Shared by build_ledger and the cohorts."""
    tg = team_games.sort(["team_id", "season_start_year", "game_id"])
    tg = tg.with_columns(
        prev_coach=pl.col("coach").shift(1).over("team_id"),
        prev_team=pl.col("team_id").shift(1),
    )
    tg = tg.with_columns(
        is_new_regime=(
            (pl.col("team_id") != pl.col("prev_team"))
            | (pl.col("coach") != pl.col("prev_coach"))
            | pl.col("prev_coach").is_null()
        )
    )
    return tg.with_columns(regime_seq=pl.col("is_new_regime").cum_sum())


def build_ledger(team_games: pl.DataFrame) -> pl.DataFrame:
    """Collapse contiguous same-coach team-game runs into regimes."""
    tg = annotate_regimes(team_games)

    agg = (
        tg.group_by("regime_seq")
        .agg(
            team_id=pl.col("team_id").first(),
            coach_name=pl.col("coach").first(),
            start_game_id=pl.col("game_id").first(),
            end_game_id=pl.col("game_id").last(),
            start_date=pl.col("game_date").first(),
            end_date=pl.col("game_date").last(),
            games_in_regime=pl.len(),
            start_season=pl.col("season_label").first(),
            end_season=pl.col("season_label").last(),
            seasons_list=pl.col("season_label").unique().sort(),
            start_syear=pl.col("season_start_year").first(),
        )
        .sort(["team_id", "start_syear", "start_game_id"])
    )
    # predecessor coach + mid-season flag (previous regime for the SAME team)
    agg = agg.with_columns(
        predecessor_coach=pl.col("coach_name").shift(1).over("team_id"),
        prev_end_season=pl.col("end_season").shift(1).over("team_id"),
    )
    agg = agg.with_columns(
        seasons_spanned=pl.when(pl.col("seasons_list").list.len() == 1)
        .then(pl.col("start_season"))
        .otherwise(pl.col("start_season") + ".." + pl.col("end_season")),
        # mid-season change: has a predecessor AND that predecessor's last game is in
        # the SAME season as this regime's first game (i.e. change was not at a
        # season boundary and not the season's game 1).
        is_mid_season_change=(
            pl.col("predecessor_coach").is_not_null()
            & (pl.col("prev_end_season") == pl.col("start_season"))
        ),
    )
    return agg.select(
        "team_id", "coach_name", "start_game_id", "end_game_id",
        "start_date", "end_date", "games_in_regime", "seasons_spanned",
        "start_season", "end_season", "is_mid_season_change", "predecessor_coach",
    )


def run(write: bool = True) -> pl.DataFrame:
    gc = assemble_game_coaches()
    tg = to_team_games(gc)
    ledger = build_ledger(tg)
    if write:
        OUT_LEDGER.parent.mkdir(parents=True, exist_ok=True)
        ledger.write_parquet(OUT_LEDGER)
    return ledger


if __name__ == "__main__":
    lg = run()
    print(f"regime ledger: {lg.height} regimes")
    print(lg.head(10))
