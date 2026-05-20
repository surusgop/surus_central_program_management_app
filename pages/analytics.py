"""
Analytics page — KPIs, program comparison, and trend driven by two slicers:
  - District dropdown   → filters all data to one district
  - Program selector    → BP, CLP, or Both (affects contacts/events KPIs and charts)

The master callback receives both slicers as Inputs and returns all chart
Outputs simultaneously, so every visual updates in one round-trip.
"""

from __future__ import annotations

from datetime import date

import dash
import dash_bootstrap_components as dbc
import pandas as pd
import plotly.graph_objects as go
from dash import Input, Output, callback, dash_table, dcc, html

from data.queries import (
    get_district_demographics,
    get_district_list,
    get_district_table,
    get_district_trend,
    get_program_comparison,
    get_program_totals,
)

dash.register_page(
    __name__,
    path="/analytics",
    name="Analytics",
    title="Analytics | Surus Central",
)

# ── Program palette ───────────────────────────────────────────────────────────

PROGRAM_COLORS = {"BP": "#0d6efd", "CLP": "#198754"}

# Placeholder years — update when wiring live data
ELECTION_YEARS = ("2022", "2024")


def _to_int(val, default: int = 0) -> int:
    """Safely coerce a SQL aggregate result to int, handling None and NaN."""
    try:
        return int(val)
    except (TypeError, ValueError):
        return default


def _fmt_date_range(start_date: str | None, end_date: str | None) -> str:
    """Return a human-readable date range label for KPI card subtitles."""
    if not start_date or not end_date:
        return "All time"
    from datetime import datetime
    fmt = lambda d: datetime.strptime(d[:10], "%Y-%m-%d").strftime("%b %d, %Y").replace(" 0", " ")
    return f"{fmt(start_date)} – {fmt(end_date)}"


# ── Election balance sheet builder ────────────────────────────────────────────

def _election_balance_sheet() -> list:
    """
    Build the static table structure for the election performance section.
    All values are placeholders ("—") until election data is wired up.

    Structure mirrors a balance sheet: section header rows divide the table
    into logical groups, with metric label + two election-year columns each.

    To wire up live data:
      1. Add a query function in data/queries.py (e.g. get_election_stats).
      2. Add an Output for each cell id to the master callback.
      3. Replace the html.Td("—", id=...) children with the callback values.
    """
    yr1, yr2 = ELECTION_YEARS

    def _section_header(label: str) -> html.Tr:
        return html.Tr(
            html.Td(
                label,
                colSpan=3,
                className="fw-semibold text-uppercase small",
                style={"backgroundColor": "#f0f4f8", "letterSpacing": "0.06em",
                       "color": "#495057", "padding": "6px 12px"},
            )
        )

    def _row(label: str, cell_id_1: str, cell_id_2: str,
             indent: bool = False) -> html.Tr:
        label_style = {"paddingLeft": "24px"} if indent else {}
        return html.Tr(
            [
                html.Td(label, style=label_style),
                html.Td("—", id=cell_id_1, className="text-end fw-semibold"),
                html.Td("—", id=cell_id_2, className="text-end fw-semibold"),
            ]
        )

    def _divider_row() -> html.Tr:
        return html.Tr(
            html.Td(colSpan=3, style={"padding": "2px", "backgroundColor": "#dee2e6"})
        )

    thead = html.Thead(
        html.Tr(
            [
                html.Th("Metric", style={"width": "55%"}),
                html.Th(yr1, className="text-end", style={"width": "22.5%"}),
                html.Th(yr2, className="text-end", style={"width": "22.5%"}),
            ],
            style={"backgroundColor": "#e9ecef"},
        )
    )

    tbody = html.Tbody(
        [
            # ── Turnout ───────────────────────────────────────────────────────
            _section_header("Turnout"),
            _row("Overall Turnout %",
                 "el-overall-turnout-yr1", "el-overall-turnout-yr2"),
            _row("Total Votes Cast",
                 "el-votes-cast-yr1",     "el-votes-cast-yr2"),
            _row("Total Registered Voters",
                 "el-registered-yr1",     "el-registered-yr2"),

            _divider_row(),

            # ── Outreach ──────────────────────────────────────────────────────
            _section_header("Outreach"),
            _row("Total Contacts Made",
                 "el-contacts-yr1",       "el-contacts-yr2"),
            _row("Unique Individuals Contacted",
                 "el-individuals-yr1",    "el-individuals-yr2"),
            _row("BP Contacts",
                 "el-bp-contacts-yr1",    "el-bp-contacts-yr2",   indent=True),
            _row("CLP Contacts",
                 "el-clp-contacts-yr1",   "el-clp-contacts-yr2",  indent=True),

            _divider_row(),

            # ── Contacted Performance ─────────────────────────────────────────
            _section_header("Contacted Performance"),
            _row("Contacted Individual Turnout %",
                 "el-contacted-turnout-yr1", "el-contacted-turnout-yr2"),
            _row("Lift vs Overall Turnout",
                 "el-lift-yr1",              "el-lift-yr2"),
        ]
    )

    return [thead, tbody]


