"""
Contacts — KPI summary cards and contact-type breakdown pie chart.
Filters: State, Nation, Group, FD, Org (multi-select) + Date Range.
"""

from __future__ import annotations

import sys
import traceback
from datetime import date

import calendar
from datetime import timedelta

import dash
import dash_ag_grid as dag
import dash_bootstrap_components as dbc
import pandas as pd
import plotly.graph_objects as go
from dash import Input, Output, State, callback, ctx, dcc, html

from data.queries import (
    display_group,
    get_contact_frequency,
    get_contact_summary,
    get_fd_list_filtered,
    get_fd_org_roster,
    get_goal_calendar_targets,
    get_goal_constants,
    get_group_list,
    get_nation_list_filtered,
    get_org_list_filtered,
    get_raw_contact_counts,
    get_state_list,
)
from reports.pdf_report import build_report
from utils.dates import clamp_range_end, last_complete_week_end, resolve_complete_week_range

dash.register_page(
    __name__,
    path="/analytics",
    name="Overview",
    title="Overview | Central Program Management",
)

# ── Contact type fields ───────────────────────────────────────────────────────

CONTACT_TYPES = [
    ("Door Knock",   "contact_door_knock"),
    ("Email",        "contact_email"),
    ("Phone",        "contact_phone"),
    ("Text",         "contact_text"),
    ("Snail Mail",   "contact_snail_mail"),
    ("Face to Face", "contact_face_to_face"),
    ("Other",        "contact_other"),
]

CONTACT_FREQUENCY = [
    ("1 Time",    "contacted_1_time"),
    ("2 Times",   "contacted_2_times"),
    ("3 Times",   "contacted_3_times"),
    ("4+ Times",  "contacted_4plus_times"),
]

CHART_COLORS = ["#C1272D", "#2A313C", "#75859E", "#E8A020", "#5B8FA8", "#8B4A6E", "#6B7A8D"]


class _DataPending(Exception):
    """Raised when no complete Mon-Sun week overlaps the selected date range."""


def _prior_period(start_date: str | None, end_date: str | None):
    """Return (prior_start, prior_end, label) for the immediately preceding period."""
    if not start_date or not end_date:
        return None, None, ""
    s = date.fromisoformat(start_date[:10])
    e = date.fromisoformat(end_date[:10])
    duration = (e - s).days + 1
    # Full calendar month → previous calendar month
    if s.day == 1 and e == date(s.year, s.month, calendar.monthrange(s.year, s.month)[1]):
        prior_end = s - timedelta(days=1)
        prior_start = date(prior_end.year, prior_end.month, 1)
        return str(prior_start), str(prior_end), f"vs {prior_end.strftime('%b %Y')}"
    # Full calendar year → previous calendar year
    if s == date(s.year, 1, 1) and e == date(s.year, 12, 31):
        return str(date(s.year - 1, 1, 1)), str(date(s.year - 1, 12, 31)), f"vs {s.year - 1}"
    # Generic — shift back by the same number of days
    prior_end = s - timedelta(days=1)
    prior_start = prior_end - timedelta(days=duration - 1)
    return str(prior_start), str(prior_end), "vs prior period"


def _delta_span(current: int, prior: int, label: str):
    """Return an html.Span with ▲/▼ delta notation, or an empty string when there is no label."""
    if not label:
        return ""
    d = current - prior
    if d == 0:
        return html.Span(f"- 0 (0.0%) {label}", className="text-muted")
    sign = "+" if d > 0 else ""
    arrow = "▲" if d > 0 else "▼"
    cls = "text-success" if d > 0 else "text-danger"
    if prior == 0:
        pct_str = "new"
    else:
        pct_str = f"{sign}{(d / prior) * 100:.1f}%"
    return html.Span(f"{arrow} {sign}{d:,} ({pct_str}) {label}", className=cls)


def _goal_span(actual: int, target: int):
    """Return an html.Span showing progress toward an annual goal, or "" if no target."""
    if not target:
        return ""
    pct = actual / target * 100
    if actual >= target:
        return html.Span(f"✓ Goal met — {actual:,} / {target:,} ({pct:.0f}%)", className="text-success")
    return html.Span(f"{actual:,} / {target:,} to goal ({pct:.0f}%)", className="text-muted")


def _progress_row(label: str, actual: int, target: int):
    """Return a labeled dbc.Progress bar with an actual/target status line beneath it."""
    pct = (actual / target * 100) if target else 0
    met = bool(target) and actual >= target
    return html.Div(
        [
            html.P(label, className="small fw-semibold mb-1"),
            dbc.Progress(
                value=min(pct, 100),
                color="success" if met else "#C1272D",
                style={"height": "10px"},
                className="mb-1",
            ),
            _goal_span(actual, target) if target else html.Span("No goal set", className="text-muted"),
        ],
        className="mb-3",
    )


