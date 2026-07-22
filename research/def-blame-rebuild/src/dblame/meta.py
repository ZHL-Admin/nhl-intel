"""Player metadata (names, sweater numbers, position D/F) cached once from BigQuery for roles + reports."""
from __future__ import annotations

import polars as pl

from . import config as C

META = C.PARQUET / "player_meta.parquet"


def build() -> pl.DataFrame:
    from google.cloud import bigquery
    c = bigquery.Client.from_service_account_json(str(C.SA_KEYFILE), project=C.BQ_PROJECT)
    q = c.query(f"""
      select player_id,
             any_value(full_name) full_name,
             any_value(sweater_number) sweater,
             any_value(position_code) pos
      from `{C.BQ_PROJECT}.nhl_staging.stg_roster_current`
      where player_id is not null group by 1""").result()
    df = pl.DataFrame([{"player_id": r.player_id, "full_name": r.full_name,
                        "sweater": r.sweater, "pos": r.pos} for r in q])
    df = df.with_columns(is_def=pl.col("pos") == "D")
    C.PARQUET.mkdir(parents=True, exist_ok=True)
    df.write_parquet(META)
    return df


def load() -> pl.DataFrame:
    return pl.read_parquet(META) if META.exists() else build()


if __name__ == "__main__":
    df = build()
    print(f"player_meta: {df.height:,} players | D: {int(df['is_def'].sum()):,} | F: {int((~df['is_def']).sum()):,}")
