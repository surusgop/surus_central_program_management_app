import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env")

import dash
import dash_bootstrap_components as dbc
from dash import dcc
from surus_auth.flask import register_auth, get_current_user

app = dash.Dash(
    __name__,
    use_pages=True,
    external_stylesheets=[
        dbc.themes.FLATLY,
        dbc.icons.BOOTSTRAP,
        "https://fonts.googleapis.com/css2?family=Open+Sans:wght@400;600;700;800&display=swap",
    ],
    suppress_callback_exceptions=True,
    title="Central Program Management",
)
server = app.server  # expose Flask server for gunicorn
register_auth(server, dash=True)

from components.navbar import create_navbar  # noqa: E402 — needs app defined first


def serve_layout():
    return dbc.Container(
        [
            dcc.Location(id="url", refresh=False),
            create_navbar(get_current_user()),  # passes full user dict
            dash.page_container,
        ],
        fluid=True,
        className="px-0",
    )


app.layout = serve_layout

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8050))
    debug = os.environ.get("DASH_DEBUG", "false").lower() == "true"
    app.run(host="0.0.0.0", port=port, debug=debug)
