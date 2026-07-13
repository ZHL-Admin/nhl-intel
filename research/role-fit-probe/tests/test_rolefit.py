"""role-fit-probe tests — Step 0 inventory invariants + Link 1 profile/stability plumbing.

Fast checks on real frozen inputs; nothing writes to data/. 2024-25 is the probe season; the
stability sanity uses three recent seasons built in-memory.
"""
import sys
from pathlib import Path

import numpy as np
import polars as pl
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from rolefit import config, profiles as P, link1, link1_rich, units as U  # noqa: E402

SEASON = "2024-25"


def test_frozen_inputs_present():
    for p in ("stints.parquet", "events.parquet", "shot_xg.parquet", "rapm_variant.parquet"):
        assert (config.ATLAS_PARQUET / p).exists(), p
    assert (config.CHEM_PARQUET / "frozen" / "pairs_corpus.parquet").exists()


def test_chem_reuse_imports_and_runs():
    import chem.corpus as cc
    st = cc._stints(SEASON)
    assert st.height > 100_000 and "rid" in st.columns


def test_only_shot_events_carry_a_player():
    ev = pl.scan_parquet(config.ATLAS_PARQUET / "events.parquet")
    hit = ev.filter(pl.col("type_desc_key") == "hit").select(
        pl.col("shooting_player_id").is_not_null().sum()).collect().item()
    sog = ev.filter(pl.col("type_desc_key") == "shot-on-goal").select(
        (pl.col("shooting_player_id").is_not_null()).mean()).collect().item()
    assert hit == 0                    # hustle events carry no player -> unusable for role
    assert sog > 0.99                  # shots are player-attributed


@pytest.fixture(scope="module")
def prof():
    return P.build_profiles(SEASON, write=False)


def test_profile_half_reconstitutes_season(prof):
    r = prof.with_columns(s=pl.col("toi_odd").fill_null(0) + pl.col("toi_even").fill_null(0))
    assert (r["toi"] - r["s"]).abs().max() == 0


def test_profiles_face_valid_by_position(prof):
    big = prof.filter(pl.col("toi") > 6000)
    f = big.filter(pl.col("pg") == "F"); d = big.filter(pl.col("pg") == "D")
    assert d["mean_dist"].median() > f["mean_dist"].median()      # D shoot from farther (point)
    assert f["slot_share"].median() > d["slot_share"].median()    # F shoot from the slot
    assert f["xg_per_shot"].median() > d["xg_per_shot"].median()  # F shots more dangerous


def test_top_role_axis_is_stable_and_beats_placebo():
    prof = pl.concat([P.build_profiles(s, write=False)
                      for s in ("2022-23", "2023-24", "2024-25")], how="vertical_relaxed")
    stats, spaces = link1.fit_role_space(prof)
    sh = link1.split_half(prof, stats, spaces)
    top = sh["F"]["PC1"]                # forward shot-location axis
    assert top["r"] > 0.45             # clearly reliable within season
    assert top["r"] > top["placebo_r"] + 0.2 and top["p"] < 0.05


# ---- UL-P1 enriched two-way path (skips cleanly if the authorized BQ pull hasn't been run) ----
_HAS_ENRICH = (P.ENRICH_DIR / "event_players.parquet").exists()
enrich_only = pytest.mark.skipif(not _HAS_ENRICH, reason="enriched parquet absent (run make enrich)")


@enrich_only
def test_enriched_join_recovers_attribution():
    ev = (pl.scan_parquet(config.ATLAS_PARQUET / "events.parquet")
          .filter((pl.col("season_label") == SEASON) & (pl.col("situation_code") == "1551")
                  & (pl.col("type_desc_key") == "hit")).select("game_id", "event_id").collect())
    epl = pl.read_parquet(P.ENRICH_DIR / "event_players.parquet")
    j = ev.join(epl, on=["game_id", "event_id"], how="left")
    assert j["hitting_player_id"].is_not_null().mean() > 0.99   # hits now carry the hitter


@enrich_only
def test_rich_profile_two_way_axes_face_valid():
    pr = P.build_profiles_rich(SEASON, write=False)
    big = pr.filter(pl.col("toi") > 6000)
    f, d = big.filter(pl.col("pg") == "F"), big.filter(pl.col("pg") == "D")
    assert d["block60"].median() > f["block60"].median()      # D block more shots
    assert set(P.INDIV_NEW + P.UNIT_AXES) <= set(pr.columns)
    assert pr.filter(pl.col("hit60") > 0).height > 500          # hits attributed to players


@enrich_only
def test_hit_axis_is_the_most_stable_and_player_carried():
    prof = pl.concat([P.build_profiles_rich(s, write=False)
                      for s in ("2022-23", "2023-24", "2024-25")], how="vertical_relaxed")
    stab = link1_rich.raw_axis_stability(prof)
    hit = stab["F"]["hit60"]
    assert hit["split_half_r"] > 0.85 and hit["yoy_same_r"] > 0.75   # physicality: a strong signature
    # unit suppression is NOT player-carried: much lower cross-team retention than an individual axis
    assert stab["D"]["xga60"]["retained_frac"] < stab["D"]["hit60"]["retained_frac"]


# ---- Link 2: units ----
def test_five_man_units_are_too_sparse_to_model():
    fm = U.five_man_distribution(SEASON)
    assert fm["ge_100min"] < 100                # only a few dozen fivesomes recur -> not a usable unit
    assert fm["toi_min_p50"] < 5                 # the median five-man set plays together for seconds


def test_trio_unit_halves_reconstitute_season():
    u = U.build_trio_units(SEASON, write=False)
    r = u.with_columns(s=pl.col("toi_odd").fill_null(0) + pl.col("toi_even").fill_null(0))
    assert (r["toi"] - r["s"]).abs().max() == 0
    assert u.filter(pl.col("toi") >= U.TRIO_FLOOR_SEC).height > 100   # trios are the tractable unit
