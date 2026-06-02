"""Utilities for loading raw data into BigQuery."""

import json
from datetime import datetime
from io import BytesIO
from google.cloud import bigquery


def load_json_to_bigquery(
    project_id: str,
    dataset_id: str,
    table_id: str,
    data: dict | list[dict],
) -> None:
    """Load raw JSON data to a BigQuery table.

    Args:
        project_id: GCP project ID.
        dataset_id: BigQuery dataset name.
        table_id: BigQuery table name.
        data: Raw data dict or list of dicts to load.
    """
    client = bigquery.Client(project=project_id)
    table_ref = f"{project_id}.{dataset_id}.{table_id}"

    if isinstance(data, dict):
        data = [data]

    # Add ingestion timestamp to each row
    ingestion_date = datetime.utcnow().date().isoformat()
    for row in data:
        row["ingestion_date"] = ingestion_date

    job_config = bigquery.LoadJobConfig(
        source_format=bigquery.SourceFormat.NEWLINE_DELIMITED_JSON,
        write_disposition=bigquery.WriteDisposition.WRITE_APPEND,
        autodetect=True,
    )

    # Convert to newline-delimited JSON bytes
    ndjson = "\n".join(json.dumps(row) for row in data)
    file_obj = BytesIO(ndjson.encode("utf-8"))

    load_job = client.load_table_from_file(
        file_obj=file_obj,
        destination=table_ref,
        job_config=job_config,
    )

    load_job.result()
