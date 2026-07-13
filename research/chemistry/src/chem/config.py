"""Shared config for Chemistry. Paths, seed, and READ-ONLY frozen inputs.

Discipline (see reports/phase0.md and the project preamble):
  - SEED is fixed and recorded; every stochastic step must consume it.
  - The Atlas and System Effects assets are READ-ONLY inputs. Never write under them, and never
    touch either project's prospective_20xx directories.
  - Production BigQuery is read-only for this project except the gated Phase 7.
"""
from __future__ import annotations

from pathlib import Path

SEED = 20260712

ROOT = Path(__file__).resolve().parents[2]          # research/chemistry/
DATA = ROOT / "data"
CACHE = DATA / "cache"
PARQUET = DATA / "parquet"                            # our derived tables (gitignored)
FROZEN_EVAL = PARQUET / "frozen_eval"                # evaluation inputs frozen before results
REPORTS = ROOT / "reports"

# READ-ONLY frozen Deployment Atlas assets (sibling research project).
ATLAS_ROOT = ROOT.parent / "deployment-atlas"
ATLAS_PARQUET = ATLAS_ROOT / "data" / "parquet"
ATLAS_SRC = ATLAS_ROOT / "src"                        # add to sys.path to import `atlas.api`

# READ-ONLY frozen System Effects assets (sibling research project).
SYSEFF_ROOT = ROOT.parent / "system-effects"
SYSEFF_PARQUET = SYSEFF_ROOT / "data" / "parquet"
SYSEFF_SRC = SYSEFF_ROOT / "src"                      # add to sys.path to import `syseff.api`

# Atlas corpus span (verified Phase 0). Primary modeling 2015-16+; pre-2015 broken out.
SEASONS_ALL = [f"{y}-{str(y+1)[2:]}" for y in range(2010, 2026)]   # 2010-11 .. 2025-26
SEASONS_PRIMARY = [f"{y}-{str(y+1)[2:]}" for y in range(2015, 2026)]