def _latest_snapshot_sum(df, cols: list[str]) -> dict[str, int]:
    """Sum point-in-time snapshot columns using each (state, group, nation, org)'s
    own latest week, not a single global-latest week — a global cutoff drops any
    group whose latest row falls on an earlier date and silently zeroes it out.
    Org must be part of the grouping key: a nation can contain several orgs, each
    with its own count_reg_voters/count_unreliable_conservatives snapshot, so
    grouping without org_name collapses them and keeps only one org's row."""
    if df.empty:
        return {c: 0 for c in cols}
    latest = df.sort_values("week_start").groupby(["state", "group", "nation", "org_name"])[cols].last()
    return {c: int(latest[c].sum()) for c in cols}


def _build_pie(data, series_def, empty_msg):
    labels, values = [], []
    for label, field in series_def:
        v = int(data[field].sum())
        if v > 0:
            labels.append(label)
            values.append(v)
    if values:
        f = go.Figure(go.Pie(
            labels=labels,
            values=values,
            hole=0.45,
            textinfo="label+percent",
            hovertemplate="%{label}: %{value:,}<extra></extra>",
            marker=dict(colors=CHART_COLORS[:len(labels)]),
        ))
        f.update_layout(
            margin=dict(t=20, b=20, l=20, r=20),
            paper_bgcolor="rgba(0,0,0,0)",
            font=dict(family="Open Sans, sans-serif", color="#2A313C"),
            showlegend=True,
            legend=dict(orientation="v", x=1.02, y=0.5),
        )
    else:
        f = go.Figure()
        f.add_annotation(
            text=empty_msg,
            x=0.5, y=0.5, xref="paper", yref="paper",
            showarrow=False, font=dict(size=14, color="#75859E"),
        )
        f.update_layout(
            margin=dict(t=20, b=20, l=20, r=20),
            paper_bgcolor="rgba(0,0,0,0)",
        )
    return f


# ── FD / Org rollup ───────────────────────────────────────────────────────────

_FD_ORG_NUM  = {"function": "params.value == null ? '—' : params.value.toLocaleString()"}
_FD_ORG_TEXT = {"function": "params.value == null ? '—' : params.value"}

# Goal status/delta per metric ("above" / "below" / "on" / "" for no goal set,
# plus the signed actual-minus-target amount) are computed server-side
# (_goal_status / _goal_delta) into companion `<field>_status` /
# `<field>_delta` columns; the formatter/cellClassRules below just read those
# sibling fields off params.data — no client-side goal math, so the figure
# shown always matches whatever get_fd_org_roster returned for that
# org/date-range.
def _goal_num_col(field: str, header: str, **extra) -> dict:
    status_field = f"{field}_status"
    delta_field  = f"{field}_delta"
    return {
        "headerName": header,
        "field": field,
        "type": "numericColumn",
        "flex": 1,
        "minWidth": 160,
        "valueFormatter": {
            "function": (
                "params.value == null ? '—' : params.value.toLocaleString() + "
                # delta is negative for 'below', so its own toLocaleString() already carries the '-'
                f"(params.data.{status_field} === 'above' ? ' (+' + params.data.{delta_field}.toLocaleString() + ')' : "
                f"params.data.{status_field} === 'below' ? ' (' + params.data.{delta_field}.toLocaleString() + ')' : "
                f"params.data.{status_field} === 'on' ? ' •' : '')"
            )
        },
        "cellClassRules": {
            "text-success": f"params.data.{status_field} === 'above'",
            "text-danger":  f"params.data.{status_field} === 'below'",
        },
        **extra,
    }


# join_date/event_modified_at are pre-formatted to display strings via
# _fmt_date_col before the rows ever reach the grid (not via a client-side
# valueFormatter) — dash-ag-grid's `new Date(...)` valueFormatter silently
# fails to render in this app (same pre-existing behavior affects the
# Contacts Detail page's Week column).
FD_ORG_COLUMN_DEFS = [
    {"headerName": "Organization",   "field": "org_label",              "pinned": "left", "flex": 2, "minWidth": 200, "cellStyle": {"fontWeight": "600"}},
    {"headerName": "Start Date",     "field": "join_date",              "valueFormatter": _FD_ORG_TEXT, "flex": 1, "minWidth": 120},
    _goal_num_col("p2p_texts",    "# P2P Texts",   minWidth=130),
    _goal_num_col("phone_calls",  "# Phone Calls", minWidth=130),
    _goal_num_col("face_to_face", "# F2F",         minWidth=110),
    _goal_num_col("total_events", "# Events",      minWidth=110),
    {"headerName": "Most Recent Event", "field": "most_recent_event_name", "valueFormatter": _FD_ORG_TEXT, "flex": 2, "minWidth": 220},
    {"headerName": "Current Stage",     "field": "event_stage",            "valueFormatter": _FD_ORG_TEXT, "flex": 1, "minWidth": 160},
    {"headerName": "Event Modified On", "field": "event_modified_at",   "valueFormatter": _FD_ORG_TEXT, "flex": 1, "minWidth": 140},
]


