# NHL Intelligence Platform

This project consists of two phases:

**Phase 1 (Complete):** A fully automated daily data pipeline that ingests raw NHL game data, transforms it into advanced hockey analytics metrics using dbt, and publishes a clean HTML intelligence report every morning. Built with Apache Airflow, dbt Core, BigQuery, and Python, the system demonstrates end-to-end data engineering practices used by professional hockey analytics organizations.

**Phase 2 (Complete):** An interactive NHL Analytics Dashboard backend API deployed to GCP Cloud Run. FastAPI application serving as a thin API layer over BigQuery mart tables, providing REST endpoints for games, teams, and players data.

The pipeline runs on GCP within free tier limits and generates metrics including Corsi percentages, expected goals, high-danger chances, and player performance indicators.

## Phase 2: Dashboard Backend API

**Production API URL:** https://nhl-dashboard-api-1025423874823.us-central1.run.app

The FastAPI backend is deployed on GCP Cloud Run and provides endpoints for:
- Game lists and detailed game stats
- Team profiles, trends, and roster data
- Player profiles, trends, game logs, and shot maps
- Head-to-head stats (team vs opponent, player vs opponent)

See `backend/README.md` for full API documentation and deployment instructions.

## Architecture

**Phase 1 (Daily Pipeline):**
- Airflow orchestrates daily data ingestion
- Raw NHL API data lands in BigQuery `nhl_raw` dataset
- dbt transforms data through staging to mart tables
- Daily HTML report generated and published to GCS

**Phase 2 (Dashboard API):**
- FastAPI backend deployed to Cloud Run
- Queries BigQuery `nhl_staging` dataset (contains mart tables)
- In-memory caching layer for performance
- Service account authentication for BigQuery access

## Setup Instructions

The project runs locally against BigQuery (the warehouse). You need a GCP project
with the `nhl_raw` / `nhl_staging` / `nhl_mart` datasets and a service-account key
with BigQuery read (and, for the model layer, write) access.

### 1. Python environment

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt           # pipeline, dbt, models, tests
pip install -r backend/requirements.txt   # FastAPI backend
```

### 2. Credentials and environment

Put your service-account JSON at `secrets/nhl-intel-sa.json` (the `secrets/`
directory is gitignored). Copy `.env.example` to `.env` and fill in:

```bash
cp .env.example .env
```

Required for local app + dbt:

| Variable | Purpose |
|---|---|
| `GCP_PROJECT_ID` | BigQuery project id |
| `GCP_DATASET_RAW` / `GCP_DATASET_STAGING` / `GCP_DATASET_MART` | `nhl_raw` / `nhl_staging` / `nhl_mart` |
| `GOOGLE_APPLICATION_CREDENTIALS` | absolute path to `secrets/nhl-intel-sa.json` |

Load it into your shell before running anything: `set -a; source .env; set +a`.

### 3. dbt

dbt reads `dbt/profiles.yml` (copy from `dbt/profiles.yml.example`). The `dev`
target points at your local keyfile and the `nhl_staging` dataset.

```bash
cd dbt
dbt deps                          # no-op today; safe to run
dbt build --select staging --target dev
```

> Always pass `--target dev` locally — the default `prod` target expects the
> Airflow VM keyfile path.

### 4. Backend

```bash
cd backend
uvicorn main:app --reload --port 8000
```

### 5. Frontend

```bash
cd frontend
npm install
VITE_API_BASE_URL=http://localhost:8000 npm run dev
```

The frontend defaults `VITE_API_BASE_URL` to `http://localhost:8000`, so the env
var is only needed if the backend runs elsewhere.

## Local Development

A top-level `Makefile` wraps the common workflows (run from the repo root with
`.env` sourced):

| Target | What it does |
|---|---|
| `make setup` | create the venv and install all Python deps + frontend deps |
| `make dbt-build` | `dbt build --target dev` (full graph + tests) |
| `make backend` | run the FastAPI backend with reload on :8000 |
| `make frontend` | run the Vite dev server |
| `make test` | run the backend/pipeline pytest suite |

Model-training and insight jobs (`models_ml/`, `insight_engine/`) get their own
targets as those layers land in later phases.
