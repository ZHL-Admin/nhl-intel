"""Utilities for loading raw data into BigQuery."""

import json
from datetime import datetime
from io import BytesIO
from typing import Union, List, Any
from google.cloud import bigquery


def _clean_empty_structs(obj: Any) -> Any:
    """Recursively convert empty dicts to None for BigQuery compatibility.

    BigQuery's autodetect cannot handle empty structs, so we convert them to null.
    """
    if isinstance(obj, dict):
        if not obj:  # Empty dict
            return None
        return {k: _clean_empty_structs(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [_clean_empty_structs(item) for item in obj]
    return obj


def load_json_to_bigquery(
    project_id: str,
    dataset_id: str,
    table_id: str,
    data: Union[dict, List[dict]],
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

    # Clean empty structs and add ingestion timestamp to each row
    ingestion_date = datetime.utcnow().date().isoformat()
    cleaned_data = []
    for row in data:
        cleaned_row = _clean_empty_structs(row)
        if cleaned_row is not None:
            cleaned_row["ingestion_date"] = ingestion_date
            cleaned_data.append(cleaned_row)

    job_config = bigquery.LoadJobConfig(
        source_format=bigquery.SourceFormat.NEWLINE_DELIMITED_JSON,
        write_disposition=bigquery.WriteDisposition.WRITE_APPEND,
        autodetect=True,
        schema_update_options=[
            bigquery.SchemaUpdateOption.ALLOW_FIELD_ADDITION,
        ],
    )

    # Convert to newline-delimited JSON bytes
    ndjson = "\n".join(json.dumps(row) for row in cleaned_data)
    file_obj = BytesIO(ndjson.encode("utf-8"))

    load_job = client.load_table_from_file(
        file_obj=file_obj,
        destination=table_ref,
        job_config=job_config,
    )

    load_job.result()