def _fmt_date_col(series: pd.Series) -> pd.Series:
    """Format a date/timestamp column to 'Mon DD, YYYY' strings, None where unparseable."""
    dt = pd.to_datetime(series, errors="coerce", utc=True)
    return dt.dt.strftime("%b %d, %Y").where(dt.notna(), None)


def _goal_status(actual: pd.Series, target: pd.Series) -> pd.Series:
    """'above' / 'below' / 'on' target, or '' where no goal is set (target 0/null)."""
    return pd.Series(
        [
            "" if not t else "above" if a > t else "below" if a < t else "on"
            for a, t in zip(actual, target)
        ],
        index=actual.index,
    )


def _goal_delta(actual: pd.Series, target: pd.Series) -> pd.Series:
    """Signed actual-minus-target amount (positive = above, negative = below)."""
    return actual - target


def _fd_org_card(fd_name: str | None, org_rows: list[dict]):
    """One card per Field Director, listing their organizations beneath their name."""
    return dbc.Card(
        [
            dbc.CardHeader(fd_name or "Unassigned", className="fw-bold"),
            dbc.CardBody(
                dag.AgGrid(
                    id={"type": "fd-org-grid", "index": fd_name or "unassigned"},
                    columnDefs=FD_ORG_COLUMN_DEFS,
                    rowData=org_rows,
                    defaultColDef={"resizable": True, "sortable": True, "minWidth": 100},
                    dashGridOptions={
                        "domLayout": "autoHeight",
                        "suppressMovableColumns": True,
                        "headerHeight": 36,
                    },
                    style={"width": "100%"},
                    className="ag-theme-alpine",
                ),
                className="p-0",
            ),
        ],
        className="mb-3 border-0 shadow-sm",
    )


# ── Layout ────────────────────────────────────────────────────────────────────

def _kpi_card(card_id: str, icon_class: str, label: str, has_goal: bool = False):
    body = [
        html.I(className=f"{icon_class} fs-2 mb-2", style={"color": "#C1272D"}),
        html.H2("—", id=card_id, className="fw-bold mb-1"),
        html.P(label, className="text-muted small mb-0"),
        html.P(id=f"{card_id}-delta", className="small mb-0 mt-1", style={"minHeight": "1.2em"}),
    ]
    if has_goal:
        body.append(html.P(id=f"{card_id}-goal", className="small mb-0 mt-1", style={"minHeight": "1.2em"}))
    return dbc.Col(
        dbc.Card(
            dbc.CardBody(body, className="text-center py-4"),
            className="h-100 border-0 kpi-card",
        ),
        xs=12, md=4, className="mb-3",
    )


