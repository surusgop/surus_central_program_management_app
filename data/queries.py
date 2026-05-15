"""
Dashboard data layer — uses Databricks SQL Connector against a SQL Warehouse.

Required env vars:
  DATABRICKS_HOST          Workspace URL  e.g. https://adb-xxx.azuredatabricks.net
  DATABRICKS_TOKEN         Personal access token
  DATABRICKS_SQL_HTTP_PATH SQL Warehouse HTTP path  e.g. /sql/1.0/warehouses/<id>

Optional:
  QUERY_CACHE_SECONDS      How long to cache query results (default: 300)

─────────────────────────────────────────────────────────────────────────────
HOW TO ADD YOUR QUERIES
  1. Replace the placeholder catalog/schema/table references below.
  2. The district_id column must match the `id` field in your GeoJSON features
     (see geojson/README.md).
  3. Add new metric keys to HEATMAP_VARIABLES and write their SQL in
     _METRIC_SQL. That's all — the map page discovers them automatically.
─────────────────────────────────────────────────────────────────────────────
"""

from __future__ import annotations

import os
import time
import threading
import functools
from typing import Any

import pandas as pd
from databricks import sql
from dotenv import load_dotenv

load_dotenv()

# ── Connection ────────────────────────────────────────────────────────────────

_HOST = os.environ.get("DATABRICKS_HOST", "").replace("https://", "").rstrip("/")
_TOKEN = os.environ.get("DATABRICKS_TOKEN", "")
_HTTP_PATH = os.environ.get("DATABRICKS_SQL_HTTP_PATH", "")
_CACHE_TTL = int(os.environ.get("QUERY_CACHE_SECONDS", 300))


def _connect() -> sql.client.Connection:
    return sql.connect(
        server_hostname=_HOST,
        http_path=_HTTP_PATH,
        access_token=_TOKEN,
    )


def run_query(sql_str: str) -> pd.DataFrame:
    with _connect() as conn:
        with conn.cursor() as cur:
            cur.execute(sql_str)
            return cur.fetchall_arrow().to_pandas()


# ── Simple TTL cache (no extra dependencies) ──────────────────────────────────

_cache: dict[str, tuple[float, Any]] = {}
_cache_lock = threading.Lock()


def _cached(key: str, fn, ttl: int = _CACHE_TTL):
    with _cache_lock:
        entry = _cache.get(key)
        if entry and (time.monotonic() - entry[0]) < ttl:
            return entry[1]
    result = fn()
    with _cache_lock:
        _cache[key] = (time.monotonic(), result)
    return result


def bust_cache():
    with _cache_lock:
        _cache.clear()


# ── Heatmap variable registry ─────────────────────────────────────────────────
#
# Add / remove entries here to control what appears in the variable slicer.
# key   → used as the button value and column alias in SQL
# label → display text on the button

HEATMAP_VARIABLES: dict[str, str] = {
    "total_population":  "Population",
    "median_income":     "Median Income",
    "voter_turnout_pct": "Voter Turnout %",
    "registered_voters": "Registered Voters",
    # "your_metric": "Your Label",
}

# ── Per-metric SQL ────────────────────────────────────────────────────────────
#
# Each key must match a key in HEATMAP_VARIABLES.
# The query must return exactly two columns: district_id and metric_value.
# Replace catalog / schema / table references with your actual names.

_METRIC_SQL: dict[str, str] = {
    "total_population": """
        SELECT district_id, SUM(population) AS metric_value
        FROM   your_catalog.your_schema.district_demographics
        GROUP  BY district_id
    """,
    "median_income": """
        SELECT district_id, MEDIAN(household_income) AS metric_value
        FROM   your_catalog.your_schema.district_demographics
        GROUP  BY district_id
    """,
    "voter_turnout_pct": """
        SELECT district_id,
               ROUND(100.0 * SUM(votes_cast) / NULLIF(SUM(eligible_voters), 0), 1) AS metric_value
        FROM   your_catalog.your_schema.election_results
        GROUP  BY district_id
    """,
    "registered_voters": """
        SELECT district_id, SUM(registered_voters) AS metric_value
        FROM   your_catalog.your_schema.voter_rolls
        GROUP  BY district_id
    """,
}