# ── Layout ────────────────────────────────────────────────────────────────────

layout = dbc.Container(
    [
        # Page header
        dbc.Row(
            dbc.Col(
                html.H4("District Analytics", className="my-3 fw-semibold text-primary"),
                width=12,
            )
        ),

        # ── Slicers row ───────────────────────────────────────────────────────
        dbc.Row(
            [
                # District
                dbc.Col(
                    html.Span("District:", className="fw-semibold me-2 align-middle"),
                    width="auto",
                    className="d-flex align-items-center",
                ),
                dbc.Col(
                    dcc.Dropdown(
                        id="district-selector",
                        options=[],
                        placeholder="Select a district…",
                        clearable=False,
                        searchable=True,
                        style={"minWidth": "240px"},
                    ),
                    width="auto",
                ),

                # Divider
                dbc.Col(html.Div(className="vr mx-2"), width="auto",
                        className="d-flex align-items-center"),

                # Program
                dbc.Col(
                    html.Span("Program:", className="fw-semibold me-2 align-middle"),
                    width="auto",
                    className="d-flex align-items-center",
                ),
                dbc.Col(
                    dbc.RadioItems(
                        id="program-selector",
                        options=[
                            {"label": "BP",   "value": "BP"},
                            {"label": "CLP",  "value": "CLP"},
                            {"label": "Both", "value": "both"},
                        ],
                        value="both",
                        inline=True,
                        inputStyle={"display": "none"},
                        labelClassName="btn btn-outline-success btn-sm me-1",
                        labelCheckedClassName="btn btn-success btn-sm me-1",
                    ),
                    width="auto",
                ),

                # Refresh
                dbc.Col(
                    dbc.Button(
                        [html.I(className="bi bi-arrow-clockwise me-1"), "Refresh"],
                        id="analytics-refresh-btn",
                        color="secondary",
                        outline=True,
                        size="sm",
                    ),
                    width="auto",
                    className="ms-auto",
                ),
            ],
            className="mb-4 align-items-center",
        ),

        # ── Date range row ────────────────────────────────────────────────────
        # Affects: Contacts KPI, Events KPI, comparison bar, trend chart.
        # Does NOT affect: Registered Voters, Unreliable Conservatives (snapshots).
        dbc.Row(
            [
                dbc.Col(
                    html.Span("Date Range:", className="fw-semibold me-2 align-middle"),
                    width="auto",
                    className="d-flex align-items-center",
                ),
                dbc.Col(
                    dcc.DatePickerRange(
                        id="date-range",
                        start_date=date(date.today().year, 1, 1).isoformat(),
                        end_date=date.today().isoformat(),
                        min_date_allowed="2018-01-01",
                        max_date_allowed=date.today().isoformat(),
                        display_format="MMM D, YYYY",
                        clearable=True,
                    ),
                    width="auto",
                ),
                dbc.Col(
                    html.Span(
                        [
                            html.I(className="bi bi-info-circle me-1 text-muted"),
                            "Affects Contacts, Events, and trend chart. "
                            "Clear to show all time.",
                        ],
                        className="text-muted small",
                    ),
                    width="auto",
                    className="d-flex align-items-center ms-2",
                ),
            ],
            className="mb-4 align-items-center",
        ),

        # ── KPI cards ─────────────────────────────────────────────────────────
        dbc.Row(
            [
                # Registered Voters — demographic, not program-filtered
                dbc.Col(dbc.Card(dbc.CardBody([
                    html.I(className="bi bi-person-check fs-3 text-primary mb-1"),
                    html.H5("—", className="fw-bold mb-0", id="kpi-registered"),
                    html.Small("Total Registered Voters", className="text-muted"),
                ], className="text-center py-3"), className="shadow-sm h-100"), xs=6, md=3),

                # Unreliable Conservatives — demographic, not program-filtered
                dbc.Col(dbc.Card(dbc.CardBody([
                    html.I(className="bi bi-exclamation-triangle fs-3 text-warning mb-1"),
                    html.H5("—", className="fw-bold mb-0", id="kpi-unreliable"),
                    html.Small("Total Unreliable Conservatives", className="text-muted"),
                ], className="text-center py-3"), className="shadow-sm h-100"), xs=6, md=3),

                # Total Contacts — filtered by program and date range
                dbc.Col(dbc.Card(dbc.CardBody([
                    html.I(className="bi bi-telephone fs-3 text-success mb-1"),
                    html.H5("—", className="fw-bold mb-0", id="kpi-contacts"),
                    html.Small("Total Contacts", className="text-muted", id="kpi-contacts-label"),
                ], className="text-center py-3"), className="shadow-sm h-100"), xs=6, md=3),

                # Total Events — filtered by program and date range
                dbc.Col(dbc.Card(dbc.CardBody([
                    html.I(className="bi bi-calendar-event fs-3 text-info mb-1"),
                    html.H5("—", className="fw-bold mb-0", id="kpi-events"),
                    html.Small("Total Events", className="text-muted", id="kpi-events-label"),
                ], className="text-center py-3"), className="shadow-sm h-100"), xs=6, md=3),
            ],
            className="mb-4 g-3",
        ),

        # ── Charts row ────────────────────────────────────────────────────────
        dbc.Row(
            [
                # Program outreach comparison (grouped bar: BP vs CLP)
                dbc.Col(
                    dbc.Card(
                        [
                            dbc.CardHeader("BP vs CLP — Outreach Comparison"),
                            dbc.CardBody(
                                dcc.Loading(
                                    dcc.Graph(
                                        id="chart-program-comparison",
                                        config={"displayModeBar": False},
                                    ),
                                    type="circle", color="#0d6efd",
                                )
                            ),
                        ],
                        className="shadow-sm",
                    ),
                    md=6, className="mb-4",
                ),

                # Outreach trend over time (line, filtered by program)
                dbc.Col(
                    dbc.Card(
                        [
                            dbc.CardHeader("Outreach Trend Over Time"),
                            dbc.CardBody(
                                dcc.Loading(
                                    dcc.Graph(
                                        id="chart-trend",
                                        config={"displayModeBar": False},
                                    ),
                                    type="circle", color="#0d6efd",
                                )
                            ),
                        ],
                        className="shadow-sm",
                    ),
                    md=6, className="mb-4",
                ),
            ]
        ),

        # ── Detail table ──────────────────────────────────────────────────────
        dbc.Row(
            dbc.Col(
                dbc.Card(
                    [
                        dbc.CardHeader("Detail Records"),
                        dbc.CardBody(
                            dcc.Loading(
                                dash_table.DataTable(
                                    id="detail-table",
                                    columns=[],
                                    data=[],
                                    page_size=15,
                                    sort_action="native",
                                    filter_action="native",
                                    style_table={"overflowX": "auto"},
                                    style_header={
                                        "backgroundColor": "#f8f9fa",
                                        "fontWeight": "bold",
                                        "borderBottom": "2px solid #dee2e6",
                                    },
                                    style_cell={
                                        "fontFamily": "var(--bs-font-sans-serif)",
                                        "fontSize": "13px",
                                        "padding": "8px 12px",
                                        "border": "1px solid #dee2e6",
                                    },
                                    style_data_conditional=[
                                        {"if": {"row_index": "odd"}, "backgroundColor": "#f8f9fa"}
                                    ],
                                ),
                                type="circle", color="#0d6efd",
                            )
                        ),
                    ],
                    className="shadow-sm",
                ),
                width=12,
                className="mb-4",
            )
        ),

        # ── Election Performance Balance Sheet ───────────────────────────────
        dbc.Row(
            dbc.Col(
                dbc.Card(
                    [
                        dbc.CardHeader(
                            dbc.Row(
                                [
                                    dbc.Col(
                                        html.Span(
                                            "Election Performance",
                                            className="fw-semibold",
                                        ),
                                        width="auto",
                                    ),
                                    dbc.Col(
                                        html.Span(
                                            "Last 2 general election cycles",
                                            className="text-muted small",
                                        ),
                                        width="auto",
                                        className="ms-auto d-flex align-items-center",
                                    ),
                                ],
                                align="center",
                            )
                        ),
                        dbc.CardBody(
                            dbc.Table(
                                _election_balance_sheet(),
                                bordered=True,
                                hover=True,
                                responsive=True,
                                className="mb-0 election-table",
                            ),
                            className="p-0",
                        ),
                    ],
                    className="shadow-sm",
                ),
                width=12,
                className="mb-4",
            )
        ),

        # Status bar
        dbc.Row(
            dbc.Col(
                html.Div(id="analytics-status", className="text-muted small mb-3"),
                width=12,
            )
        ),
    ],
    fluid=True,
    className="px-4",
)


