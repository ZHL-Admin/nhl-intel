"""Shared config for the role-fit probe. Paths, seed, and READ-ONLY frozen inputs.

Discipline (see the probe preamble):
  - SEED is fixed and recorded; every stochastic step consumes it.
  - Atlas, System Effects, and Chemistry assets are READ-ONLY frozen inputs. Never write under them.
  - The Chemistry stint-expansion utility is REUSED (brute-force validated, 1497=1497), not rewritten.
  - No external fetching; this is a frozen-corpus probe.
"""
from __future__ import annotations

import sys
from pathlib import Path

SEED = 20260713

ROOT = Path(__file__).resolve().parents[2]           # research/role-fit-probe/
DATA = ROOT / "data"
PARQUET = DATA / "parquet"
REPORTS = ROOT / "reports"

# READ-ONLY frozen Deployment Atlas assets.
ATLAS_ROOT = ROOT.parent / "deployment-atlas"
ATLAS_PARQUET = ATLAS_ROOT / "data" / "parquet"
ATLAS_SRC = ATLAS_ROOT / "src"

# READ-ONLY frozen System Effects assets.
SYSEFF_ROOT = ROOT.parent / "system-effects"
SYSEFF_PARQUET = SYSEFF_ROOT / "data" / "parquet"

# READ-ONLY frozen Chemistry assets — REUSE its validated stint-expansion machinery.
CHEM_ROOT = ROOT.parent / "chemistry"
CHEM_SRC = CHEM_ROOT / "src"
CHEM_PARQUET = CHEM_ROOT / "data" / "parquet"

# Put Chemistry (and Atlas) src on the path so `import chem.corpus` / `atlas.api` work.
for _p in (CHEM_SRC, ATLAS_SRC):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

SEASONS_ALL = [f"{y}-{str(y+1)[2:]}" for y in range(2010, 2026)]     # 2010-11 .. 2025-26
SEASONS_PRIMARY = [f"{y}-{str(y+1)[2:]}" for y in range(2015, 2026)]
