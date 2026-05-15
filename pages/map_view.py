"""
District heatmap page with swappable metric variable slicer.

GeoJSON setup:
  Place your district boundary file at geojson/districts.geojson.
  Each feature must have a property whose value matches the district_id
  column returned by your Databricks queries.
  Set GEOJSON_ID_PROPERTY below to that property name (default: "id").
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import dash
import dash_bootstrap_components as dbc
import plotly.graph_objects as go
from dash import Input, Output, callback, dcc, html

from data.queries import HEATMAP_VARIABLES, get_district_metric

dash.register_page(__name__, path="/map", name="Map", title="District Map | Surus Central")

# ── GeoJSON config ────────────────────────────────────────────────────────────

GEOJSON_PATH = Path(__file__).parent.parent / "geojson" / "districts.geojson"
GEOJSON_ID_PROPERTY = "id"  # ← set to the feature property that equals district_id

_geojson_cache: dict | None = None


def _load_geojson() -> dict | None:
    global _geojson_cache
    if _geojson_cache is None and GEOJSON_PATH.exists():
        with open(GEOJSON_PATH) as f:
            _geojson_cache = json.load(f)
    return _geojson_cache


# ── Map defaults ──────────────────────────────────────────────────────────────

MAPBOX_TOKEN = os.environ.get("MAPBOX_TOKEN", "")
DEFAULT_METRIC = list(HEATMAP_VARIABLES.keys())[0]

MAP_CENTER = {"lat": 38.0, "lon": -97.0}   # ← set to your district region center
MAP_ZOOM = 5                                # ← adjust to fit your boundaries

COLORSCALE = "Viridis"  # any Plotly colorscale: "Blues", "RdYlGn", "Plasma", etc.

# ── Layout ────────────────────────────────────────────────────────────────────

layout = dbc.Container(
    [
        # Page header
        dbc.Row(
            dbc.Col(
                html.H4("District Map", className="my-3 fw-semibold text-primary"),
                width=12,
            )
        ),

        # Variable slicer (button-style radio)
        dbc.Row(
            [
                dbc.Col(
                    html.Span("View by:", className="fw-semibold me-2 align-middle"),
                    width="auto",
                    className="d-flex align-items-center",
                ),
                dbc.Col(
                    dbc.RadioItems(
                        id="heatmap-variable",
                        options=[
                            {"label": label, "value": key}
                            for key, label in HEATMAP_VARIABLES.items()
                        ],
                        value=DEFAULT_METRIC,
                        inline=True,
                        inputStyle={"display": "none"},
                        labelClassName="btn btn-outline-primary btn-sm me-1",
                        labelCheckedClassName="btn btn-primary btn-sm me-1",
                    ),
                    width="auto",
                ),
                dbc.Col(
                    dbc.Button(
                        [html.I(className="bi bi-arrow-clockwise me-1"), "Refresh"],
                        id="refresh-btn",
                        color="secondary",
                        outline=True,
                        size="sm",
                    ),
                    width="auto",
                    className="ms-auto",
                ),
            ],
            className="mb-3 align-items-center",
        ),

        # Map + loading wrapper
        dbc.Row(
            dbc.Col(
                dcc.Loading(
                    dcc.Graph(
                        id="district-map",
                        config={"scrollZoom": True, "displayModeBar": True},
                        style={"height": "72vh"},
                    ),
                    type="circle",
                    color="#0d6efd",
                ),
                width=12,
            )
        ),

        # Status / error message area
        dbc.Row(
            dbc.Col(html.Div(id="map-status", className="text-muted small mt-2"), width=12)
        ),
    ],
    fluid=True,
    className="px-4",
)


# ── Callback ──────────────────────────────────────────────────────────────────

@callback(
    Output("district-map", "figure"),
    Output("map-status", "children"),
    Input("heatmap-variable", "value"),
    Input("refresh-btn", "n_clicks"),
)
def update_map(metric: str, _refresh_clicks):
    from data.queries import bust_cache

    triggered = dash.callback_context.triggered_id
    if triggered == "refresh-btn":
        bust_cache()

    geojson = _load_geojson()

    if geojson is None:
        fig = _empty_map("No district GeoJSON found. See geojson/README.md.")
        return fig, "Place your GeoJSON at geojson/districts.geojson to enable the map."

    try:
        df = get_district_metric(metric)
    except Exception as exc:
        fig = _empty_map(str(exc))
        return fig, f"Query error: {exc}"

    metric_label = HEATMAP_VARIABLES.get(metric, metric)

    fig = go.Figure(
        go.Choroplethmapbox(
            geojson=geojson,
            locations=df["district_id"],
            z=df["metric_value"],
            featureidkey=f"properties.{GEOJSON_ID_PROPERTY}",
            colorscale=COLORSCALE,
            colorbar=dict(
                title=dict(text=metric_label, side="right"),
                thickness=14,
                len=0.6,
            ),
            marker_opacity=0.75,
            marker_line_width=1.2,
            marker_line_color="white",
            hovertemplate=(
                "<b>District %{location}</b><br>"
                f"{metric_label}: %{{z:,.1f}}<extra></extra>"
            ),
        )
    )

    fig.update_layout(
        mapbox=dict(
            accesstoken=MAPBOX_TOKEN,
            style="carto-positron",
            center=MAP_CENTER,
            zoom=MAP_ZOOM,
        ),
        margin={"r": 0, "t": 0, "l": 0, "b": 0},
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
    )

    n = len(df)
    return fig, f"Showing {n:,} districts · {metric_label}"


def _empty_map(message: str) -> go.Figure:
    fig = go.Figure()
    fig.add_annotation(
        text=message,
        xref="paper", yref="paper",
        x=0.5, y=0.5,
        showarrow=False,
        font=dict(size=14, color="#6c757d"),
    )
    fig.update_layout(
        mapbox=dict(
            accesstoken=MAPBOX_TOKEN,
            style="carto-positron",
            center=MAP_CENTER,
            zoom=MAP_ZOOM,
        ),
        margin={"r": 0, "t": 0, "l": 0, "b": 0},
    )
    return fig