# ── Populate district dropdown on page load ───────────────────────────────────

@callback(
    Output("district-selector", "options"),
    Output("district-selector", "value"),
    Input("district-selector", "id"),
)
def load_district_options(_):
    try:
        options = get_district_list()
        default = options[0]["value"] if options else None
        return options, default
    except Exception as exc:
        print(f"[analytics] district list failed: {exc}", flush=True)
        return [], None


# ── Master callback ───────────────────────────────────────────────────────────
#
# Both slicers are Inputs — changing either rerenders every Output at once.
# To add another chart: add an Output, build the figure, append to the return.

@callback(
    Output("kpi-registered",          "children"),
    Output("kpi-unreliable",          "children"),
    Output("kpi-contacts",            "children"),
    Output("kpi-events",              "children"),
    Output("kpi-contacts-label",      "children"),
    Output("kpi-events-label",        "children"),
    Output("chart-program-comparison","figure"),
    Output("chart-trend",             "figure"),
    Output("detail-table",            "columns"),
    Output("detail-table",            "data"),
    Output("analytics-status",        "children"),
    Input("district-selector",        "value"),
    Input("program-selector",         "value"),
    Input("date-range",               "start_date"),
    Input("date-range",               "end_date"),
    Input("analytics-refresh-btn",    "n_clicks"),
)
def update_all(
    district_id: str | None,
    program: str,
    start_date: str | None,
    end_date: str | None,
    _,
):
    from data.queries import bust_cache

    if dash.callback_context.triggered_id == "analytics-refresh-btn":
        bust_cache()

    date_label = _fmt_date_range(start_date, end_date)
    contacts_label = f"Total Contacts · {date_label}"
    events_label   = f"Total Events · {date_label}"

    if not district_id:
        blank = _placeholder_fig("Select a district above")
        return "—", "—", "—", "—", contacts_label, events_label, blank, blank, [], [], ""

    try:
        demographics = get_district_demographics(district_id)
    except Exception as exc:
        print(f"[analytics] demographics failed: {exc}", flush=True)
        demographics = {}

    try:
        prog_totals = get_program_totals(district_id, program, start_date, end_date)
    except Exception as exc:
        print(f"[analytics] program totals failed: {exc}", flush=True)
        prog_totals = {}

    try:
        comparison = get_program_comparison(district_id, start_date, end_date)
    except Exception as exc:
        print(f"[analytics] comparison failed: {exc}", flush=True)
        comparison = pd.DataFrame(columns=["program", "contacts", "events"])

    try:
        trend = get_district_trend(district_id, program, start_date, end_date)
    except Exception as exc:
        print(f"[analytics] trend failed: {exc}", flush=True)
        trend = pd.DataFrame()

    try:
        detail = get_district_table(district_id)
    except Exception as exc:
        print(f"[analytics] detail table failed: {exc}", flush=True)
        detail = pd.DataFrame()

    # ── KPI values ────────────────────────────────────────────────────────────
    registered  = f"{_to_int(demographics.get('registered_voters')):,}"
    unreliable  = f"{_to_int(demographics.get('unreliable_conservatives')):,}"
    contacts    = f"{_to_int(prog_totals.get('total_contacts')):,}"
    events      = f"{_to_int(prog_totals.get('total_events')):,}"

    # ── Program comparison grouped bar ────────────────────────────────────────
    programs_to_show = ["BP", "CLP"] if program == "both" else [program]
    comp_fig = go.Figure()

    for prog in programs_to_show:
        row = comparison[comparison["program"] == prog]
        if row.empty:
            continue
        c_val = _to_int(row["contacts"].iloc[0])
        e_val = _to_int(row["events"].iloc[0])
        comp_fig.add_trace(
            go.Bar(
                name=prog,
                x=["Contacts", "Events"],
                y=[c_val, e_val],
                marker_color=PROGRAM_COLORS.get(prog, "#6c757d"),
                text=[f"{c_val:,}", f"{e_val:,}"],
                textposition="outside",
            )
        )

    comp_fig.update_layout(
        barmode="group",
        margin=dict(t=20, b=30, l=10, r=10),
        plot_bgcolor="white",
        paper_bgcolor="white",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        yaxis=dict(showgrid=True, gridcolor="#f0f0f0"),
        xaxis=dict(showgrid=False),
    )

    if comp_fig.data == ():
        comp_fig = _error_fig("No comparison data for this district.")

    # ── Trend line ────────────────────────────────────────────────────────────
    if trend.empty:
        trend_fig = _error_fig("No trend data for this selection.")
    else:
        trend_fig = go.Figure()
        # When "both" is selected, draw one line per program
        if "program" in trend.columns and program == "both":
            for prog in ["BP", "CLP"]:
                subset = trend[trend["program"] == prog]
                if not subset.empty:
                    trend_fig.add_trace(
                        go.Scatter(
                            x=subset["period"],
                            y=subset["metric_value"],
                            mode="lines+markers",
                            name=prog,
                            line=dict(color=PROGRAM_COLORS.get(prog, "#6c757d"), width=2),
                        )
                    )
        else:
            trend_fig.add_trace(
                go.Scatter(
                    x=trend["period"],
                    y=trend["metric_value"],
                    mode="lines+markers",
                    name=program.upper() if program != "both" else "Total",
                    line=dict(color="#0d6efd", width=2),
                )
            )
        trend_fig.update_layout(
            margin=dict(t=20, b=30, l=10, r=10),
            plot_bgcolor="white",
            paper_bgcolor="white",
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
            xaxis=dict(showgrid=False),
            yaxis=dict(showgrid=True, gridcolor="#f0f0f0"),
        )

    # ── Detail table ──────────────────────────────────────────────────────────
    if detail.empty:
        table_cols, table_data = [], []
    else:
        table_cols = [{"name": c, "id": c} for c in detail.columns]
        table_data = detail.to_dict("records")

    prog_label = program.upper() if program != "both" else "BP + CLP"
    status = f"District: {district_id} · Program: {prog_label} · {date_label} · {len(detail):,} records"
    return (
        registered, unreliable, contacts, events,
        contacts_label, events_label,
        comp_fig, trend_fig,
        table_cols, table_data,
        status,
    )


