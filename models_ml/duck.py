"""Shared DuckDB serving access + BigQuery->DuckDB SQL compatibility shim.

ONE place, used by both the backend (request-time reads, via backend/services/serving.py and
the BigQueryService facade) and the model-scoring layer (models_ml/bq.query_df, so score_line /
score_team_fit read the same serving file when the API calls them).

BigQuery stays the nightly COMPUTE engine. `serving_backend()` is 'bigquery' by DEFAULT
(compute-safe: training/precompute/export jobs read BigQuery), and the API process opts into
'duckdb' (main.py sets SERVING_BACKEND=duckdb). `to_duckdb_sql` rewrites the BigQuery-isms that
appear in this codebase's request-time queries into DuckDB equivalents — narrow and verified by
scripts/verify_serving_parity.py, not a general translator.
"""
from __future__ import annotations

import os
import re
import threading
from pathlib import Path
from typing import Any, Dict, List, Optional

REPO_ROOT = Path(__file__).resolve().parent.parent
_DATASETS = ("nhl_staging", "nhl_mart", "nhl_models", "nhl_raw")


def serving_backend() -> str:
    """'bigquery' (default, compute-safe) or 'duckdb' (the API opts in)."""
    return os.getenv("SERVING_BACKEND", "bigquery").strip().lower()


def serving_active() -> bool:
    return serving_backend() == "duckdb"


def duckdb_path() -> Path:
    p = os.getenv("SERVING_DUCKDB_PATH", "data/serving/nhl_intel.duckdb")
    path = Path(p)
    return path if path.is_absolute() else REPO_ROOT / path


# --------------------------------------------------------------------------- #
# BigQuery -> DuckDB SQL compatibility shim
# --------------------------------------------------------------------------- #
_QUALIFIED_3 = re.compile(
    r"`?[A-Za-z0-9_\-]+\.(" + "|".join(_DATASETS) + r")\.([A-Za-z0-9_]+)`?"
)
_QUALIFIED_2 = re.compile(r"`?\b(" + "|".join(_DATASETS) + r")\.([A-Za-z0-9_]+)`?")
_OFFSET = re.compile(r"OFFSET\((\d+)\)", re.IGNORECASE)
_ORDINAL = re.compile(r"ORDINAL\((\d+)\)", re.IGNORECASE)
# ARRAY_AGG(... ORDER BY ... LIMIT 1) -> drop the inner LIMIT (DuckDB array_agg has no inner
# LIMIT; taking [1] of the fully-ordered aggregate yields the same "first row" result).
_ARRAYAGG_LIMIT = re.compile(
    r"(ARRAY_AGG\([^()]*ORDER BY[^()]*?)\s+LIMIT\s+1\s*\)", re.IGNORECASE
)


def to_duckdb_sql(sql: str) -> str:
    s = sql
    # 1. Fully-qualified table names -> bare table name (DuckDB default schema).
    s = _QUALIFIED_3.sub(r"\2", s)
    s = _QUALIFIED_2.sub(r"\2", s)
    s = s.replace("`", "")
    # 2. ARRAY_AGG(... LIMIT 1) -> ARRAY_AGG(...)   (before the OFFSET rewrite below)
    s = _ARRAYAGG_LIMIT.sub(r"\1)", s)
    # 3. BigQuery array indexing OFFSET(n)/ORDINAL(n) -> DuckDB 1-based [n+1]/[n]
    s = _OFFSET.sub(lambda m: str(int(m.group(1)) + 1), s)
    s = _ORDINAL.sub(lambda m: m.group(1), s)
    # 4. SAFE_CAST -> TRY_CAST; SPLIT -> string_split; COUNTIF -> count_if
    s = re.sub(r"\bSAFE_CAST\b", "TRY_CAST", s, flags=re.IGNORECASE)
    s = re.sub(r"\bCOUNTIF\b", "count_if", s, flags=re.IGNORECASE)
    s = re.sub(r"\bSPLIT\s*\(", "string_split(", s, flags=re.IGNORECASE)
    # 5. BigQuery scalar types -> DuckDB types
    s = re.sub(r"\bINT64\b", "BIGINT", s, flags=re.IGNORECASE)
    s = re.sub(r"\bFLOAT64\b", "DOUBLE", s, flags=re.IGNORECASE)
    s = re.sub(r"\bAS\s+STRING\b", "AS VARCHAR", s, flags=re.IGNORECASE)
    # 6. Named params @x -> $x (DuckDB prepared-param syntax)
    s = re.sub(r"@([A-Za-z_][A-Za-z0-9_]*)", r"$\1", s)
    return s


# safe_divide is a function in BigQuery; recreate it as a session TEMP macro so the same SQL runs.
# TEMP (not persistent) because the serving file is attached read-only.
_INIT_SQL = [
    "CREATE OR REPLACE TEMP MACRO safe_divide(a, b) AS "
    "(CASE WHEN b = 0 OR b IS NULL THEN NULL ELSE a / b END)",
]


def params_to_dict(params: Optional[List[Any]]) -> Optional[Dict[str, Any]]:
    """Convert a BigQuery ScalarQueryParameter list into a {name: value} dict for DuckDB."""
    if not params:
        return None
    out: Dict[str, Any] = {}
    for p in params:
        name = getattr(p, "name", None)
        value = getattr(p, "value", None)
        if name is not None:
            out[name] = value
    return out or None


_con = None
_con_lock = threading.Lock()


def connection():
    """Singleton read-only DuckDB connection to the serving file (lazily opened)."""
    global _con
    if _con is None:
        with _con_lock:
            if _con is None:
                import duckdb

                path = duckdb_path()
                if not path.exists():
                    raise RuntimeError(
                        f"DuckDB serving file not found at {path}. Run `make export-serving` "
                        f"(python -m scripts.export_to_duckdb) first, or set "
                        f"SERVING_BACKEND=bigquery to bypass the serving layer."
                    )
                con = duckdb.connect(str(path), read_only=True)
                for stmt in _INIT_SQL:
                    con.execute(stmt)
                _con = con
    return _con


# Serialize access to the single read-only connection (where the TEMP safe_divide macro lives).
# Serving queries are millisecond-fast on the local columnar file, so a lock is cheap and avoids
# DuckDB cursor / temp-object scoping issues across worker threads.
_query_lock = threading.Lock()


def query_rows(sql: str, params: Optional[List[Any]] = None) -> List[Dict[str, Any]]:
    """Run a (BigQuery-dialect) query against DuckDB, returning a list of dict rows."""
    duck_sql = to_duckdb_sql(sql)
    bind = params_to_dict(params)
    con = connection()
    with _query_lock:
        rel = con.execute(duck_sql, bind) if bind else con.execute(duck_sql)
        cols = [d[0] for d in rel.description]
        rows = rel.fetchall()
    return [dict(zip(cols, row)) for row in rows]


def query_df(sql: str):
    """Run a (BigQuery-dialect) query against DuckDB, returning a pandas DataFrame."""
    duck_sql = to_duckdb_sql(sql)
    con = connection()
    with _query_lock:
        return con.execute(duck_sql).df()
