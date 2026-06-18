"""Backend adapter over the shared DuckDB serving layer (models_ml/duck.py).

The actual connection + BigQuery->DuckDB SQL shim live in models_ml/duck so the backend and
the model-scoring layer share one implementation. This module exposes the small slice the
BigQueryService facade uses, and ensures the repo root is importable (the backend runs from
backend/, the model layer lives at the repo root).
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, List, Optional

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from models_ml import duck  # noqa: E402


def serving_backend() -> str:
    return duck.serving_backend()


class ServingDB:
    """Read-only DuckDB serving access mirroring the BigQueryService slice the routers use."""

    def query(self, sql: str, params: Optional[List[Any]] = None) -> List[dict]:
        return duck.query_rows(sql, params)

    @staticmethod
    def get_full_table_id(table_name: str) -> str:
        return table_name

    @staticmethod
    def get_models_table_id(table_name: str) -> str:
        return table_name


_serving_db: Optional[ServingDB] = None


def get_serving_db() -> ServingDB:
    global _serving_db
    if _serving_db is None:
        _serving_db = ServingDB()
    return _serving_db