# ── Election balance sheet callback ──────────────────────────────────────────
#
# Responds to the district filter so the section clears/updates with every
# district change. All values are "—" stubs until election data is wired up.
#
# To add live data:
#   1. Write a query function in data/queries.py (e.g. get_election_stats).
#   2. Call it here with district_id.
#   3. Replace the "—" returns with the actual formatted values.

_ELECTION_CELL_IDS = [
    "el-overall-turnout-yr1",  "el-overall-turnout-yr2",
    "el-votes-cast-yr1",       "el-votes-cast-yr2",
    "el-registered-yr1",       "el-registered-yr2",
    "el-contacts-yr1",         "el-contacts-yr2",
    "el-individuals-yr1",      "el-individuals-yr2",
    "el-bp-contacts-yr1",      "el-bp-contacts-yr2",
    "el-clp-contacts-yr1",     "el-clp-contacts-yr2",
    "el-contacted-turnout-yr1","el-contacted-turnout-yr2",
    "el-lift-yr1",             "el-lift-yr2",
]

@callback(
    *[Output(cid, "children") for cid in _ELECTION_CELL_IDS],
    Input("district-selector",     "value"),
    Input("analytics-refresh-btn", "n_clicks"),
)
def update_election_section(district_id: str | None, _):
    blank = ("—",) * len(_ELECTION_CELL_IDS)

    if not district_id:
        return blank

    # TODO: replace stubs with live election data once queries are ready.
    # Example:
    #   stats = get_election_stats(district_id)   # returns dict keyed by yr1/yr2
    #   return (
    #       f"{stats['yr1']['overall_turnout']:.1f}%",
    #       f"{stats['yr2']['overall_turnout']:.1f}%",
    #       ...
    #   )
    return blank


# ── Figure helpers ────────────────────────────────────────────────────────────

def _placeholder_fig(message: str) -> go.Figure:
    fig = go.Figure()
    fig.add_annotation(
        text=message, x=0.5, y=0.5, xref="paper", yref="paper",
        showarrow=False, font=dict(size=14, color="#adb5bd"),
    )
    fig.update_layout(margin=dict(t=20, b=20, l=20, r=20),
                      plot_bgcolor="white", paper_bgcolor="white")
    return fig


def _error_fig(message: str) -> go.Figure:
    fig = go.Figure()
    fig.add_annotation(
        text=message, x=0.5, y=0.5, xref="paper", yref="paper",
        showarrow=False, font=dict(size=13, color="#dc3545"),
    )
    fig.update_layout(margin=dict(t=20, b=20, l=20, r=20),
                      plot_bgcolor="white", paper_bgcolor="white")
    return fig
