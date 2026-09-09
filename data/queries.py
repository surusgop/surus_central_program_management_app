"""
Dashboard data layer — uses Databricks SQL Connector against a SQL Warehouse.

Required env vars:
  DATABRICKS_HOST          Workspace URL  e.g. https://adb-xxx.azuredatabricks.net
  DATABRICKS_TOKEN         Personal access token
  DATABRICKS_SQL_HTTP_PATH SQL Warehouse HTTP path  e.g. /sql/1.0/warehouses/<id>

Optional:
  QUERY_CACHE_SECONDS                 How long to cache query results (default: 300)
  DATABRICKS_CONTACT_ANALYSIS_TABLE   Overrides the pre-aggregated contact analysis table
                                       (default: universal.bitables.contact_analysis_dash)
  DATABRICKS_CONTACTS_TABLE           Overrides the raw contact table
                                       (default: universal.bitables.contact_pull_trimmed)
  DATABRICKS_BOUNDARIES_TABLE         Overrides the map boundaries table
                                       (default: geo_assets.boundaries.cb_2025_500k)
  DATABRICKS_GOALS_TABLE              Overrides the goal constants table
                                       (default: universal.bitables.clp_goals_source)
  DATABRICKS_GOAL_CALENDAR_TABLE      Overrides the nation goal calendar table
                                       (default: universal.bitables.nation_goal_calendar)
  DATABRICKS_FD_SOURCE_TABLE          Overrides the FD -> org roster table
                                       (default: universal.bitables.fd_source)
  DATABRICKS_RECENT_EVENT_TABLE       Overrides the most-recent-event-per-org table
                                       (default: universal.bitables.recent_event_source)
  DATABRICKS_GOAL_CALENDAR_ORG_TABLE  Overrides the org-level goal calendar table
                                       (default: universal.bitables.nation_goal_calendar_org)
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

_TABLE               = os.environ.get("DATABRICKS_CONTACT_ANALYSIS_TABLE", "universal.bitables.contact_analysis_dash")
_RAW_TABLE           = os.environ.get("DATABRICKS_CONTACTS_TABLE", "universal.bitables.contact_pull_trimmed")
_BOUNDARIES_TABLE    = os.environ.get("DATABRICKS_BOUNDARIES_TABLE", "geo_assets.boundaries.cb_2025_500k")
_FD_SOURCE_TABLE     = os.environ.get("DATABRICKS_FD_SOURCE_TABLE", "universal.bitables.fd_source")
_RECENT_EVENT_TABLE  = os.environ.get("DATABRICKS_RECENT_EVENT_TABLE", "universal.bitables.recent_event_source")
_GOAL_CALENDAR_ORG_TABLE = os.environ.get("DATABRICKS_GOAL_CALENDAR_ORG_TABLE", "universal.bitables.nation_goal_calendar_org")

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


def _fetch_nation_list(where_clause: str = "") -> list[dict]:
    """Query distinct nations for the nation dropdown, using the raw nation
    value as both label and value."""
    df = run_query(
        f"""
        SELECT DISTINCT nation AS value, nation AS label
        FROM {_TABLE}
        WHERE 1=1 {where_clause}
        ORDER BY value
        """,
        label="nation_list",
    )
    return df.to_dict("records")


def get_nation_list() -> list[dict]:
    """Return [{label, value}] for the nation dropdown."""
    return _cached("nation_list", lambda: _fetch_nation_list())


# The source table's `group` column still stores the historical program code
# "CLP" — it is displayed to users as "CSP" everywhere (dropdowns, grids, PDF
# reports) while the underlying value stays "CLP" so filters/joins against the
# source table are unaffected.
GROUP_DISPLAY_ALIASES = {"CLP": "CSP"}


def display_group(value: str) -> str:
    """Map a raw `group` value to its user-facing display label."""
    return GROUP_DISPLAY_ALIASES.get(value, value)


def get_group_list() -> list[dict]:
    """Return [{label, value}] for the group dropdown."""
    def _fetch():
        df = run_query(
            f"SELECT DISTINCT `group` FROM {_TABLE} ORDER BY `group`",
            label="group_list",
        )
        df = df.rename(columns={"group": "value"})
        df["label"] = df["value"].map(display_group)
        return df.to_dict("records")
    return _cached("group_list", _fetch)


def get_nation_list_filtered(
    state_ids: list[str],
    group_ids: list[str],
    fd_ids: list[str] | None = None,
    org_ids: list[str] | None = None,
) -> list[dict]:
    """Return [{label, value}] for nation dropdown filtered by selected states, groups, FDs, and orgs."""
    fd_ids = fd_ids or []
    org_ids = org_ids or []
    if not state_ids and not group_ids and not fd_ids and not org_ids:
        return get_nation_list()

    state_filter = _in_filter("state",     state_ids)
    group_filter = _in_filter("`group`",   group_ids)
    fd_filter    = _in_filter("fd",        fd_ids)
    org_filter   = _in_filter("org_name",  org_ids)

    key = (
        f"nation_list_filtered|{_list_key(state_ids)}|{_list_key(group_ids)}"
        f"|{_list_key(fd_ids)}|{_list_key(org_ids)}"
    )
    return _cached(key, lambda: _fetch_nation_list(f"{state_filter} {group_filter} {fd_filter} {org_filter}"))


def _fetch_fd_list(where_clause: str = "") -> list[dict]:
    df = run_query(
        f"""
        SELECT DISTINCT fd
        FROM {_TABLE}
        WHERE fd IS NOT NULL {where_clause}
        ORDER BY fd
        """,
        label="fd_list",
    )
    df = df.rename(columns={"fd": "label"})
    df["value"] = df["label"]
    return df.to_dict("records")


def get_fd_list() -> list[dict]:
    """Return [{label, value}] for the Field Director dropdown."""
    return _cached("fd_list", lambda: _fetch_fd_list())


def get_fd_list_filtered(
    state_ids: list[str],
    nation_ids: list[str],
    group_ids: list[str],
    org_ids: list[str] | None = None,
) -> list[dict]:
    """Return [{label, value}] for FD dropdown filtered by selected states, nations, groups, and orgs."""
    org_ids = org_ids or []
    if not state_ids and not nation_ids and not group_ids and not org_ids:
        return get_fd_list()

    state_filter  = _in_filter("state",    state_ids)
    nation_filter = _in_filter("nation",   nation_ids)
    group_filter  = _in_filter("`group`",  group_ids)
    org_filter    = _in_filter("org_name", org_ids)

    key = (
        f"fd_list_filtered|{_list_key(state_ids)}|{_list_key(nation_ids)}"
        f"|{_list_key(group_ids)}|{_list_key(org_ids)}"
    )
    return _cached(key, lambda: _fetch_fd_list(f"{state_filter} {nation_filter} {group_filter} {org_filter}"))


def _fetch_org_list(where_clause: str = "") -> list[dict]:
    df = run_query(
        f"""
        SELECT DISTINCT org_name
        FROM {_TABLE}
        WHERE org_name IS NOT NULL {where_clause}
        ORDER BY org_name
        """,
        label="org_list",
    )
    df = df.rename(columns={"org_name": "label"})
    df["value"] = df["label"]
    return df.to_dict("records")


def get_org_list() -> list[dict]:
    """Return [{label, value}] for the Org dropdown."""
    return _cached("org_list", lambda: _fetch_org_list())


def get_org_list_filtered(
    state_ids: list[str],
    nation_ids: list[str],
    group_ids: list[str],
    fd_ids: list[str] | None = None,
) -> list[dict]:
    """Return [{label, value}] for Org dropdown filtered by selected states, nations, groups, and FDs."""
    fd_ids = fd_ids or []
    if not state_ids and not nation_ids and not group_ids and not fd_ids:
        return get_org_list()

    state_filter  = _in_filter("state",    state_ids)
    nation_filter = _in_filter("nation",   nation_ids)
    group_filter  = _in_filter("`group`",  group_ids)
    fd_filter     = _in_filter("fd",       fd_ids)

    key = (
        f"org_list_filtered|{_list_key(state_ids)}|{_list_key(nation_ids)}"
        f"|{_list_key(group_ids)}|{_list_key(fd_ids)}"
    )
    return _cached(key, lambda: _fetch_org_list(f"{state_filter} {nation_filter} {group_filter} {fd_filter}"))


# ── Contact summary ───────────────────────────────────────────────────────────

def get_contact_summary(
    state_ids: list[str],
    nation_ids: list[str],
    group_ids: list[str],
    fd_ids: list[str] | None = None,
    org_ids: list[str] | None = None,
) -> pd.DataFrame:
    """
    Returns rows from the pre-aggregated contact analysis table filtered by the
    provided state, nation, group, FD, and org values. Empty lists mean no filter.

    Columns: state, group, nation, fd, week_start, total_contacts, unique_contacts,
             contact_door_knock, contact_email, contact_phone, contact_text,
             contact_snail_mail, contact_face_to_face, contact_other, total_events,
             contacted_1_time, contacted_2_times, contacted_3_times, contacted_4plus_times
    """
    fd_ids        = fd_ids or []
    org_ids       = org_ids or []
    state_filter  = _in_filter("state",    state_ids)
    nation_filter = _in_filter("nation",   nation_ids)
    group_filter  = _in_filter("`group`",  group_ids)
    fd_filter     = _in_filter("fd",       fd_ids)
    org_filter    = _in_filter("org_name", org_ids)

    sql_str = f"""
        SELECT
            state,
            `group`,
            nation,
            fd,
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
            fe_contacts,
            count_reg_voters
        FROM {_TABLE}
        WHERE 1=1
        {group_filter}
        {state_filter}
        {nation_filter}
        {fd_filter}
        {org_filter}
        ORDER BY week_start
    """

    key = (
        f"contact_summary|{_list_key(state_ids)}|{_list_key(nation_ids)}"
        f"|{_list_key(group_ids)}|{_list_key(fd_ids)}|{_list_key(org_ids)}"
    )
    return _cached(key, lambda: run_query(sql_str, label="contact_summary"))


# ── FD/Org → nation resolution (fd/org_name only live on contact_analysis_dash) ─

def _resolve_nation_ids(
    nation_ids: list[str],
    fd_ids: list[str],
    org_ids: list[str] | None = None,
) -> list[str]:
    """Intersect an explicit nation selection with the nations belonging to the
    selected FD(s) and/or Org(s). Needed by queries against tables that don't
    carry fd/org_name columns (the raw contact table) — those columns only
    live on contact_analysis_dash, so FD/Org selections are translated to
    nation values there first. Returns a sentinel that matches nothing if
    fd_ids/org_ids narrow the selection down to zero nations, so the filter
    doesn't silently no-op."""
    org_ids = org_ids or []
    if not fd_ids and not org_ids:
        return nation_ids

    constrained = None  # accumulated intersection of fd- and org-implied nations

    if fd_ids:
        fd_filter = _in_filter("fd", fd_ids)
        key = f"fd_nation_resolve|{_list_key(fd_ids)}"
        fd_nations = _cached(
            key,
            lambda: run_query(
                f"SELECT DISTINCT nation FROM {_TABLE} WHERE 1=1 {fd_filter}",
                label="fd_nation_resolve",
            )["nation"].tolist(),
        )
        constrained = set(fd_nations)

    if org_ids:
        org_filter = _in_filter("org_name", org_ids)
        key = f"org_nation_resolve|{_list_key(org_ids)}"
        org_nations = _cached(
            key,
            lambda: run_query(
                f"SELECT DISTINCT nation FROM {_TABLE} WHERE 1=1 {org_filter}",
                label="org_nation_resolve",
            )["nation"].tolist(),
        )
        constrained = set(org_nations) if constrained is None else constrained & set(org_nations)

    resolved = [n for n in nation_ids if n in constrained] if nation_ids else list(constrained)
    return resolved or ["__no_match__"]


