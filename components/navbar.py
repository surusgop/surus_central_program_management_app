import dash_bootstrap_components as dbc

navbar = dbc.NavbarSimple(
    children=[
        dbc.NavItem(dbc.NavLink("Overview", href="/analytics")),
    ],
    brand="Central Program Management",
    brand_href="/",
    color="primary",
    dark=True,
    fluid=True,
    className="mb-0 shadow-sm",
)
