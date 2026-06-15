"""
Thin BigQuery helpers shared by the model layer (``models_ml/``).

Centralises client creation, query-to-DataFrame, and DataFrame-to-table writes so the
training and scoring jobs never re-implement them. Model outputs land in the
``nhl_models`` dataset (config.MODELS_DATASET), created on first write if absent.
"""

from __future__ import annotations

import os

import pandas as pd
from google.cloud import bigquery

from models_ml import config

STAGING_DATASET = "nhl_staging"
MART_DATASET = "nhl_mart"


def client() -> bigquery.Client:
    return bigquery.Client(project=os.environ[config.GCP_PROJECT_ENV])


def project() -> str:
    return os.environ[config.GCP_PROJECT_ENV]


def staging(table: str) -> str:
    return f"`{project()}.{STAGING_DATASET}.{table}`"


def mart(table: str) -> str:
    return f"`{project()}.{MART_DATASET}.{table}`"


def models(table: str) -> str:
    return f"`{project()}.{config.MODELS_DATASET}.{table}`"


def query_df(sql: str, cli: bigquery.Client | None = None) -> pd.DataFrame:
    cli = cli or client()
    # Use the BigQuery Storage API when available (far faster than the REST download for
    # the multi-million-row training/scoring pulls); fall back to REST if it is missing.
    try:
        return cli.query(sql).result().to_dataframe(create_bqstorage_client=True)
    except Exception:
        return cli.query(sql).result().to_dataframe(create_bqstorage_client=False)


def ensure_models_dataset(cli: bigquery.Client | None = None) -> None:
    cli = cli or client()
    ds_id = f"{project()}.{config.MODELS_DATASET}"
    try:
        cli.get_dataset(ds_id)
    except Exception:
        ds = bigquery.Dataset(ds_id)
        ds.location = "US"
        cli.create_dataset(ds, exists_ok=True)


def write_df(
    df: pd.DataFrame,
    table: str,
    write_disposition: str = "WRITE_TRUNCATE",
    cli: bigquery.Client | None = None,
    clustering_fields: list[str] | None = None,
) -> None:
    """Write a DataFrame to nhl_models.<table>. WRITE_TRUNCATE replaces, WRITE_APPEND adds."""
    cli = cli or client()
    ensure_models_dataset(cli)
    table_id = f"{project()}.{config.MODELS_DATASET}.{table}"
    job_config = bigquery.LoadJobConfig(write_disposition=write_disposition)
    if clustering_fields:
        job_config.clustering_fields = clustering_fields
    cli.load_table_from_dataframe(df, table_id, job_config=job_config).result()


def delete_partition_since(table: str, date_col: str, since: str,
                           cli: bigquery.Client | None = None) -> None:
    """Delete rows on/after `since` so an incremental --since rescore is idempotent.
    No-op if the table does not exist yet."""
    cli = cli or client()
    table_id = f"{project()}.{config.MODELS_DATASET}.{table}"
    try:
        cli.get_table(table_id)
    except Exception:
        return
    cli.query(
        f"DELETE FROM `{table_id}` WHERE {date_col} >= '{since}'"
    ).result()
