"""Fast Phase 3 tests — read cached artifacts (no rebuild). Guard the invariants the report
relies on: primitives present, context reconciles with Atlas, types assignable for every
200+-min player-season, on-ice xG share well-formed.
"""
import sys
from pathlib import Path

import polars as pl
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from syseff import config, context as C  # noqa: E402

SEASONS = config.SEASONS_ALL


def test_primitives_present():
    for d in (C.PCTX_DIR, C.ONICE_DIR, C.DEPFULL_DIR):
        assert len(list(d.glob("*.parquet"))) == len(SEASONS), f"missing seasons in {d.name}"


def test_context_reconciles_atlas_2024_25():
    """Re-derived multi-season context must match the one materialized Atlas season."""
    # drop our own (player/team) share columns so they do not shadow Atlas's in the join
    ps = C.player_season_context("2024-25").drop("pp_share_of_own", "pk_share_of_own")
    atlas = pl.read_parquet(config.ATLAS_PARQUET / "player_context_2024-25.parquet")
    m = ps.join(atlas, on="player_id", how="inner")
    for mine, atl in [("toi_5v5_min", "toi_5v5_min"), ("oz_start_share", "oz_start_share"),
                      ("pp_frac", "pp_share_of_own"), ("pk_frac", "pk_share_of_own")]:
        mad = m.select((pl.col(mine) - pl.col(atl)).abs().mean()).item()
        assert mad < 0.01, f"{mine} vs Atlas {atl}: mad={mad}"


def test_player_types_cover_all_qualifying():
    t = pl.read_parquet(config.PARQUET / "player_types.parquet")
    n_types = t["type_id"].n_unique()
    assert 6 <= n_types <= 10, f"{n_types} types, expected 6-10"
    # every 200+-min player-season is assigned
    assert t.filter(pl.col("player_type").is_null()).height == 0


def test_onice_share_wellformed():
    o = pl.read_parquet(C.ONICE_DIR / "2024_25.parquet")
    onice = pl.read_parquet(C.ONICE_DIR / "2024_25.parquet")
    # a known team-season aggregate xg share is in (0,1)
    gids = onice["game_id"].unique().to_list()[:50]
    s = C.onice_share(onice, gids, onice["player_id"][0], onice["team_id"][0])
    if s["xg_share"] is not None:
        assert 0.0 <= s["xg_share"] <= 1.0
