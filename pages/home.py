import dash
import dash_bootstrap_components as dbc
from dash import html

dash.register_page(__name__, path="/", name="Home", title="Surus Central Program Management")

layout = dbc.Container(
    dbc.Row(
        dbc.Col(
            [
                html.H3("Surus Central Program Management", className="mt-5 brand-title"),
                html.P(
                    "Voter contact data by state and nation. Use the navigation above to explore.",
                    className="text-muted",
                ),
                dbc.Button("View Overview", href="/analytics", color="primary", className="mt-2"),
            ],
            width={"size": 6, "offset": 3},
            className="text-center",
        )
    ),
    fluid=True,
)
