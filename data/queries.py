"""
Dashboard data layer — uses Databricks SQL Connector against a SQL Warehouse.

Required env vars:
  DATABRICKS_HOST          Workspace URL  e.g. https://adb-xxx.azuredatabricks.net
  DATABRICKS_TOKEN         Personal access token
  DATABRICKS_SQL_HTTP_PATH SQL Warehouse HTTP path  e.g. /sql/1.0/warehouses/<id>

Optional:
  QUERY_CACHE_SECONDS      How long to cache query results (default: 300)
"""

from __future__ import annotations

import os
import sys
import time
import threading
import traceback
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
    print(f"{tag} executing query", file=sys.stderr, flush=True)
    t0 = time.monotonic()
    try:
        with _connect() as conn:
            with conn.cursor() as cur:
                cur.execute(sql_str)
                df = cur.fetchall_arrow().to_pandas()
        elapsed = time.monotonic() - t0
        print(f"{tag} OK — {len(df)} rows in {elapsed:.2f}s", file=sys.stderr, flush=True)
        return df
    except Exception:
        elapsed = time.monotonic() - t0
        print(f"{tag} FAILED after {elapsed:.2f}s:\n{traceback.format_exc()}", file=sys.stderr, flush=True)
        raise


# ── Simple TTL cache ──────────────────────────────────────────────────────────

_cache: dict[str, tuple[float, Any]] = {}
_cache_lock = threading.Lock()


def _cached(key: str, fn, ttl: int = _CACHE_TTL):
    with _cache_lock:
        entry = _cache.get(key)
        if entry and (time.monotonic() - entry[0]) < ttl:
            age = time.monotonic() - entry[0]
            print(f"[cache HIT] {key!r} (age {age:.0f}s)", file=sys.stderr, flush=True)
            return entry[1]
    print(f"[cache MISS] {key!r}", file=sys.stderr, flush=True)
    result = fn()
    with _cache_lock:
        _cache[key] = (time.monotonic(), result)
    return result


def bust_cache():
    with _cache_lock:
        _cache.clear()


def _list_key(values: list[str] | None) -> str:
    return "|".join(sorted(str(v) for v in values)) if values else ""


def _in_filter(column: str, values: list[str] | None) -> str:
    if not values:
        return ""
    escaped = ", ".join(f"'{v}'" for v in values)
    return f"AND {column} IN ({escaped})"


# ── Filter / slicer data ──────────────────────────────────────────────────────

_TABLE            = "universal.bitables.contact_analysis_dash"
_RAW_TABLE        = os.environ.get("DATABRICKS_CONTACTS_TABLE", "universal.bitables.contact_pull_trimmed")
_FD_TABLE         = "universal.bitables.FD_source"
_BOUNDARIES_TABLE = "geo_assets.boundaries.cb_2025_500k"

# 2-letter abbreviation → full name used in the boundary table's state_name column
_STATE_ABBR_TO_NAME = {
    "AL": "Alabama", "AK": "Alaska", "AZ": "Arizona", "AR": "Arkansas",
    "CA": "California", "CO": "Colorado", "CT": "Connecticut", "DE": "Delaware",
    "FL": "Florida", "GA": "Georgia", "HI": "Hawaii", "ID": "Idaho",
    "IL": "Illinois", "IN": "Indiana", "IA": "Iowa", "KS": "Kansas",
    "KY": "Kentucky", "LA": "Louisiana", "ME": "Maine", "MD": "Maryland",
    "MA": "Massachusetts", "MI": "Michigan", "MN": "Minnesota", "MS": "Mississippi",
    "MO": "Missouri", "MT": "Montana", "NE": "Nebraska", "NV": "Nevada",
    "NH": "New Hampshire", "NJ": "New Jersey", "NM": "New Mexico", "NY": "New York",
    "NC": "North Carolina", "ND": "North Dakota", "OH": "Ohio", "OK": "Oklahoma",
    "OR": "Oregon", "PA": "Pennsylvania", "RI": "Rhode Island", "SC": "South Carolina",
    "SD": "South Dakota", "TN": "Tennessee", "TX": "Texas", "UT": "Utah",
    "VT": "Vermont", "VA": "Virginia", "WA": "Washington", "WV": "West Virginia",
    "WI": "Wisconsin", "WY": "Wyoming",
}


def get_state_list() -> list[dict]:
    """Return [{label, value}] for the state dropdown."""
    def _fetch():
        df = run_query(
            f"SELECT DISTINCT state FROM {_TABLE} ORDER BY state",
            label="state_list",
        )
        df = df.rename(columns={"state": "label"})
        df["value"] = df["label"]
        return df.to_dict("records")
    return _cached("state_list", _fetch)


