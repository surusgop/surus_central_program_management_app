import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env")

import dash
import dash_bootstrap_components as dbc
from dash import Input, Output, dcc
from flask import request
from surus_auth import get_config
from surus_auth.flask import register_auth, get_current_user
from surus_auth.roles.flask import admin_blueprint

from platform_setup import ADMIN_THEME, kit, page_name, track

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

# Sign-in from surus-auth; roles and usage tracking live in the shared
# universal.ops tables (app_id "central_pm", see platform_setup.py).
# role_resolver reads team_members (cached 60 s); on_login creates the row on
# first sign-in and logs it. ADMIN_BOOTSTRAP_EMAILS are always admin. /admin is
# for admins only.
register_auth(server, dash=True, role_resolver=kit.resolver, on_login=kit.on_login)
server.register_blueprint(admin_blueprint(kit, theme=ADMIN_THEME))


# dash=True leaves all /_* routes public, including the callback endpoint that
# returns the contact data and PDF reports — require a signed-in user there,
# whose access hasn't been turned off on /admin.
@server.before_request
def guard_dash_callbacks():
    if get_config().is_configured and request.path.startswith("/_dash-update-component"):
        user = get_current_user()
        if not user:
            return "Not signed in.", 401
        if user.get("role") == "disabled":
            return "Your access to this app is turned off.", 403


from components.navbar import create_navbar  # noqa: E402 — needs app defined first


def serve_layout():
    return dbc.Container(
        [
            dcc.Location(id="url", refresh=False),
            dcc.Store(id="page-view-logged"),
            create_navbar(get_current_user()),  # passes full user dict
            dash.page_container,
        ],
        fluid=True,
        className="px-0",
    )


app.layout = serve_layout


@app.callback(Output("page-view-logged", "data"), Input("url", "pathname"))
def log_page_view(pathname):
    """One page.view per page opened, with the page's name (home, analytics,
    analytics-2, contacts)."""
    known = pathname in {p["path"] for p in dash.page_registry.values()}
    page = page_name(pathname) if known else None
    if page:
        track("page.view", event_type="view", page=page)
    return page


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8050))
    debug = os.environ.get("DASH_DEBUG", "false").lower() == "true"
    app.run(host="0.0.0.0", port=port, debug=debug)
