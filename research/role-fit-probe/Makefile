# role-fit-probe — one target per step. Reproducible from cache. Frozen inputs are read-only.
# src/ is on PYTHONPATH; Chemistry + Atlas src are added by config.py so their code is importable.
PY := PYTHONPATH=src .venv/bin/python
PIP := .venv/bin/pip

.PHONY: venv test clean step0 step0b enrich link1 link1rich link2

venv:
	python3 -m venv .venv
	$(PIP) install --upgrade pip
	$(PIP) install -e ".[dev]"

# Step 0 — scaffold + frozen-input timestamps + event-primitive inventory.
step0:
	$(PY) -m rolefit.step0
	@echo "See reports/probe.md §0"

# Step 0b — re-audit of event attribution (raw vs ingested), mirror + sequence feasibility.
step0b:
	$(PY) -m rolefit.step0b
	@echo "See reports/probe.md §0b + reports/upstream-ledger.md UL-P1 — STOP for review"

# Enrich (UL-P1, authorized one-time BQ read) — recover the 6 dropped player-id cols + faceoffs.
# Requires BigQuery creds; run with a BQ-capable interpreter (deployment-atlas/.venv). One-time; the
# resulting data/parquet/enriched/*.parquet + MANIFEST.json are the reproducible artifact.
enrich:
	PYTHONPATH=src:../deployment-atlas/src ../deployment-atlas/.venv/bin/python -m rolefit.enrich
	@echo "See reports/upstream-ledger.md UL-P1"

# Link 1 (GATE) — role profiles, role space, stability tests, verdict (shot-only, §1).
link1:
	$(PY) -m rolefit.link1
	@echo "See reports/probe.md §1 — STOP for owner review"

# Link 1 re-gate on the UL-P1-enriched two-way role space (§1b). Needs `make enrich` first.
link1rich:
	$(PY) -m rolefit.profiles --rich
	$(PY) -m rolefit.link1_rich
	@echo "See reports/probe.md §1b — STOP for owner review"

# Link 2 (GATE) — unit over-performance within-season stability. Only run if Link 1 passed.
link2:
	$(PY) -m rolefit.link2
	@echo "See reports/probe.md §2"

test:
	$(PY) -m pytest -q

clean:
	rm -rf data/parquet/* __pycache__ src/rolefit/__pycache__ .pytest_cache
