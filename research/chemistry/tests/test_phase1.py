"""Phase 1 tests — pair/trio corpus integrity on a freshly-built season (no writes).

Uses 2024-25 as the probe season (fast, ~4s). Asserts the 1.3 invariants directly on in-memory
frames so the suite is self-contained and leaves data/ untouched.
"""
import sys
from pathlib import Path

import polars as pl
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from chem import config, corpus  # noqa: E402

SEASON = "2024-25"


@pytest.fixture(scope="module")
def st():
    return corpus._stints(SEASON)


@pytest.fixture(scope="module")
def pairs():
    return corpus.build_pairs(SEASON, write=False)


def test_row_id_is_unique(st):
    # the whole expansion depends on rid being globally unique (stint_id is only game-local).
    assert st["rid"].n_unique() == st.height
    assert st.select("game_id", "stint_id").unique().height == st.height


def test_canonical_ordering_and_uniqueness(pairs):
    assert bool((pairs["a"] < pairs["b"]).all())                       # 1.3(a) a<b everywhere
    keys = pairs.select("season_label", "team_id", "a", "b")
    assert keys.unique().height == pairs.height                        # no duplicate orderings


def test_floor_and_tiers(pairs):
    assert pairs["toi"].min() >= corpus.FLOOR_SEC                      # 50-min floor respected
    assert set(pairs["tier"].unique().to_list()) <= {50, 100, 200}


def test_expected_columns(pairs):
    need = {"a", "b", "team_id", "toi", "xgf", "xga", "cf", "ca", "gf", "ga",
            "oz_start_share", "opp_rapm", "share_lead", "share_tied", "share_trail",
            "a_without_toi", "a_without_xg_share", "b_without_toi", "b_without_xg_share",
            "pos_pair", "season_label", "tier"}
    assert need <= set(pairs.columns)


def test_pos_pair_domain(pairs):
    assert set(pairs["pos_pair"].unique().to_list()) <= {"D-D", "D-F", "F-F"}


def test_shares_in_unit_interval(pairs):
    for c in ("xg_share", "oz_start_share", "share_lead", "share_tied", "share_trail"):
        sub = pairs.filter(pl.col(c).is_not_null())
        assert sub[c].min() >= 0.0 and sub[c].max() <= 1.0, c


def test_conservation_identity(st):
    # 1.3(b): partner-summed shared TOI == 4 x player 5v5 TOI (each stint => 4 teammate pairs).
    c = corpus.conservation(SEASON, st=st)
    assert (c["ratio"] - 4.0).abs().max() <= 1e-6


def test_reconciliation_vs_player5v5(st):
    # 1.3(c): derived on-ice aggregates match the frozen Atlas player_5v5 source of record.
    o = corpus.build_player_onice(SEASON, write=False, st=st)
    p5 = (pl.read_parquet(config.ATLAS_PARQUET / "player_5v5.parquet")
          .filter(pl.col("season_label") == SEASON).select("player_id", "toi_s", "xgf"))
    m = o.join(p5, on="player_id", how="inner").with_columns(
        tr=pl.col("toi") / pl.col("toi_s"), xr=pl.col("xgf") / pl.col("xgf_right"))
    assert abs(m["tr"].median() - 1.0) < 1e-3
    assert abs(m["xr"].median() - 1.0) < 1e-3
