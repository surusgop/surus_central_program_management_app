"""
Analytics page — multiple charts driven by a single district slicer.

Pattern:
  One callback receives the district dropdown value as its single Input
  and returns figures/data for every chart on the page as Outputs.
  Selecting a district rerenders all charts simultaneously.

Adding more charts:
  1. Add an Output to the callback decorator.
  2. Return an additional figure/value at the end of the return tuple.
  3. Add the corresponding dcc.Graph (or other component) to the layout.
  That's it — no extra wiring needed.
"""

from __future__ import annotations

import dash
import dash_bootstrap_components as dbc
import plotly.express as px
import plotly.graph_objects as go
from dash import Input, Output, callback, dash_table, dcc, html

from data.queries import (
    get_district_breakdown,
    get_district_kpis,
    get_district_list,
    get_district_table,
    get_district_trend,
)

dash.register_page(
    __name__,
    path="/analytics",
    name="Analytics",
    title="Analytics | Surus Central",
)

# ── KPI card helper ───────────────────────────────────────────────────────────

def _kpi_card(title: str, value: str, icon: str, color: str = "primary") -> dbc.Col:
    return dbc.Col(
        dbc.Card(
            dbc.CardBody(
                [
                    html.Div(
                        html.I(className=f"bi {icon} fs-3 text-{color}"),
                        className="mb-1",
                    ),
                    html.H5(value, className="fw-bold mb-0", id=f"kpi-{title.lower().replace(' ', '-')}"),
                    html.Small(title, className="text-muted"),
                ],
                className="text-center py-3",
            ),
            className="shadow-sm h-100",
        ),
        xs=6, md=3,
    )


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

        # ── Page-level slicer ─────────────────────────────────────────────────
        # This single dropdown drives ALL charts below via one callback.
        dbc.Row(
            [
                dbc.Col(
                    html.Span("District:", className="fw-semibold me-2 align-middle"),
                    width="auto",
                    className="d-flex align-items-center",
                ),
                dbc.Col(
                    dcc.Dropdown(
                        id="district-selector",
                        options=[],          # populated on page load by a separate callback
                        placeholder="Select a district…",
                        clearable=False,
                        searchable=True,
                        style={"minWidth": "260px"},
                    ),
                    width="auto",
                ),
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

        # ── KPI cards ─────────────────────────────────────────────────────────
        dbc.Row(
            [
                dbc.Col(dbc.Card(dbc.CardBody([
                    html.I(className="bi bi-people fs-3 text-primary mb-1"),
                    html.H5("—", className="fw-bold mb-0", id="kpi-population"),
                    html.Small("Total Population", className="text-muted"),
                ], className="text-center py-3"), className="shadow-sm h-100"), xs=6, md=3),

                dbc.Col(dbc.Card(dbc.CardBody([
                    html.I(className="bi bi-cash-stack fs-3 text-success mb-1"),
                    html.H5("—", className="fw-bold mb-0", id="kpi-income"),
                    html.Small("Median Income", className="text-muted"),
                ], className="text-center py-3"), className="shadow-sm h-100"), xs=6, md=3),

                dbc.Col(dbc.Card(dbc.CardBody([
                    html.I(className="bi bi-check2-square fs-3 text-warning mb-1"),
                    html.H5("—", className="fw-bold mb-0", id="kpi-turnout"),
                    html.Small("Voter Turnout %", className="text-muted"),
                ], className="text-center py-3"), className="shadow-sm h-100"), xs=6, md=3),

                dbc.Col(dbc.Card(dbc.CardBody([
                    html.I(className="bi bi-person-check fs-3 text-info mb-1"),
                    html.H5("—", className="fw-bold mb-0", id="kpi-registered"),
                    html.Small("Registered Voters", className="text-muted"),
                ], className="text-center py-3"), className="shadow-sm h-100"), xs=6, md=3),
            ],
            className="mb-4 g-3",
        ),

        # ── Charts row — bar + trend line side by side ────────────────────────
        dbc.Row(
            [
                dbc.Col(
                    dbc.Card(
                        [
                            dbc.CardHeader("Category Breakdown"),
                            dbc.CardBody(
                                dcc.Loading(
                                    dcc.Graph(id="chart-bar", config={"displayModeBar": False}),
                                    type="circle", color="#0d6efd",
                                )
                            ),
                        ],
                        className="shadow-sm",
                    ),
                    md=6, className="mb-4",
                ),
                dbc.Col(
                    dbc.Card(
                        [
                            dbc.CardHeader("Trend Over Time"),
                            dbc.CardBody(
                                dcc.Loading(
                                    dcc.Graph(id="chart-trend", config={"displayModeBar": False}),
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
                                        {
                                            "if": {"row_index": "odd"},
                                            "backgroundColor": "#f8f9fa",
                                        }
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

        # Status bar
        dbc.Row(
            dbc.Col(html.Div(id="analytics-status", className="text-muted small mb-3"), width=12)
        ),
    ],
    fluid=True,
    className="px-4",
)


# ── Populate district dropdown on page load ───────────────────────────────────

@callback(
    Output("district-selector", "options"),
    Output("district-selector", "value"),
    Input("district-selector", "id"),   # fires once on mount
)
def load_district_options(_):
    try:
        options = get_district_list()
        default = options[0]["value"] if options else None
        return options, default
    except Exception:
        return [], None


# ── Master callback: one Input → every chart + KPI on the page ───────────────
#
# To add another chart:
#   1. Add Output("your-new-chart-id", "figure") to the decorator.
#   2. Build and return the new figure at the end of the return tuple.
#   3. Add the corresponding dcc.Graph to the layout above.

@callback(
    Output("kpi-population",  "children"),
    Output("kpi-income",      "children"),
    Output("kpi-turnout",     "children"),
    Output("kpi-registered",  "children"),
    Output("chart-bar",       "figure"),
    Output("chart-trend",     "figure"),
    Output("detail-table",    "columns"),
    Output("detail-table",    "data"),
    Output("analytics-status","children"),
    Input("district-selector",       "value"),
    Input("analytics-refresh-btn",   "n_clicks"),
)
def update_all(district_id: str | None, _refresh):
    from data.queries import bust_cache

    if dash.callback_context.triggered_id == "analytics-refresh-btn":
        bust_cache()

    # Nothing selected yet — return blank state
    if not district_id:
        blank = go.Figure()
        blank.update_layout(
            annotations=[dict(text="Select a district above", x=0.5, y=0.5,
                              xref="paper", yref="paper", showarrow=False,
                              font=dict(color="#adb5bd", size=14))],
            margin=dict(t=20, b=20, l=20, r=20),
        )
        return "—", "—", "—", "—", blank, blank, [], [], ""

    # ── Fetch all data ────────────────────────────────────────────────────────
    try:
        kpis      = get_district_kpis(district_id)
        breakdown = get_district_breakdown(district_id)
        trend     = get_district_trend(district_id)
        detail    = get_district_table(district_id)
    except Exception as exc:
        blank = _error_fig(str(exc))
        return "Err", "Err", "Err", "Err", blank, blank, [], [], f"Error: {exc}"

    # ── KPI values ────────────────────────────────────────────────────────────
    pop       = f"{int(kpis.get('total_population', 0)):,}"
    income    = f"${int(kpis.get('median_income', 0)):,}"
    turnout   = f"{kpis.get('voter_turnout_pct', 0):.1f}%"
    registered = f"{int(kpis.get('registered_voters', 0)):,}"

    # ── Bar chart: category breakdown ─────────────────────────────────────────
    if breakdown.empty:
        bar_fig = _error_fig("No breakdown data for this district.")
    else:
        bar_fig = px.bar(
            breakdown,
            x="value",
            y="category",
            orientation="h",
            color="value",
            color_continuous_scale="Blues",
            labels={"value": "Value", "category": ""},
        )
        bar_fig.update_layout(
            coloraxis_showscale=False,
            margin=dict(t=10, b=30, l=10, r=10),
            yaxis=dict(categoryorder="total ascending"),
            plot_bgcolor="white",
            paper_bgcolor="white",
        )
        bar_fig.update_xaxes(showgrid=True, gridcolor="#f0f0f0")
        bar_fig.update_yaxes(showgrid=False)

    # ── Line chart: trend over time ───────────────────────────────────────────
    if trend.empty:
        trend_fig = _error_fig("No trend data for this district.")
    else:
        trend_fig = px.line(
            trend,
            x="period",
            y="metric_value",
            markers=True,
            labels={"period": "", "metric_value": "Value"},
        )
        trend_fig.update_traces(line_color="#0d6efd", line_width=2)
        trend_fig.update_layout(
            margin=dict(t=10, b=30, l=10, r=10),
            plot_bgcolor="white",
            paper_bgcolor="white",
        )
        trend_fig.update_xaxes(showgrid=False)
        trend_fig.update_yaxes(showgrid=True, gridcolor="#f0f0f0")

    # ── Data table ────────────────────────────────────────────────────────────
    if detail.empty:
        table_cols, table_data = [], []
    else:
        table_cols = [{"name": c, "id": c} for c in detail.columns]
        table_data = detail.to_dict("records")

    status = f"District: {district_id} · {len(detail):,} records"
    return pop, income, turnout, registered, bar_fig, trend_fig, table_cols, table_data, status


def _error_fig(message: str) -> go.Figure:
    fig = go.Figure()
    fig.add_annotation(
        text=message, x=0.5, y=0.5, xref="paper", yref="paper",
        showarrow=False, font=dict(size=13, color="#dc3545"),
    )
    fig.update_layout(margin=dict(t=20, b=20, l=20, r=20))
    return fig