layout = dbc.Container(
    [
        dbc.Row(
            [
                dbc.Col(
                    html.H4("Overview", className="my-3 brand-title"),
                    width="auto",
                ),
                dbc.Col(
                    dbc.Button(
                        [html.I(className="bi bi-file-earmark-pdf me-2"), "Download Report"],
                        id="btn-download-report",
                        color="danger",
                        outline=True,
                        size="sm",
                        className="my-3",
                    ),
                    width="auto",
                    className="ms-auto d-flex align-items-center",
                ),
            ],
            className="align-items-center",
        ),
        dcc.Download(id="report-download"),

        # ── Filters ───────────────────────────────────────────────────────────
        dbc.Row(
            [
                dbc.Col(
                    [
                        dbc.Label("Field Director", className="fw-semibold small mb-1"),
                        dcc.Dropdown(
                            id="field-director-selector",
                            options=[],
                            placeholder="All field directors…",
                            multi=True,
                            clearable=True,
                        ),
                    ],
                    xs=12, sm=6, lg=2, className="mb-3",
                ),
                dbc.Col(
                    [
                        dbc.Label("Org", className="fw-semibold small mb-1"),
                        dcc.Dropdown(
                            id="org-selector",
                            options=[],
                            placeholder="All orgs…",
                            multi=True,
                            clearable=True,
                        ),
                    ],
                    xs=12, sm=6, lg=2, className="mb-3",
                ),
                dbc.Col(
                    [
                        dbc.Label("State", className="fw-semibold small mb-1"),
                        dcc.Dropdown(
                            id="state-selector",
                            options=[],
                            placeholder="All states…",
                            multi=True,
                            clearable=True,
                        ),
                    ],
                    xs=12, sm=6, lg=2, className="mb-3",
                ),
                dbc.Col(
                    [
                        dbc.Label("Nation", className="fw-semibold small mb-1"),
                        dcc.Dropdown(
                            id="nation-selector",
                            options=[],
                            placeholder="All nations…",
                            multi=True,
                            clearable=True,
                        ),
                    ],
                    xs=12, sm=6, lg=2, className="mb-3",
                ),
                dbc.Col(
                    [
                        dbc.Label("Group", className="fw-semibold small mb-1"),
                        dcc.Dropdown(
                            id="group-selector",
                            options=[],
                            value=["CLP"],
                            placeholder="All groups…",
                            multi=True,
                            clearable=True,
                        ),
                    ],
                    xs=12, sm=6, lg=2, className="mb-3",
                ),
                dbc.Col(
                    [
                        dbc.Label("Date Range", className="fw-semibold small mb-1"),
                        dcc.DatePickerRange(
                            id="date-range",
                            clearable=True,
                            display_format="MMM D, YYYY",
                            start_date=date(date.today().year, 1, 1),
                            end_date=date.today(),
                            style={"width": "100%"},
                        ),
                    ],
                    xs=12, sm=6, lg=2, className="mb-3",
                ),
            ],
            className="mb-2 align-items-end",
        ),

        # ── KPI cards ─────────────────────────────────────────────────────────
        dbc.Row(
            [
                _kpi_card("kpi-total-contacts",  "bi bi-journal-check",       "Total Contacts",  has_goal=True),
                _kpi_card("kpi-total-events",    "bi bi-calendar-event-fill", "Total Events",    has_goal=True),
                _kpi_card("kpi-connector-count", "bi bi-diagram-3-fill",      "# of Connectors", has_goal=True),
            ],
            className="mb-4",
        ),

        # ── Field Director / Organization rollup ─────────────────────────────
        dbc.Row(
            dbc.Col(
                dbc.Card(
                    [
                        dbc.CardHeader("Field Directors & Organizations", className="fw-semibold"),
                        dbc.CardBody(
                            [
                                html.P(
                                    [
                                        html.Span("(+123)", className="text-success fw-bold"), " above goal · ",
                                        html.Span("(-123)", className="text-danger fw-bold"),  " below goal · ",
                                        html.Span("•", className="fw-bold"),                   " on goal",
                                    ],
                                    className="text-muted small mb-2",
                                ),
                                dcc.Loading(
                                    html.Div(id="fd-org-rollup"),
                                    target_components={"fd-org-rollup": "children"},
                                    type="circle",
                                    color="#C1272D",
                                ),
                            ],
                            className="p-3",
                        ),
                    ],
                    className="border-0",
                ),
                width=12, className="mb-4",
            )
        ),

        # ── Status ────────────────────────────────────────────────────────────
        dbc.Row(
            dbc.Col(
                html.Div(id="contacts-status", className="text-muted small mb-3"),
                width=12,
            )
        ),

        dcc.Interval(id="analytics-init", interval=1, max_intervals=1, n_intervals=0),
    ],
    fluid=True,
    className="px-4",
)


# ── Load filter options on page mount ─────────────────────────────────────────

@callback(
    Output("state-selector", "options"),
    Output("group-selector", "options"),
    Input("analytics-init",  "n_intervals"),
)
def load_filter_options(_):
    print("[contacts] load_filter_options fired", file=sys.stderr, flush=True)
    try:
        states = get_state_list()
        groups = get_group_list()
        print(f"[contacts] load_filter_options → {len(states)} states, {len(groups)} groups", file=sys.stderr, flush=True)
        return states, groups
    except Exception:
        print(f"[contacts] load_filter_options FAILED:\n{traceback.format_exc()}", file=sys.stderr, flush=True)
        return [], []


@callback(
    Output("nation-selector",        "options"),
    Input("state-selector",          "value"),
    Input("group-selector",          "value"),
    Input("field-director-selector", "value"),
    Input("org-selector",            "value"),
)
def update_nation_options(states, groups, fd_ids, org_ids):
    try:
        return get_nation_list_filtered(states or [], groups or [], fd_ids or [], org_ids or [])
    except Exception:
        print(f"[contacts] update_nation_options FAILED:\n{traceback.format_exc()}", file=sys.stderr, flush=True)
        return []


@callback(
    Output("field-director-selector", "options"),
    Input("state-selector",           "value"),
    Input("group-selector",           "value"),
    Input("nation-selector",          "value"),
    Input("org-selector",             "value"),
)
def update_fd_options(states, groups, nations, org_ids):
    try:
        return get_fd_list_filtered(states or [], nations or [], groups or [], org_ids or [])
    except Exception:
        print(f"[contacts] update_fd_options FAILED:\n{traceback.format_exc()}", file=sys.stderr, flush=True)
        return []


