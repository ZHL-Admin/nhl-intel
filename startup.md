# Daily NHL Intelligence Report — Project Plan

## Overview

This document is the single source of truth for building the Daily NHL Intelligence Report. It is written to be used alongside Claude Code as an AI pair programmer. Every decision — architectural, stylistic, and operational — is documented here so context does not need to be re-established between sessions.

The goal is to build a fully automated daily pipeline that ingests raw NHL data, transforms it into meaningful hockey analytics metrics, and publishes a clean HTML intelligence report every morning. The system is a real portfolio project built with the exact stack used by professional hockey analytics organizations.

---

## Project Goals

1. Build a working, deployed data pipeline that runs daily without manual intervention
2. Demonstrate proficiency with: Airflow, dbt, BigQuery, GCP, Python, and LLM APIs
3. Produce hockey metrics that reflect genuine domain understanding, not just surface-level stats
4. Maintain a clean, well-documented GitHub repository that itself serves as a portfolio artifact
5. Keep infrastructure cost at or near zero

---

## Stack

| Tool | Role | Notes |
|------|------|-------|
| Apache Airflow | Orchestration | Run locally via conda, deployed to GCP |
| dbt Core | Data transformation | Open source, free |
| BigQuery | Data warehouse | GCP free tier is sufficient for this data volume |
| Python 3.11+ | Ingestion, metrics, reporting, LLM calls | Primary language throughout |
| GCP Compute Engine | Airflow host in production | e2-micro is free tier eligible |
| LLM API | Narrative report generation | Google Gemini (free tier) to start |
| GitHub | Version control and public portfolio | Public repo |
| Conda | Local development environment | Python environment management |

---

## Local Development Setup

### Prerequisites

- Python 3.11+
- Conda or Miniconda
- GCP service account with BigQuery access

### Initial Setup

1. **Create and activate conda environment:**
```bash
conda create -n nhl-intel python=3.11
conda activate nhl-intel
```

2. **Install dependencies:**
```bash
pip install -r requirements.txt
pip install apache-airflow==2.8.1 --constraint "https://raw.githubusercontent.com/apache/airflow/constraints-2.8.1/constraints-3.11.txt"
```

3. **Configure environment variables:**
```bash
cp .env.example .env
# Edit .env with your GCP project details
```

4. **Set up Airflow:**
```bash
export AIRFLOW_HOME=~/airflow
export PYTHONPATH="${PYTHONPATH}:$(pwd)"
airflow db init
airflow users create \
    --username admin \
    --firstname Admin \
    --lastname User \
    --role Admin \
    --email admin@example.com \
    --password admin
```

5. **Run Airflow:**
```bash
# Terminal 1: Start webserver
airflow webserver --port 8080

# Terminal 2: Start scheduler
airflow scheduler
```

6. **Access Airflow UI:**
- Navigate to http://localhost:8080
- Login with admin/admin

---

## Repository Structure

```
nhl-intel/
├── dags/                        # Airflow DAGs
│   └── nhl_daily.py             # Main daily pipeline DAG
├── dbt/                         # dbt project
│   ├── dbt_project.yml
│   ├── profiles.yml.example     # Example only, never commit real credentials
│   ├── models/
│   │   ├── raw/                 # Source declarations
│   │   ├── staging/             # Cleaned, typed, renamed source data
│   │   ├── intermediate/        # Business logic and joins
│   │   └── mart/                # Final analytics-ready tables
│   ├── tests/                   # Custom dbt tests
│   └── macros/                  # Reusable SQL macros
├── ingestion/                   # Python ingestion scripts
│   ├── nhl_api.py               # NHL API client
│   └── loaders.py               # BigQuery load utilities
├── reporting/                   # Report generation
│   ├── query.py                 # Pulls from mart tables
│   ├── render.py                # Builds HTML report
│   └── llm_summary.py           # LLM narrative generation
├── tests/                       # Python unit tests
├── .env.example                 # Env var template, never commit .env
├── docker-compose.yml           # Local Airflow environment
├── requirements.txt             # Python dependencies
└── README.md                    # Setup instructions and architecture diagram
```

---

## Code Standards

