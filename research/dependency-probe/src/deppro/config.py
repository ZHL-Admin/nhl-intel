"""Shared config for the dependency probe. Paths, seed, READ-ONLY frozen inputs.

Discipline (see the probe preamble):
  - SEED fixed and recorded; every stochastic step consumes it.
  - Atlas, System Effects, Chemistry, and role-fit-probe assets are READ-ONLY frozen inputs.
  - Reuse the role-fit-probe ENRICHED corpus (recovered six-column attribution, validated + hashed)
    and the Chemistry stint-expansion machinery; never rewrite. If the enriched corpus is missing,
    STOP (this probe depends on it).
  - No external fetch; frozen / already-ingested-read corpus only.
  - Standing confound: behavioral dependency is tangled with DEPLOYMENT; control it everywhere.
  - Proxy honesty: the feeding signal is shot-adjacent sequence inference, NOT true passing (Tier iii).
"""
from __future__ import annotations

import sys
from pathlib import Path

SEED = 20260713    # "20260713b" per preamble; int form for numpy rng
SEED_TAG = "20260713b"

ROOT = Path(__file__).resolve().parents[2]           # research/dependency-probe/
DATA = ROOT / "data"
PARQUET = DATA / "parquet"
REPORTS = ROOT / "reports"

ATLAS_ROOT = ROOT.parent / "deployment-atlas"
ATLAS_PARQUET = ATLAS_ROOT / "data" / "parquet"
ATLAS_SRC = ATLAS_ROOT / "src"

SYSEFF_ROOT = ROOT.parent / "system-effects"
SYSEFF_PARQUET = SYSEFF_ROOT / "data" / "parquet"

CHEM_ROOT = ROOT.parent / "chemistry"
CHEM_SRC = CHEM_ROOT / "src"

# role-fit-probe enriched corpus (REQUIRED) + two-way role axes.
ROLEFIT_ROOT = ROOT.parent / "role-fit-probe"
ROLEFIT_SRC = ROLEFIT_ROOT / "src"
ENRICH_DIR = ROLEFIT_ROOT / "data" / "parquet" / "enriched"
RICH_PROFILE_DIR = ROLEFIT_ROOT / "data" / "parquet" / "profiles_rich"

for _p in (CHEM_SRC, ATLAS_SRC, ROLEFIT_SRC):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

SEASONS_ALL = [f"{y}-{str(y+1)[2:]}" for y in range(2010, 2026)]
SEASONS_PRIMARY = [f"{y}-{str(y+1)[2:]}" for y in range(2015, 2026)]   # is_primary_scope window