def get_district_metric(metric: str) -> pd.DataFrame:
    """
    Return a DataFrame with columns [district_id, metric_value] for the
    requested metric. Results are cached for QUERY_CACHE_SECONDS seconds.

    Raises KeyError if metric is not in HEATMAP_VARIABLES.
    """
    if metric not in _METRIC_SQL:
        raise KeyError(f"Unknown metric '{metric}'. Add it to _METRIC_SQL in data/queries.py.")

    return _cached(
        key=f"district_metric:{metric}",
        fn=functools.partial(run_query, _METRIC_SQL[metric]),
    )


# ── Filter / slicer data ──────────────────────────────────────────────────────

def get_filter_options(table: str, column: str) -> list[str]:
    """Generic helper: distinct values for a column, alphabetically sorted."""
    sql_str = f"""
        SELECT DISTINCT {column} AS val
        FROM   {table}
        ORDER  BY val
    """
    df = _cached(key=f"filter:{table}:{column}", fn=functools.partial(run_query, sql_str))
    return df["val"].dropna().astype(str).tolist()


def get_district_list() -> list[dict]:
    """
    Return [{label: "District Name", value: "district_id"}, ...] for the
    district dropdown slicer.  Replace the query with your actual source.
    """
    sql_str = """
        SELECT DISTINCT district_id, district_name
        FROM   your_catalog.your_schema.districts
        ORDER  BY district_name
    """
    df = _cached(key="district_list", fn=functools.partial(run_query, sql_str))
    return [
        {"label": row["district_name"], "value": row["district_id"]}
        for _, row in df.iterrows()
    ]


# ── Per-district detail queries ───────────────────────────────────────────────
#
# Each function accepts a district_id and returns a DataFrame for one chart.
# Replace catalog/schema/table references with your actual names.

def get_district_kpis(district_id: str) -> dict:
    """
    Scalar KPIs for the selected district.
    Returns a dict of {metric_name: value}.
    """
    sql_str = f"""
        SELECT
            SUM(population)                                                  AS total_population,
            MEDIAN(household_income)                                         AS median_income,
            ROUND(100.0 * SUM(votes_cast) / NULLIF(SUM(eligible_voters),0), 1) AS voter_turnout_pct,
            SUM(registered_voters)                                           AS registered_voters
        FROM   your_catalog.your_schema.district_demographics
        WHERE  district_id = '{district_id}'
    """
    df = _cached(
        key=f"kpis:{district_id}",
        fn=functools.partial(run_query, sql_str),
        ttl=_CACHE_TTL,
    )
    return df.iloc[0].to_dict() if not df.empty else {}


def get_district_trend(district_id: str) -> pd.DataFrame:
    """
    Time-series data for the selected district.
    Returns columns [period, metric_value].
    Replace with your actual trend table and date column.
    """
    sql_str = f"""
        SELECT period, metric_value
        FROM   your_catalog.your_schema.district_trends
        WHERE  district_id = '{district_id}'
        ORDER  BY period
    """
    return _cached(
        key=f"trend:{district_id}",
        fn=functools.partial(run_query, sql_str),
    )


def get_district_breakdown(district_id: str) -> pd.DataFrame:
    """
    Category breakdown for the selected district (drives the bar chart).
    Returns columns [category, value].
    """
    sql_str = f"""
        SELECT category, SUM(value) AS value
        FROM   your_catalog.your_schema.district_breakdown
        WHERE  district_id = '{district_id}'
        GROUP  BY category
        ORDER  BY value DESC
        LIMIT  15
    """
    return _cached(
        key=f"breakdown:{district_id}",
        fn=functools.partial(run_query, sql_str),
    )


def get_district_table(district_id: str) -> pd.DataFrame:
    """
    Detail rows for the selected district (drives the data table).
    Returns any columns you want displayed.
    """
    sql_str = f"""
        SELECT *
        FROM   your_catalog.your_schema.district_detail
        WHERE  district_id = '{district_id}'
        ORDER  BY sort_key
        LIMIT  500
    """
    return _cached(
        key=f"table:{district_id}",
        fn=functools.partial(run_query, sql_str),
    )
