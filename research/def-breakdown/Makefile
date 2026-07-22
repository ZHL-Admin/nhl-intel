PY = ./.venv/bin/python
export PYTHONPATH = src
export PYTHONWARNINGS = ignore

.PHONY: link0 link1 link2 events signals tally report report2 test clean

link0: events
	@echo "Link 0 complete."

events:
	$(PY) -m defbreak.events

# Link 1 (needs Link 0 event cache).
link1: signals report test
	@echo "Link 1 complete."

signals:
	$(PY) -m defbreak.signals

report:
	$(PY) -m defbreak.report

test:
	$(PY) -m pytest -q tests

clean:
	rm -rf data/parquet/*.parquet

# Link 2 (culprit-rate tally + stability gate); appends to probe.md after Link 1.
link2: signals tally report2 test
	@echo "Link 2 complete."

tally:
	$(PY) -m defbreak.link2

report2:
	$(PY) -m defbreak.report_link2

# Culprit-rate context-adjustment probe (extends def-breakdown; def-culprit-adj).
adjprobe: context adjrates report_adj test
	@echo "Adjustment probe complete."
context:
	$(PY) -m defbreak.context
adjrates:
	$(PY) -m defbreak.adjrates
report_adj:
	$(PY) -m defbreak.report_adj

inspect:
	$(PY) -m defbreak.inspect