These standards apply to every file in the project. Claude Code should follow them without being asked in each session.

### Python

- Python 3.11+
- Use `black` for formatting (line length 88)
- Use `ruff` for linting
- Type hints on all function signatures
- Use `pathlib.Path` over `os.path`
- Prefer `httpx` over `requests` for HTTP calls
- Use `pydantic` for data validation where appropriate
- Avoid deeply nested logic; extract functions early

### Comments

Comments should be minimal, consistent, and purposeful. The goal is to explain intent, not to narrate code. Follow these rules exactly:

- Use a `#` comment only when the code itself does not make the reason clear
- One space after `#`, sentence case, no period at the end
- Do not comment on what the code does if the code already says it clearly
- Do not include anything about claude, claude code, or anthropic in any comments
- Docstrings on all public functions and classes, using the Google style:

```python
def get_games(date: str) -> list[dict]:
    """Fetch all games for a given date from the NHL API.

    Args:
        date: Date string in YYYY-MM-DD format.

    Returns:
        List of game dicts from the API response.
    """
```

- Module-level docstrings at the top of every file, one or two sentences max
- No commented-out code committed to the repo; use git to preserve history

**Example of correct commenting style:**

```python
# Retry on 429 to handle NHL API rate limiting
@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
def fetch_game(game_id: str) -> dict:
    """Fetch boxscore data for a single game."""
    response = client.get(f"{BASE_URL}/gamecenter/{game_id}/boxscore")
    response.raise_for_status()
    return response.json()
```

**Example of incorrect commenting style (do not do this):**

```python
# This function gets a game
def fetch_game(game_id: str) -> dict:
    # Make the request
    response = client.get(...)  # Get the response
    response.raise_for_status()  # Raise an error if it failed
    return response.json()  # Return the JSON
```

### SQL and dbt

- All SQL lowercase
- CTEs over subqueries, always
- CTE names are descriptive snake_case nouns (`game_events`, `player_stats_cleaned`)
- One CTE per logical transformation step
- Final `SELECT` at the bottom of every model references only the last CTE
- Column aliases used consistently when renaming
- dbt model file names match the model name exactly

**Standard CTE pattern:**

```sql
with source as (
    select * from {{ source('nhl', 'raw_games') }}
),

renamed as (
    select
        game_id,
        game_date,
        home_team_id,
        away_team_id,
        home_score,
        away_score
    from source
),

final as (
    select
        *,
        case when home_score > away_score then home_team_id else away_team_id end as winning_team_id
    from renamed
)

select * from final
```

### dbt Model Comments

- Every model has a description in `schema.yml`
- Every column that is not obviously named has a description
- No inline SQL comments unless the logic is genuinely non-obvious

### Git

- Commit messages: imperative mood, present tense, 50 chars or less for the subject
  - Good: `Add staging model for player stats`
  - Bad: `added staging model for player stats` or `WIP`
- Branch per feature or phase: `phase-1-ingestion`, `phase-2-dbt`, etc.
- Never commit `.env`, credentials, or `profiles.yml`
- `.gitignore` covers: `.env`, `*.pyc`, `__pycache__`, `.dbt/`, `target/`, `logs/`

---

## Environment and Secrets

- All secrets in `.env` locally, loaded via `python-dotenv`
- In production (GCP), manually create .env on the VM via SSH.
- `.env.example` is committed with placeholder values, never real values
- Required environment variables:

```
GCP_PROJECT_ID=
GCP_DATASET_RAW=nhl_raw
GCP_DATASET_STAGING=nhl_staging
GCP_DATASET_MART=nhl_mart
GOOGLE_APPLICATION_CREDENTIALS=path/to/service-account.json
LLM_API_KEY=
LLM_PROVIDER=gemini
REPORT_OUTPUT_BUCKET=
```

---

## Data Source

### NHL API

The unofficial NHL API at `https://api-web.nhle.com` is free and requires no authentication. It is community-documented and reasonably stable.

Key endpoints:

