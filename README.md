# Hotspot - Influenza Surveillance Visualization

This project is a multi-page Dash application designed to visualize influenza-like illness (ILI) data and risk levels. It provides an interactive interface for exploring health surveillance metrics, utilizing geospatial data and interactive charts.

## Project Structure

The application is built using **Dash** (on top of Flask) and is structured as follows:

- **`app.py`**: The main entry point. It initializes the Flask server and mounts two Dash applications (`app1` and `app2`). It handles routing, redirecting the root URL to the first app.
- **`page1.py`**: Defines the layout for the first Dash app (`/app1/`). It serves as a landing dashboard featuring summary metrics (e.g., ILI values) in a card layout.
- **`page2.py`**: Defines the layout and logic for the second Dash app (`/app2/`). This page typically contains more detailed analytics and map visualizations.
- **`requirements.txt`**: Lists all Python dependencies required to run the project.

## Installation

1.  **Clone the repository**:
    ```bash
    git clone <repository_url>
    cd hotspot
    ```

2.  **Set up a virtual environment** (recommended):
    ```bash
    python3 -m venv venv
    source venv/bin/activate
    ```

3.  **Install dependencies**:
    ```bash
    pip install -r requirements.txt
    ```

## Usage

To run the application locally:

```bash
python app.py
```

The server will start on port `8080`.
- Open your browser and navigate to `http://localhost:8080/`.
- You will be automatically redirected to the dashboard at `http://localhost:8080/app1/`.

## Data Management

**Note:** Data files (CSVs, JSONs, GeoJSONs) are excluded from version control for privacy and size reasons. Ensure you have the following data files in your project root before running the app:
- `Chicago_Population_Counts.csv`
- `FluSurveillance_Custom_Download_Data.csv`
- `Influenza_Surveillance_Weekly.csv`
- `risk_level.csv`
- `Timeline.json`
- `data_18_24.json`
- Relevant GeoJSON files in the `geojson/` directory.

## Deployment

The project is configured for deployment (e.g., on Heroku) via the included `Procfile`, which uses `gunicorn` as the production server.

## Technologies Used

- **Dash & Flask**: For the web application framework.
- **Plotly**: For interactive graphs and visualizations.
- **Pandas & NumPy**: For data processing and analysis.
- **GeoPandas**: For handling geospatial operations.
- **OpenCage**: For geocoding and location services.
