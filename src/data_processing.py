"""Data layer for the Health Hotspot Tracker.

This module is the single source of truth for loading and shaping every dataset
the dashboard uses, plus the (optional) parsing of a user's own Google "Timeline"
export into the per-ZIP activity stream that drives the exposure-probability
metric.

Paths are resolved relative to this file so the code works regardless of the
current working directory.
"""

import os
import json
from datetime import datetime

import numpy as np
import pandas as pd

# Repo root (one level up from src/).
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _path(name):
    return os.path.join(BASE_DIR, name)


# ---------------------------------------------------------------------------
# Exposure-probability model constants
# ---------------------------------------------------------------------------
# Per-activity exposure weighting. The idea: time spent stationary indoors or on
# crowded transit carries more contact risk per minute than time spent running or
# cycling. These are heuristic weights, not empirically calibrated.
ACTIVITY_FACTORS = {
    "UNKNOWN": 1.0,
    "positionscan": 2.0,
    "wifiscan": 2.0,
    "STILL": 2.0,
    "WALKING": 1.0,
    "ON_FOOT": 1.0,
    "RUNNING": 0.5,
    "ON_BICYCLE": 0.5,
    "IN_ROAD_VEHICLE": 0.5,
    "IN_RAIL_VEHICLE": 5.0,   # crowded transit -> highest weight
    "IN_VEHICLE": 2.0,
    "TILTING": 1.0,
    "EXITING_VEHICLE": 1.0,
}
# Gaps between consecutive timeline events longer than this (minutes) are treated
# as "device off / not moving" and excluded rather than counted as exposure.
MAX_GAP_MINUTES = 240
# Calibration constant for the risk -> probability curve (larger == flatter).
EXPOSURE_SCALE = 600.0
# Surveillance case counts lag exposure; timeline week W is matched against the
# surveillance week W - CASE_REPORTING_LAG_WEEKS.
CASE_REPORTING_LAG_WEEKS = 2


# ---------------------------------------------------------------------------
# Surveillance / reference data loaders
# ---------------------------------------------------------------------------
def load_surveillance(path=None):
    """Weekly Chicago flu surveillance, filtered to the 2024 season.

    Adds a plain ``week`` column derived from the real ``MMWR_WEEK`` (stored as
    ``YYYYWW``) instead of fabricating one with a fixed-length range.
    """
    df = pd.read_csv(path or _path("Influenza_Surveillance_Weekly.csv"))
    df["WEEK_START"] = pd.to_datetime(df["WEEK_START"])
    df["WEEK_END"] = pd.to_datetime(df["WEEK_END"])
    df = df[df["WEEK_START"].dt.year >= 2024].copy()
    df.sort_values("WEEK_START", inplace=True)
    df["week"] = (df["MMWR_WEEK"] % 100).astype(int)
    return df


def load_risk(path=None):
    """ILI activity level by Chicago ZIP code (the choropleth source)."""
    df = pd.read_csv(path or _path("risk_level.csv"))
    df = df[(df["ZIP_Code"] > 60600) & (df["ZIP_Code"] < 60666)].copy()
    df["Week_Start"] = pd.to_datetime(df["Week_Start"])
    df["Week_End"] = pd.to_datetime(df["Week_End"])
    df = df[df["Week_Start"].dt.year >= 2024]
    df.rename(columns={"ILI_Activity_Level": "ILI"}, inplace=True)
    df.sort_values("Week_Start", inplace=True)
    return df


def load_age(path=None):
    """CDC FluSurv-NET weekly infection rate by age group (2024)."""
    df = pd.read_csv(path or _path("FluSurveillance_Custom_Download_Data.csv"), skiprows=2)
    df.rename(columns=str.lower, inplace=True)
    df = df[["age category", "mmwr-year", "mmwr-week", "cumulative rate", "weekly rate"]].copy()
    df.replace([np.inf, -np.inf], np.nan, inplace=True)
    df.dropna(inplace=True)
    df["mmwr-year"] = df["mmwr-year"].astype("int64")
    df["mmwr-week"] = df["mmwr-week"].astype("int64")
    df = df[df["mmwr-year"] == 2024]
    df = df[df["age category"] != "Overall"]
    return df


def load_population(path=None):
    """ZIP -> total population mapping (2021 Chicago counts)."""
    pop = pd.read_csv(path or _path("Chicago_Population_Counts.csv"))
    pop = pop[pop["Year"] == 2021][["Geography", "Population - Total"]].copy()
    # 'Geography' holds ZIP codes plus non-numeric aggregate rows (e.g. citywide
    # totals); coercing to numeric and dropping NaN removes them without relying
    # on a hardcoded row index.
    pop["Geography"] = pd.to_numeric(pop["Geography"], errors="coerce")
    pop.dropna(subset=["Geography"], inplace=True)
    pop["Geography"] = pop["Geography"].astype("int64")
    return pop.set_index("Geography")["Population - Total"].to_dict()


