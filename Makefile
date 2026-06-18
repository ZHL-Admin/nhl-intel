.PHONY: setup dbt-build backend frontend test edge-refresh rapm gar gar-validate goalie-gar goalie-gar-validate overall linefit team-needs trade-fit-validate archetypes-v2 radar deployment archetype-explainer

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

# Deployment efficiency (Divergence Board rework): actual vs justified usage by situation.
# Writes nhl_models.deployment_efficiency. `--dry-run` prints the boards without writing.
deployment:
	python -m models_ml.compute_deployment_efficiency

# Compute Value GAR/WAR (Phase 6): actual goals above replacement, the goals-reality companion
# to RAPM (which is read, never modified). Writes nhl_models.player_gar. `make gar-validate` runs
# the Kucherov/Panarin divergence + stability + replacement-sensitivity checks.
gar:
	python -m models_ml.compute_gar
gar-validate:
	python -m models_ml.validate_gar

# Goalie Value GAR/WAR: goals SAVED above a replacement (backup) goalie, on the SAME goals-per-win
# scale as skaters so goalie + skater WAR share one cross-position list. Read-only over the GSAx
# layer. `make goalie-gar-validate` runs the smell-test / distribution / YoY / sensitivity checks.
goalie-gar:
	python -m models_ml.compute_goalie_gar
goalie-gar-validate:
	python -m models_ml.validate_goalie_gar

# Per-player Overall (card-only summary): within-position percentile, averaged-and-re-percentiled
# from a player's component percentiles. Writes nhl_models.player_overall + goalie_overall.
overall:
	python -m models_ml.compute_overall

# Train the Lineup Lab line-fit model (Phase 5.1): predicts a line's on-ice xGF% / xGF60 / xGA60
# from member profiles. Reads int_line_seasons + archetypes + RAPM; writes artifacts/linefit_v1.
linefit:
	python -m models_ml.train_linefit

# Compute per-team need profiles (Phase 5.3) for the trade-fit tool: archetype + component gaps
# vs the top-8 teams by power rating. Writes nhl_models.team_needs.
team-needs:
	python -m models_ml.compute_team_needs

# Validate the multi-dimension Trade Fit rebuild: print disagreement cases (need vs style/quality)
# and confirm the defenseman-to-strong-defense team no longer scores ~0. Reads only; no writes.
trade-fit-validate:
	python -m models_ml.validate_trade_fit

# Refit archetypes v2 (enriched vector) then emit player_archetypes. Single-threaded for a
# reproducible fit. Run without --write first to refresh the trait audit, confirm names, then --write.
archetypes-v2:
	VECLIB_MAXIMUM_THREADS=1 OMP_NUM_THREADS=1 python -m models_ml.fit_archetypes_v2 --write

# Build the skater + goalie skills radars (Part B) into nhl_models.player_radar / goalie_radar.
radar:
	python -m models_ml.compute_player_radar
	python -m models_ml.compute_goalie_radar

# Archetype explainer (gallery + player style-map) into nhl_models.archetype_gallery /
# player_style_map. Reads the locked v2 artifacts (no retrain). `--dry-run` prints, no write.
archetype-explainer:
	VECLIB_MAXIMUM_THREADS=1 OMP_NUM_THREADS=1 python -m models_ml.compute_archetype_explainer

