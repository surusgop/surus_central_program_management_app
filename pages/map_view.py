"""
Map — voter contact pins color-coded by contact count, with optional district boundaries.
Filters: State, Nation, Group (multi-select) + Date Range.
"""

from __future__ import annotations

import json
import sys
import traceback
from datetime import date

import dash
import dash_bootstrap_components as dbc
import pandas as pd
import plotly.graph_objects as go
from dash import Input, Output, callback, ctx, dcc, html

from data.queries import get_boundaries, get_group_list, get_nation_list_filtered, get_state_list, get_voter_map_data

dash.register_page(
    __name__,
    path="/map",
    name="Map",
    title="Map | Surus Central Program Management",
)

# ── Boundary layer options ────────────────────────────────────────────────────

BOUNDARY_LAYERS = [
    {"label": "None",                                 "value": "none"},
    {"label": "County",                               "value": "county"},
    {"label": "State",                                "value": "state"},
    {"label": "Congressional District (119th)",       "value": "cd119"},
    {"label": "State Senate District",                "value": "sldu"},
    {"label": "State House District",                 "value": "sldl"},
    {"label": "Census Tract",                         "value": "tract"},
    {"label": "Block Group",                          "value": "bg"},
    {"label": "Place / City",                         "value": "place"},
    {"label": "County Subdivision",                   "value": "cousub"},
    {"label": "Metro Area (CBSA)",                    "value": "cbsa"},
    {"label": "Combined Statistical Area",            "value": "csa"},
    {"label": "Metropolitan Division",                "value": "metdiv"},
    {"label": "Census Region",                        "value": "region"},
    {"label": "Census Division",                      "value": "division"},
    {"label": "Unified School District",              "value": "unsd"},
    {"label": "Elementary School District",           "value": "elsd"},
    {"label": "Secondary School District",            "value": "scsd"},
    {"label": "Am. Indian / Alaska Native / NH Area", "value": "aiannh"},
    {"label": "Am. Indian Tribal Subdivision",        "value": "aitsn"},
    {"label": "Alaska Native Regional Corp.",         "value": "anrc"},
    {"label": "Tribal Block Group",                   "value": "tbg"},
    {"label": "Tribal Census Tract",                  "value": "ttract"},
    {"label": "Consolidated City",                    "value": "concity"},
    {"label": "Estate (USVI)",                        "value": "estate"},
    {"label": "Subbarrio (Puerto Rico)",              "value": "subbarrio"},
    {"label": "County within Cong. District",         "value": "county_within_cd119"},
]

_BOUNDARY_LABEL = {opt["value"]: opt["label"] for opt in BOUNDARY_LAYERS}

# ── Pin bucket config: (min_count, max_count, color, label) ──────────────────
# max_count=None means "or more"

BUCKETS = [
    (1, 1,    "#4FC3F7", "1 Contact"),
    (2, 2,    "#81C784", "2 Contacts"),
    (3, 3,    "#FFB74D", "3 Contacts"),
    (4, None, "#C1272D", "4+ Contacts"),
]

# ── Helpers ───────────────────────────────────────────────────────────────────

def _border_trace(geo_df, label: str = "Boundaries") -> go.Scattermapbox:
    """Build a single border trace from a county boundaries DataFrame.
    Each row's geometry_geojson is a GeoJSON geometry string (Polygon or MultiPolygon).
    """
    lats, lons = [], []
    for geojson_str in geo_df["geometry_geojson"]:
        try:
            geom = json.loads(geojson_str)
        except (json.JSONDecodeError, TypeError):
            continue
        gtype = geom.get("type", "")
        coords = geom.get("coordinates", [])
        polys = coords if gtype == "MultiPolygon" else [coords]
        for poly in polys:
            for ring in poly:
                for lon, lat in ring:
                    lons.append(lon)
                    lats.append(lat)
                lons.append(None)
                lats.append(None)
    return go.Scattermapbox(
        lat=lats,
        lon=lons,
        mode="lines",
        line=dict(width=1, color="#2A313C"),
        hoverinfo="skip",
        showlegend=False,
        name=label,
    )


