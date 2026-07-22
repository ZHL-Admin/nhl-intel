PY = ./.venv/bin/python
export PYTHONPATH = src
export PYTHONWARNINGS = ignore

.PHONY: stage0 stage1 stage2 stage4 stage4_sweep f25_predict descriptors signatures reliability2 report2 audit fuse quality validate mechanisms profiles reliability test report report1 clean

# F25 offensive-signature predictive test (does early signature forecast future role/production).
f25_predict:
	$(PY) -m gtrack.f25_predict

# Stage 4 (team goal-style enrichment), reproducible from the Stage-0/2 cache.
stage4:
	$(PY) -m gtrack.stage4

# Stage 4 sweep — full offensive-style axis space across all 5 dimensions.
stage4_sweep:
	$(PY) -m gtrack.stage4_sweep

# Full Stage 1 (goalie mechanism profiles), reproducible from the Stage-0 cache.
stage1: mechanisms profiles reliability test report1
	@echo "Stage 1 complete."

mechanisms:
	$(PY) -m gtrack.mechanisms

profiles:
	$(PY) -m gtrack.profiles

reliability:
	$(PY) -m gtrack.reliability

report1:
	$(PY) -m gtrack.report_stage1

# Full Stage 0, reproducible from cache (frame/pbp caches must exist; fuse reads them offline).
stage0: audit fuse validate test report
	@echo "Stage 0 complete."

audit:
	$(PY) -m gtrack.audit

fuse:
	$(PY) -m gtrack.fuse

quality:
	$(PY) -c "from gtrack import quality,json; d=quality.distribution(quality.load_scored()); print('clean_frac',round(d['overall_clean_frac'],3),'n_clean',d['n_clean'])"

validate:
	$(PY) -m gtrack.report validate

test:
	$(PY) -m pytest -q tests

# Regenerate reports/stage0.md from the built artifacts.
report:
	$(PY) -m gtrack.report write

# Stage 2 (playmaking & buildup description), from the Stage-0 cache.
stage2: descriptors signatures reliability2 test report2
	@echo "Stage 2 complete."

descriptors:
	$(PY) -m gtrack.stage2_descriptors

signatures:
	$(PY) -m gtrack.stage2_signatures

reliability2:
	$(PY) -m gtrack.stage2_reliability

report2:
	$(PY) -m gtrack.report_stage2

clean:
	rm -rf data/parquet/*.parquet