def _resolve_org_ids(
    state_ids: list[str],
    nation_ids: list[str],
    group_ids: list[str],
    org_ids: list[str],
) -> list[str]:
    """Intersect an explicit org selection with the orgs implied by the selected
    state(s)/nation(s)/group(s). Needed by fd_source, which carries no
    state/nation/group columns of its own -- those live only on
    contact_analysis_dash_org, so a state/nation/group selection is bridged
    through it to a concrete org_name list first. Mirrors _resolve_nation_ids.
    Returns a sentinel that matches nothing if the selection narrows down to
    zero orgs, so the caller's filter doesn't silently no-op."""
    if not state_ids and not nation_ids and not group_ids:
        return org_ids

    state_filter  = _in_filter("state",   state_ids)
    nation_filter = _in_filter("nation",  nation_ids)
    group_filter  = _in_filter("`group`", group_ids)
    key = f"org_resolve|{_list_key(state_ids)}|{_list_key(nation_ids)}|{_list_key(group_ids)}"
    implied = _cached(
        key,
        lambda: run_query(
            f"""
            SELECT DISTINCT org_name FROM {_TABLE}
            WHERE org_name IS NOT NULL {state_filter} {nation_filter} {group_filter}
            """,
            label="org_resolve",
        )["org_name"].tolist(),
    )
    resolved = [o for o in org_ids if o in implied] if org_ids else list(implied)
    return resolved or ["__no_match__"]


