"""Utilities for loading raw data into BigQuery."""

import json
import logging
from datetime import datetime
from io import BytesIO
from typing import Union, List, Any
from google.cloud import bigquery

logger = logging.getLogger(__name__)


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


def _serialize_nested_fields(row: dict, fields_to_serialize: List[str]) -> dict:
    """Serialize specified nested fields to JSON strings.

    This makes the schema resilient to API type changes in nested fields that are not
    used in dbt models. These fields are stored as raw JSON strings rather than typed
    RECORD structures.

    Args:
        row: Data row dict to process.
        fields_to_serialize: List of top-level field names to serialize to JSON.

    Returns:
        Modified row with specified fields serialized to JSON strings.
    """
    for field in fields_to_serialize:
        if field in row and row[field] is not None:
            row[field] = json.dumps(row[field])
    return row


def load_json_to_bigquery(
    project_id: str,
    dataset_id: str,
    table_id: str,
    data: Union[dict, List[dict]],
    season: str = None,
) -> None:
    """Load raw JSON data to a BigQuery table.

    Args:
        project_id: GCP project ID.
        dataset_id: BigQuery dataset name.
        table_id: BigQuery table name.
        data: Raw data dict or list of dicts to load.
        season: Season string in format "YYYY-YY" (e.g., "2024-25").
                If not provided, defaults to current season derived from ingestion date.
    """
    client = bigquery.Client(project=project_id)
    table_ref = f"{project_id}.{dataset_id}.{table_id}"

    if isinstance(data, dict):
        data = [data]

    # Clean empty structs and add ingestion timestamp and season to each row
    ingestion_date = datetime.utcnow().date().isoformat()

    # Derive season from ingestion date if not provided
    if season is None:
        current_year = datetime.utcnow().year
        current_month = datetime.utcnow().month
        # NHL season runs from October to June, so if month >= 10, it's the start of the season
        if current_month >= 10:
            season = f"{current_year}-{str(current_year + 1)[2:]}"
        else:
            season = f"{current_year - 1}-{str(current_year)[2:]}"

    # Define nested fields to serialize as JSON strings to avoid schema conflicts
    # These are fields not used in dbt models that could have API type changes
    fields_to_serialize_by_table = {
        "raw_boxscores": ["tvBroadcasts", "gameVideo"],
        "raw_play_by_play": ["tvBroadcasts"],
        "raw_schedule": ["tvBroadcasts", "ticketsLink"],
        # Shift charts: store the whole shift array as a serialized JSON string,
        # parsed downstream by stg_shifts (resilient to API schema drift).
        "raw_shift_charts": ["data"],
        # Edge reports: each report's payload shape differs; store it serialized and
        # parse per-report in the stg_edge_* models.
        "raw_edge_skaters": ["data"],
        "raw_edge_goalies": ["data"],
        "raw_edge_teams": ["data"],
    }

    cleaned_data = []
    for row in data:
        cleaned_row = _clean_empty_structs(row)
        if cleaned_row is not None:
            cleaned_row["ingestion_date"] = ingestion_date
            cleaned_row["season"] = season
            # Add game_id from id field if it exists (for boxscores and play-by-play)
            if "id" in cleaned_row and table_id in ["raw_boxscores", "raw_play_by_play", "raw_shift_charts"]:
                cleaned_row["game_id"] = cleaned_row["id"]

            # Serialize vulnerable nested fields to JSON strings
            if table_id in fields_to_serialize_by_table:
                cleaned_row = _serialize_nested_fields(
                    cleaned_row, fields_to_serialize_by_table[table_id]
                )

            cleaned_data.append(cleaned_row)

    job_config = bigquery.LoadJobConfig(
        source_format=bigquery.SourceFormat.NEWLINE_DELIMITED_JSON,
        write_disposition=bigquery.WriteDisposition.WRITE_APPEND,
        autodetect=True,
        ignore_unknown_values=True,
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

    result = load_job.result()

    # Log warnings if any rows had unknown values
    if result.output_rows != len(cleaned_data):
        logger.warning(
            f"Loaded {result.output_rows} rows to {table_id}, but {len(cleaned_data)} rows were provided. "
            f"Some rows may have had unknown values that were ignored."
        )
