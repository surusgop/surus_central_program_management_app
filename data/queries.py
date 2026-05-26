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
import sys
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


def run_query(sql_str: str, label: str = "") -> pd.DataFrame:
    tag = f"[sql:{label}]" if label else "[sql]"
    print(f"{tag} {' '.join(sql_str.split())}", file=sys.stderr, flush=True)
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


def _list_key(values: list[str] | None) -> str:
    """Deterministic cache-key fragment for a list of strings."""
    return "|".join(sorted(values)) if values else ""


def _in_filter(column: str, values: list[str] | None) -> str:
    """Build an 'AND column IN (...)' clause, or '' when values is empty."""
    if not values:
        return ""
    escaped = ", ".join(f"'{v}'" for v in values)
    return f"AND {column} IN ({escaped})"


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
        fn=functools.partial(run_query, _METRIC_SQL[metric], label=f"heatmap:{metric}"),
    )


# ── Filter / slicer data ──────────────────────────────────────────────────────

def get_filter_options(table: str, column: str) -> list[str]:
    """Generic helper: distinct values for a column, alphabetically sorted."""
    sql_str = f"""
        SELECT DISTINCT {column} AS val
        FROM   {table}
        ORDER  BY val
    """
    df = _cached(key=f"filter:{table}:{column}", fn=functools.partial(run_query, sql_str, label=f"filter:{column}"))
    return df["val"].dropna().astype(str).tolist()


def get_state_list() -> list[dict]:
    """Return [{label: "IL", value: "IL"}, ...] for the state dropdown."""
    sql_str = """
        SELECT DISTINCT `registered_address.state` AS state_abbr
        FROM   universal.deltatables.vcs_gold
        WHERE  `registered_address.state` IS NOT NULL
        ORDER  BY state_abbr
    """
    df = _cached(key="state_list", fn=functools.partial(run_query, sql_str, label="state_list"))
    return [
        {"label": row["state_abbr"], "value": row["state_abbr"]}
        for _, row in df.iterrows()
    ]


def get_client_list(states: list[str], program: str) -> list[dict]:
    """
    Return [{label: "nation-slug", value: "nation-slug"}, ...] for the client
    dropdown, filtered to the selected states and program.
    When program='both', labels include the program in parentheses.
    """
    if not states:
        return []
    prog_filter   = "`group` IN ('CLP', 'BP')" if program == "both" else f"`group` = '{program}'"
    state_filter  = _in_filter("state", states)
    sql_str = f"""
        SELECT DISTINCT nation, `group`
        FROM   universal.prod.signups
        WHERE  {prog_filter}
        {state_filter}
        ORDER  BY nation
    """
    df = _cached(
        key=f"client_list:{_list_key(states)}:{program}",
        fn=functools.partial(run_query, sql_str, label="client_list"),
    )
    show_group = program == "both"
    return [
        {
            "label": f"{row['nation']} ({row['group']})" if show_group else row["nation"],
            "value": row["nation"],
        }
        for _, row in df.iterrows()
    ]


def get_district_list(states: list[str]) -> list[dict]:
    """
    Return [{label: "District Name", value: "district_id"}, ...] for the
    district dropdown, filtered to the selected states.
    """
    if not states:
        return []
    state_filter = _in_filter("`registered_address.state`", states)
    sql_str = f"""
        SELECT DISTINCT state_upper_district AS district_id
        FROM   universal.deltatables.vcs_gold
        WHERE  1=1
        {state_filter}
        ORDER  BY district_id
    """
    df = _cached(
        key=f"district_list:{_list_key(states)}",
        fn=functools.partial(run_query, sql_str, label="district_list"),
    )
    return [
        {"label": row["district_id"], "value": row["district_id"]}
        for _, row in df.iterrows()
    ]


# ── Per-district detail queries ───────────────────────────────────────────────
#
# Each function accepts a district_id and returns a DataFrame for one chart.
# Replace catalog/schema/table references with your actual names.

def get_district_demographics(district_ids: list[str] | None = None) -> dict:
    """
    Voter-file demographics aggregated across the given districts.
    Pass None or [] for ecosystem-wide totals.
    Returns a dict of {metric_name: value}.
    """
    scope_filter = _in_filter("state_upper_district", district_ids)
    sql_str = f"""
        SELECT
            count(external_id) AS registered_voters,
            sum(case when `custom_fields.surus_voter_segmentation` = 'Republican Turnout' then 1 else 0 end) AS unreliable_conservatives
        FROM   universal.deltatables.vcs_gold
        WHERE  1=1
        {scope_filter}
    """
    df = _cached(
        key=f"demographics:{_list_key(district_ids)}",
        fn=functools.partial(run_query, sql_str, label="demographics"),
    )
    return df.iloc[0].to_dict() if not df.empty else {}


