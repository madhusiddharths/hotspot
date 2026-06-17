"""Smoke tests for the data layer.

These guard against the class of bug that the old fixed-length ``np.arange``
week index introduced: silently empty frames or misaligned weeks.
Run with: ``pytest -q``
"""

import numpy as np
import pandas as pd

from src import data_processing as dp


def test_surveillance_week_matches_mmwr():
    df = dp.load_surveillance()
    assert not df.empty
    # 'week' must be the real MMWR week, not a fabricated 1..N range.
    assert (df["week"] == df["MMWR_WEEK"] % 100).all()
    assert df["week"].between(1, 53).all()


def test_risk_has_zip_and_ili():
    df = dp.load_risk()
    assert not df.empty
    assert {"ZIP_Code", "ILI", "MMWR_Week"} <= set(df.columns)
    assert df["ZIP_Code"].between(60601, 60665).all()


def test_population_is_numeric_and_nonempty():
    pop = dp.load_population()
    assert pop, "population mapping is empty"
    assert all(isinstance(z, (int, np.integer)) for z in pop)


def test_geojson_collection_loads():
    geo = dp.load_geojson_collection()
    assert geo["type"] == "FeatureCollection"
    assert len(geo["features"]) > 0


def test_dashboard_bundle_is_consistent():
    data = dp.load_dashboard_data()
    for key in ("surveillance", "risk", "age", "population", "geojson", "estimates"):
        assert key in data
    # The sample timeline should yield at least one day of exposure estimates.
    assert isinstance(data["estimates"], dict)
    assert len(data["estimates"]) > 0


def test_exposure_probability_bounds():
    data = dp.load_dashboard_data()
    for date_str in data["estimates"]:
        p = dp.exposure_probability(data["estimates"], date_str)
        assert p is None or 0.0 <= p <= 99.99
    assert dp.exposure_probability(data["estimates"], "1900-01-01") is None