def _landed_weeks_join(
    state_ids: list[str] | None = None,
    group_ids: list[str] | None = None,
    fd_ids: list[str] | None = None,
    org_ids: list[str] | None = None,
) -> str:
    """
    JOIN fragment that restricts raw-table rows to only the (nation, week)
    cells where contact_analysis_dash actually has a non-null total_contacts
    value for that week, UNDER THE SAME state/group/fd/org selection the
    caller applied -- i.e. cells the weekly batch extract has actually
    populated for the specific entity being viewed, not just the nation as a
    whole. The landed CTE's join columns are renamed (landed_nation /
    landed_week_start) so they don't collide with the raw table's own
    `nation` column and every existing bare-column filter (_in_filter, the
    date filters) keeps referring to the raw table unambiguously.

    Nation alone isn't specific enough to gate on: a nation can have several
    orgs/FDs (see _resolve_nation_ids), and since the raw table carries no
    org/fd column at all, checking landedness only at the nation level lets
    one org's landed week "unlock" gating for a sibling org's un-landed week
    -- so selecting an org with zero aggregate data all year could still show
    a large Unique Contacts figure borrowed from a different org active in
    the same nation. Filtering the landed CTE by the same state/group/fd/org
    selection keeps it scoped to what Total Contacts is actually filtered to.

    Used by get_raw_contact_counts/get_contact_frequency when
    gate_to_landed_weeks=True, so a raw-sourced figure displayed alongside an
    aggregate-sourced one (e.g. Unique vs Total Contacts) is computed from the
    identical underlying slice of data instead of silently covering more real
    activity than the aggregate table currently reflects for that selection.
    """
    state_filter = _in_filter("state",    state_ids)
    group_filter = _in_filter("`group`",  group_ids)
    fd_filter    = _in_filter("fd",       fd_ids)
    org_filter   = _in_filter("org_name", org_ids)
    return f"""
        JOIN (
            SELECT DISTINCT nation AS landed_nation, CAST(week_start AS DATE) AS landed_week_start
            FROM {_TABLE}
            WHERE total_contacts IS NOT NULL
              {state_filter}
              {group_filter}
              {fd_filter}
              {org_filter}
        ) landed
          ON landed.landed_nation = nation
         AND CAST(LEFT(created_at, 10) AS DATE) >= landed.landed_week_start
         AND CAST(LEFT(created_at, 10) AS DATE) <= DATE_ADD(landed.landed_week_start, 6)
    """


