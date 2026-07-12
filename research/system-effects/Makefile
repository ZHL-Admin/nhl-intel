# System Effects — one target per phase. Every phase reproducible from cache.
# Uses the project-local venv (make venv). Production is read-only.

# src/ is on PYTHONPATH (package is not pip-installed, keeping the folder self-contained).
PY := PYTHONPATH=src .venv/bin/python
PIP := .venv/bin/pip

.PHONY: venv test clean phase0 phase1 phase2 phase3 phase4 phase5 summer prospective all report backfill primitives

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

# Phase 2 — fingerprints v2: reliability + discontinuity test.
phase2:
	$(PY) -m syseff.fingerprints
	$(PY) -m syseff.phase2
	@echo "See reports/phase2.md"

# Phase 3 primitives — multi-season context + on-ice xG (cached, heavy).
primitives:
	$(PY) -m syseff.context

# Phase 3 — pooling, both tracks, opponent track, stability.
phase3: primitives
	$(PY) -m syseff.phase3
	@echo "See reports/phase3.md"

# Phase 4 — product surfaces (portability + schedule adjustment) + exhibits. Computed, not published.
phase4:
	$(PY) -m syseff.phase4
	@echo "See reports/phase4.md"

# Phase 5 — pre-registered validation (internal track only). Freezes eval inputs, then metrics.
phase5:
	$(PY) -m syseff.phase5
	@echo "See reports/phase5.md"

# Phase 5 addendum — summer-install question (F12 scope; exploratory, observational).
summer:
	$(PY) -m syseff.summer
	@echo "See reports/phase5-summer-addendum.md"

# Phase 6.4 — freeze 2025-26 predictor inputs for the 2026-27 prospective registration.
prospective:
	$(PY) -m syseff.prospective

# Reproduce every phase + addendum from cache, reporting per-step wall time.
all: primitives
	@echo "Reproducing all phases + addenda from cache (seed 20260711)..."
	@t=$$SECONDS; \
	for p in phase1 phase2 phase3 phase4 phase5 summer prospective; do \
	  s=$$SECONDS; $(PY) -m syseff.$$p >/dev/null 2>&1 && ok="ok" || ok="FAIL"; \
	  echo "  $$p: $$(($$SECONDS - s))s [$$ok]"; \
	done; \
	echo "total wall time: $$(($$SECONDS - t))s"; \
	$(MAKE) -s test

# List the frozen reports of record.
report:
	@echo "System Effects — reports of record:"
	@ls -1 reports/*.md | sed 's/^/  /'
	@echo "  ../PROGRAM-FINDINGS.md (cross-project ledger)"

test:
	$(PY) -m pytest -q

clean:
	rm -rf data/parquet/*.parquet __pycache__ src/syseff/__pycache__ .pytest_cache
