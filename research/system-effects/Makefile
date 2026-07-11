# System Effects — one target per phase. Every phase reproducible from cache.
# Uses the project-local venv (make venv). Production is read-only.

PY := .venv/bin/python
PIP := .venv/bin/pip

.PHONY: venv test clean phase0 phase1 backfill

venv:
	python3 -m venv .venv
	$(PIP) install --upgrade pip
	$(PIP) install -e ".[dev]"

# Phase 0 — environment, asset audit, coach-data era probe.
phase0:
	$(PY) -m syseff.probe_rightrail

# Gate A — historical right-rail coach backfill (resumable) + parse to parquet.
backfill:
	$(PY) -m syseff.backfill_rightrail
	$(PY) -m syseff.backfill_rightrail --parse

# Phase 1 — regime ledger, validation, cohorts. Reproducible from cache.
phase1:
	$(PY) -m syseff.phase1
	@echo "See reports/phase1.md"

test:
	$(PY) -m pytest -q

clean:
	rm -rf data/parquet/*.parquet __pycache__ src/syseff/__pycache__ .pytest_cache