def get_program_totals(
    district_ids: list[str] | None,
    program: str,
    start_date: str | None = None,
    end_date: str | None = None,
    client_ids: list[str] | None = None,
) -> dict:
    """
    Aggregate contacts and events across the given districts and clients.
    Pass None/[] for either to include all.  program='both' for combined totals.
    Returns a dict with keys total_contacts, total_events.
    """
    prog_filter     = f"AND program = '{program}'" if program != "both" else ""
    date_filter     = (
        f"AND activity_week BETWEEN '{start_date}' AND '{end_date}'"
        if start_date and end_date else ""
    )
    district_filter = _in_filter("district_id", district_ids)
    client_filter   = _in_filter("nation", client_ids)
    sql_str = f"""
        SELECT
            SUM(contacts) AS total_contacts,
            SUM(events)   AS total_events
        FROM   your_catalog.your_schema.outreach_activity
        WHERE  1=1
        {district_filter}
        {prog_filter}
        {date_filter}
        {client_filter}
    """
    df = _cached(
        key=f"program_totals:{_list_key(district_ids)}:{program}:{start_date}:{end_date}:{_list_key(client_ids)}",
        fn=functools.partial(run_query, sql_str, label="program_totals"),
    )
    return df.iloc[0].to_dict() if not df.empty else {}


def get_program_comparison(
    district_ids: list[str] | None,
    start_date: str | None = None,
    end_date: str | None = None,
    client_ids: list[str] | None = None,
) -> pd.DataFrame:
    """
    Contacts and events broken down by program (BP, CLP) across the given
    districts and clients.  Pass None/[] to include all.
    Returns columns [program, contacts, events].
    """
    date_filter     = (
        f"AND activity_week BETWEEN '{start_date}' AND '{end_date}'"
        if start_date and end_date else ""
    )
    district_filter = _in_filter("district_id", district_ids)
    client_filter   = _in_filter("nation", client_ids)
    sql_str = f"""
        SELECT
            program,
            SUM(contacts) AS contacts,
            SUM(events)   AS events
        FROM   your_catalog.your_schema.outreach_activity
        WHERE  program IN ('BP', 'CLP')
        {district_filter}
        {date_filter}
        {client_filter}
        GROUP  BY program
        ORDER  BY program
    """
    return _cached(
        key=f"program_comparison:{_list_key(district_ids)}:{start_date}:{end_date}:{_list_key(client_ids)}",
        fn=functools.partial(run_query, sql_str, label="program_comparison"),
    )


def get_district_trend(
    district_ids: list[str] | None,
    program: str = "both",
    start_date: str | None = None,
    end_date: str | None = None,
    client_ids: list[str] | None = None,
) -> pd.DataFrame:
    """
    Time-series outreach data across the given districts, program, date range,
    and clients.  Pass None/[] to include all.
    When program='both', returns columns [period, program, metric_value].
    When a single program is selected, returns [period, metric_value].
    """
    date_filter     = (
        f"AND activity_week BETWEEN '{start_date}' AND '{end_date}'"
        if start_date and end_date else ""
    )
    district_filter = _in_filter("district_id", district_ids)
    client_filter   = _in_filter("nation", client_ids)
    if program == "both":
        sql_str = f"""
            SELECT period, program, SUM(contacts + events) AS metric_value
            FROM   your_catalog.your_schema.outreach_activity
            WHERE  program IN ('BP', 'CLP')
            {district_filter}
            {date_filter}
            {client_filter}
            GROUP  BY period, program
            ORDER  BY period, program
        """
    else:
        sql_str = f"""
            SELECT period, SUM(contacts + events) AS metric_value
            FROM   your_catalog.your_schema.outreach_activity
            WHERE  program = '{program}'
            {district_filter}
            {date_filter}
            {client_filter}
            GROUP  BY period
            ORDER  BY period
        """
    return _cached(
        key=f"trend:{_list_key(district_ids)}:{program}:{start_date}:{end_date}:{_list_key(client_ids)}",
        fn=functools.partial(run_query, sql_str, label="district_trend"),
    )


def get_district_table(
    district_ids: list[str] | None = None,
    client_ids: list[str] | None = None,
) -> pd.DataFrame:
    """
    Detail rows across the given districts and clients.
    Pass None/[] for either to include all.
    """
    district_filter = _in_filter("district_id", district_ids)
    client_filter   = _in_filter("nation", client_ids)
    sql_str = f"""
        SELECT *
        FROM   your_catalog.your_schema.district_detail
        WHERE  1=1
        {district_filter}
        {client_filter}
        ORDER  BY sort_key
        LIMIT  500
    """
    return _cached(
        key=f"table:{_list_key(district_ids)}:{_list_key(client_ids)}",
        fn=functools.partial(run_query, sql_str, label="district_table"),
    )