@callback(
    Output("org-selector",           "options"),
    Input("state-selector",          "value"),
    Input("group-selector",          "value"),
    Input("nation-selector",         "value"),
    Input("field-director-selector", "value"),
)
def update_org_options(states, groups, nations, fd_ids):
    try:
        return get_org_list_filtered(states or [], nations or [], groups or [], fd_ids or [])
    except Exception:
        print(f"[contacts] update_org_options FAILED:\n{traceback.format_exc()}", file=sys.stderr, flush=True)
        return []


# ── Master callback ───────────────────────────────────────────────────────────

@callback(
    Output("kpi-total-contacts",        "children"),
    Output("kpi-total-events",          "children"),
    Output("kpi-connector-count",       "children"),
    Output("contacts-status",           "children"),
    Output("kpi-total-contacts-delta",  "children"),
    Output("kpi-total-events-delta",    "children"),
    Output("kpi-connector-count-delta", "children"),
    Output("kpi-total-contacts-goal",   "children"),
    Output("kpi-total-events-goal",     "children"),
    Output("kpi-connector-count-goal",  "children"),
    Input("field-director-selector", "value"),
    Input("org-selector",            "value"),
    Input("state-selector",          "value"),
    Input("nation-selector",         "value"),
    Input("group-selector",          "value"),
    Input("date-range",              "start_date"),
    Input("date-range",              "end_date"),
)
def update_summary(fd_ids, orgs, states, nations, groups, start_date, end_date):
    triggered = ctx.triggered_id or "initial"
    print(
        f"[contacts] update_summary triggered_by={triggered!r} "
        f"fd_ids={fd_ids!r} orgs={orgs!r} states={states!r} nations={nations!r} groups={groups!r} "
        f"start={start_date!r} end={end_date!r}",
        file=sys.stderr, flush=True,
    )

    fd_ids  = fd_ids  or []
    orgs    = orgs    or []
    states  = states  or []
    nations = nations or []
    groups  = groups  or []
    pending_note = ""

    try:
        # Snap the picked range to whole complete Mon-Sun weeks so every
        # figure below describes the exact same calendar weeks — and so an
        # in-progress current week never quietly zeroes out a KPI instead of
        # being reported as pending.
        snapped = resolve_complete_week_range(start_date, end_date)
        if snapped is None:
            raise _DataPending()
        snap_start, snap_end = snapped

        df_all = get_contact_summary(
            state_ids=states,
            nation_ids=nations,
            group_ids=groups,
            fd_ids=fd_ids,
            org_ids=orgs,
        )

        df = df_all
        df = df[df["week_start"].astype(str) >= snap_start]
        df = df[df["week_start"].astype(str) <= snap_end]

        # Total Contacts/Events sum directly from the pre-aggregated
        # contact_analysis_dash table (not the raw table), matching the
        # actuals used for the P2P/Phone/F2F progress bars below.
        total_contacts = int(df["total_contacts"].sum()) if not df.empty else 0
        total_events   = int(df["total_events"].sum())   if not df.empty else 0

        # ── Prior period delta computation ────────────────────────────────────
        # Uses the raw picker dates (not the week-snapped range) so the full-
        # calendar-month/year pattern match in _prior_period still lines up
        # with what the user actually picked; the resulting prior period is
        # then snapped separately before it's used to fetch data.
        prior_start, prior_end, prior_label = _prior_period(start_date, end_date)
        prior_snapped = resolve_complete_week_range(prior_start, prior_end) if prior_start and prior_end else None

        if prior_snapped:
            p_start, p_end = prior_snapped
            df_prior = df_all[df_all["week_start"].astype(str) >= p_start]
            df_prior = df_prior[df_prior["week_start"].astype(str) <= p_end]

            prior_total_contacts = int(df_prior["total_contacts"].sum()) if not df_prior.empty else 0
            prior_total_events   = int(df_prior["total_events"].sum())   if not df_prior.empty else 0

            d_total_contacts = _delta_span(total_contacts, prior_total_contacts, prior_label)
            d_total_events   = _delta_span(total_events,   prior_total_events,   prior_label)
        else:
            d_total_contacts = d_total_events = ""

        # Build summary grid — aggregate by state/group/nation. fd/total_contacts
        # come along as native per-row columns on contact_analysis_dash, so each
        # (state, group, nation) combo's FD is its own first value rather than
        # a separate nation-only lookup, and total_contacts is a plain sum
        # rather than a merge against a separate raw-table query.
        if not df.empty:
            grid_df = df.groupby(["state", "group", "nation"]).agg(
                total_events=("total_events",   "sum"),
                total_contacts=("total_contacts", "sum"),
                field_director=("fd", "first"),
            ).reset_index()
            grid_df["field_director"] = grid_df["field_director"].fillna("")
            grid_df["group"] = grid_df["group"].map(display_group)
            # Placeholder until connector_count lands in contact_analysis_dash
            grid_df["connector_count"] = None
            grid_rows = grid_df.to_dict("records")
        else:
            grid_rows = []

        # ── Annual goal comparison (Total Contacts — always full year-to-date,
        # ignores date-range filter, capped to the last fully-complete week so
        # an in-progress current week never pollutes the YTD figure) ──
        goals = get_goal_constants()
        ytd_resolved = resolve_complete_week_range(date(date.today().year, 1, 1), date.today())

        if ytd_resolved:
            calc_ytd_start, calc_ytd_end = ytd_resolved
            df_ytd = df_all[df_all["week_start"].astype(str) >= calc_ytd_start]
            df_ytd = df_ytd[df_ytd["week_start"].astype(str) <= calc_ytd_end]

            total_contacts_ytd = int(df_ytd["total_contacts"].sum()) if not df_ytd.empty else 0
            ytd_latest_sums = _latest_snapshot_sum(df_ytd, ["count_reg_voters"])
            count_reg_voters_ytd = ytd_latest_sums["count_reg_voters"]
        else:
            # Only possible in the first days of January, before this year's
            # first complete week has landed.
            total_contacts_ytd = count_reg_voters_ytd = 0

        g_total_contacts = _goal_span(total_contacts_ytd, goals.get("t_contacts", 0) * count_reg_voters_ytd)

        # Total Events / # of Connectors / P2P/Phone/F2F targets all come from
        # the org-level goal calendar (real per-org targets), scoped to the
        # currently selected (snapped) date range rather than a flat
        # KPI-constant multiplier.
        goal_cal_df = get_goal_calendar_targets(
            state_ids=states,
            nation_ids=nations,
            group_ids=groups,
            start_date=snap_start,
            end_date=snap_end,
            fd_ids=fd_ids,
            org_ids=orgs,
        )
        events_target     = int(goal_cal_df["events_target"].sum())     if not goal_cal_df.empty else 0
        connectors_target = int(goal_cal_df["connectors_target"].sum()) if not goal_cal_df.empty else 0
        p2p_text_target    = int(goal_cal_df["texts_target"].sum())     if not goal_cal_df.empty else 0
        phone_target        = int(goal_cal_df["calls_target"].sum())    if not goal_cal_df.empty else 0
        f2f_target           = int(goal_cal_df["f2f_target"].sum())     if not goal_cal_df.empty else 0

        g_total_events    = _goal_span(total_events, events_target)
        # # of Connectors isn't wired up to a real data source yet — placeholder actual of 0
        g_connector_count = _goal_span(0, connectors_target)

        # Contact goal progress bars — granular actuals from the pre-aggregated
        # table, filtered to the currently selected date range, so they always
        # match the Total Contacts KPI above.
        p2p_text_actual = int(df["contact_text"].sum())         if not df.empty else 0
        phone_actual    = int(df["contact_phone"].sum())        if not df.empty else 0
        f2f_actual      = int(df["contact_face_to_face"].sum()) if not df.empty else 0

        contact_goal_progress = [
            _progress_row("P2P / Text",   p2p_text_actual, p2p_text_target),
            _progress_row("Phone Call",   phone_actual,    phone_target),
            _progress_row("Face to Face", f2f_actual,      f2f_target),
        ]

        row_count = len(df)
        print(f"[contacts] update_summary → {row_count} rows", file=sys.stderr, flush=True)

        total_contacts_display = f"{total_contacts:,}"
        total_events_display   = f"{total_events:,}"

    except _DataPending:
        print("[contacts] update_summary → Data Pending (no complete week in range)", file=sys.stderr, flush=True)
        total_contacts_display = total_events_display = "Data Pending"
        grid_rows = []
        d_total_contacts = d_total_events = ""
        g_total_events = g_total_contacts = g_connector_count = ""
        contact_goal_progress = [
            html.P("Data Pending — no complete week in the selected range yet.", className="text-muted small mb-0"),
        ]
        pending_note = "Data Pending"
    except Exception:
        print(f"[contacts] update_summary FAILED:\n{traceback.format_exc()}", file=sys.stderr, flush=True)
        total_contacts_display = total_events_display = "—"
        grid_rows = []
        d_total_contacts = d_total_events = ""
        g_total_events = g_total_contacts = g_connector_count = ""
        contact_goal_progress = []

    parts = [
        ", ".join(sorted(fd_ids))  if fd_ids  else "All field directors",
        ", ".join(sorted(orgs))    if orgs    else "All orgs",
        ", ".join(sorted(states))  if states  else "All states",
        ", ".join(sorted(nations)) if nations else "All nations",
        ", ".join(sorted(display_group(g) for g in groups)) if groups else "All groups",
    ]
    if start_date or end_date:
        date_part = f"{start_date[:10] if start_date else '…'} → {end_date[:10] if end_date else '…'}"
        parts.append(date_part)
    if pending_note:
        parts.append(pending_note)

    # grid_rows / contact_goal_progress are computed above but no longer
    # rendered — the Summary by State/Group/Nation grid and Contact Goal
    # Progress bars were replaced by the FD/Org rollup below. Kept so those
    # visualizations can be reimplemented without redoing the aggregation.
    _ = grid_rows, contact_goal_progress

    return (
        total_contacts_display,
        total_events_display,
        "—",
        " · ".join(parts),
        d_total_contacts,
        d_total_events,
        "",
        g_total_contacts,
        g_total_events,
        g_connector_count,
    )


