import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from clean import (  # noqa: E402
    SERVICE_COLUMNS,
    band_age,
    band_distance,
    bucket_delay,
    build_star_schema,
    clean,
)

RAW_SERVICE_NAMES = [
    "Inflight wifi service", "Departure/Arrival time convenient", "Ease of Online booking",
    "Gate location", "Food and drink", "Online boarding", "Seat comfort",
    "Inflight entertainment", "On-board service", "Leg room service", "Baggage handling",
    "Checkin service", "Inflight service", "Cleanliness",
]


@pytest.fixture
def raw() -> pd.DataFrame:
    rows = [
        # id, gender, customer type, age, travel, class, distance, dep, arr, satisfaction
        (1, "Male", "Loyal Customer", 13, "Personal Travel", "Eco Plus", 460, 25, 18.0,
         "neutral or dissatisfied"),
        (2, "Female", "disloyal Customer", 25, "Business travel", "Business", 1200, 0, np.nan,
         "satisfied"),
        (3, "Female", "Loyal Customer", 65, "Business travel", "Eco", 3500, 90, 85.0,
         "neutral or dissatisfied"),
    ]
    df = pd.DataFrame(rows, columns=[
        "id", "Gender", "Customer Type", "Age", "Type of Travel", "Class", "Flight Distance",
        "Departure Delay in Minutes", "Arrival Delay in Minutes", "satisfaction",
    ])
    for i, name in enumerate(RAW_SERVICE_NAMES):
        df[name] = [0, 5, 3] if i == 0 else [3, 4, 2]
    df.insert(0, "Unnamed: 0", range(len(df)))
    df["source_split"] = "train"
    return df


def test_bands():
    assert band_age(pd.Series([17, 18, 30, 31, 45, 46, 60, 61])).tolist() == [
        "<18", "18-30", "18-30", "31-45", "31-45", "46-60", "46-60", "60+"]
    assert bucket_delay(pd.Series([0, 1, 15, 16, 60, 61])).tolist() == [
        "On time", "1-15 min", "1-15 min", "16-60 min", "16-60 min", "60+ min"]
    assert band_distance(pd.Series([999, 1000, 2999, 3000])).tolist() == [
        "Short (<1000)", "Medium (1000-3000)", "Medium (1000-3000)", "Long (3000+)"]


def test_clean(raw):
    df = clean(raw)
    assert "unnamed_0" not in df.columns
    assert set(SERVICE_COLUMNS) <= set(df.columns)
    # missing arrival delay filled from departure delay
    assert df.loc[df.passenger_id == 2, "arr_delay"].item() == 0
    assert df["is_satisfied"].tolist() == [0, 1, 0]
    assert df["customer_type"].tolist() == ["Loyal Customer", "Disloyal Customer", "Loyal Customer"]
    assert df["class"].tolist() == ["Eco Plus", "Business", "Economy"]
    # rating 0 is "not applicable" and excluded from the average
    assert df.loc[0, "services_not_applicable"] == 1
    assert df.loc[0, "avg_service_rating"] == pytest.approx(3.0)


def test_star_schema(raw):
    tables = build_star_schema(clean(raw))
    fact, ratings = tables["fact_flights"], tables["fact_service_ratings"]
    assert len(fact) == 3 and fact["passenger_id"].is_unique
    assert fact["customer_id"].isin(tables["dim_customer"]["customer_id"]).all()
    assert fact["travel_id"].isin(tables["dim_travel"]["travel_id"]).all()
    assert len(tables["dim_service"]) == 14
    assert len(ratings) == 3 * 14
    assert ratings["service_id"].isin(tables["dim_service"]["service_id"]).all()
    assert not ratings.duplicated(["passenger_id", "service_id"]).any()
