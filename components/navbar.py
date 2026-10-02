import dash_bootstrap_components as dbc


def create_navbar(user: dict | None = None):
    # external_link forces a full page load so the server-side auth guard runs
    # on every data page (Dash's client-side router would otherwise bypass it).
    nav_links = [
        dbc.NavItem(dbc.NavLink("Overview", href="/analytics", external_link=True)),
    ]

    if user:
        full_name = " ".join(p for p in [user.get("first_name"), user.get("last_name")] if p)
        display_name = full_name or user.get("email", "")
        nav_links.append(dbc.NavItem(dbc.NavLink(display_name, href="#", disabled=True)))
        nav_links.append(dbc.NavItem(dbc.NavLink("Sign out", href="/auth/logout", external_link=True)))

    return dbc.NavbarSimple(
        children=nav_links,
        brand="Central Program Management",
        brand_href="/",
        color="primary",
        dark=True,
        fluid=True,
        className="mb-0 shadow-sm",
    )