# ── FD / Org rollup callback ──────────────────────────────────────────────────

@callback(
    Output("fd-org-rollup", "children"),
    Input("field-director-selector", "value"),
    Input("org-selector",            "value"),
    Input("state-selector",          "value"),
    Input("nation-selector",         "value"),
    Input("group-selector",          "value"),
    Input("date-range",              "start_date"),
    Input("date-range",              "end_date"),
)
def update_fd_org_rollup(fd_ids, orgs, states, nations, groups, start_date, end_date):
    fd_ids  = fd_ids  or []
    orgs    = orgs    or []
    states  = states  or []
    nations = nations or []
    groups  = groups  or []

    try:
        snapped = resolve_complete_week_range(start_date, end_date)
        if snapped is None:
            raise _DataPending()
        snap_start, snap_end = snapped

        df = get_fd_org_roster(
            state_ids=states,
            nation_ids=nations,
            group_ids=groups,
            fd_ids=fd_ids,
            org_ids=orgs,
            start_date=snap_start,
            end_date=snap_end,
        )

        if df.empty:
            return html.P("No organizations match the selected filters.", className="text-muted small mb-0")

        df["join_date"]         = _fmt_date_col(df["join_date"])
        df["event_modified_at"] = _fmt_date_col(df["event_modified_at"])

        for field in ("p2p_texts", "phone_calls", "face_to_face", "total_events"):
            df[f"{field}_status"] = _goal_status(df[field], df[f"{field}_target"])
            df[f"{field}_delta"]  = _goal_delta(df[field], df[f"{field}_target"])

        return [
            _fd_org_card(fd_name, fd_df.drop(columns="fd").to_dict("records"))
            for fd_name, fd_df in df.groupby("fd", dropna=False, sort=True)
        ]
    except _DataPending:
        print("[contacts] update_fd_org_rollup → Data Pending (no complete week in range)", file=sys.stderr, flush=True)
        return html.P("Data Pending — no complete week in the selected range yet.", className="text-muted small mb-0")
    except Exception:
        print(f"[contacts] update_fd_org_rollup FAILED:\n{traceback.format_exc()}", file=sys.stderr, flush=True)
        return html.P("Unable to load Field Director / Organization data.", className="text-danger small mb-0")


