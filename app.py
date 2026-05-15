import os
import dash
import dash_bootstrap_components as dbc
from dotenv import load_dotenv

from auth import register_auth

load_dotenv()

app = dash.Dash(
    __name__,
    use_pages=True,
    external_stylesheets=[dbc.themes.FLATLY, dbc.icons.BOOTSTRAP],
    suppress_callback_exceptions=True,
    title="Surus Central",
)
server = app.server  # expose Flask server for gunicorn
register_auth(server)

from components.navbar import navbar  # noqa: E402 — needs app defined first

app.layout = dbc.Container(
    [
        navbar,
        dash.page_container,
    ],
    fluid=True,
    className="px-0",
)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8050))
    debug = os.environ.get("DASH_DEBUG", "false").lower() == "true"
    app.run(host="0.0.0.0", port=port, debug=debug)
