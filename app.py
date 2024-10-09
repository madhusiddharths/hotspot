import numpy as np
import pandas as pd
import json
import plotly.express as px
import os
import dash
from dash import dcc, html, callback, Input, Output, State
import dash.dependencies as dd
from datetime import datetime, timedelta
import re
import geopandas as gpd
import requests
from opencage.geocoder import OpenCageGeocode
import warnings
import dash_bootstrap_components as dbc
from flask import Flask, redirect
from page1 import run_app_1
from page2 import run_app_2

# Create Flask server
server = Flask(__name__)

# Redirect root to app_1
@server.route('/')
def home():
    return redirect('/app1/')  # Redirect to App 1 at start

app_1 = run_app_1(server)
app_2 = run_app_2(server)

# Run server
if __name__ == "__main__":
    server.run(debug=True, port=8080)  # Flask server runs both Dash apps
