"""
Contacts — KPI summary cards and contact-type breakdown pie chart.
Filters: State, Nation, Group (multi-select) + Date Range.
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
import plotly.graph_objects as go
from dash import Input, Output, State, callback, ctx, dcc, html

from data.queries import get_contact_summary, get_fd_list, get_fd_source, get_group_list, get_nation_list_filtered, get_state_list, get_raw_contact_counts
from reports.pdf_report import build_report

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


# ── Layout ────────────────────────────────────────────────────────────────────

def _kpi_card(card_id: str, icon_class: str, label: str):
    return dbc.Col(
        dbc.Card(
            dbc.CardBody([
                html.I(className=f"{icon_class} fs-2 mb-2", style={"color": "#C1272D"}),
                html.H2("—", id=card_id, className="fw-bold mb-1"),
                html.P(label, className="text-muted small mb-0"),
                html.P(id=f"{card_id}-delta", className="small mb-0 mt-1", style={"minHeight": "1.2em"}),
            ], className="text-center py-4"),
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
                    xs=12, sm=6, lg=3, className="mb-3",
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
                    xs=12, sm=6, lg=3, className="mb-3",
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
                    xs=12, sm=6, lg=3, className="mb-3",
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
                    xs=12, sm=6, lg=3, className="mb-3",
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
                    xs=12, sm=6, lg=3, className="mb-3",
                ),
            ],
            className="mb-2 align-items-end",
        ),

        # ── KPI cards ─────────────────────────────────────────────────────────
        dbc.Row(
            [
                _kpi_card("kpi-total-contacts",  "bi bi-journal-check",       "Total Contacts"),
                _kpi_card("kpi-total-events",    "bi bi-calendar-event-fill", "Total Events"),
                _kpi_card("kpi-connector-count", "bi bi-diagram-3-fill",      "# of Connectors"),
            ],
            className="mb-4",
        ),

        # ── Summary grid ──────────────────────────────────────────────────────
        dbc.Row(
            dbc.Col(
                dbc.Card(
                    [
                        dbc.CardHeader("Summary by State, Group & Nation", className="fw-semibold"),
                        dbc.CardBody(
                            dcc.Loading(
                                dag.AgGrid(
                                    id="analytics-summary-grid",
                                    columnDefs=[
                                        {"headerName": "State",          "field": "state",          "pinned": "left", "width": 130, "cellStyle": {"fontWeight": "600"}},
                                        {"headerName": "Group",          "field": "group",          "width": 120},
                                        {"headerName": "Nation",         "field": "nation",         "width": 180},
                                        {"headerName": "Field Director", "field": "field_director", "width": 160, "valueFormatter": {"function": "params.value == null ? '—' : params.value"}},
                                        {"headerName": "Total Contacts", "field": "total_contacts", "valueFormatter": {"function": "params.value == null ? '—' : params.value.toLocaleString()"}, "type": "numericColumn", "flex": 1, "minWidth": 140},
                                        {"headerName": "Total Events",   "field": "total_events",   "valueFormatter": {"function": "params.value == null ? '—' : params.value.toLocaleString()"}, "type": "numericColumn", "flex": 1, "minWidth": 130},
                                    ],
                                    rowData=[],
                                    defaultColDef={"resizable": True, "sortable": True, "minWidth": 100},
                                    dashGridOptions={
                                        "domLayout": "autoHeight",
                                        "suppressMovableColumns": True,
                                        "headerHeight": 36,
                                    },
                                    style={"width": "100%"},
                                    className="ag-theme-alpine",
                                ),
                                target_components={"analytics-summary-grid": "rowData"},
                                type="circle",
                                color="#0d6efd",
                            ),
                            className="p-0",
                        ),
                    ],
                    className="border-0",
                ),
                width=12,
                className="mb-4",
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
    Output("state-selector",          "options"),
    Output("group-selector",          "options"),
    Output("field-director-selector", "options"),
    Input("analytics-init",           "n_intervals"),
)
def load_filter_options(_):
    print("[contacts] load_filter_options fired", file=sys.stderr, flush=True)
    try:
        states = get_state_list()
        groups = get_group_list()
        fds    = get_fd_list()
        print(f"[contacts] load_filter_options → {len(states)} states, {len(groups)} groups, {len(fds)} FDs", file=sys.stderr, flush=True)
        return states, groups, fds
    except Exception:
        print(f"[contacts] load_filter_options FAILED:\n{traceback.format_exc()}", file=sys.stderr, flush=True)
        return [], [], []


@callback(
    Output("nation-selector",         "options"),
    Input("state-selector",           "value"),
    Input("group-selector",           "value"),
    Input("field-director-selector",  "value"),
)
def update_nation_options(states, groups, fd_ids):
    try:
        options = get_nation_list_filtered(states or [], groups or [])
        if fd_ids:
            fd_df = get_fd_source()
            fd_nations = set(fd_df[fd_df["fd"].isin(fd_ids)]["slug"].tolist())
            options = [o for o in options if o["value"] in fd_nations]
        return options
    except Exception:
        print(f"[contacts] update_nation_options FAILED:\n{traceback.format_exc()}", file=sys.stderr, flush=True)
        return []


# ── Master callback ───────────────────────────────────────────────────────────

@callback(
    Output("kpi-total-contacts",        "children"),
    Output("kpi-total-events",          "children"),
    Output("kpi-connector-count",       "children"),
    Output("analytics-summary-grid",    "rowData"),
    Output("contacts-status",           "children"),
    Output("kpi-total-contacts-delta",  "children"),
    Output("kpi-total-events-delta",    "children"),
    Output("kpi-connector-count-delta", "children"),
    Input("field-director-selector", "value"),
    Input("state-selector",          "value"),
    Input("nation-selector",         "value"),
    Input("group-selector",          "value"),
    Input("date-range",              "start_date"),
    Input("date-range",              "end_date"),
)
def update_summary(fd_ids, states, nations, groups, start_date, end_date):
    triggered = ctx.triggered_id or "initial"
    print(
        f"[contacts] update_summary triggered_by={triggered!r} "
        f"fd_ids={fd_ids!r} states={states!r} nations={nations!r} groups={groups!r} "
        f"start={start_date!r} end={end_date!r}",
        file=sys.stderr, flush=True,
    )

    try:
        # Resolve effective nations — when FDs are selected, derive nations from FD source
        fd_df = get_fd_source()
        if fd_ids:
            fd_nations = fd_df[fd_df["fd"].isin(fd_ids)]["slug"].tolist()
            effective_nations = list(set(nations) & set(fd_nations)) if nations else fd_nations
        else:
            effective_nations = nations or []

        df_all = get_contact_summary(
            state_ids=states or [],
            nation_ids=effective_nations,
            group_ids=groups or [],
        )

        # Apply date filter in Python (full dataset already cached per state/nation/group)
        df = df_all
        if start_date:
            df = df[df["week_start"].astype(str) >= start_date[:10]]
        if end_date:
            df = df[df["week_start"].astype(str) <= end_date[:10]]

        total_events = int(df["total_events"].sum())

        # Total contact counts come from the raw table (truly de-duplicated across the date range)
        raw_df = get_raw_contact_counts(
            state_ids=states or [],
            nation_ids=effective_nations,
            group_ids=groups or [],
            start_date=start_date,
            end_date=end_date,
        )
        total_contacts = int(raw_df["total_contacts"].sum()) if not raw_df.empty else 0

        # ── Prior period delta computation ────────────────────────────────────
        prior_start, prior_end, prior_label = _prior_period(start_date, end_date)

        if prior_start and prior_end:
            df_prior = df_all[df_all["week_start"].astype(str) >= prior_start]
            df_prior = df_prior[df_prior["week_start"].astype(str) <= prior_end]

            prior_total_events = int(df_prior["total_events"].sum()) if not df_prior.empty else 0

            raw_prior = get_raw_contact_counts(
                state_ids=states or [],
                nation_ids=effective_nations,
                group_ids=groups or [],
                start_date=prior_start,
                end_date=prior_end,
            )
            prior_total_contacts = int(raw_prior["total_contacts"].sum()) if not raw_prior.empty else 0

            d_total_contacts = _delta_span(total_contacts, prior_total_contacts, prior_label)
            d_total_events   = _delta_span(total_events,   prior_total_events,   prior_label)
        else:
            d_total_contacts = d_total_events = ""

        # Build summary grid — aggregate by state/group/nation
        if not df.empty:
            grid_agg = df.groupby(["state", "group", "nation"]).agg(
                {"total_events": "sum"}
            ).reset_index()
            if not raw_df.empty:
                grid_df = grid_agg.merge(
                    raw_df[["state", "group", "nation", "total_contacts"]],
                    on=["state", "group", "nation"],
                    how="left",
                )
                grid_df["total_contacts"] = grid_df["total_contacts"].fillna(0).astype(int)
            else:
                grid_df = grid_agg
                grid_df["total_contacts"] = 0
            # Join the latest FD assignment per nation
            if not fd_df.empty:
                fd_lookup = fd_df[["slug", "fd"]].rename(columns={"slug": "nation", "fd": "field_director"})
                grid_df = grid_df.merge(fd_lookup, on="nation", how="left")
                grid_df["field_director"] = grid_df["field_director"].fillna("")
            else:
                grid_df["field_director"] = ""
            grid_rows = grid_df.to_dict("records")
        else:
            grid_rows = []

        row_count = len(df)
        print(f"[contacts] update_summary → {row_count} rows", file=sys.stderr, flush=True)

    except Exception:
        print(f"[contacts] update_summary FAILED:\n{traceback.format_exc()}", file=sys.stderr, flush=True)
        total_contacts = total_events = 0
        grid_rows = []
        row_count = 0
        d_total_contacts = d_total_events = ""

    parts = [
        ", ".join(sorted(fd_ids))  if fd_ids  else "All field directors",
        ", ".join(sorted(states))  if states  else "All states",
        ", ".join(sorted(nations)) if nations else "All nations",
        ", ".join(sorted(groups))  if groups  else "All groups",
    ]
    if start_date or end_date:
        date_part = f"{start_date[:10] if start_date else '…'} → {end_date[:10] if end_date else '…'}"
        parts.append(date_part)

    return (
        f"{total_contacts:,}",
        f"{total_events:,}",
        "—",
        grid_rows,
        " · ".join(parts),
        d_total_contacts,
        d_total_events,
        "",
    )


# ── Report download callback ──────────────────────────────────────────────────

@callback(
    Output("report-download", "data"),
    Input("btn-download-report", "n_clicks"),
    State("state-selector",  "value"),
    State("nation-selector", "value"),
    State("group-selector",  "value"),
    prevent_initial_call=True,
)
def download_report(_, states, nations, groups):
    print("[contacts] download_report fired", file=sys.stderr, flush=True)
    try:
        return _generate_report(states, nations, groups)
    except Exception:
        print(f"[contacts] download_report FAILED:\n{traceback.format_exc()}", file=sys.stderr, flush=True)
        return None


def _generate_report(states, nations, groups):
    today     = date.today()
    ytd_start = date(today.year, 1, 1)

    this_monday = today - timedelta(days=today.weekday())
    pw_start = this_monday - timedelta(days=7)
    pw_end   = this_monday - timedelta(days=1)

    first_of_month = date(today.year, today.month, 1)
    pm_end   = first_of_month - timedelta(days=1)
    pm_start = date(pm_end.year, pm_end.month, 1)

    def _fmt(d): return f"{d.strftime('%b')} {d.day}, {d.year}"

    filter_parts = [
        ", ".join(sorted(states))  if states  else "All States",
        ", ".join(sorted(nations)) if nations else "All Nations",
        ", ".join(sorted(groups))  if groups  else "All Groups",
    ]
    filter_context = " · ".join(filter_parts)

    def _compute(start, end):
        df = get_contact_summary(
            state_ids=states   or [],
            nation_ids=nations or [],
            group_ids=groups   or [],
        )
        s, e = str(start), str(end)
        df = df[df["week_start"].astype(str) >= s]
        df = df[df["week_start"].astype(str) <= e]

        raw_df = get_raw_contact_counts(
            state_ids=states   or [],
            nation_ids=nations or [],
            group_ids=groups   or [],
            start_date=s,
            end_date=e,
        )

        total_contacts     = int(raw_df["total_contacts"].sum())     if not raw_df.empty else 0
        unique_contacts    = int(raw_df["unique_contacts"].sum())    if not raw_df.empty else 0
        uc_total_contacts  = int(raw_df["uc_total_contacts"].sum())  if not raw_df.empty else 0
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
        fig_type = _build_pie(df, CONTACT_TYPES,     "No contact data.")
        fig_freq = _build_pie(df, CONTACT_FREQUENCY, "No frequency data.")
        return kpis, fig_type, fig_freq

    pw_kpis,  pw_fig_type,  pw_fig_freq  = _compute(pw_start,  pw_end)
    pm_kpis,  pm_fig_type,  pm_fig_freq  = _compute(pm_start,  pm_end)
    ytd_kpis, ytd_fig_type, ytd_fig_freq = _compute(ytd_start, today)

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