def _assign_voters_to_counties(voters_df: pd.DataFrame, county_df: pd.DataFrame) -> pd.DataFrame:
    """Vectorized point-in-polygon join — returns per-county voter aggregation."""
    try:
        import numpy as np
        from shapely import points as shp_points
        from shapely.geometry import shape
        from shapely.strtree import STRtree
        print("[map] shapely OK", file=sys.stderr, flush=True)
    except ImportError as exc:
        print(f"[map] shapely unavailable: {exc}", file=sys.stderr, flush=True)
        return pd.DataFrame()

    try:
        geom_list, geoid_list, name_list, state_list = [], [], [], []
        for _, row in county_df.iterrows():
            try:
                geom_list.append(shape(json.loads(row["geometry_geojson"])))
                geoid_list.append(str(row["geoid"]))
                name_list.append(row["name"])
                state_list.append(row["state_name"])
            except Exception:
                continue

        print(f"[map] county geoms parsed: {len(geom_list)}", file=sys.stderr, flush=True)
        if not geom_list:
            return pd.DataFrame()

        lngs = voters_df["lng"].to_numpy(dtype=float)
        lats = voters_df["lat"].to_numpy(dtype=float)
        valid = ~(np.isnan(lngs) | np.isnan(lats))
        lngs, lats = lngs[valid], lats[valid]
        orig_indices = np.where(valid)[0]
        print(f"[map] voter points: {len(lngs)} valid of {len(voters_df)}", file=sys.stderr, flush=True)

        if len(lngs) == 0:
            return pd.DataFrame()

        voter_pts = shp_points(np.column_stack([lngs, lats]))
        tree = STRtree(geom_list)
        result = tree.query(voter_pts, predicate="intersects")
        print(f"[map] STRtree result shape: {result.shape}", file=sys.stderr, flush=True)

        if result.size == 0:
            return pd.DataFrame()

        pt_idx = result[0]
        co_idx = result[1]

        voters_reset = voters_df.reset_index(drop=True)
        county_stats: dict[int, dict] = {}
        seen_voters: set[int] = set()

        for pi, ci in zip(pt_idx.tolist(), co_idx.tolist()):
            orig_vi = int(orig_indices[pi])
            if orig_vi in seen_voters:
                continue
            seen_voters.add(orig_vi)
            if ci not in county_stats:
                county_stats[ci] = {
                    "geoid": geoid_list[ci],
                    "name": name_list[ci],
                    "state_name": state_list[ci],
                    "unique_voters": 0,
                    "total_contacts": 0,
                    "bucket_1": 0,
                    "bucket_2": 0,
                    "bucket_3": 0,
                    "bucket_4plus": 0,
                }
            s = county_stats[ci]
            s["unique_voters"] += 1
            cnt = int(voters_reset.at[orig_vi, "contact_count"])
            s["total_contacts"] += cnt
            if cnt == 1:
                s["bucket_1"] += 1
            elif cnt == 2:
                s["bucket_2"] += 1
            elif cnt == 3:
                s["bucket_3"] += 1
            else:
                s["bucket_4plus"] += 1

        print(f"[map] county_stats: {len(county_stats)} counties matched", file=sys.stderr, flush=True)
        return pd.DataFrame(list(county_stats.values())) if county_stats else pd.DataFrame()

    except Exception:
        print(f"[map] _assign_voters_to_counties FAILED:\n{traceback.format_exc()}", file=sys.stderr, flush=True)
        return pd.DataFrame()


def _choropleth_trace(county_df: pd.DataFrame, stats_df: pd.DataFrame) -> go.Choroplethmapbox:
    """Choropleth fill colored by unique voter count per county."""
    features = []
    for _, row in county_df.iterrows():
        try:
            geom = json.loads(row["geometry_geojson"])
        except (json.JSONDecodeError, TypeError):
            continue
        features.append({
            "type": "Feature",
            "id": str(row["geoid"]),
            "properties": {"name": row["name"]},
            "geometry": geom,
        })

    geojson_fc = {"type": "FeatureCollection", "features": features}
    max_val = max(int(stats_df["unique_voters"].max()), 1)

    return go.Choroplethmapbox(
        geojson=geojson_fc,
        locations=stats_df["geoid"].astype(str).tolist(),
        z=stats_df["unique_voters"].tolist(),
        colorscale=[[0, "#FFF7ED"], [0.5, "#FFB74D"], [1, "#C1272D"]],
        zmin=0,
        zmax=max_val,
        marker_opacity=0.5,
        marker_line_width=1,
        marker_line_color="#2A313C",
        customdata=stats_df.assign(
            name=stats_df["name"].fillna(""),
            state_name=stats_df["state_name"].fillna("").apply(
                lambda s: f", {s}" if s else ""
            ),
        )[["name", "state_name", "unique_voters", "total_contacts",
           "bucket_1", "bucket_2", "bucket_3", "bucket_4plus"]].values.tolist(),
        hovertemplate=(
            "<b>%{customdata[0]}%{customdata[1]}</b><br>"
            "Unique Contacted Voters: %{customdata[2]:,}<br>"
            "Total Contacts: %{customdata[3]:,}<br>"
            "<i>Click for details</i>"
            "<extra></extra>"
        ),
        showscale=False,
        name="Voter Density",
    )