| Endpoint | Data |
|----------|------|
| `/v1/schedule/{date}` | Games scheduled for a given date |
| `/v1/gamecenter/{game_id}/boxscore` | Full boxscore for a game |
| `/v1/gamecenter/{game_id}/play-by-play` | All events in a game |
| `/v1/player/{player_id}/landing` | Player profile and season stats |
| `/v1/standings/now` | Current league standings |

Rate limiting is not formally documented but the API tolerates reasonable request rates. Use exponential backoff on retries. Do not hammer endpoints in parallel; use a small concurrency limit.

### Supplementary Sources

If the NHL API does not expose a needed metric, the following sources provide downloadable CSVs:

- **MoneyPuck** (`moneypuck.com/data.htm`) — advanced team and player metrics including xG, CF%, HDCA
- **Natural Stat Trick** (`naturalstattrick.com`) — similar coverage, excellent for zone entry data

These are used sparingly. The NHL API is the primary source.

---

## BigQuery Schema Design

Three datasets, each with a clear purpose. Never read from a lower layer in a higher-layer model; always go through dbt.

### `nhl_raw`

Raw data landed exactly as received from the API. No transformations. Partitioned by `ingestion_date`. Used only by staging models.

Tables:
- `raw_games` — one row per game, full API response stored as JSON or flattened
- `raw_boxscores` — one row per game, full boxscore
- `raw_play_by_play` — one row per event
- `raw_player_stats` — one row per player per game

### `nhl_staging`

Cleaned, typed, and renamed raw data. No business logic. One staging model per raw table.

Rules:
- Cast all types explicitly (no implicit conversions)
- Rename columns to snake_case
- Drop columns not needed downstream
- Add `_loaded_at` timestamp

### `nhl_mart`

Analytics-ready tables built for reporting. This is where metrics are computed. Models here join across staging tables and apply hockey-specific logic.

Tables:
- `mart_team_game_stats` — one row per team per game, all computed metrics
- `mart_player_game_stats` — one row per player per game
- `mart_team_rolling` — rolling 5-game window metrics per team
- `mart_daily_report_feed` — one row per reporting day, denormalized for the report generator

### Partitioning and Clustering

- Partition all raw and mart tables on `game_date` (DATE type)
- Cluster `mart_team_game_stats` on `team_id`
- Cluster `mart_player_game_stats` on `player_id, team_id`

---

## Metrics

These are the metrics to build. They are divided by scope. Simple counting stats (goals, assists, saves) are excluded intentionally. The metrics below are what a modern hockey analytics team actually uses.

### Team Metrics (per game and rolling 5-game)

| Metric | Definition |
|--------|------------|
| `cf_pct` | Corsi for percentage at 5v5. Shot attempts for / (shot attempts for + shot attempts against) |
| `xgf_pct` | Expected goals for percentage at 5v5. Team xGF / (xGF + xGA) |
| `hdcf_per60` | High-danger chance rate for per 60 minutes of 5v5 ice time |
| `hdca_per60` | High-danger chance rate against per 60 minutes |
| `rush_shot_share` | Percentage of shot attempts that are rush attempts |
| `zone_entry_success_rate` | Controlled zone entries / total zone entry attempts |
| `gsax` | Goals saved above expected (goalie performance vs xG against) |
| `rolling_xgf_pct_5gp` | xGF% averaged over the last 5 games |
| `rolling_cf_pct_5gp` | CF% averaged over the last 5 games |

### Player Metrics (per game)

| Metric | Definition |
|--------|------------|
| `ixg_per60` | Individual expected goals per 60 minutes of ice time |
| `on_ice_xgf_pct` | Team xGF% while this player is on ice at 5v5 |
| `primary_points_per60` | Goals + primary assists per 60 minutes |
| `zone_entry_rate` | Zone entries attempted per 60 minutes (skaters) |
| `toi_5v5` | Time on ice at 5v5 strength |
| `hot_cold_flag` | Whether current ixG/60 is above or below season average by >15% |

### Goalie Metrics

| Metric | Definition |
|--------|------------|
| `gsax` | Goals saved above expected (actual saves - expected saves) |
| `hd_save_pct` | Save percentage on high-danger shots only |
| `xsv_pct` | Expected save percentage based on shot quality faced |

---

## Airflow DAG Design

