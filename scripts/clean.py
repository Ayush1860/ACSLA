"""Clean the raw Kaggle CSVs and export a star schema for Power BI.

Input : data/raw/train.csv, data/raw/test.csv
Output: data/processed/
    fact_flights.csv           one row per passenger (grain: passenger_id)
    dim_customer.csv           gender x customer_type x age_band
    dim_travel.csv             travel_type x class x distance_band
    dim_service.csv            the 14 rated services (service_id, service_name, journey_stage)
    fact_service_ratings.csv   ratings unpivoted to long format (passenger_id, service_id, rating);
                               rating 0 = "not applicable" and is excluded by the DAX measures

Usage:
    python scripts/clean.py
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = ROOT / "data" / "raw"
OUT_DIR = ROOT / "data" / "processed"

# The 14 service ratings (0 = not applicable, 1-5 = score), in snake_case.
SERVICE_COLUMNS = [
    "inflight_wifi_service",
    "departure_arrival_time_convenient",
    "ease_of_online_booking",
    "gate_location",
    "food_and_drink",
    "online_boarding",
    "seat_comfort",
    "inflight_entertainment",
    "on_board_service",
    "leg_room_service",
    "baggage_handling",
    "checkin_service",
    "inflight_service",
    "cleanliness",
]

# Readable names for the Power BI service table, plus the journey stage each belongs to.
SERVICE_LABELS = {
    "inflight_wifi_service": ("Inflight Wi-Fi", "In-flight"),
    "departure_arrival_time_convenient": ("Departure/Arrival Time", "Pre-flight"),
    "ease_of_online_booking": ("Online Booking", "Pre-flight"),
    "gate_location": ("Gate Location", "Airport"),
    "food_and_drink": ("Food & Drink", "In-flight"),
    "online_boarding": ("Online Boarding", "Airport"),
    "seat_comfort": ("Seat Comfort", "In-flight"),
    "inflight_entertainment": ("Inflight Entertainment", "In-flight"),
    "on_board_service": ("On-board Service", "In-flight"),
    "leg_room_service": ("Leg Room", "In-flight"),
    "baggage_handling": ("Baggage Handling", "Airport"),
    "checkin_service": ("Check-in Service", "Airport"),
    "inflight_service": ("Inflight Service", "In-flight"),
    "cleanliness": ("Cleanliness", "In-flight"),
}

AGE_BANDS = ["<18", "18-30", "31-45", "46-60", "60+"]
DELAY_BUCKETS = ["On time", "1-15 min", "16-60 min", "60+ min"]
DISTANCE_BANDS = ["Short (<1000)", "Medium (1000-3000)", "Long (3000+)"]


def to_snake(name: str) -> str:
    name = re.sub(r"[^0-9a-zA-Z]+", "_", name.strip())
    return name.strip("_").lower()


def load_raw() -> pd.DataFrame:
    frames = []
    for split in ("train", "test"):
        path = RAW_DIR / f"{split}.csv"
        if not path.exists():
            sys.exit(f"Missing {path}. Run `python scripts/download_data.py` first.")
        df = pd.read_csv(path)
        df["source_split"] = split
        frames.append(df)
    return pd.concat(frames, ignore_index=True)


def band_age(age: pd.Series) -> pd.Series:
    return pd.cut(age, bins=[-np.inf, 17, 30, 45, 60, np.inf], labels=AGE_BANDS).astype(str)


def bucket_delay(minutes: pd.Series) -> pd.Series:
    return pd.cut(minutes, bins=[-np.inf, 0, 15, 60, np.inf], labels=DELAY_BUCKETS).astype(str)


def band_distance(km: pd.Series) -> pd.Series:
    return pd.cut(km, bins=[-np.inf, 999, 2999, np.inf], labels=DISTANCE_BANDS).astype(str)


def clean(raw: pd.DataFrame) -> pd.DataFrame:
    df = raw.copy()

    # Drop pandas index columns written into the CSV ("Unnamed: 0").
    df = df.loc[:, ~df.columns.str.startswith("Unnamed")]
    df.columns = [to_snake(c) for c in df.columns]
    df = df.rename(
        columns={
            "id": "passenger_id",
            "type_of_travel": "travel_type",
            "departure_delay_in_minutes": "dep_delay",
            "arrival_delay_in_minutes": "arr_delay",
        }
    )

    df = df.drop_duplicates(subset="passenger_id")

    # ~0.3% of arrival delays are missing: departure delay is the best proxy
    # (corr ~0.96); fall back to the median if that is missing too.
    df["arr_delay"] = df["arr_delay"].fillna(df["dep_delay"]).fillna(df["arr_delay"].median())

    int_cols = ["passenger_id", "age", "flight_distance", "dep_delay", "arr_delay", *SERVICE_COLUMNS]
    df[int_cols] = df[int_cols].round().astype("int64")

    # Harmonise category labels.
    df["customer_type"] = df["customer_type"].str.replace("disloyal", "Disloyal", regex=False)
    df["travel_type"] = df["travel_type"].replace({"Business travel": "Business Travel"})
    df["class"] = df["class"].replace({"Eco": "Economy"})

    # Derived columns.
    df["age_band"] = band_age(df["age"])
    df["delay_bucket"] = bucket_delay(df["dep_delay"])
    df["distance_band"] = band_distance(df["flight_distance"])
    df["is_satisfied"] = (df["satisfaction"].str.strip().str.lower() == "satisfied").astype(int)
    df["satisfaction"] = np.where(df["is_satisfied"] == 1, "Satisfied", "Neutral or Dissatisfied")
    df["is_delayed_15"] = (df["dep_delay"] > 15).astype(int)

    # Rating 0 means "not applicable" - keep a count, and a per-passenger average
    # that ignores those zeros.
    ratings = df[SERVICE_COLUMNS].replace(0, np.nan)
    df["services_not_applicable"] = ratings.isna().sum(axis=1)
    df["avg_service_rating"] = ratings.mean(axis=1).round(3)

    return df.sort_values("passenger_id").reset_index(drop=True)


def build_star_schema(df: pd.DataFrame) -> dict[str, pd.DataFrame]:
    customer_keys = ["gender", "customer_type", "age_band"]
    dim_customer = (
        df[customer_keys].drop_duplicates().sort_values(customer_keys).reset_index(drop=True)
    )
    dim_customer.insert(0, "customer_id", range(1, len(dim_customer) + 1))
    dim_customer["age_band_order"] = dim_customer["age_band"].map(AGE_BANDS.index) + 1
    dim_customer["customer_segment"] = dim_customer[customer_keys].agg(" | ".join, axis=1)

    travel_keys = ["travel_type", "class", "distance_band"]
    dim_travel = df[travel_keys].drop_duplicates().sort_values(travel_keys).reset_index(drop=True)
    dim_travel.insert(0, "travel_id", range(1, len(dim_travel) + 1))
    class_order = {"Business": 1, "Eco Plus": 2, "Economy": 3}
    dim_travel["class_order"] = dim_travel["class"].map(class_order)
    dim_travel["distance_band_order"] = dim_travel["distance_band"].map(DISTANCE_BANDS.index) + 1
    dim_travel["trip_segment"] = dim_travel[travel_keys].agg(" | ".join, axis=1)

    fact = df.merge(dim_customer[["customer_id", *customer_keys]], on=customer_keys).merge(
        dim_travel[["travel_id", *travel_keys]], on=travel_keys
    )
    fact["delay_bucket_order"] = fact["delay_bucket"].map(DELAY_BUCKETS.index) + 1
    fact_flights = fact[
        [
            "passenger_id",
            "customer_id",
            "travel_id",
            "age",
            "flight_distance",
            "dep_delay",
            "arr_delay",
            "delay_bucket",
            "delay_bucket_order",
            "is_delayed_15",
            "avg_service_rating",
            "services_not_applicable",
            "is_satisfied",
            "satisfaction",
            "source_split",
        ]
    ].sort_values("passenger_id").reset_index(drop=True)

    dim_service = pd.DataFrame(
        {
            "service_id": range(1, len(SERVICE_COLUMNS) + 1),
            "service_key": SERVICE_COLUMNS,
            "service_name": [SERVICE_LABELS[k][0] for k in SERVICE_COLUMNS],
            "journey_stage": [SERVICE_LABELS[k][1] for k in SERVICE_COLUMNS],
        }
    )

    # Ratings unpivoted to long format: one row per passenger per service.
    fact_service_ratings = df.melt(
        id_vars="passenger_id",
        value_vars=SERVICE_COLUMNS,
        var_name="service_key",
        value_name="rating",
    )
    fact_service_ratings["service_id"] = fact_service_ratings["service_key"].map(
        dict(zip(dim_service["service_key"], dim_service["service_id"]))
    )
    fact_service_ratings = (
        fact_service_ratings[["passenger_id", "service_id", "rating"]]
        .sort_values(["passenger_id", "service_id"])
        .reset_index(drop=True)
    )

    return {
        "fact_flights": fact_flights,
        "dim_customer": dim_customer,
        "dim_travel": dim_travel,
        "dim_service": dim_service,
        "fact_service_ratings": fact_service_ratings,
    }


def main() -> None:
    raw = load_raw()
    print(f"Loaded {len(raw):,} raw rows")
    print(f"Missing arrival delays: {raw['Arrival Delay in Minutes'].isna().sum():,}")

    df = clean(raw)
    tables = build_star_schema(df)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for name, table in tables.items():
        path = OUT_DIR / f"{name}.csv"
        table.to_csv(path, index=False)
        print(f"Wrote {path.relative_to(ROOT)}: {len(table):,} rows x {table.shape[1]} cols")

    # Wide cleaned file for the notebook / driver analysis.
    df.to_csv(OUT_DIR / "flights_clean.csv", index=False)
    print(f"Wrote data/processed/flights_clean.csv: {len(df):,} rows")
    print(f"Overall satisfaction: {df['is_satisfied'].mean():.1%}")


if __name__ == "__main__":
    main()
