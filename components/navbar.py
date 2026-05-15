import dash_bootstrap_components as dbc

navbar = dbc.NavbarSimple(
    children=[
        dbc.NavItem(dbc.NavLink("Map", href="/map")),
        dbc.NavItem(dbc.NavLink("Analytics", href="/analytics")),
        # Add more pages here as the app grows:
        # dbc.NavItem(dbc.NavLink("Reports", href="/reports")),
    ],
    brand="Surus Central",
    brand_href="/",
    color="primary",
    dark=True,
    fluid=True,
    className="mb-0 shadow-sm",
)
