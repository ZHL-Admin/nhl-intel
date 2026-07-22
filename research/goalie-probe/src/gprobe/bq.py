"""BigQuery read-only with once-per-run parquet cache (reproducible offline)."""
from __future__ import annotations
import polars as pl
from . import config

def client():
    from google.cloud import bigquery
    return bigquery.Client.from_service_account_json(str(config.SA_KEYFILE), project=config.BQ_PROJECT)

def cached_query(name: str, sql: str, refresh: bool = False) -> pl.DataFrame:
    config.CACHE.mkdir(parents=True, exist_ok=True)
    f = config.CACHE / f"{name}.parquet"
    if f.exists() and not refresh:
        return pl.read_parquet(f)
    df = pl.from_arrow(client().query(sql).result().to_arrow())
    if isinstance(df, pl.Series): df = df.to_frame()
    df.write_parquet(f)
    return df