def _empty_map(message: str = "No data for this selection.", geo_df=None) -> go.Figure:
    fig = go.Figure()
    if geo_df is not None and not geo_df.empty:
        fig.add_trace(_border_trace(geo_df))
    fig.update_layout(
        mapbox=dict(style="carto-positron", zoom=7, center=dict(lat=41.88, lon=-88.0)),
        margin=dict(t=0, b=0, l=0, r=0),
        paper_bgcolor="rgba(0,0,0,0)",
        height=600,
    )
    fig.add_annotation(
        text=message,
        x=0.5, y=0.5, xref="paper", yref="paper",
        showarrow=False,
        font=dict(size=14, color="#75859E"),
        bgcolor="rgba(255,255,255,0.75)",
        borderpad=8,
    )
    return fig


def _status_parts(states, nations, groups, start_date, end_date) -> list[str]:
    parts = [
        ", ".join(sorted(states))  if states  else "All states",
        ", ".join(sorted(nations)) if nations else "All nations",
        ", ".join(sorted(groups))  if groups  else "All groups",
    ]
    if start_date or end_date:
        parts.append(
            f"{start_date[:10] if start_date else '…'} → {end_date[:10] if end_date else '…'}"
        )
    return parts


# ── Layout ────────────────────────────────────────────────────────────────────

