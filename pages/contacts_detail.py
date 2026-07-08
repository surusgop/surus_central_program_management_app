"""
Contacts Detail — full weekly grid broken down by state, nation, and group.
"""

from __future__ import annotations

import sys
import traceback

import dash
import dash_ag_grid as dag
import dash_bootstrap_components as dbc
from dash import Input, Output, callback, ctx, dcc, html

from data.queries import get_contact_summary, get_group_list, get_nation_list_filtered, get_state_list

dash.register_page(
    __name__,
    path="/contacts",
    name="Contacts Detail",
    title="Contacts Detail | Central Program Management",
)

# ── Column definitions ────────────────────────────────────────────────────────

_NUM  = {"function": "params.value == null ? '—' : params.value.toLocaleString()"}
_DATE = {"function": "params.value ? new Date(params.value).toLocaleDateString() : '—'"}


def _num_col(header: str, field: str) -> dict:
    return {"headerName": header, "field": field, "valueFormatter": _NUM,
            "type": "numericColumn", "flex": 1, "minWidth": 120}


COLUMN_DEFS = [
    {
        "headerName": "State",
        "field": "state",
        "pinned": "left",
        "width": 130,
        "cellStyle": {"fontWeight": "600"},
        "suppressSizeToFit": True,
    },
    {"headerName": "Group",  "field": "group",     "width": 120},
    {"headerName": "Nation", "field": "nation",     "width": 180},
    {"headerName": "Week",   "field": "week_start", "valueFormatter": _DATE, "width": 130},
    _num_col("Total Contacts",   "total_contacts"),
    _num_col("Unique Contacts",  "unique_contacts"),
    _num_col("Door Knock",       "contact_door_knock"),
    _num_col("Email",            "contact_email"),
    _num_col("Phone",            "contact_phone"),
    _num_col("Text",             "contact_text"),
    _num_col("Snail Mail",       "contact_snail_mail"),
    _num_col("Face to Face",     "contact_face_to_face"),
    _num_col("Other",            "contact_other"),
    _num_col("Total Events",     "total_events"),
]

DEFAULT_COL_DEF = {
    "resizable": True,
    "sortable": True,
    "minWidth": 100,
}

# ── Layout ────────────────────────────────────────────────────────────────────

layout = dbc.Container(
    [
        dbc.Row(
            dbc.Col(
                html.H4("Contacts Detail", className="my-3 brand-title"),
                width=12,
            )
        ),

        # ── Filters ───────────────────────────────────────────────────────────
        dbc.Row(
            [
                dbc.Col(
                    [
                        dbc.Label("State", html_for="cd-state-selector",
                                  className="fw-semibold small mb-1"),
                        dcc.Dropdown(
                            id="cd-state-selector",
                            options=[],
                            placeholder="All states…",
                            multi=True,
                            clearable=True,
                            searchable=True,
                        ),
                    ],
                    xs=12, sm=6, lg=4, className="mb-3",
                ),
                dbc.Col(
                    [
                        dbc.Label("Nation", html_for="cd-nation-selector",
                                  className="fw-semibold small mb-1"),
                        dcc.Dropdown(
                            id="cd-nation-selector",
                            options=[],
                            placeholder="All nations…",
                            multi=True,
                            clearable=True,
                            searchable=True,
                        ),
                    ],
                    xs=12, sm=6, lg=4, className="mb-3",
                ),
                dbc.Col(
                    [
                        dbc.Label("Group", html_for="cd-group-selector",
                                  className="fw-semibold small mb-1"),
                        dcc.Dropdown(
                            id="cd-group-selector",
                            options=[],
                            placeholder="All groups…",
                            multi=True,
                            clearable=True,
                            searchable=True,
                        ),
                    ],
                    xs=12, sm=6, lg=4, className="mb-3",
                ),
            ],
            className="mb-2 align-items-end",
        ),

        # ── Grid ──────────────────────────────────────────────────────────────
        dbc.Row(
            dbc.Col(
                dbc.Card(
                    [
                        dbc.CardHeader("Contacts by State, Nation & Group"),
                        dbc.CardBody(
                            dcc.Loading(
                                dag.AgGrid(
                                    id="cd-grid",
                                    columnDefs=COLUMN_DEFS,
                                    rowData=[],
                                    defaultColDef=DEFAULT_COL_DEF,
                                    dashGridOptions={
                                        "domLayout": "autoHeight",
                                        "suppressMovableColumns": True,
                                        "headerHeight": 36,
                                    },
                                    style={"width": "100%"},
                                    className="ag-theme-alpine",
                                ),
                                target_components={"cd-grid": "rowData"},
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
                html.Div(id="cd-status", className="text-muted small mb-3"),
                width=12,
            )
        ),

        dcc.Interval(id="cd-init", interval=1, max_intervals=1, n_intervals=0),
    ],
    fluid=True,
    className="px-4",
)


# ── Load filter options on page mount ─────────────────────────────────────────

@callback(
    Output("cd-state-selector", "options"),
    Output("cd-group-selector", "options"),
    Input("cd-init",            "n_intervals"),
)
def load_filter_options(_):
    print("[contacts-detail] load_filter_options fired", file=sys.stderr, flush=True)
    try:
        states = get_state_list()
        groups = get_group_list()
        return states, groups
    except Exception:
        print(f"[contacts-detail] load_filter_options FAILED:\n{traceback.format_exc()}", file=sys.stderr, flush=True)
        return [], []


@callback(
    Output("cd-nation-selector", "options"),
    Input("cd-state-selector",   "value"),
    Input("cd-group-selector",   "value"),
)
def update_nation_options(states, groups):
    try:
        return get_nation_list_filtered(states or [], groups or [])
    except Exception:
        print(f"[contacts-detail] update_nation_options FAILED:\n{traceback.format_exc()}", file=sys.stderr, flush=True)
        return []


# ── Main callback ─────────────────────────────────────────────────────────────

@callback(
    Output("cd-grid",   "rowData"),
    Output("cd-status", "children"),
    Input("cd-state-selector",  "value"),
    Input("cd-nation-selector", "value"),
    Input("cd-group-selector",  "value"),
)
def update_grid(states, nations, groups):
    triggered = ctx.triggered_id or "initial"
    print(f"[contacts-detail] update_grid triggered_by={triggered!r}", file=sys.stderr, flush=True)
    try:
        df = get_contact_summary(
            state_ids=states  or [],
            nation_ids=nations or [],
            group_ids=groups  or [],
        )
        row_data = df.to_dict("records")
        print(f"[contacts-detail] update_grid → {len(row_data)} rows", file=sys.stderr, flush=True)
    except Exception:
        print(f"[contacts-detail] update_grid FAILED:\n{traceback.format_exc()}", file=sys.stderr, flush=True)
        row_data = []

    parts = [
        ", ".join(sorted(states))  if states  else "All states",
        ", ".join(sorted(nations)) if nations else "All nations",
        ", ".join(sorted(groups))  if groups  else "All groups",
    ]
    return row_data, " · ".join(parts)
