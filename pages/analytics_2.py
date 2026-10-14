"""
Analytics 2 — working revision of the Overview (/analytics) page.
Copied from pages/analytics.py; component IDs are prefixed "a2-" so they
don't collide with the original page's callbacks.

Unlike the original, the period filter is a From/To month selection rather
than a free-form date range: goals are benchmarked monthly while data lands
weekly, so a selected month means exactly the weeks whose week_start Monday
falls in it (see utils.dates "Program months"), and both actuals and goals
are summed over those same weeks.
"""

from __future__ import annotations

import sys
import traceback
from datetime import date, timedelta

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
    get_fd_org_roster_v2,
    get_goal_calendar_targets_v2,
    get_goal_constants,
    get_group_list,
    get_nation_list_filtered,
    get_org_list_filtered,
    get_raw_contact_counts,
    get_state_list,
)
from reports.pdf_report import build_report
from utils.dates import (
    last_complete_week_end,
    month_span,
    prior_month_period,
    resolve_month_period,
)

dash.register_page(
    __name__,
    path="/analytics-2",
    name="Analytics 2",
    title="Analytics 2 | Central Program Management",
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
    """Raised when no complete Mon-Sun week falls in the selected months."""


# Earliest month offered in the period dropdowns — goal calendar data starts
# Mar 2026, so there's nothing to benchmark before this program year.
_PERIOD_FLOOR = "2026-01"


def _month_options() -> list[dict]:
    """Program months from _PERIOD_FLOOR through the current month."""
    return [
        {"label": date(y, m, 1).strftime("%b %Y"), "value": f"{y}-{m:02d}"}
        for y, m in month_span(_PERIOD_FLOOR, date.today().strftime("%Y-%m"))
    ]


def _fmt_day(d: str | date) -> str:
    """'2026-09-07' -> 'Sep 7, 2026'."""
    d = d if isinstance(d, date) else date.fromisoformat(d[:10])
    return f"{d.strftime('%b')} {d.day}, {d.year}"


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

# Each goal cell reads "actual (goal)", where goal is the org's target for the
# selected period. Goal status per metric ("above" / "below" / "on" / "" for
# no goal set) is computed server-side (_goal_status) into a companion
# `<field>_status` column; the formatter/cellClassRules below just read that
# and `<field>_target` off params.data — no client-side goal math, so the
# figure shown always matches whatever get_fd_org_roster_v2 returned for that
# org/period.
def _goal_num_col(field: str, header: str, fill: bool = False, **extra) -> dict:
    """fill=True swaps the green/red text for a goal-status cell background
    (goal-fill-* in assets/styles.css): light green on goal, dark green above,
    yellow below."""
    status_field = f"{field}_status"
    target_field = f"{field}_target"
    if fill:
        class_rules = {
            "goal-fill-on":    f"params.data.{status_field} === 'on'",
            "goal-fill-above": f"params.data.{status_field} === 'above'",
            "goal-fill-below": f"params.data.{status_field} === 'below'",
        }
    else:
        class_rules = {
            "text-success": f"params.data.{status_field} === 'above'",
            "text-danger":  f"params.data.{status_field} === 'below'",
        }
    return {
        "headerName": header,
        "field": field,
        "type": "numericColumn",
        "flex": 1,
        "minWidth": 160,
        "valueFormatter": {
            "function": (
                "params.value == null ? '—' : params.value.toLocaleString() + "
                # status is '' when no goal is set — show the bare actual
                f"(params.data.{status_field} ? ' (' + params.data.{target_field}.toLocaleString() + ')' : '')"
            )
        },
        "cellClassRules": class_rules,
        **extra,
    }


# join_date is pre-formatted to a display string via
# _fmt_date_col before the rows ever reach the grid (not via a client-side
# valueFormatter) — dash-ag-grid's `new Date(...)` valueFormatter silently
# fails to render in this app (same pre-existing behavior affects the
# Contacts Detail page's Week column).
# Columns are grouped under Events / Connectors / Contacts header bands;
# Organization and Start Date describe the org itself and sit ungrouped on
# the left.
FD_ORG_COLUMN_DEFS = [
    {"headerName": "Organization",   "field": "org_label",              "pinned": "left", "flex": 2, "minWidth": 200, "cellStyle": {"fontWeight": "600"}},
    {"headerName": "Start Date",     "field": "join_date",              "valueFormatter": _FD_ORG_TEXT, "flex": 1, "minWidth": 120},
    {
        "headerName": "Events",
        "children": [
            _goal_num_col("total_events", "# Events", fill=True, minWidth=110),
        ],
    },
    {
        "headerName": "Connectors",
        "children": [_goal_num_col("connectors", "# Connectors", fill=True, minWidth=130)],
    },
    {
        "headerName": "Contacts",
        "children": [
            {"headerName": "Total Contacts", "field": "total_contacts", "type": "numericColumn", "valueFormatter": _FD_ORG_NUM, "flex": 1, "minWidth": 130},
            _goal_num_col("p2p_texts",    "# P2P Texts",   fill=True, minWidth=130),
            _goal_num_col("phone_calls",  "# Calls",       minWidth=110),
            _goal_num_col("face_to_face", "# F2F",         minWidth=110),
        ],
    },
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


def _fd_org_card(fd_name: str | None, org_rows: list[dict]):
    """One card per Field Director, listing their organizations beneath their name."""
    return dbc.Card(
        [
            dbc.CardHeader(fd_name or "Unassigned", className="fw-bold"),
            dbc.CardBody(
                dag.AgGrid(
                    id={"type": "a2-fd-org-grid", "index": fd_name or "unassigned"},
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


def layout(**_kwargs):
    # A function rather than a module constant so the period dropdowns'
    # options and Jan-to-current-month default track today's date on every
    # page load.
    return dbc.Container(
        [
            dbc.Row(
                [
                    dbc.Col(
                        html.H4("Analytics 2", className="my-3 brand-title"),
                        width="auto",
                    ),
                    dbc.Col(
                        dbc.Button(
                            [html.I(className="bi bi-file-earmark-pdf me-2"), "Download Report"],
                            id="a2-btn-download-report",
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
            dcc.Download(id="a2-report-download"),

            # ── Filters ───────────────────────────────────────────────────────────
            dbc.Row(
                [
                    dbc.Col(
                        [
                            dbc.Label("Field Director", className="fw-semibold small mb-1"),
                            dcc.Dropdown(
                                id="a2-field-director-selector",
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
                                id="a2-org-selector",
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
                                id="a2-state-selector",
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
                                id="a2-nation-selector",
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
                                id="a2-group-selector",
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
                            dbc.Label("Period (months)", className="fw-semibold small mb-1"),
                            dbc.Row(
                                [
                                    dbc.Col(
                                        dcc.Dropdown(
                                            id="a2-month-from",
                                            options=_month_options(),
                                            value=f"{date.today().year}-01",
                                            clearable=False,
                                            searchable=False,
                                        ),
                                        width=6, className="pe-1",
                                    ),
                                    dbc.Col(
                                        dcc.Dropdown(
                                            id="a2-month-to",
                                            options=_month_options(),
                                            value=date.today().strftime("%Y-%m"),
                                            clearable=False,
                                            searchable=False,
                                        ),
                                        width=6, className="ps-1",
                                    ),
                                ],
                                className="g-0",
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
                    _kpi_card("a2-kpi-total-contacts",  "bi bi-journal-check",       "Total Contacts",  has_goal=True),
                    _kpi_card("a2-kpi-total-events",    "bi bi-calendar-event-fill", "Total Events",    has_goal=True),
                    _kpi_card("a2-kpi-connector-count", "bi bi-diagram-3-fill",      "# of Connectors", has_goal=True),
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
                                            "Actual ", html.Span("(goal for period)", className="fw-bold"), " · ",
                                            html.Span("green", className="text-success fw-bold"), " above goal · ",
                                            html.Span("red", className="text-danger fw-bold"),    " below goal",
                                            html.Span(" | ", className="mx-2"),
                                            "Events, Connectors, P2P Texts: ",
                                            html.Span("above", className="goal-swatch goal-fill-above"), " ",
                                            html.Span("on",    className="goal-swatch goal-fill-on"),    " ",
                                            html.Span("below", className="goal-swatch goal-fill-below"),
                                        ],
                                        className="text-muted small mb-2",
                                    ),
                                    dcc.Loading(
                                        html.Div(id="a2-fd-org-rollup"),
                                        target_components={"a2-fd-org-rollup": "children"},
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
                    html.Div(id="a2-contacts-status", className="text-muted small mb-3"),
                    width=12,
                )
            ),

            dcc.Interval(id="a2-analytics-init", interval=1, max_intervals=1, n_intervals=0),
        ],
        fluid=True,
        className="px-4",
    )


# ── Load filter options on page mount ─────────────────────────────────────────

@callback(
    Output("a2-state-selector", "options"),
    Output("a2-group-selector", "options"),
    Input("a2-analytics-init",  "n_intervals"),
)
def load_filter_options(_):
    print("[analytics2] load_filter_options fired", file=sys.stderr, flush=True)
    try:
        states = get_state_list()
        groups = get_group_list()
        print(f"[analytics2] load_filter_options → {len(states)} states, {len(groups)} groups", file=sys.stderr, flush=True)
        return states, groups
    except Exception:
        print(f"[analytics2] load_filter_options FAILED:\n{traceback.format_exc()}", file=sys.stderr, flush=True)
        return [], []


@callback(
    Output("a2-nation-selector",        "options"),
    Input("a2-state-selector",          "value"),
    Input("a2-group-selector",          "value"),
    Input("a2-field-director-selector", "value"),
    Input("a2-org-selector",            "value"),
)
def update_nation_options(states, groups, fd_ids, org_ids):
    try:
        return get_nation_list_filtered(states or [], groups or [], fd_ids or [], org_ids or [])
    except Exception:
        print(f"[analytics2] update_nation_options FAILED:\n{traceback.format_exc()}", file=sys.stderr, flush=True)
        return []


@callback(
    Output("a2-field-director-selector", "options"),
    Input("a2-state-selector",           "value"),
    Input("a2-group-selector",           "value"),
    Input("a2-nation-selector",          "value"),
    Input("a2-org-selector",             "value"),
)
def update_fd_options(states, groups, nations, org_ids):
    try:
        return get_fd_list_filtered(states or [], nations or [], groups or [], org_ids or [])
    except Exception:
        print(f"[analytics2] update_fd_options FAILED:\n{traceback.format_exc()}", file=sys.stderr, flush=True)
        return []


@callback(
    Output("a2-org-selector",           "options"),
    Input("a2-state-selector",          "value"),
    Input("a2-group-selector",          "value"),
    Input("a2-nation-selector",         "value"),
    Input("a2-field-director-selector", "value"),
)
def update_org_options(states, groups, nations, fd_ids):
    try:
        return get_org_list_filtered(states or [], nations or [], groups or [], fd_ids or [])
    except Exception:
        print(f"[analytics2] update_org_options FAILED:\n{traceback.format_exc()}", file=sys.stderr, flush=True)
        return []


# ── Master callback ───────────────────────────────────────────────────────────

@callback(
    Output("a2-kpi-total-contacts",        "children"),
    Output("a2-kpi-total-events",          "children"),
    Output("a2-kpi-connector-count",       "children"),
    Output("a2-contacts-status",           "children"),
    Output("a2-kpi-total-contacts-delta",  "children"),
    Output("a2-kpi-total-events-delta",    "children"),
    Output("a2-kpi-connector-count-delta", "children"),
    Output("a2-kpi-total-contacts-goal",   "children"),
    Output("a2-kpi-total-events-goal",     "children"),
    Output("a2-kpi-connector-count-goal",  "children"),
    Input("a2-field-director-selector", "value"),
    Input("a2-org-selector",            "value"),
    Input("a2-state-selector",          "value"),
    Input("a2-nation-selector",         "value"),
    Input("a2-group-selector",          "value"),
    Input("a2-month-from",              "value"),
    Input("a2-month-to",                "value"),
)
def update_summary(fd_ids, orgs, states, nations, groups, month_from, month_to):
    triggered = ctx.triggered_id or "initial"
    print(
        f"[analytics2] update_summary triggered_by={triggered!r} "
        f"fd_ids={fd_ids!r} orgs={orgs!r} states={states!r} nations={nations!r} groups={groups!r} "
        f"from={month_from!r} to={month_to!r}",
        file=sys.stderr, flush=True,
    )

    fd_ids  = fd_ids  or []
    orgs    = orgs    or []
    states  = states  or []
    nations = nations or []
    groups  = groups  or []
    pending_note = ""
    period = None

    try:
        # Resolve the selected months to their complete Mon-Sun weeks (a week
        # belongs to the month its Monday falls in), so actuals and goals
        # below are summed over exactly the same weeks — and an in-progress
        # current week is left out rather than quietly zeroing a KPI.
        period = resolve_month_period(month_from, month_to) if month_from and month_to else None
        if period is None:
            raise _DataPending()
        snap_start, snap_end = period.start, period.end

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
        # Previous month(s), or the same months last year for a Jan-start
        # run; cut to the same number of weeks when the last month is still
        # in progress (see prior_month_period).
        prior = prior_month_period(period)

        if prior:
            p_start, p_end, prior_label = prior
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
        # ignores the period filter, capped to the last fully-complete week so
        # an in-progress current week never pollutes the YTD figure) ──
        goals = get_goal_constants()
        ytd_resolved = resolve_month_period(f"{date.today().year}-01", date.today().strftime("%Y-%m"))

        if ytd_resolved:
            calc_ytd_start, calc_ytd_end = ytd_resolved.start, ytd_resolved.end
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
        # selected program months — an in-progress month pro-rated to its
        # complete weeks. The spread shares are fractional, so round after
        # summing across orgs.
        goal_cal_df = get_goal_calendar_targets_v2(
            state_ids=states,
            nation_ids=nations,
            group_ids=groups,
            start_date=snap_start,
            end_date=snap_end,
            fd_ids=fd_ids,
            org_ids=orgs,
        )
        events_target     = round(goal_cal_df["events_target"].sum())     if not goal_cal_df.empty else 0
        connectors_target = round(goal_cal_df["connectors_target"].sum()) if not goal_cal_df.empty else 0
        p2p_text_target    = round(goal_cal_df["texts_target"].sum())     if not goal_cal_df.empty else 0
        phone_target        = round(goal_cal_df["calls_target"].sum())    if not goal_cal_df.empty else 0
        f2f_target           = round(goal_cal_df["f2f_target"].sum())     if not goal_cal_df.empty else 0

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
        print(f"[analytics2] update_summary → {row_count} rows", file=sys.stderr, flush=True)

        total_contacts_display = f"{total_contacts:,}"
        total_events_display   = f"{total_events:,}"

    except _DataPending:
        print("[analytics2] update_summary → Data Pending (no complete week in range)", file=sys.stderr, flush=True)
        total_contacts_display = total_events_display = "Data Pending"
        grid_rows = []
        d_total_contacts = d_total_events = ""
        g_total_events = g_total_contacts = g_connector_count = ""
        contact_goal_progress = [
            html.P("Data Pending — no complete week in the selected months yet.", className="text-muted small mb-0"),
        ]
        pending_note = "Data Pending"
    except Exception:
        print(f"[analytics2] update_summary FAILED:\n{traceback.format_exc()}", file=sys.stderr, flush=True)
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
    if period:
        last_week = date.fromisoformat(period.end) - timedelta(days=6)
        week_span = (
            f"week of {_fmt_day(period.start)}"
            if str(last_week) == period.start
            else f"weeks of {_fmt_day(period.start)} – {_fmt_day(last_week)}"
        )
        parts.append(f"{period.label} ({week_span})")
        if period.partial:
            parts.append(f"{period.pace_note}, goals pro-rated")
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
    Output("a2-fd-org-rollup", "children"),
    Input("a2-field-director-selector", "value"),
    Input("a2-org-selector",            "value"),
    Input("a2-state-selector",          "value"),
    Input("a2-nation-selector",         "value"),
    Input("a2-group-selector",          "value"),
    Input("a2-month-from",              "value"),
    Input("a2-month-to",                "value"),
)
def update_fd_org_rollup(fd_ids, orgs, states, nations, groups, month_from, month_to):
    fd_ids  = fd_ids  or []
    orgs    = orgs    or []
    states  = states  or []
    nations = nations or []
    groups  = groups  or []

    try:
        period = resolve_month_period(month_from, month_to) if month_from and month_to else None
        if period is None:
            raise _DataPending()
        snap_start, snap_end = period.start, period.end

        df = get_fd_org_roster_v2(
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

        df["join_date"] = _fmt_date_col(df["join_date"])

        for field in ("p2p_texts", "phone_calls", "face_to_face", "total_events", "connectors"):
            df[f"{field}_status"] = _goal_status(df[field], df[f"{field}_target"])

        cards = [
            _fd_org_card(fd_name, fd_df.drop(columns="fd").to_dict("records"))
            for fd_name, fd_df in df.groupby("fd", dropna=False, sort=True)
        ]
        if period.partial:
            cards.insert(0, html.P(
                [html.I(className="bi bi-hourglass-split me-1"),
                 f"{period.pace_note} — goals are pro-rated to match."],
                className="text-muted small mb-2",
            ))
        return cards
    except _DataPending:
        print("[analytics2] update_fd_org_rollup → Data Pending (no complete week in range)", file=sys.stderr, flush=True)
        return html.P("Data Pending — no complete week in the selected months yet.", className="text-muted small mb-0")
    except Exception:
        print(f"[analytics2] update_fd_org_rollup FAILED:\n{traceback.format_exc()}", file=sys.stderr, flush=True)
        return html.P("Unable to load Field Director / Organization data.", className="text-danger small mb-0")


# ── Report download callback ──────────────────────────────────────────────────

@callback(
    Output("a2-report-download", "data"),
    Input("a2-btn-download-report", "n_clicks"),
    State("a2-field-director-selector", "value"),
    State("a2-org-selector",    "value"),
    State("a2-state-selector",  "value"),
    State("a2-nation-selector", "value"),
    State("a2-group-selector",  "value"),
    prevent_initial_call=True,
)
def download_report(_, fd_ids, orgs, states, nations, groups):
    print("[analytics2] download_report fired", file=sys.stderr, flush=True)
    try:
        return _generate_report(states, nations, groups, fd_ids, orgs)
    except Exception:
        print(f"[analytics2] download_report FAILED:\n{traceback.format_exc()}", file=sys.stderr, flush=True)
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
