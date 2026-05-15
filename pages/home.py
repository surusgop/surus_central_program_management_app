import dash
import dash_bootstrap_components as dbc
from dash import html

dash.register_page(__name__, path="/", name="Home", title="Surus Central")

layout = dbc.Container(
    dbc.Row(
        dbc.Col(
            [
                html.H3("Surus Central", className="mt-5 fw-semibold"),
                html.P(
                    "Program management dashboard. Use the navigation above to explore.",
                    className="text-muted",
                ),
                dbc.Button("Open District Map", href="/map", color="primary", className="mt-2"),
            ],
            width={"size": 6, "offset": 3},
            className="text-center",
        )
    ),
    fluid=True,
)