def get_raw_contact_counts(
    state_ids: list[str],
    nation_ids: list[str],
    group_ids: list[str],
    start_date: str | None,
    end_date: str | None,
    fd_ids: list[str] | None = None,
    org_ids: list[str] | None = None,
    gate_to_landed_weeks: bool = False,
) -> pd.DataFrame:
    """
    Returns true unique and total contact counts from the raw contact table,
    properly de-duplicated across the full date range.  UC figures are computed
    via conditional aggregation so both sets come from a single query pass.

    gate_to_landed_weeks: when True, only counts contacts from (nation, week)
    cells that contact_analysis_dash has actually populated (see
    _landed_weeks_join) -- pass this where the result is shown alongside an
    aggregate-sourced Total Contacts figure so the two describe the same
    scope. Leave False (default) where there's no aggregate counterpart being
    compared.

    org_ids filters directly against the raw table's own org_name column --
    no resolving an org selection to its nation(s) and losing org-level
    precision the way fd_ids still has to (the raw table carries no fd column).

    Columns: state, group, nation,
             unique_contacts, total_contacts,
             uc_unique_contacts, uc_total_contacts
    """
    fd_ids            = fd_ids or []
    org_ids           = org_ids or []
    nation_ids        = _resolve_nation_ids(nation_ids, fd_ids)
    state_filter      = _in_filter("state",    state_ids)
    nation_filter     = _in_filter("nation",   nation_ids)
    group_filter      = _in_filter("`group`",  group_ids)
    org_filter        = _in_filter("org_name", org_ids)
    date_start_filter = f"AND LEFT(created_at, 10) >= '{start_date[:10]}'" if start_date else ""
    date_end_filter   = f"AND LEFT(created_at, 10) <= '{end_date[:10]}'"   if end_date   else ""
    landed_join       = (
        _landed_weeks_join(state_ids, group_ids, fd_ids, org_ids) if gate_to_landed_weeks else ""
    )

    sql_str = f"""
        SELECT
            state,
            `group`,
            nation,
            COUNT(DISTINCT uuid_contactee) AS unique_contacts,
            COUNT(*)                        AS total_contacts,
            COUNT(DISTINCT CASE WHEN `custom_fields.surus_voter_segmentation` IN ('Unreliable Conservative', 'Republican Turnout')
                                THEN uuid_contactee END) AS uc_unique_contacts,
            COUNT(CASE WHEN `custom_fields.surus_voter_segmentation` IN ('Unreliable Conservative', 'Republican Turnout')
                       THEN 1 END)                       AS uc_total_contacts
        FROM {_RAW_TABLE}
        {landed_join}
        WHERE 1=1
          {state_filter}
          {nation_filter}
          {group_filter}
          {org_filter}
          {date_start_filter}
          {date_end_filter}
        GROUP BY state, `group`, nation
    """

    key = (
        f"raw_contact_counts|{_list_key(state_ids)}|{_list_key(nation_ids)}"
        f"|{_list_key(group_ids)}|{start_date or ''}|{end_date or ''}|{_list_key(fd_ids)}|{_list_key(org_ids)}"
        f"|gated={gate_to_landed_weeks}"
    )
    return _cached(key, lambda: run_query(sql_str, label="raw_contact_counts"))