layout = dbc.Container(
    [
        dbc.Row(
            dbc.Col(
                html.H4("Contact Map", className="my-3 brand-title"),
                width=12,
            )
        ),

        # ── Filters ───────────────────────────────────────────────────────────
        dbc.Row(
            [
                dbc.Col(
                    [
                        dbc.Label("State", className="fw-semibold small mb-1"),
                        dcc.Dropdown(
                            id="map-state-selector",
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
                            id="map-nation-selector",
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
                            id="map-group-selector",
                            options=[],
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
                            id="map-date-range",
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

        # ── Boundary layer selector + pins toggle ─────────────────────────────
        dbc.Row(
            [
                dbc.Col(
                    [
                        dbc.Label("Boundary Layer", className="fw-semibold small mb-1"),
                        dcc.Dropdown(
                            id="map-boundary-selector",
                            options=BOUNDARY_LAYERS,
                            value="none",
                            clearable=False,
                        ),
                    ],
                    xs=12, sm=6, lg=3, className="mb-3",
                ),
                dbc.Col(
                    dbc.Switch(
                        id="map-pins-toggle",
                        label="Show Pins",
                        value=True,
                        className="mt-4 pt-1",
                    ),
                    xs=12, sm=6, lg=3, className="mb-3",
                ),
            ],
            className="mb-2 align-items-end",
        ),

        # ── Map ───────────────────────────────────────────────────────────────
        dbc.Row(
            dbc.Col(
                dbc.Card(
                    dbc.CardBody(
                        dcc.Loading(
                            dcc.Graph(
                                id="map-voter-pins",
                                config={"displayModeBar": True, "scrollZoom": True},
                                style={"height": "600px"},
                            ),
                            target_components={"map-voter-pins": "figure"},
                            custom_spinner=html.Div(
                                [
                                    dbc.Spinner(color="#C1272D", size="lg"),
                                    html.Div(
                                        id="map-spinner-label",
                                        className="text-muted small mt-2 text-center",
                                    ),
                                ],
                                className="d-flex flex-column align-items-center py-5",
                            ),
                            overlay_style={
                                "visibility": "visible",
                                "opacity": 0.9,
                                "backgroundColor": "white",
                            },
                        ),
                        className="p-0",
                    ),
                    className="border-0",
                ),
                width=12,
                className="mb-4",
            )
        ),

        # ── Status ────────────────────────────────────────────────────────────
        dbc.Row(
            dbc.Col(
                html.Div(id="map-status", className="text-muted small mb-3"),
                width=12,
            )
        ),

        dcc.Interval(id="map-init", interval=1, max_intervals=1, n_intervals=0),

        # ── County detail modal ───────────────────────────────────────────────
        dbc.Modal(
            [
                dbc.ModalHeader(
                    [
                        dbc.ModalTitle(id="county-modal-title"),
                        dbc.Button(
                            "×",
                            id="county-modal-close",
                            className="btn-close ms-auto",
                            n_clicks=0,
                        ),
                    ],
                    className="d-flex align-items-center",
                    close_button=False,
                ),
                dbc.ModalBody(id="county-modal-body"),
            ],
            id="county-modal",
            is_open=False,
            size="md",
            backdrop=True,
            scrollable=False,
        ),
    ],
    fluid=True,
    className="px-4",
)


# ── Load filter options on page mount ─────────────────────────────────────────

@callback(
    Output("map-state-selector", "options"),
    Output("map-group-selector", "options"),
    Input("map-init",            "n_intervals"),
)
def load_filter_options(_):
    print("[map] load_filter_options fired", file=sys.stderr, flush=True)
    try:
        states = get_state_list()
        groups = get_group_list()
        return states, groups
    except Exception:
        print(f"[map] load_filter_options FAILED:\n{traceback.format_exc()}", file=sys.stderr, flush=True)
        return [], []


@callback(
    Output("map-nation-selector", "options"),
    Input("map-state-selector",   "value"),
    Input("map-group-selector",   "value"),
)
def update_nation_options(states, groups):
    try:
        return get_nation_list_filtered(states or [], groups or [])
    except Exception:
        print(f"[map] update_nation_options FAILED:\n{traceback.format_exc()}", file=sys.stderr, flush=True)
        return []


# ── Spinner label (fast — no DB) ──────────────────────────────────────────────

@callback(
    Output("map-spinner-label", "children"),
    Input("map-state-selector",    "value"),
    Input("map-nation-selector",   "value"),
    Input("map-group-selector",    "value"),
    Input("map-date-range",        "start_date"),
    Input("map-date-range",        "end_date"),
    Input("map-boundary-selector", "value"),
    Input("map-init",              "n_intervals"),
)
def _update_spinner_label(states, nations, groups, start_date, end_date, boundary_layer, _):
    parts = _status_parts(states or [], nations or [], groups or [], start_date, end_date)
    layer_label = _BOUNDARY_LABEL.get(boundary_layer or "none", "")
    if layer_label and layer_label != "None":
        parts.append(layer_label)
    return "Loading " + " · ".join(parts) + "…"


# ── Master callback ───────────────────────────────────────────────────────────

@callback(
    Output("map-voter-pins", "figure"),
    Output("map-status",     "children"),
    Input("map-state-selector",    "value"),
    Input("map-nation-selector",   "value"),
    Input("map-group-selector",    "value"),
    Input("map-date-range",        "start_date"),
    Input("map-date-range",        "end_date"),
    Input("map-boundary-selector", "value"),
    Input("map-pins-toggle",       "value"),
)
def update_map(states, nations, groups, start_date, end_date, boundary_layer, show_pins):
    triggered = ctx.triggered_id or "initial"
    print(
        f"[map] update_map triggered_by={triggered!r} "
        f"states={states!r} nations={nations!r} groups={groups!r} "
        f"start={start_date!r} end={end_date!r}",
        file=sys.stderr, flush=True,
    )

    try:
        df = get_voter_map_data(
            state_ids=states   or [],
            nation_ids=nations or [],
            group_ids=groups   or [],
            start_date=start_date[:10] if start_date else None,
            end_date=end_date[:10]     if end_date   else None,
        )

        data_states = df["state"].dropna().unique().tolist() if not df.empty else []
        geo_df = get_boundaries(boundary_layer, data_states) if boundary_layer != "none" and data_states else None

        if df.empty:
            parts = _status_parts(states, nations, groups, start_date, end_date)
            return _empty_map("No contacts for this selection.", geo_df=geo_df), " · ".join(parts)

        fig = go.Figure()

        boundary_label = _BOUNDARY_LABEL.get(boundary_layer, "Boundaries")
        if geo_df is not None and not geo_df.empty:
            county_stats = _assign_voters_to_counties(df, geo_df)
            if not county_stats.empty:
                fig.add_trace(_choropleth_trace(geo_df, county_stats))
                print(f"[map] choropleth: {len(county_stats)} {boundary_layer} features", file=sys.stderr, flush=True)
            else:
                fig.add_trace(_border_trace(geo_df, label=boundary_label))

        if show_pins:
            for min_c, max_c, color, label in BUCKETS:
                mask = (df["contact_count"] == min_c) if max_c is not None else (df["contact_count"] >= min_c)
                subset = df[mask]
                if subset.empty:
                    continue
                fig.add_trace(go.Scattermapbox(
                    lat=subset["lat"].tolist(),
                    lon=subset["lng"].tolist(),
                    mode="markers",
                    marker=dict(size=9, color=color, opacity=0.85),
                    name=label,
                    hovertemplate=(
                        f"<b>{label}</b><br>"
                        "Lat: %{lat:.5f}<br>"
                        "Lon: %{lon:.5f}<br>"
                        "<extra></extra>"
                    ),
                ))

        fig.update_layout(
            mapbox=dict(
                style="carto-positron",
                zoom=9,
                center=dict(
                    lat=float(df["lat"].mean()),
                    lon=float(df["lng"].mean()),
                ),
            ),
            margin=dict(t=0, b=0, l=0, r=0),
            paper_bgcolor="rgba(0,0,0,0)",
            legend=dict(
                orientation="v",
                x=0.01, y=0.99,
                bgcolor="rgba(255,255,255,0.85)",
                bordercolor="#dee2e6",
                borderwidth=1,
            ),
            height=600,
            uirevision="map-voter-pins",
        )

        pin_count = len(df)
        parts = _status_parts(states, nations, groups, start_date, end_date)
        status = f"{pin_count:,} voters · " + " · ".join(parts)
        print(f"[map] update_map → {pin_count} voters", file=sys.stderr, flush=True)

    except Exception:
        print(f"[map] update_map FAILED:\n{traceback.format_exc()}", file=sys.stderr, flush=True)
        fig = _empty_map("Error loading map data.")
        status = "Error loading data."

    return fig, status


# ── County detail modal ───────────────────────────────────────────────────────

@callback(
    Output("county-modal",       "is_open"),
    Output("county-modal-title", "children"),
    Output("county-modal-body",  "children"),
    Input("map-voter-pins",      "clickData"),
    Input("county-modal-close",  "n_clicks"),
    prevent_initial_call=True,
)
def show_county_modal(click_data, _close_clicks):
    if ctx.triggered_id == "county-modal-close":
        return False, dash.no_update, dash.no_update

    if not click_data:
        return False, dash.no_update, dash.no_update

    point = (click_data.get("points") or [{}])[0]

    # Only react to choropleth clicks (they carry a "location" key)
    if "location" not in point or not point.get("customdata"):
        return False, dash.no_update, dash.no_update

    name, state_name, unique_voters, total_contacts, b1, b2, b3, b4 = point["customdata"]
    avg = total_contacts / unique_voters if unique_voters else 0

    title = f"{name}{state_name}"

    body = dbc.Row(
        [
            dbc.Col(
                dbc.Card(dbc.CardBody([
                    html.H4(f"{unique_voters:,}", className="mb-0", style={"color": "#C1272D"}),
                    html.P("Unique Contacted Voters", className="text-muted small mb-0"),
                ]), className="text-center h-100"),
                width=4,
            ),
            dbc.Col(
                dbc.Card(dbc.CardBody([
                    html.H4(f"{total_contacts:,}", className="mb-0", style={"color": "#C1272D"}),
                    html.P("Total Contacts", className="text-muted small mb-0"),
                ]), className="text-center h-100"),
                width=4,
            ),
            dbc.Col(
                dbc.Card(dbc.CardBody([
                    html.H4(f"{avg:.1f}", className="mb-0", style={"color": "#C1272D"}),
                    html.P("Avg Contacts / Contacted Voter", className="text-muted small mb-0"),
                ]), className="text-center h-100"),
                width=4,
            ),
            dbc.Col(
                html.Div(
                    [
                        html.P("Contact Frequency", className="fw-semibold small mb-1 mt-3"),
                        dbc.Table(
                            [
                                html.Tbody([
                                    html.Tr([html.Td([html.Span("■ ", style={"color": "#4FC3F7"}), "1 Contact"]), html.Td(f"{b1:,}", className="text-end fw-semibold")]),
                                    html.Tr([html.Td([html.Span("■ ", style={"color": "#81C784"}), "2 Contacts"]), html.Td(f"{b2:,}", className="text-end fw-semibold")]),
                                    html.Tr([html.Td([html.Span("■ ", style={"color": "#FFB74D"}), "3 Contacts"]), html.Td(f"{b3:,}", className="text-end fw-semibold")]),
                                    html.Tr([html.Td([html.Span("■ ", style={"color": "#C1272D"}), "4+ Contacts"]), html.Td(f"{b4:,}", className="text-end fw-semibold")]),
                                ])
                            ],
                            bordered=False,
                            size="sm",
                            className="mb-0",
                        ),
                    ]
                ),
                width=12,
            ),
        ],
        className="g-3",
    )

    return True, title, body
