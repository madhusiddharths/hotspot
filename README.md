# Health Hotspot Tracker

An interactive **Streamlit** dashboard for exploring influenza-like illness (ILI)
surveillance in Chicago. It overlays weekly ILI activity on a ZIP-code choropleth
map and surfaces supporting metrics — case counts, week-over-week change, the most
affected age group, and an optional personal-exposure probability computed from a
Google *Timeline* export.

> Originally a multi-page Dash app; migrated to a single-page Streamlit app.

**[▶ Try the live app](https://madhusiddharths-hotspot-streamlit-app-ndfk0y.streamlit.app)** *(free-tier host — may need a click to wake)* — the full 36-week 2024 season, 131,896 lab-tested cases across 56 Chicago ZIP codes.

## Features

- **ZIP-code choropleth** of weekly ILI activity for Chicago (≈ 60601–60661).
- **Click a ZIP** on the map to drive the metric cards for that area.
- **Week selector / slider** to move through the 2024–25 season.
- **Trend chart** of ILI and lab-tested cases over the season.
- **Age-group breakdown** of weekly infection rates.
- **Personal exposure probability** — upload your own Google *Timeline* JSON to
  estimate contact-weighted risk (no personal data ships with this repo; a small
  synthetic `sample_timeline.json` is used for the default view).

## Project structure

```
streamlit_app.py        # Streamlit entry point (UI)
src/
  data_processing.py     # Timeline parsing + shared data loading
.streamlit/config.toml   # Theme / server config
geojson/                 # Chicago ZIP-code boundaries (public)
*.csv                    # Public surveillance / population data (see below)
sample_timeline.json     # Synthetic timeline so the demo runs out of the box
tests/                   # Smoke tests
```

## Installation

```bash
git clone https://github.com/madhusiddharths/hotspot.git
cd hotspot
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
```

## Running

```bash
streamlit run streamlit_app.py
```

Then open http://localhost:8501.

## Data

The public reference data needed to run is tracked in the repo:

| File | Source |
| --- | --- |
| `Influenza_Surveillance_Weekly.csv` | Chicago Dept. of Public Health flu surveillance |
| `risk_level.csv` | ILI activity level by ZIP code |
| `FluSurveillance_Custom_Download_Data.csv` | CDC FluSurv-NET age-group rates |
| `Chicago_Population_Counts.csv` | Chicago population by area |
| `geojson/*.geojson` | Chicago ZIP-code boundaries |

**Personal data is never committed.** Google *Timeline* exports
(`Timeline.json`) and anything derived from them are git-ignored. To use the
exposure-probability feature with your own data, either upload your `Timeline.json`
in the app, or process it locally:

```bash
python src/data_processing.py   # writes processed_timeline.json from Timeline.json
```

## Deployment

Deploy on [Streamlit Community Cloud](https://streamlit.io/cloud) (point it at
`streamlit_app.py`) or any host that respects the `Procfile`:

```
web: streamlit run streamlit_app.py --server.port $PORT --server.address 0.0.0.0 --server.headless true
```

## Tech stack

Streamlit · Plotly · pandas / NumPy · GeoPandas (offline ZIP lookup for Timeline parsing).
