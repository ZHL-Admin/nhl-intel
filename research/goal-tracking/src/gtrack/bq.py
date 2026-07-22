"""BigQuery read-only access with a once-per-stage local parquet cache.

Every query is cached to ``data/cache/<name>.parquet``; downstream phases read the cache so the whole
program is reproducible offline (``make stage0`` re-derives from cache without touching BigQuery). No
writes to production. Auth uses the repo service-account keyfile via config (no atlas/production import).
"""
from __future__ import annotations

from pathlib import Path

import polars as pl

from . import config


def client():
    from google.cloud import bigquery
    return bigquery.Client.from_service_account_json(str(config.SA_KEYFILE), project=config.BQ_PROJECT)


def cached_query(name: str, sql: str, refresh: bool = False) -> pl.DataFrame:
    """Run ``sql`` once, cache the result to data/cache/<name>.parquet, and reuse it thereafter."""
    config.CACHE.mkdir(parents=True, exist_ok=True)
    f = config.CACHE / f"{name}.parquet"
    if f.exists() and not refresh:
        return pl.read_parquet(f)
    tbl = client().query(sql).result().to_arrow()
    df = pl.from_arrow(tbl)
    if isinstance(df, pl.Series):
        df = df.to_frame()
    df.write_parquet(f)
    return df


def cache_path(name: str) -> Path:
    return config.CACHE / f"{name}.parquet"
