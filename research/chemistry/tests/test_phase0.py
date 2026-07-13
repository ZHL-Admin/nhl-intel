"""Phase 0 tests — frozen inputs present + isolation invariants."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from chem import config  # noqa: E402


def test_frozen_atlas_inputs_present():
    for f in ("stints.parquet", "events.parquet", "player_5v5.parquet",
              "rapm_variant.parquet", "movers_eval.parquet"):
        assert (config.ATLAS_PARQUET / f).exists(), f
    assert (config.ATLAS_SRC / "atlas" / "api.py").exists()


def test_frozen_syseff_inputs_present():
    for f in ("player_types.parquet", "team_season_fp.parquet",
              "regime_ledger.parquet", "regime_ledger_consolidated.parquet"):
        assert (config.SYSEFF_PARQUET / f).exists(), f
    assert (config.SYSEFF_SRC / "syseff" / "api.py").exists()


def test_seed_and_paths():
    assert config.SEED == 20260712
    assert config.ROOT.name == "chemistry"
    # data/ is gitignored and self-contained
    assert config.PARQUET == config.ROOT / "data" / "parquet"
