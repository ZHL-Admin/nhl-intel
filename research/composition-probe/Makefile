PY := PYTHONPATH=src .venv/bin/python
PIP := .venv/bin/pip
.PHONY: venv test clean probe

venv:
	python3 -m venv .venv
	$(PIP) install --upgrade pip
	$(PIP) install -e ".[dev]"

# THE GATE — style vocabulary + recipes + talent/style-matched contrast + era-split repeat + verdict.
probe:
	$(PY) -m comppro.styles
	$(PY) -m comppro.gate
	@echo "See reports/probe.md — STOP for owner review"

test:
	$(PY) -m pytest -q

clean:
	rm -rf data/parquet/* __pycache__ src/comppro/__pycache__ .pytest_cache
