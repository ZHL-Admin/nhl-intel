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

_Local environment setup and GCP configuration instructions coming soon._

## Local Development

_Docker Compose setup and testing workflow coming soon._