def get_nation_list() -> list[dict]:
    """Return [{label, value}] for the nation dropdown."""
    def _fetch():
        df = run_query(
            f"SELECT DISTINCT nation FROM {_TABLE} ORDER BY nation",
            label="nation_list",
        )
        df = df.rename(columns={"nation": "label"})
        df["value"] = df["label"]
        return df.to_dict("records")
    return _cached("nation_list", _fetch)


def get_group_list() -> list[dict]:
    """Return [{label, value}] for the group dropdown."""
    def _fetch():
        df = run_query(
            f"SELECT DISTINCT `group` FROM {_TABLE} ORDER BY `group`",
            label="group_list",
        )
        df = df.rename(columns={"group": "label"})
        df["value"] = df["label"]
        return df.to_dict("records")
    return _cached("group_list", _fetch)


def get_nation_list_filtered(
    state_ids: list[str],
    group_ids: list[str],
) -> list[dict]:
    """Return [{label, value}] for nation dropdown filtered by selected states and groups."""
    if not state_ids and not group_ids:
        return get_nation_list()

    state_filter = _in_filter("state",   state_ids)
    group_filter = _in_filter("`group`", group_ids)

    def _fetch():
        df = run_query(
            f"SELECT DISTINCT nation FROM {_TABLE} WHERE 1=1 {state_filter} {group_filter} ORDER BY nation",
            label="nation_list_filtered",
        )
        df = df.rename(columns={"nation": "label"})
        df["value"] = df["label"]
        return df.to_dict("records")

    key = f"nation_list_filtered|{_list_key(state_ids)}|{_list_key(group_ids)}"
    return _cached(key, _fetch)


def get_fd_list() -> list[dict]:
    """Return [{label, value}] for the Field Director dropdown."""
    def _fetch():
        df = run_query(
            f"SELECT DISTINCT fd FROM {_FD_TABLE} WHERE fd IS NOT NULL AND fd != '' ORDER BY fd",
            label="fd_list",
        )
        df = df.rename(columns={"fd": "label"})
        df["value"] = df["label"]
        return df.to_dict("records")
    return _cached("fd_list", _fetch)


def get_fd_source() -> pd.DataFrame:
    """Return the latest Field Director assignment per nation (slug).

    Columns: slug, fd
    """
    def _fetch():
        return run_query(
            f"""
            SELECT slug, fd FROM (
                SELECT slug, fd,
                       ROW_NUMBER() OVER (PARTITION BY slug ORDER BY date_recorded DESC NULLS LAST) AS rn
                FROM {_FD_TABLE}
                WHERE slug IS NOT NULL AND slug != ''
                  AND fd   IS NOT NULL AND fd   != ''
            ) WHERE rn = 1
            """,
            label="fd_source",
        )
    return _cached("fd_source", _fetch)


# ── Contact summary ───────────────────────────────────────────────────────────

def get_contact_summary(
    state_ids: list[str],
    nation_ids: list[str],
    group_ids: list[str],
) -> pd.DataFrame:
    """
    Returns rows from the pre-aggregated contact analysis table filtered by the
    provided state, nation, and group values. Empty lists mean no filter.

    Columns: state, group, nation, week_start, total_contacts, unique_contacts,
             contact_door_knock, contact_email, contact_phone, contact_text,
             contact_snail_mail, contact_face_to_face, contact_other, total_events,
             contacted_1_time, contacted_2_times, contacted_3_times, contacted_4plus_times
    """
    state_filter  = _in_filter("state",   state_ids)
    nation_filter = _in_filter("nation",  nation_ids)
    group_filter  = _in_filter("`group`", group_ids)

    sql_str = f"""
        SELECT
            state,
            `group`,
            nation,
            week_start,
            total_contacts,
            unique_contacts,
            contact_door_knock,
            contact_email,
            contact_phone,
            contact_text,
            contact_snail_mail,
            contact_face_to_face,
            contact_other,
            total_events,
            contacted_1_time,
            contacted_2_times,
            contacted_3_times,
            contacted_4plus_times,
            count_unreliable_conservatives,
            uc_total_contacts,
            uc_unique_contacts,
            fe_contacts
        FROM {_TABLE}
        WHERE 1=1
        {group_filter}
        {state_filter}
        {nation_filter}
        ORDER BY week_start
    """

    key = f"contact_summary|{_list_key(state_ids)}|{_list_key(nation_ids)}|{_list_key(group_ids)}"
    return _cached(key, lambda: run_query(sql_str, label="contact_summary"))


