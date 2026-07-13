# Chemistry — one target per phase. Every phase reproducible from cache. Production is read-only.
# src/ is on PYTHONPATH (package not pip-installed, keeping the folder self-contained).
PY := PYTHONPATH=src .venv/bin/python
PIP := .venv/bin/pip

.PHONY: venv test clean phase0 phase1 phase2

venv:
	python3 -m venv .venv
	$(PIP) install --upgrade pip
	$(PIP) install -e ".[dev]"

# Phase 0 — scaffold, asset audit, fit-incumbent inventory, derivation cost probe.
phase0:
	$(PY) -m chem.phase0
	@echo "See reports/phase0.md"

# Phase 1 — build the pair/trio corpus from frozen stints, run the 1.3 integrity suite, and
# freeze the combined corpus to data/parquet/frozen/ with recorded sha256 hashes.
# Reproducible from cache; add --rebuild to force a fresh corpus build.
phase1:
	$(PY) -m chem.phase1
	@echo "See reports/phase1.md and reports/phase1_analysis.json"

# Phase 2 — the keystone. Build pair-half tables + strata, fit the null under both anchors, run
# split-half + YoY persistence with placebos, apply the pre-registered verdict, write exhibits.
# `--halves` (re)builds only the odd/even pair-half tables.
phase2:
	$(PY) -m chem.phase2
	@echo "See reports/phase2.md and reports/phase2_analysis.json"

test:
	$(PY) -m pytest -q

clean:
	rm -rf data/parquet/*.parquet __pycache__ src/chem/__pycache__ .pytest_cache