def get_contact_frequency(
    state_ids: list[str],
    nation_ids: list[str],
    group_ids: list[str],
    start_date: str | None,
    end_date: str | None,
    fd_ids: list[str] | None = None,
    org_ids: list[str] | None = None,
    gate_to_landed_weeks: bool = False,
) -> pd.DataFrame:
    """
    Returns the number of distinct voters contacted exactly 1, 2, 3, or 4+ times
    within the given date range, de-duplicated from the raw contact table (each
    voter is bucketed once, by their total contact count over the period — not
    summed across weekly snapshot rows).

    gate_to_landed_weeks / org_ids: see get_raw_contact_counts.

    Columns: state, group, nation,
             contacted_1_time, contacted_2_times, contacted_3_times, contacted_4plus_times
    """
    fd_ids            = fd_ids or []
    org_ids           = org_ids or []
    nation_ids        = _resolve_nation_ids(nation_ids, fd_ids)
    state_filter      = _in_filter("state",    state_ids)
    nation_filter     = _in_filter("nation",   nation_ids)
    group_filter      = _in_filter("`group`",  group_ids)
    org_filter        = _in_filter("org_name", org_ids)
    date_start_filter = f"AND LEFT(created_at, 10) >= '{start_date[:10]}'" if start_date else ""
    date_end_filter   = f"AND LEFT(created_at, 10) <= '{end_date[:10]}'"   if end_date   else ""
    landed_join       = (
        _landed_weeks_join(state_ids, group_ids, fd_ids, org_ids) if gate_to_landed_weeks else ""
    )

    sql_str = f"""
        WITH voter_counts AS (
            SELECT
                state,
                `group`,
                nation,
                uuid_contactee,
                COUNT(*) AS n_contacts
            FROM {_RAW_TABLE}
            {landed_join}
            WHERE 1=1
              {state_filter}
              {nation_filter}
              {group_filter}
              {org_filter}
              {date_start_filter}
              {date_end_filter}
            GROUP BY state, `group`, nation, uuid_contactee
        )
        SELECT
            state,
            `group`,
            nation,
            COUNT(CASE WHEN n_contacts = 1  THEN 1 END) AS contacted_1_time,
            COUNT(CASE WHEN n_contacts = 2  THEN 1 END) AS contacted_2_times,
            COUNT(CASE WHEN n_contacts = 3  THEN 1 END) AS contacted_3_times,
            COUNT(CASE WHEN n_contacts >= 4 THEN 1 END) AS contacted_4plus_times
        FROM voter_counts
        GROUP BY state, `group`, nation
    """

    key = (
        f"contact_frequency|{_list_key(state_ids)}|{_list_key(nation_ids)}"
        f"|{_list_key(group_ids)}|{start_date or ''}|{end_date or ''}|{_list_key(fd_ids)}|{_list_key(org_ids)}"
        f"|gated={gate_to_landed_weeks}"
    )
    return _cached(key, lambda: run_query(sql_str, label="contact_frequency"))


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