The main DAG is `nhl_daily`. It runs once per day at 08:00 ET (13:00 UTC) to allow overnight game data to be fully available.

### Task Structure

```
ingest_schedule
    └── ingest_boxscores
            └── ingest_play_by_play
                    └── load_to_bigquery
                            └── run_dbt_models
                                    └── generate_report
                                                └── publish_report
```

### Task Definitions

**`ingest_schedule`**
Calls the NHL schedule endpoint for yesterday's date. Writes a list of `game_id`s to an Airflow XCom.

**`ingest_boxscores`**
Reads game IDs from XCom. Fetches boxscore for each game. Writes raw JSON to GCS staging bucket.

**`ingest_play_by_play`**
Same pattern as boxscores. Fetches play-by-play for each game.

**`load_to_bigquery`**
Reads raw files from GCS and loads them into `nhl_raw` dataset tables. Uses `WRITE_APPEND` mode with `ingestion_date` partition.

**`run_dbt_models`**
Calls `dbt run --select staging+ --target prod` followed by `dbt test`. If tests fail, the DAG fails and no report is generated.

**`generate_report`**
Python operator that queries `mart_daily_report_feed`, computes trend flags, calls the LLM API for the narrative summary, and renders the HTML report.

**`publish_report`**
Uploads the rendered HTML to a public GCS bucket. The bucket serves static files via a public URL.

### DAG Defaults

```python
default_args = {
    "owner": "nhl-intel",
    "retries": 2,
    "retry_delay": timedelta(minutes=5),
    "email_on_failure": True,
    "email_on_retry": False,
}
```

### Task Guidelines

- Every task is idempotent; re-running it for the same date should not create duplicate data
- Use `BashOperator` or `PythonOperator` only; avoid complex Airflow patterns in v1
- Log clearly at the start and end of each task with the date being processed
- Do not put business logic inside DAG files; DAGs only wire together functions defined elsewhere

---

## Report Generation

### Output Format

A single static HTML file. Clean, readable, no JavaScript required. Designed to be viewable in a browser via a public GCS URL. The report covers the previous day's games.

### Report Structure

```
[AI Narrative Summary]          <- LLM-generated, 4-6 sentences
[Yesterday's Game Results]      <- Scores and key stats per game
[Team Trends]                   <- Rolling metrics with change indicators
[Player Movers]                 <- Notable individual performances
[Goalie Report]                 <- GSAX and high-danger save pct
```

### LLM Summary Generation

The LLM call receives a structured JSON payload derived from the mart tables and returns a narrative paragraph. It is not used for analysis or judgment — it is used for natural language rendering of patterns that are already computed in SQL.

**Prompt design:**

```python
SYSTEM_PROMPT = """
You are a hockey analytics assistant writing the daily summary section of an internal intelligence report.
Write 4 to 6 sentences. Be specific and cite the metrics provided. Use plain language.
Do not use cliches like 'battle-tested' or 'fired on all cylinders'.
Do not speculate beyond what the data shows.
"""

def build_user_prompt(metrics: dict) -> str:
    """Build the user prompt from structured metric data."""
    return f"""
Yesterday's NHL metrics summary:

{json.dumps(metrics, indent=2)}

Write the daily intelligence summary based on the above data.
"""
```

The `metrics` dict passed to the LLM includes only pre-computed values from the mart tables. The LLM does not receive raw data or make calculations.

---

## Phase Plan

Complete each phase fully before starting the next. Do not skip ahead.

### Phase 1 — Local foundation

**Goal:** Pull NHL data locally and write it somewhere. Confirm the API works and data is usable.

Tasks:
- Initialize Git repo with the full directory structure
- Set up local Airflow in conda environment
- Write `nhl_api.py` with functions for schedule, boxscore, and play-by-play endpoints
- Write a simple test script that fetches one day of data and prints game IDs
- Set up GCP project, enable BigQuery API, create service account with BigQuery Data Editor role
- Create `nhl_raw` dataset in BigQuery
- Write `loaders.py` to load a raw game dict to BigQuery
- Create a minimal Airflow DAG with a single task that runs the ingestion script

**Exit criteria:** Running the DAG manually ingests recent games into BigQuery raw tables without errors.

