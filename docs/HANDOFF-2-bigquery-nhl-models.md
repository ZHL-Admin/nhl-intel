# Handoff 2: BigQuery access and the nhl_models dataset

**Provide this when Claude Code needs to create or write to the `nhl_models` dataset, or hits any BigQuery permission/credential error (first needed in Phase 2.2 scoring, referenced from Phase 1 onward).**

## Project facts
- GCP project: `nhl-intel-498216`
- Existing datasets: `nhl_raw` (raw API JSON), `nhl_staging` (dbt staging + marts; yes, marts currently live in the staging dataset, see note below)
- Auth: service account `nhl-intel-sa@nhl-intel-498216.iam.gserviceaccount.com`, key file referenced by `GOOGLE_APPLICATION_CREDENTIALS` (path in `.env`, key stored at `secrets/nhl-intel-sa.json`, gitignored)
- Location: keep every new dataset in the same location as `nhl_raw` (check with `bq show --format=prettyjson nhl-intel-498216:nhl_raw | grep location` before creating anything; do not assume US).

## Dataset creation (I run this once; you generate it, I execute)
Generate `scripts/setup_models_dataset.py` (idempotent) that:
1. Creates dataset `nhl_models` in the matched location with description "In-house model outputs: xG scores, win probability, RAPM, ratings, archetypes, insights. Written by models_ml jobs; read by dbt and the API."
2. Creates nothing else: model tables are created by their scoring jobs with explicit schemas (`bigquery.Table` with schema definitions, never autodetect, since these are typed numeric outputs).
3. Prints what it created vs what already existed.

If the service account lacks dataset-creation rights, I will instead run, from my own gcloud auth:
```bash
bq --location=<LOC> mk --dataset --description "In-house model outputs" nhl-intel-498216:nhl_models
```
and grant the SA on it:
```bash
# roles needed by the SA, scoped to the new dataset
bq update --dataset \
  --source <(bq show --format=prettyjson nhl-intel-498216:nhl_models) \
  nhl-intel-498216:nhl_models   # (I'll do this via console IAM if the CLI dance is awkward)
```
Required SA capabilities, dataset-scoped where possible: `roles/bigquery.dataEditor` on `nhl_raw`, `nhl_staging`, and `nhl_models`; `roles/bigquery.jobUser` at project level. It already has the first two (the pipeline works); only `nhl_models` is new.

## Conventions for every model table (enforce in code review of your own work)
- Name: `nhl_models.<thing>` exactly as the plan specifies (`shot_xg`, `win_probability`, `team_ratings`, `deserved_standings`, `style_map`, `streak_cards`, `player_impact`, `player_composite`, `player_archetypes`, `player_clutch`, `player_consistency`, `player_coach_trust`, `divergence_board`, `aging_curves`, `player_twins`, `team_needs`, `insights`, `prediction_ledger`).
- Every table carries `model_version` (string, e.g. `xg_v1`) and `scored_at` (timestamp) columns.
- Writes are idempotent: scoring jobs use `WRITE_TRUNCATE` on a partition (or delete-then-insert keyed on game_id/date range for `--since` incremental runs), never blind appends that can duplicate.
- Partition large tables: `shot_xg` and `win_probability` by a `game_date` DATE column, clustered by `season`; small lookup tables (ratings, archetypes) need no partitioning.
- dbt reads them via a second source definition: add `nhl_models` as a new source in `dbt/models/raw/sources.yml` (or a dedicated `sources_models.yml`) so refs stay declared and `dbt build` can test not_null on join keys.

## Free-tier guardrails
The project targets free-tier comfort. Before any job that scans the full 16-season pbp/shift tables, print the estimated bytes with a dry-run query (`job_config.dry_run=True`) and keep single-job scans under ~50 GB. Aggregate-then-pull patterns (do the heavy group-bys in BigQuery SQL, pull only the reduced frame into pandas) are preferred over `SELECT *` into memory. The RAPM design matrix specifically must be built from the pre-aggregated identical-lineup grouping (as the plan states), pulled as one reduced query.

## Credential failure protocol
On any 403/permission error: print the exact missing permission from the error, the table involved, and stop. I will fix IAM and tell you to retry. Do not work around permissions by writing to a different dataset.