# ── Report download callback ──────────────────────────────────────────────────

@callback(
    Output("report-download", "data"),
    Input("btn-download-report", "n_clicks"),
    State("field-director-selector", "value"),
    State("org-selector",    "value"),
    State("state-selector",  "value"),
    State("nation-selector", "value"),
    State("group-selector",  "value"),
    prevent_initial_call=True,
)
def download_report(_, fd_ids, orgs, states, nations, groups):
    print("[contacts] download_report fired", file=sys.stderr, flush=True)
    try:
        return _generate_report(states, nations, groups, fd_ids, orgs)
    except Exception:
        print(f"[contacts] download_report FAILED:\n{traceback.format_exc()}", file=sys.stderr, flush=True)
        return None


def _generate_report(states, nations, groups, fd_ids, orgs):
    states  = states  or []
    nations = nations or []
    groups  = groups  or []
    fd_ids  = fd_ids  or []
    orgs    = orgs    or []

    today     = date.today()
    ytd_start = date(today.year, 1, 1)
    # Cap at the last fully-complete Mon-Sun week so an in-progress current
    # week never pollutes "Prior Week" or "Year to Date" figures.
    cutoff = last_complete_week_end()

    pw_end   = cutoff
    pw_start = pw_end - timedelta(days=6)

    first_of_month = date(today.year, today.month, 1)
    pm_end   = first_of_month - timedelta(days=1)
    pm_start = date(pm_end.year, pm_end.month, 1)

    ytd_end = min(today, cutoff)

    def _fmt(d): return f"{d.strftime('%b')} {d.day}, {d.year}"

    filter_parts = [
        ", ".join(sorted(fd_ids))  if fd_ids  else "All Field Directors",
        ", ".join(sorted(orgs))    if orgs    else "All Orgs",
        ", ".join(sorted(states))  if states  else "All States",
        ", ".join(sorted(nations)) if nations else "All Nations",
        ", ".join(sorted(display_group(g) for g in groups)) if groups else "All Groups",
    ]
    filter_context = " · ".join(filter_parts)

    def _compute(start, end):
        df = get_contact_summary(
            state_ids=states,
            nation_ids=nations,
            group_ids=groups,
            fd_ids=fd_ids,
            org_ids=orgs,
        )
        s, e = str(start), str(end)
        df = df[df["week_start"].astype(str) >= s]
        df = df[df["week_start"].astype(str) <= e]

        # Gated to the same (nation, week) cells contact_analysis_dash has
        # actually populated, so Unique/UC Unique Contacts are computed from
        # the identical underlying slice of data as Total Contacts above
        # instead of the full raw dataset.
        raw_df = get_raw_contact_counts(
            state_ids=states,
            nation_ids=nations,
            group_ids=groups,
            start_date=s,
            end_date=e,
            fd_ids=fd_ids,
            org_ids=orgs,
            gate_to_landed_weeks=True,
        )

        total_contacts     = int(df["total_contacts"].sum())         if not df.empty     else 0
        unique_contacts    = int(raw_df["unique_contacts"].sum())    if not raw_df.empty else 0
        uc_total_contacts  = int(df["uc_total_contacts"].sum())      if not df.empty     else 0
        uc_unique_contacts = int(raw_df["uc_unique_contacts"].sum()) if not raw_df.empty else 0
        total_events       = int(df["total_events"].sum())           if not df.empty else 0
        fe_contacts        = int(df["fe_contacts"].sum())            if not df.empty else 0

        if not df.empty:
            df_latest = df[df["week_start"] == df["week_start"].max()]
        else:
            df_latest = df
        count_uc = int(df_latest["count_unreliable_conservatives"].sum()) if not df_latest.empty else 0

        kpis = [
            ("Total Contacts",    f"{total_contacts:,}"),
            ("Unique Contacts",   f"{unique_contacts:,}"),
            ("Total Events",      f"{total_events:,}"),
            ("UC's",              f"{count_uc:,}"),
            ("UC Total Conts.",   f"{uc_total_contacts:,}"),
            ("UC Unique Conts.",  f"{uc_unique_contacts:,}"),
            ("# of CLs",         "—"),
            ("# of Connectors",  "—"),
            ("# of FE Contacts",  f"{fe_contacts:,}"),
        ]
        # Frequency pie uses a true raw-table dedup (each voter bucketed once
        # by their total contact count over the period) rather than summing
        # the pre-aggregated weekly snapshot columns.
        freq_df = get_contact_frequency(
            state_ids=states,
            nation_ids=nations,
            group_ids=groups,
            start_date=s,
            end_date=e,
            fd_ids=fd_ids,
            org_ids=orgs,
            gate_to_landed_weeks=True,
        )
        fig_type = _build_pie(df,      CONTACT_TYPES,     "No contact data.")
        fig_freq = _build_pie(freq_df, CONTACT_FREQUENCY, "No frequency data.")
        return kpis, fig_type, fig_freq

    pw_kpis,  pw_fig_type,  pw_fig_freq  = _compute(pw_start,  pw_end)
    pm_kpis,  pm_fig_type,  pm_fig_freq  = _compute(pm_start,  pm_end)
    ytd_kpis, ytd_fig_type, ytd_fig_freq = _compute(ytd_start, ytd_end)

    pdf_bytes = build_report(
        pw_heading=f"Prior Week — {_fmt(pw_start)} → {_fmt(pw_end)}",
        pw_kpis=pw_kpis,
        pw_fig_type=pw_fig_type,
        pw_fig_freq=pw_fig_freq,
        pm_heading=f"Prior Month — {pm_start.strftime('%B %Y')}",
        pm_kpis=pm_kpis,
        pm_fig_type=pm_fig_type,
        pm_fig_freq=pm_fig_freq,
        ytd_heading=f"Year to Date — {_fmt(ytd_start)} → {_fmt(today)}",
        ytd_kpis=ytd_kpis,
        ytd_fig_type=ytd_fig_type,
        ytd_fig_freq=ytd_fig_freq,
        filter_context=filter_context,
    )

    return dcc.send_bytes(pdf_bytes, f"contact_report_{today.strftime('%Y%m%d')}.pdf")