def load_geojson_collection(geojson_dir=None):
    """Merge every ZIP-code geojson into one FeatureCollection for Plotly."""
    geojson_dir = geojson_dir or _path("geojson")
    collection = {"type": "FeatureCollection", "features": []}
    for filename in sorted(os.listdir(geojson_dir)):
        if filename.endswith(".geojson"):
            with open(os.path.join(geojson_dir, filename)) as f:
                collection["features"].extend(json.load(f)["features"])
    return collection


# ---------------------------------------------------------------------------
# Exposure probability (from a processed per-ZIP timeline)
# ---------------------------------------------------------------------------
def build_exposure_estimates(timeline_records, pop_dict, weekly_cases_by_week):
    """Turn a processed timeline into per-day exposure contributions.

    ``timeline_records`` is a list of ``{timestamp, type, zipcode}`` dicts (the
    output of :func:`process_timeline_file`). Returns ``{date_str: [(dt_minutes,
    activity_factor, local_case_rate), ...]}`` consumed by
    :func:`exposure_probability`.
    """
    df = pd.DataFrame(timeline_records)
    if df.empty:
        return {}

    df["timestamp"] = pd.to_datetime(df["timestamp"])
    df["type"] = df["type"].astype(str)
    df["zipcode"] = pd.to_numeric(df["zipcode"], errors="coerce")
    df.dropna(subset=["zipcode"], inplace=True)
    df["zipcode"] = df["zipcode"].astype("int64")
    df = df[df["zipcode"] <= 60666]

    # Drop duplicate-timestamp passive scans (position/wifi fire repeatedly).
    df = df[~(df["timestamp"].duplicated() & df["type"].isin(["positionscan", "wifiscan"]))]
    df = df.sort_values("timestamp").reset_index(drop=True)

    df["week"] = df["timestamp"].dt.isocalendar().week.astype(int)
    df["population"] = df["zipcode"].map(pop_dict)
    df.dropna(subset=["population"], inplace=True)
    df["cases"] = df["week"].map(
        lambda w: weekly_cases_by_week.get(w - CASE_REPORTING_LAG_WEEKS, 0)
    )

    # Collapse runs of identical consecutive (type, zip) into their first event so
    # a single contribution spans the whole dwell.
    keep = (df["type"] != df["type"].shift()) | (df["zipcode"] != df["zipcode"].shift())
    df = df[keep].reset_index(drop=True)
    if len(df) < 2:
        return {}

    # Each event contributes for the time until the next event.
    df["dt"] = df["timestamp"].diff().shift(-1).dt.total_seconds() / 60.0
    df["factor"] = df["type"].map(ACTIVITY_FACTORS).fillna(1.0)
    df["rate"] = np.where(df["population"] > 0, df["cases"] / df["population"], 0.0)

    valid = df[(df["dt"] > 0) & (df["dt"] <= MAX_GAP_MINUTES)]
    estimates = {}
    for date_str, group in valid.groupby(valid["timestamp"].dt.strftime("%Y-%m-%d")):
        estimates[date_str] = list(zip(group["dt"], group["factor"], group["rate"]))
    return estimates


def exposure_probability(estimates, date_str):
    """Probability (%) of exposure on ``date_str`` or ``None`` if no data."""
    if date_str not in estimates:
        return None
    items = estimates[date_str]
    if not items:
        return 0.0
    risk_sum = np.sum(np.prod(np.array(items), axis=1))
    probability = (1 - np.exp(-risk_sum / EXPOSURE_SCALE)) * 100
    return float(min(probability, 99.99))


# ---------------------------------------------------------------------------
# Top-level bundle used by the Streamlit app
# ---------------------------------------------------------------------------
DEFAULT_TIMELINE = "sample_timeline.json"


def load_dashboard_data(timeline_path=None):
    """Load everything the dashboard needs as one dict."""
    surveillance = load_surveillance()
    risk = load_risk()
    age = load_age()
    pop = load_population()
    geo = load_geojson_collection()

    weekly_cases = surveillance.set_index("week")["LAB_FLU_TESTED"].to_dict()

    tpath = timeline_path or _path(DEFAULT_TIMELINE)
    estimates = {}
    if os.path.exists(tpath):
        with open(tpath) as f:
            estimates = build_exposure_estimates(json.load(f), pop, weekly_cases)

    return {
        "surveillance": surveillance,
        "risk": risk,
        "age": age,
        "population": pop,
        "geojson": geo,
        "estimates": estimates,
    }


