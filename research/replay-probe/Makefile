.PHONY: probe test
# Reproduce the verified facts from the local cache (stdlib only; no BQ, no fetch).
probe:
	python3 -m replayprobe.probe
test:
	python3 -m pytest -q