def get_raw_contact_counts(
    state_ids: list[str],
    nation_ids: list[str],
    group_ids: list[str],
    start_date: str | None,
    end_date: str | None,
) -> pd.DataFrame:
    """
    Returns true unique and total contact counts from the raw contact table,
    properly de-duplicated across the full date range.  UC figures are computed
    via conditional aggregation so both sets come from a single query pass.

    Columns: state, group, nation,
             unique_contacts, total_contacts,
             uc_unique_contacts, uc_total_contacts
    """
    state_filter      = _in_filter("state",   state_ids)
    nation_filter     = _in_filter("nation",  nation_ids)
    group_filter      = _in_filter("`group`", group_ids)
    date_start_filter = f"AND LEFT(created_at, 10) >= '{start_date[:10]}'" if start_date else ""
    date_end_filter   = f"AND LEFT(created_at, 10) <= '{end_date[:10]}'"   if end_date   else ""

    sql_str = f"""
        SELECT
            state,
            `group`,
            nation,
            COUNT(DISTINCT uuid_contactee) AS unique_contacts,
            COUNT(*)                        AS total_contacts,
            COUNT(DISTINCT CASE WHEN `custom_fields.surus_voter_segmentation` = 'Unreliable Conservative'
                                THEN uuid_contactee END) AS uc_unique_contacts,
            COUNT(CASE WHEN `custom_fields.surus_voter_segmentation` = 'Unreliable Conservative'
                       THEN 1 END)                       AS uc_total_contacts
        FROM {_RAW_TABLE}
        WHERE 1=1
          {state_filter}
          {nation_filter}
          {group_filter}
          {date_start_filter}
          {date_end_filter}
        GROUP BY state, `group`, nation
    """

    key = (
        f"raw_contact_counts|{_list_key(state_ids)}|{_list_key(nation_ids)}"
        f"|{_list_key(group_ids)}|{start_date or ''}|{end_date or ''}"
    )
    return _cached(key, lambda: run_query(sql_str, label="raw_contact_counts"))


# ── Voter map data ─────────────────────────────────────────────────────────────

def get_voter_map_data(
    state_ids: list[str],
    nation_ids: list[str],
    group_ids: list[str],
    start_date: str | None,
    end_date: str | None,
) -> pd.DataFrame:
    """
    Returns one row per voter with coordinates and total contact count in the
    given date window. Empty lists / None values mean no filter applied.

    Columns: uuid_contactee, lat, lng, contact_count
    """
    state_filter  = _in_filter("state",   state_ids)
    nation_filter = _in_filter("nation",  nation_ids)
    group_filter  = _in_filter("`group`", group_ids)
    # created_at is a string (ISO 8601); compare using the first 10 chars (YYYY-MM-DD)
    date_start_filter = f"AND LEFT(created_at, 10) >= '{start_date}'" if start_date else ""
    date_end_filter   = f"AND LEFT(created_at, 10) <= '{end_date}'"   if end_date   else ""

    sql_str = f"""
        SELECT
            uuid_contactee,
            state,
            CAST(`registered_address.lat` AS DOUBLE) AS lat,
            CAST(`registered_address.lng` AS DOUBLE) AS lng,
            COUNT(*)                                  AS contact_count
        FROM {_RAW_TABLE}
        WHERE 1=1
          AND `registered_address.lat` IS NOT NULL AND `registered_address.lat` != ''
          AND `registered_address.lng` IS NOT NULL AND `registered_address.lng` != ''
          {state_filter}
          {nation_filter}
          {group_filter}
          {date_start_filter}
          {date_end_filter}
        GROUP BY
            uuid_contactee,
            state,
            `registered_address.lat`,
            `registered_address.lng`
    """

    key = (
        f"voter_map|{_list_key(state_ids)}|{_list_key(nation_ids)}"
        f"|{_list_key(group_ids)}|{start_date or ''}|{end_date or ''}"
    )
    return _cached(key, lambda: run_query(sql_str, label="voter_map"))


# ── Boundaries ────────────────────────────────────────────────────────────────

def get_boundaries(layer: str, state_ids: list[str]) -> pd.DataFrame:
    """
    Returns boundary rows for the given layer and states (2-letter abbreviations).
    If state_ids is empty, returns all features for that layer.

    Columns: geoid, name, state_name, geometry_geojson
    """
    state_names = [_STATE_ABBR_TO_NAME[s] for s in (state_ids or []) if s in _STATE_ABBR_TO_NAME]
    name_filter = _in_filter("state_name", state_names)

    sql_str = f"""
        SELECT
            geoid,
            name,
            state_name,
            geometry_geojson
        FROM {_BOUNDARIES_TABLE}
        WHERE layer = '{layer}'
        {name_filter}
    """

    key = f"boundaries|{layer}|{_list_key(state_names)}"
    return _cached(key, lambda: run_query(sql_str, label=f"boundaries_{layer}"), ttl=3600)
