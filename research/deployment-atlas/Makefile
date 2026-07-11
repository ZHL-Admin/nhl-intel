# Deployment Atlas — research pipeline. Each phase has a target; phases stop
# after writing their report. All commands run inside the project-local venv so
# the folder is self-contained and removable with zero impact on the site.

PY := .venv/bin/python
PIP := .venv/bin/pip
PYTEST := .venv/bin/pytest

.DEFAULT_GOAL := help

.PHONY: help venv install test all report phase0 phase1 stints rapm phase3 phase5 clean

help: ## List targets
	@grep -E '^[a-zA-Z0-9_-]+:.*?## .*$$' $(MAKEFILE_LIST) \
		| awk 'BEGIN{FS=":.*?## "}{printf "  \033[36m%-12s\033[0m %s\n", $$1, $$2}'

venv: ## Create the project-local virtualenv
	python3 -m venv .venv

install: ## Install the pinned stack into the venv
	$(PIP) install --upgrade pip
	$(PIP) install -e ".[dev]"

test: ## Run the unit + fixture test suite
	$(PYTEST) -q

all: ## Reproduce every phase's tables from the cached corpus (idempotent; skips present)
	$(PY) -m atlas.pipeline

report: ## Rebuild report figures from cache (no BigQuery); confirm narrative reports present
	$(PY) -m atlas.reports

# --- individual heavy phases (only needed after `make clean` or to force a rebuild) ---
phase0: ## Verify API semantics against real payloads
	$(PY) -m atlas.phase0
phase1: ## Materialize the corpus from BigQuery + gap fetches + integrity
	$(PY) -m atlas.phase1
stints: ## Derive stints + attach outcomes
	$(PY) -m atlas.stints && $(PY) -m atlas.stints --outcomes
rapm: ## Fit the Atlas RAPM variant (heavy: ~3 min/season)
	$(PY) -m atlas.rapm
phase3: ## Fill stint xG + per-player rates + reconciliation
	$(PY) -m atlas.phase3

clean: ## Remove derived data (keeps source + report markdown)
	rm -rf data/raw data/parquet/*.parquet data/atlas.duckdb reports/*_probe.json
