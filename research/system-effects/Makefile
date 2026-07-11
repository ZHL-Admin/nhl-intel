# System Effects — one target per phase. Every phase reproducible from cache.
# Uses the project-local venv (make venv). Production is read-only.

PY := .venv/bin/python
PIP := .venv/bin/pip

.PHONY: venv test clean phase0 report0

venv:
	python3 -m venv .venv
	$(PIP) install --upgrade pip
	$(PIP) install -e ".[dev]"

# Phase 0 — environment, asset audit, coach-data era probe.
phase0:
	$(PY) -m syseff.probe_rightrail

report0: phase0
	@echo "See reports/phase0.md"

test:
	$(PY) -m pytest -q

clean:
	rm -rf data/parquet/*.parquet __pycache__ src/syseff/__pycache__ .pytest_cache
