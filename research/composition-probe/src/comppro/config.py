"""Shared config for the composition probe. Paths, seed, READ-ONLY frozen inputs.

Reuse (never rewrite): Chemistry trios/pairs corpus + null idea, role-fit two-way role axes (rich
profiles) + trio units (with odd/even halves), the additive-plus-curvature null, deployment controls.
Scoped to the primary window 2015-16..2025-26 where the validated style axes exist (role-fit
is_primary_scope; pre-2015 style axes are not validated — see probe.md).
"""
from __future__ import annotations

import sys
from pathlib import Path

SEED = 20260713          # "20260713d"
SEED_TAG = "20260713d"

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data"
PARQUET = DATA / "parquet"
REPORTS = ROOT / "reports"

ATLAS_ROOT = ROOT.parent / "deployment-atlas"
ATLAS_PARQUET = ATLAS_ROOT / "data" / "parquet"
ATLAS_SRC = ATLAS_ROOT / "src"

CHEM_ROOT = ROOT.parent / "chemistry"
CHEM_SRC = CHEM_ROOT / "src"
CHEM_PARQUET = CHEM_ROOT / "data" / "parquet" / "frozen"

ROLEFIT_ROOT = ROOT.parent / "role-fit-probe"
RICH_PROFILE_DIR = ROLEFIT_ROOT / "data" / "parquet" / "profiles_rich"
TRIO_UNIT_DIR = ROLEFIT_ROOT / "data" / "parquet" / "units"
ENRICH_DIR = ROLEFIT_ROOT / "data" / "parquet" / "enriched"

SYSEFF_PARQUET = ROOT.parent / "system-effects" / "data" / "parquet"

for _p in (CHEM_SRC, ATLAS_SRC):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

SEASONS = [f"{y}-{str(y+1)[2:]}" for y in range(2015, 2026)]      # 2015-16 .. 2025-26 (11)
ERA_EARLY = [f"{y}-{str(y+1)[2:]}" for y in range(2015, 2020)]    # 2015-16 .. 2019-20 (5)
ERA_LATE = [f"{y}-{str(y+1)[2:]}" for y in range(2020, 2026)]     # 2020-21 .. 2025-26 (6)