# ===========================================================================
# Google Timeline export parsing (only needed to process a user's own data)
# ===========================================================================
def load_geojson_boundaries(geojson_dir):
    """Load ZIP boundaries as a single GeoDataFrame for spatial joins."""
    import geopandas as gpd  # imported lazily; only needed for timeline parsing

    gdfs = []
    for filename in os.listdir(geojson_dir):
        if not filename.endswith(".geojson"):
            continue
        try:
            gdf = gpd.read_file(os.path.join(geojson_dir, filename))
            if "postal-code" in gdf.columns:
                gdfs.append(gdf[["postal-code", "geometry"]])
            elif "ZIP" in gdf.columns:
                gdf["postal-code"] = gdf["ZIP"]
                gdfs.append(gdf[["postal-code", "geometry"]])
        except Exception as e:  # pragma: no cover - defensive
            print(f"Error loading {filename}: {e}")

    if not gdfs:
        raise ValueError("No valid geojson files found with a postal-code property.")

    combined = pd.concat(gdfs, ignore_index=True)
    import geopandas as gpd  # noqa: F811
    combined = gpd.GeoDataFrame(combined, geometry="geometry")
    if combined.crs is None:
        combined.set_crs(epsg=4326, inplace=True)
    elif combined.crs.to_epsg() != 4326:
        combined.to_crs(epsg=4326, inplace=True)
    return combined


def _parse_latlng(raw):
    lat, lon = raw.split(",")
    return float(lat.replace("°", "").strip()), float(lon.replace("°", "").strip())


def extract_timeline_data(timeline_path):
    """Flatten a Google Timeline JSON into timestamp/type/lat/lon records."""
    with open(timeline_path, "r") as f:
        data = json.load(f)

    records = []
    for i in data.get("rawSignals", []):
        if "activityRecord" in i:
            records.append({
                "timestamp": i["activityRecord"]["timestamp"],
                "type": i["activityRecord"]["probableActivities"][0]["type"],
                "lat": None, "lon": None,
            })
        elif "wifiScan" in i:
            records.append({
                "timestamp": i["wifiScan"]["deliveryTime"],
                "type": "wifiscan", "lat": None, "lon": None,
            })
        elif "position" in i:
            lat, lon = _parse_latlng(i["position"]["LatLng"])
            records.append({
                "timestamp": i["position"]["timestamp"],
                "type": "positionscan", "lat": lat, "lon": lon,
            })

    for i in data.get("semanticSegments", []):
        if "visit" in i:
            lat, lon = _parse_latlng(i["visit"]["topCandidate"]["placeLocation"]["latLng"])
            records.append({"timestamp": i["startTime"], "type": "stay", "lat": lat, "lon": lon})
        elif "activity" in i:
            lat, lon = _parse_latlng(i["activity"]["start"]["latLng"])
            records.append({
                "timestamp": i["startTime"],
                "type": i["activity"]["topCandidate"]["type"],
                "lat": lat, "lon": lon,
            })

    df = pd.DataFrame(records)
    df["timestamp"] = pd.to_datetime(df["timestamp"], format="mixed", utc=True)
    df.sort_values("timestamp", inplace=True)
    df.reset_index(drop=True, inplace=True)
    return df


def map_zipcodes(df, geo_df):
    """Spatially join coordinates to ZIP codes, forward-filling between fixes."""
    import geopandas as gpd
    from shapely.geometry import Point

    has_coords = df.dropna(subset=["lat", "lon"]).copy()
    geometry = [Point(xy) for xy in zip(has_coords["lon"], has_coords["lat"])]
    points = gpd.GeoDataFrame(has_coords, geometry=geometry, crs="EPSG:4326")
    joined = gpd.sjoin(points, geo_df, how="left", predicate="intersects")
    has_coords["zipcode"] = joined["postal-code"]

    df.loc[has_coords.index, "zipcode"] = has_coords["zipcode"]
    df["zipcode"] = df["zipcode"].ffill()
    df.dropna(subset=["zipcode"], inplace=True)
    df["zipcode"] = df["zipcode"].astype(str).str.split(".").str[0]
    return df


def process_timeline_file(timeline_path, geojson_dir=None, output_path=None):
    """Parse a Google Timeline export into ``[{timestamp, type, zipcode}, ...]``.

    If ``output_path`` is given, also writes the records there as JSON.
    """
    geojson_dir = geojson_dir or _path("geojson")
    geo_df = load_geojson_boundaries(geojson_dir)
    df = extract_timeline_data(timeline_path)
    df = map_zipcodes(df, geo_df)

    df = df[~(df["timestamp"].duplicated() & df["type"].isin(["positionscan", "wifiscan"]))]
    df["timestamp"] = df["timestamp"].dt.strftime("%Y-%m-%dT%H:%M:%S.000-05:00")
    records = df[["timestamp", "type", "zipcode"]].to_dict(orient="records")

    if output_path:
        with open(output_path, "w") as f:
            json.dump(records, f, indent=4)
        print(f"Saved {len(records)} processed records to {output_path}")
    return records


def main():
    timeline_path = _path("Timeline.json")
    if not os.path.exists(timeline_path):
        print(f"Error: {timeline_path} not found.")
        return
    process_timeline_file(timeline_path, output_path=_path("processed_timeline.json"))
    print("Done!")


if __name__ == "__main__":
    main()
