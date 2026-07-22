PY := PYTHONWARNINGS=ignore PYTHONPATH=src ./.venv/bin/python

link0: universe tracks
	@echo "Link 0 complete."
universe:
	$(PY) -m dblame.data
tracks:
	$(PY) -m dblame.tracks
report0:
	$(PY) -m dblame.link0
link1: features events
	@echo "Link 1 complete."
features:
	$(PY) -m dblame.link1
events:
	$(PY) -m dblame.link1_report

all: link0 link1
	@echo "Link 0 + Link 1 complete; reports/probe.md written."
test:
	$(PY) -m pytest -q tests

holdout:
	$(PY) -m dblame.holdout

puckloss: 
	$(PY) -m dblame.puckloss coupling
	$(PY) -m dblame.puckloss

rushdef:
	$(PY) -m dblame.rushdef
