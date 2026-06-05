"""BigQuery client and query utilities.

Provides singleton BigQuery client and helper methods for querying mart tables.
"""
import os
from pathlib import Path
from typing import List, Dict, Any, Optional
from google.cloud import bigquery


class BigQueryService:
    """Singleton service for BigQuery operations.

    Manages connection to BigQuery and provides query utilities for mart tables.
    """

    _instance: Optional['BigQueryService'] = None
    _client: Optional[bigquery.Client] = None

    def __new__(cls) -> 'BigQueryService':
        """Ensure only one instance of BigQueryService exists."""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self) -> None:
        """Initialize BigQuery client if not already initialized."""
        if self._client is None:
            self.project_id = os.getenv("GCP_PROJECT_ID")
            # Configure datasets for different model layers
            self.dataset_staging = os.getenv("GCP_DATASET_STAGING", "nhl_staging")
            self.dataset_mart = os.getenv("GCP_DATASET_MART", "nhl_mart")

            # Handle credentials path - make it absolute if relative
            creds_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
            if creds_path and not Path(creds_path).is_absolute():
                # Assume relative to project root (parent of backend dir)
                root_dir = Path(__file__).parent.parent.parent
                creds_path = str(root_dir / creds_path)
                os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = creds_path

            self._client = bigquery.Client(project=self.project_id)

    @property
    def client(self) -> bigquery.Client:
        """Get BigQuery client instance.

        Returns:
            BigQuery client instance.
        """
        if self._client is None:
            raise RuntimeError("BigQuery client not initialized")
        return self._client

    def query(self, sql: str, params: Optional[List[Any]] = None) -> List[Dict[str, Any]]:
        """Execute a query and return results as list of dicts.

        Args:
            sql: SQL query string.
            params: Optional query parameters for parameterized queries.

        Returns:
            List of dictionaries representing query results.

        Raises:
            Exception: If query execution fails.
        """
        job_config = bigquery.QueryJobConfig()

        if params:
            job_config.query_parameters = params

        query_job = self.client.query(sql, job_config=job_config)
        results = query_job.result()

        return [dict(row) for row in results]

    def get_full_table_id(self, table_name: str) -> str:
        """Get fully qualified table ID, routing to correct dataset by prefix.

        Args:
            table_name: Name of the table (e.g., 'stg_boxscores', 'mart_team_game_stats').

        Returns:
            Fully qualified table ID (project.dataset.table).
        """
        # Route tables to correct dataset based on prefix
        if table_name.startswith('mart_'):
            dataset = self.dataset_mart
        elif table_name.startswith('stg_') or table_name.startswith('int_'):
            dataset = self.dataset_staging
        else:
            # Default to mart for backwards compatibility
            dataset = self.dataset_mart

        return f"{self.project_id}.{dataset}.{table_name}"


# Create singleton instance
bq_service = BigQueryService()
