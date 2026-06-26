import dash
import dash_bootstrap_components as dbc
from dash import html

dash.register_page(__name__, path="/test", name="Test", title="Test | Surus Central Program Management")

layout = dbc.Container(
    dbc.Row(
        dbc.Col(
            html.H4("Test Page", className="my-3 fw-semibold text-primary"),
            width=12,
        )
    ),
    fluid=True,
    className="px-4",
)
