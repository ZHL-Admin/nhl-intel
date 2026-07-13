"""composition-probe tests — inputs, style vocabulary stability, and the hard-null gate."""
import sys
from pathlib import Path

import polars as pl

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from comppro import config, styles as S, gate as G  # noqa: E402


def test_frozen_inputs_present():
    assert (config.CHEM_PARQUET / "trios_corpus.parquet").exists()
    assert (config.RICH_PROFILE_DIR / "2024_25.parquet").exists()
    assert (config.TRIO_UNIT_DIR / "trio_2024_25.parquet").exists()
    assert (config.ENRICH_DIR / "player_bio.parquet").exists()


def test_style_vocabulary_stable_above_chance():
    d, km, names = S.fit_vocabulary()
    st = S.stability(d, km)
    assert st["split_half_assignment_agreement"] > 2 * st["chance_agreement"]   # >2x chance
    assert st["yoy_assignment_agreement"] > 2 * st["chance_agreement"]
    assert 12 <= S.K <= 20                                                       # finer vocabulary


def test_recipes_recur_across_player_sets():
    trios, _ = G.load_recipes()
    rc = trios.group_by("recipe").len()
    assert rc.height > 100                          # many distinct recipes
    assert float(rc["len"].median()) >= 2           # recipes recur, unlike specific trios


def test_composition_adds_nothing_beyond_talent_and_style():
    trios, _ = G.load_recipes()
    trios = G._residual(trios)
    reg = G.regression(trios)
    # the whole point: finer composition ingredients add ~0 beyond talent+deployment (Link 2 was ~1%)
    assert reg["incremental_r2_composition"] < 0.03      # far below the 3% ship bar
    mc = G.matched_contrast(trios, n_boot=400)
    assert not mc["ci_excludes_zero"]                    # balanced vs redundant indistinguishable
