PY = ./.venv/bin/python
export PYTHONPATH = src
export PYTHONWARNINGS = ignore

.PHONY: g1 g2 probe spine savequality stability behavior test report clean

# LINK G1, reproducible from the local cache (BigQuery pulled once to data/cache).
g1: spine savequality test report
	@echo "G1 complete (stability gate + verdict in reports/probe.md)."

spine:
	$(PY) -m gprobe.spine

savequality:
	$(PY) -m gprobe.savequality

stability:
	$(PY) -m gprobe.stability

test:
	$(PY) -m pytest -q tests

report:
	$(PY) -m gprobe.report

behavior:
	$(PY) -m gprobe.behavior

# LINK G2 (needs G1 + goal-tracking Stage 0/1 artifacts present).
g2: behavior test report
	@echo "G2 complete (behavior stability + probe verdict in reports/probe.md)."

probe: spine savequality behavior test report
	@echo "Full probe (G1+G2) complete."

clean:
	rm -rf data/parquet/*.parquet
