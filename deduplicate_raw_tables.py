"""Deduplicate raw BigQuery tables.

This script removes duplicate game records from raw tables by keeping
only the most recent ingestion_date for each unique game_id.
"""

import os
from google.cloud import bigquery
from dotenv import load_dotenv

load_dotenv()


def deduplicate_table(client: bigquery.Client, project_id: str, dataset: str, table: str):
    """Deduplicate a table by keeping the latest ingestion_date per game_id.

    Args:
        client: BigQuery client.
        project_id: GCP project ID.
        dataset: Dataset name.
        table: Table name.
    """
    temp_table = f"{table}_deduped"
    full_table_ref = f"{project_id}.{dataset}.{table}"
    temp_table_ref = f"{project_id}.{dataset}.{temp_table}"

    print(f"\nDeduplicating {full_table_ref}...")

    # Create deduplicated temp table
    dedup_query = f"""
    CREATE OR REPLACE TABLE `{temp_table_ref}` AS
    SELECT * EXCEPT(row_num)
    FROM (
        SELECT
            *,
            ROW_NUMBER() OVER (
                PARTITION BY game_id, season
                ORDER BY ingestion_date DESC
            ) as row_num
        FROM `{full_table_ref}`
    )
    WHERE row_num = 1
    """

    print(f"  Creating deduplicated temp table...")
    job = client.query(dedup_query)
    job.result()  # Wait for completion
    print(f"  ✓ Created {temp_table}")

    # Get counts
    original_count_query = f"SELECT COUNT(*) as cnt FROM `{full_table_ref}`"
    deduped_count_query = f"SELECT COUNT(*) as cnt FROM `{temp_table_ref}`"

    original_job = client.query(original_count_query)
    original_count = list(original_job.result())[0].cnt

    deduped_job = client.query(deduped_count_query)
    deduped_count = list(deduped_job.result())[0].cnt

    duplicates_removed = original_count - deduped_count

    print(f"  Original rows: {original_count:,}")
    print(f"  Deduplicated rows: {deduped_count:,}")
    print(f"  Duplicates removed: {duplicates_removed:,}")

    # Drop original table and rename temp table
    print(f"  Replacing original table with deduplicated version...")
    client.delete_table(full_table_ref)

    # Use ALTER TABLE RENAME (more efficient than CREATE TABLE AS SELECT)
    rename_query = f"ALTER TABLE `{temp_table_ref}` RENAME TO {table}"
    rename_job = client.query(rename_query)
    rename_job.result()  # Wait for completion

    print(f"  ✓ Replaced {table} with deduplicated version")


def main():
    """Main deduplication process."""
    project_id = os.getenv("GCP_PROJECT_ID")
    dataset_raw = os.getenv("GCP_DATASET_RAW", "nhl_raw")

    client = bigquery.Client(project=project_id)

    print(f"{'='*60}")
    print(f"Deduplicating Raw Tables in {dataset_raw}")
    print(f"{'='*60}")

    tables_to_dedupe = ["raw_boxscores", "raw_play_by_play"]

    for table in tables_to_dedupe:
        deduplicate_table(client, project_id, dataset_raw, table)

    print(f"\n{'='*60}")
    print(f"Deduplication Complete!")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    main()
