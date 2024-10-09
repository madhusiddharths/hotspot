import dash
from dash import dcc, html
import dash_bootstrap_components as dbc

def run_app_1(server):
    # Initialize Dash app 1 with Bootstrap and Flask server
    app1 = dash.Dash("app1", external_stylesheets=[dbc.themes.BOOTSTRAP], server=server, url_base_pathname='/app1/')

    # Define the layout for the initial page (ILI box)
    app1.layout = dbc.Container([
            dbc.Row(
                dbc.Col(
                    # Adding dcc.Link to make the card clickable and navigate to App 2
                    dcc.Link(
                        dbc.Card(
                            dbc.CardBody(
                                [
                                    html.H1(
                                        "3.0",  # Larger text
                                        className="card-title",
                                        style={
                                            "text-align": "center",
                                            "margin-bottom": "0",
                                            "text-decoration": "none"  # Remove underline
                                        },
                                    ),
                                    html.H6(
                                        "ILI value",  # Smaller text
                                        className="card-subtitle",
                                        style={
                                            "text-align": "center",
                                            "color": "#6c757d",
                                            "margin-top": "0",
                                            "text-decoration": "none"  # Remove underline
                                        },
                                    ),
                                ]
                            ),
                            style={
                                "width": "300px",
                                "margin": "auto",
                                "box-shadow": "0 4px 20px rgba(0, 0, 0, 0.1)",
                                "border": "2px solid #007bff",
                                "background-color": "#f8f9fa",
                                "border-radius": "15px",
                                "padding": "20px",
                                "cursor": "pointer",  # Change cursor to pointer when hovered
                            },
                        ),
                        href='/app2/',  # Navigate to App 2 when clicked
                        style={'text-decoration': 'none'}  # Ensure no underline on link
                    ),
                    width=12,
                ),
            ),
        ],
        className="mt-5",
    )
    return app1
