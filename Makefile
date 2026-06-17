.PHONY: setup dbt-build backend frontend test edge-refresh rapm linefit team-needs archetypes-v2 radar

# Create the Python venv and install all dependencies (Python + frontend).
setup:
	python3 -m venv .venv
	. .venv/bin/activate && pip install -r requirements.txt -r backend/requirements.txt
	cd frontend && npm install

# Build the full dbt graph and run its tests against the local (dev) target.
dbt-build:
	cd dbt && dbt build --target dev

# Run the FastAPI backend with auto-reload on port 8000.
backend:
	cd backend && uvicorn main:app --reload --port 8000

# Run the Vite dev server.
frontend:
	cd frontend && npm run dev

# Run the Python test suite (backend API + pipeline).
test:
	pytest -q

# Refresh NHL Edge season aggregates for the current season into raw tables.
# Run per season (resumable) to backfill history, e.g. SEASON=2023-24.
SEASON ?= 2025-26
edge-refresh:
	python -m scripts.refresh_edge --season $(SEASON)

# Fit isolated-impact RAPM (Phase 4.1): 3-season window + recent single seasons, with
# bootstrap SDs, into nhl_models.player_impact. Long-running (~1-2h with bootstrap).
rapm:
	python -m models_ml.train_rapm

# Train the Lineup Lab line-fit model (Phase 5.1): predicts a line's on-ice xGF% / xGF60 / xGA60
# from member profiles. Reads int_line_seasons + archetypes + RAPM; writes artifacts/linefit_v1.
linefit:
	python -m models_ml.train_linefit

# Compute per-team need profiles (Phase 5.3) for the trade-fit tool: archetype + component gaps
# vs the top-8 teams by power rating. Writes nhl_models.team_needs.
team-needs:
	python -m models_ml.compute_team_needs

# Refit archetypes v2 (enriched vector) then emit player_archetypes. Single-threaded for a
# reproducible fit. Run without --write first to refresh the trait audit, confirm names, then --write.
archetypes-v2:
	VECLIB_MAXIMUM_THREADS=1 OMP_NUM_THREADS=1 python -m models_ml.fit_archetypes_v2 --write

# Build the skater + goalie skills radars (Part B) into nhl_models.player_radar / goalie_radar.
radar:
	python -m models_ml.compute_player_radar
	python -m models_ml.compute_goalie_radar

