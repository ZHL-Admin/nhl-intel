# dependency-probe — one target per link. Reproducible from cache. Frozen inputs read-only.
PY := PYTHONPATH=src .venv/bin/python
PIP := .venv/bin/pip

.PHONY: venv test clean linkA linkQ linkB linkC

venv:
	python3 -m venv .venv
	$(PIP) install --upgrade pip
	$(PIP) install -e ".[dev]"

# Link A (GATE) — behavioral axes conditioned on partner + across-partner movement test.
linkA:
	$(PY) -m deppro.linkA
	@echo "See reports/probe.md Link A — STOP for owner review"

# Link Q (Round 2 GATE) — quality/location/decision axes conditioned on partner + opponent control.
linkQ:
	$(PY) -m deppro.qaxes
	$(PY) -m deppro.q3unit --build
	$(PY) -m deppro.linkQ
	$(PY) -m deppro.q3unit
	@echo "See reports/probe.md Round 2 — STOP for owner review"

# Link B (GATE) — dependence score + stability. Only if A passed.
linkB:
	$(PY) -m deppro.linkB
	@echo "See reports/probe.md Link B — STOP for owner review"

# Link C (GATE, payoff) — dependence on a departing teammate predicts A's change. Only if B passed.
linkC:
	$(PY) -m deppro.linkC
	@echo "See reports/probe.md Link C — STOP for owner review"

test:
	$(PY) -m pytest -q

clean:
	rm -rf data/parquet/* __pycache__ src/deppro/__pycache__ .pytest_cache
