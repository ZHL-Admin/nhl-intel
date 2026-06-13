.PHONY: setup dbt-build backend frontend test edge-refresh

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