# ── Program goals ─────────────────────────────────────────────────────────────

_GOALS_TABLE = os.environ.get("DATABRICKS_GOALS_TABLE", "universal.bitables.clp_goals_source")


def get_goal_constants() -> dict[str, int]:
    """Return {KPI: Value} using the latest date_recorded row per KPI."""
    def _fetch():
        df = run_query(
            f"""
                SELECT KPI, Value FROM (
                    SELECT KPI, Value,
                           ROW_NUMBER() OVER (PARTITION BY KPI ORDER BY date_recorded DESC) AS rn
                    FROM {_GOALS_TABLE}
                ) WHERE rn = 1
            """,
            label="goal_constants",
        )
        return dict(zip(df["KPI"], df["Value"]))
    return _cached("goal_constants", _fetch, ttl=3600)


_GOAL_CALENDAR_TABLE = os.environ.get("DATABRICKS_GOAL_CALENDAR_TABLE", "universal.bitables.nation_goal_calendar")


def get_goal_calendar_targets(
    state_ids: list[str],
    nation_ids: list[str],
    group_ids: list[str],
    start_date: str | None,
    end_date: str | None,
    fd_ids: list[str] | None = None,
    org_ids: list[str] | None = None,
) -> pd.DataFrame:
    """
    Returns per-nation goal targets for the selected date range.

    texts/calls/events/f2f are summed from the per-week delta columns — summing
    deltas (rather than diffing the cumulative columns) gives the correct target
    for any range, including ones that cross a January reset boundary.

    connectors_target is a lifetime cumulative figure (never resets), so instead
    of summing its delta over the range, this reports its value as of the last
    week in the selected range (MAX_BY on week_start) — i.e. "how many connectors
    should exist by now," not "how many were added during this window."

    state/group aren't stored on nation_goal_calendar itself (its grain is just
    nation + week_start), so they're pulled in via the same nation -> state/group
    mapping already used by contact_analysis_dash. fd is pulled in the same way
    and filtered directly (nation_dim comes straight from contact_analysis_dash,
    the only table that has an fd column).

    org_ids is NOT joined into nation_dim the way fd is — a nation can have many
    orgs, and nation_dim is DISTINCT'd per (state, group, nation, fd), so adding
    org_name there would multiply nation_dim's rows per nation and silently
    inflate every SUM()-based target below. Instead, org_ids is resolved to the
    nation(s) it implies (via _resolve_nation_ids, same bridge the raw-table
    queries use) and applied as a plain nation filter.

    Columns: state, group, nation,
             connectors_target, texts_target, calls_target, events_target, f2f_target
    """
    fd_ids            = fd_ids or []
    org_ids           = org_ids or []
    nation_ids        = _resolve_nation_ids(nation_ids, [], org_ids)
    state_filter      = _in_filter("nd.state",   state_ids)
    nation_filter     = _in_filter("g.nation",   nation_ids)
    group_filter      = _in_filter("nd.`group`", group_ids)
    fd_filter         = _in_filter("nd.fd",      fd_ids)
    date_start_filter = f"AND CAST(g.week_start AS DATE) >= '{start_date[:10]}'" if start_date else ""
    date_end_filter   = f"AND CAST(g.week_start AS DATE) <= '{end_date[:10]}'"   if end_date   else ""

    sql_str = f"""
        WITH nation_dim AS (
            SELECT DISTINCT state, `group`, nation, fd
            FROM {_TABLE}
        )
        SELECT
            nd.state,
            nd.`group`,
            g.nation,
            MAX_BY(g.connectors_target, g.week_start) AS connectors_target,
            SUM(g.texts_delta)      AS texts_target,
            SUM(g.calls_delta)      AS calls_target,
            SUM(g.events_delta)     AS events_target,
            SUM(g.f2f_delta)        AS f2f_target
        FROM {_GOAL_CALENDAR_TABLE} g
        JOIN nation_dim nd ON nd.nation = g.nation
        WHERE 1=1
          {state_filter}
          {nation_filter}
          {group_filter}
          {fd_filter}
          {date_start_filter}
          {date_end_filter}
        GROUP BY nd.state, nd.`group`, g.nation
    """

    key = (
        f"goal_calendar_targets|{_list_key(state_ids)}|{_list_key(nation_ids)}"
        f"|{_list_key(group_ids)}|{start_date or ''}|{end_date or ''}|{_list_key(fd_ids)}|{_list_key(org_ids)}"
    )
    return _cached(key, lambda: run_query(sql_str, label="goal_calendar_targets"))


