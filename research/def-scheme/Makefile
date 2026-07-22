PY = ./.venv/bin/python
export PYTHONPATH = src
export PYTHONWARNINGS = ignore

.PHONY: phase0 phase1 phase2 primitives signatures keystone test report0 report1 report2 clean

# Phase 0, reproducible from the goal-tracking cache.
phase0: primitives report0 test
	@echo "Phase 0 complete."

primitives:
	$(PY) -m defscheme.defprimitives

test:
	$(PY) -m pytest -q tests

report0:
	$(PY) -m defscheme.report_phase0

# Phase 1 (scheme-norm), from the primitive cache.
phase1: signatures report1 test
	@echo "Phase 1 complete."

signatures:
	$(PY) -m defscheme.scheme_norm

report1:
	$(PY) -m defscheme.report_phase1

# Phase 2 keystone (needs Phase 1 signatures).
phase2: signatures report2 test
	@echo "Phase 2 complete."

report2:
	$(PY) -m defscheme.report_phase2

clean:
	rm -rf data/parquet/*.parquet
