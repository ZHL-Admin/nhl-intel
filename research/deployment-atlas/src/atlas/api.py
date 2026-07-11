"""Typed query interface for the Deployment Atlas (Phase 6.2).

Every function returns a polars DataFrame. These read the frozen research-layer
Parquet tables under data/parquet/ (see README.md for the schema freeze). Nothing
here touches production BigQuery.
"""

from __future__ import annotations

import polars as pl

from . import config, stints as stints_mod


def _p(name: str):
    return config.PARQUET_DIR / name


def rapm_table(season: str) -> pl.DataFrame:
    """Atlas-variant RAPM ratings for a season (research-internal rating).

    Columns: player_id, off_impact, def_impact, toi_min, alpha, prior_weight, season.
    Higher = better for both off and def (def is the negated defence coefficient).

    Example:
        >>> from atlas import api
        >>> df = api.rapm_table("2024-25")
        >>> df.sort("off_impact", descending=True).select("player_id", "off_impact").head(3)
    """
    return pl.read_parquet(_p("rapm_variant.parquet")).filter(pl.col("season") == season)


def player_context(player_id: int, season: str) -> pl.DataFrame:
    """Descriptive 5v5 context for a player-season: QoC, QoT, OZ start share,
    matchup strictness, PP/PK shares (from player_context_{season}.parquet).

    Example:
        >>> from atlas import api
        >>> api.player_context(8478402, "2024-25").select("qoc", "qot", "oz_start_share")
    """
    return pl.read_parquet(_p(f"player_context_{season}.parquet")).filter(
        pl.col("player_id") == player_id)


def team_fingerprint(team_id: int, season: str) -> pl.DataFrame:
    """Coach deployment fingerprint for a team-season: top-6 forward TOI
    concentration, home−away matchup strictness, zone-start polarization, and
    close-game bench shortening.

    CAVEAT (Phase 5.6): `home_away_strictness` did NOT pass its last-change
    validation — neither the coarse HHI nor the refined top-line-targeting metric
    showed a home advantage (34–43% of teams positive; refined Wilcoxon p=0.008 in
    the opposite direction). Treat that column as descriptive only; the other three
    metrics validated (bench shortening was positive for all 32 teams).

    Example:
        >>> from atlas import api
        >>> api.team_fingerprint(22, "2024-25").select("top6_fwd_toi_share", "close_game_shortening")
    """
    return pl.read_parquet(_p(f"coach_fingerprints_{season}.parquet")).filter(
        pl.col("team_id") == team_id)


def shared_toi(player_id_a: int, player_id_b: int, season: str,
               relation: str = "with") -> pl.DataFrame:
    """Shared 5v5 TOI between two players in a season, derived from stints.

    relation="with"    -> seconds both were on ice as teammates.
    relation="against" -> seconds they were on ice as opponents.
    Returns one row: (season, player_id_a, player_id_b, relation, toi_seconds).

    Example:
        >>> from atlas import api
        >>> api.shared_toi(8478402, 8477934, "2024-25", "with")   # McDavid & Draisaitl
    """
    if relation not in {"with", "against"}:
        raise ValueError("relation must be 'with' or 'against'")
    st = pl.read_parquet(stints_mod.STINTS_PARQUET).filter(
        (pl.col("season_label") == season) & ~pl.col("is_quarantined")
        & (pl.col("home_skater_ids").list.len() == 5) & (pl.col("away_skater_ids").list.len() == 5))
    a_home = pl.col("home_skater_ids").list.contains(player_id_a)
    b_home = pl.col("home_skater_ids").list.contains(player_id_b)
    a_away = pl.col("away_skater_ids").list.contains(player_id_a)
    b_away = pl.col("away_skater_ids").list.contains(player_id_b)
    if relation == "with":
        mask = (a_home & b_home) | (a_away & b_away)
    else:
        mask = (a_home & b_away) | (a_away & b_home)
    toi = int(st.filter(mask)["duration_seconds"].sum())
    return pl.DataFrame({"season": [season], "player_id_a": [player_id_a],
                         "player_id_b": [player_id_b], "relation": [relation],
                         "toi_seconds": [toi]})
