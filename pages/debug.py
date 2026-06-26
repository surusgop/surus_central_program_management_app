"""
Debug — raw dump of universal.bitables.contact_analysis_dash (no filters).
"""

from __future__ import annotations

import dash
import dash_ag_grid as dag
import dash_bootstrap_components as dbc
from dash import Input, Output, callback, dcc, html

dash.register_page(
    __name__,
    path="/debug",
    name="Debug",
    title="Debug | Surus Central Program Management",
)

_NUM = {"function": "params.value == null ? '—' : params.value.toLocaleString()"}
_DATE = {"function": "params.value ? new Date(params.value).toLocaleDateString() : '—'"}

COLUMN_DEFS = [
    {"headerName": "State",  "field": "state",      "width": 130, "cellStyle": {"fontWeight": "600"}},
    {"headerName": "Group",  "field": "group",      "width": 120},
    {"headerName": "Nation", "field": "nation",     "width": 180},
    {"headerName": "Week",   "field": "week_start", "valueFormatter": _DATE, "width": 130},
    {"headerName": "Total Contacts",  "field": "total_contacts",  "valueFormatter": _NUM, "type": "numericColumn", "flex": 1},
    {"headerName": "Unique Contacts", "field": "unique_contacts", "valueFormatter": _NUM, "type": "numericColumn", "flex": 1},
    {"headerName": "Total Events",    "field": "total_events",    "valueFormatter": _NUM, "type": "numericColumn", "flex": 1},
]

layout = dbc.Container(
    [
        dbc.Row(
            dbc.Col(
                html.H4("Debug — Raw Table Data", className="my-3 brand-title"),
                width=12,
            )
        ),

        dbc.Row(
            dbc.Col(
                dbc.Card(
                    [
                        dbc.CardHeader("universal.bitables.contact_analysis_dash — AG Grid, no dcc.Loading"),
                        dbc.CardBody(
                            dcc.Loading(
                                dag.AgGrid(
                                    id="debug-grid",
                                    columnDefs=COLUMN_DEFS,
                                    rowData=[],
                                    defaultColDef={"resizable": True, "sortable": True, "minWidth": 100},
                                    dashGridOptions={"domLayout": "autoHeight", "suppressMovableColumns": True},
                                    style={"width": "100%"},
                                    className="ag-theme-alpine",
                                ),
                                target_components={"debug-grid": "rowData"},
                                type="circle",
                                color="#C1272D",
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

        dbc.Row(
            dbc.Col(
                html.Div(id="debug-status", className="text-muted small mb-3"),
                width=12,
            )
        ),
        dcc.Interval(id="debug-init", interval=1, max_intervals=1, n_intervals=0),
    ],
    fluid=True,
    className="px-4",
)

_STUB_ROWS = [
    {"state": "IL", "group": "BP", "nation": "Stub Nation A", "week_start": "2024-01-07",
     "total_contacts": 120, "unique_contacts": 95, "total_events": 4},
    {"state": "IL", "group": "CLP", "nation": "Stub Nation B", "week_start": "2024-01-14",
     "total_contacts": 87, "unique_contacts": 70, "total_events": 2},
]


@callback(
    Output("debug-grid",   "rowData"),
    Output("debug-status", "children"),
    Input("debug-init",    "n_intervals"),
)
def load_table(_):
    return _STUB_ROWS, f"{len(_STUB_ROWS):,} rows (stub — no dcc.Loading)"