---

### Phase 2 — dbt project and staging models

**Goal:** Transform raw data into clean, typed, tested staging tables.

Tasks:
- Initialize dbt project with BigQuery profile
- Create source declarations in `models/raw/sources.yml`
- Build `stg_games`, `stg_boxscores`, `stg_play_by_play`, `stg_player_stats` staging models
- Write schema.yml with column descriptions and tests (`not_null`, `unique`, `accepted_values`)
- Run `dbt test` and confirm all tests pass
- Add `run_dbt_models` task to the DAG after ingestion tasks

**Exit criteria:** `dbt run && dbt test` completes clean on real data.

---

### Phase 3 — Metrics and mart layer

**Goal:** Build the analytics tables that power the report.

Tasks:
- Build intermediate models for 5v5 event filtering and time-on-ice calculations
- Build `mart_team_game_stats` with all team metrics from the metrics table above
- Build `mart_player_game_stats` with all player metrics
- Build `mart_team_rolling` using a 5-game window (use dbt's `lag` or a rolling window macro)
- Build `mart_daily_report_feed` as a denormalized view across the mart tables
- Add descriptions and tests to all mart models
- Validate metrics against a known source (Natural Stat Trick or MoneyPuck) for a recent game

**Exit criteria:** `mart_daily_report_feed` returns correct metrics for a recent game date, validated against an external source.

---

### Phase 4 — Report generation

**Goal:** Produce a readable HTML report from mart data.

Tasks:
- Write `query.py` to pull from `mart_daily_report_feed` for a given date
- Write `render.py` to produce an HTML report from the query output (use Jinja2 templating)
- Write `llm_summary.py` to call the LLM API and return a narrative paragraph
- Wire all three into `generate_report` Airflow task
- Add `publish_report` task to upload the HTML file to a public GCS bucket
- Test the full report for a recent date manually before adding to the DAG

**Exit criteria:** Report is accessible via a public URL and contains accurate metrics and a coherent AI summary.

---

### Phase 5 — Production deployment

**Goal:** Deploy to GCP and confirm the pipeline runs automatically.

Tasks:
- Provision a GCP e2-micro Compute Engine VM (Debian, free tier)
- Install Docker and Docker Compose on the VM
- Clone the repo and configure `.env` using GCP Secret Manager values
- Start Airflow and confirm the DAG appears in the UI
- Trigger one manual run to confirm end-to-end function on the VM
- Enable the schedule and monitor for 7 consecutive days
- Set up failure alerting (email via Airflow SMTP config or a simple GCP Cloud Monitoring alert)

**Exit criteria:** The pipeline runs at 08:00 ET for 7 days in a row without manual intervention and produces a publicly accessible report each day.

---

## Testing Strategy

### Python Tests

- Unit tests in `tests/` using `pytest`
- Test ingestion functions with mocked HTTP responses (`respx` for `httpx`)
- Test report rendering with a fixture dict
- Test LLM prompt builder with a fixture metrics dict
- Do not test external API connectivity in unit tests

### dbt Tests

Built-in tests applied to every model:
- `not_null` on all primary keys and key foreign keys
- `unique` on all primary keys
- `accepted_values` on status and category columns

Custom tests:
- `assert_cf_pct_between_0_and_1` on all percentage metrics
- `assert_game_has_two_teams` on boxscore staging model

Run tests as part of the DAG. Fail the DAG if any dbt test fails.

---

## Cost Management

| Resource | Free Tier Limit | Expected Usage | Cost |
|----------|----------------|---------------|------|
| BigQuery storage | 10 GB/month | < 1 GB | $0 |
| BigQuery queries | 1 TB/month | < 1 GB | $0 |
| Compute Engine (e2-micro) | 1 instance/month | 1 instance | $0 |
| GCS storage | 5 GB/month | < 100 MB | $0 |
| LLM API (Google Gemini) | 1,500 req/day | ~1 req/day | $0 |

If LLM cost becomes a factor, switch to Groq's free tier first. Claude and OpenAI are both acceptable but incur token costs. At one report per day with ~500 tokens per call, cost on either platform is under $1/month.

---
