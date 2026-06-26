import dash_bootstrap_components as dbc

navbar = dbc.NavbarSimple(
    children=[
        dbc.NavItem(dbc.NavLink("Overview", href="/analytics")),
        dbc.NavItem(dbc.NavLink("Map", href="/map")),
        dbc.NavItem(dbc.NavLink("Debug", href="/debug")),
        dbc.NavItem(dbc.NavLink("Test", href="/test")),
    ],
    brand="Surus Central Program Management",
    brand_href="/",
    color="primary",
    dark=True,
    fluid=True,
    className="mb-0 shadow-sm",
)