# ── FD / Org roster (Field Director -> Organization rollup) ──────────────────

def get_fd_org_roster(
    state_ids: list[str] | None = None,
    nation_ids: list[str] | None = None,
    group_ids: list[str] | None = None,
    fd_ids: list[str] | None = None,
    org_ids: list[str] | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
) -> pd.DataFrame:
    """
    Returns one row per (FD, Org) on the FD roster (fd_source, latest snapshot),
    with contact metrics summed from contact_analysis_dash_org over the given
    date range, matching goal targets pulled from nation_goal_calendar_org as
    of the last week in that date range, and the org's most-recently-captured
    event pulled in from recent_event_source. Drives the FD -> Org rollup view
    that replaced the removed Contact Goal Progress / Summary by
    State-Group-Nation visualizations.

    fd_source carries no state/nation/group columns, so those filters are
    bridged to a concrete org list via _resolve_org_ids before being applied
    to the roster; they're also applied directly to the metrics query since
    contact_analysis_dash_org does have those columns. nation_goal_calendar_org
    isn't filtered by state/nation/group/fd/org directly -- it's joined to the
    roster by org_name, which already carries that scoping.

    Unlike get_goal_calendar_targets (nation-level), texts/calls/events/f2f
    targets here are NOT summed from the per-week delta columns -- spot-checking
    against the org-level goal sheet showed those deltas don't reliably
    reconcile with the actual *_target trajectory (a target can jump between
    two weeks by more than that week's recorded delta), so summing them
    under-counts. Instead, each target is read directly via MAX_BY(*_target,
    week_start) -- its value as of the last week in the selected range, the
    same point-in-time treatment get_goal_calendar_targets already uses for
    connectors_target. Same caveat applies: a range spanning a January reset
    boundary will reflect only the post-reset target, not the full prior year.

    An org can appear with 0 metrics/targets / a blank Most Recent Event if
    it's on the FD roster but hasn't landed in contact_analysis_dash_org,
    nation_goal_calendar_org, or recent_event_source yet (e.g. a newly added
    org).

    Columns: fd, org_name, org_label, join_date,
             p2p_texts, phone_calls, face_to_face, total_events,
             p2p_texts_target, phone_calls_target, face_to_face_target, total_events_target,
             most_recent_event_name, event_modified_at, event_stage
    """
    state_ids  = state_ids  or []
    nation_ids = nation_ids or []
    group_ids  = group_ids  or []
    fd_ids     = fd_ids     or []
    org_ids    = org_ids    or []

    roster_org_ids = _resolve_org_ids(state_ids, nation_ids, group_ids, org_ids)

    fd_filter         = _in_filter("fd",       fd_ids)
    roster_org_filter = _in_filter("org_name", roster_org_ids)

    metrics_state_filter  = _in_filter("state",    state_ids)
    metrics_nation_filter = _in_filter("nation",   nation_ids)
    metrics_group_filter  = _in_filter("`group`",  group_ids)
    metrics_fd_filter     = _in_filter("fd",       fd_ids)
    metrics_org_filter    = _in_filter("org_name", org_ids)
    date_start_filter     = f"AND CAST(week_start AS DATE) >= '{start_date[:10]}'" if start_date else ""
    date_end_filter       = f"AND CAST(week_start AS DATE) <= '{end_date[:10]}'"   if end_date   else ""

    sql_str = f"""
        WITH roster AS (
            SELECT fd, org_name, clp_orgs AS org_label, join_date
            FROM {_FD_SOURCE_TABLE}
            WHERE date_recorded = (SELECT MAX(date_recorded) FROM {_FD_SOURCE_TABLE})
            {fd_filter}
            {roster_org_filter}
        ),
        metrics AS (
            SELECT
                org_name,
                SUM(contact_text)         AS p2p_texts,
                SUM(contact_phone)        AS phone_calls,
                SUM(contact_face_to_face) AS face_to_face,
                SUM(total_events)         AS total_events
            FROM {_TABLE}
            WHERE org_name IS NOT NULL
              {metrics_state_filter}
              {metrics_nation_filter}
              {metrics_group_filter}
              {metrics_fd_filter}
              {metrics_org_filter}
              {date_start_filter}
              {date_end_filter}
            GROUP BY org_name
        ),
        goals AS (
            SELECT
                org_name,
                MAX_BY(texts_target,  week_start) AS p2p_texts_target,
                MAX_BY(calls_target,  week_start) AS phone_calls_target,
                MAX_BY(f2f_target,    week_start) AS face_to_face_target,
                MAX_BY(events_target, week_start) AS total_events_target
            FROM {_GOAL_CALENDAR_ORG_TABLE}
            WHERE org_name IS NOT NULL
              {date_start_filter}
              {date_end_filter}
            GROUP BY org_name
        ),
        recent_event AS (
            SELECT org_tag, event_name, updated_at, TRIM(step) AS step
            FROM {_RECENT_EVENT_TABLE}
            WHERE rn = 1 AND org_tag IS NOT NULL
        )
        SELECT
            r.fd,
            r.org_name,
            r.org_label,
            r.join_date,
            COALESCE(m.p2p_texts, 0)    AS p2p_texts,
            COALESCE(m.phone_calls, 0)  AS phone_calls,
            COALESCE(m.face_to_face, 0) AS face_to_face,
            COALESCE(m.total_events, 0) AS total_events,
            COALESCE(g.p2p_texts_target, 0)    AS p2p_texts_target,
            COALESCE(g.phone_calls_target, 0)  AS phone_calls_target,
            COALESCE(g.face_to_face_target, 0) AS face_to_face_target,
            COALESCE(g.total_events_target, 0) AS total_events_target,
            e.event_name AS most_recent_event_name,
            e.updated_at AS event_modified_at,
            e.step       AS event_stage
        FROM roster r
        LEFT JOIN metrics m      ON m.org_name = r.org_name
        LEFT JOIN goals g        ON g.org_name = r.org_name
        LEFT JOIN recent_event e ON e.org_tag  = r.org_name
        ORDER BY r.fd, r.org_label
    """

    key = (
        f"fd_org_roster|{_list_key(state_ids)}|{_list_key(nation_ids)}|{_list_key(group_ids)}"
        f"|{_list_key(fd_ids)}|{_list_key(org_ids)}|{start_date or ''}|{end_date or ''}"
    )
    return _cached(key, lambda: run_query(sql_str, label="fd_org_roster"))


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
