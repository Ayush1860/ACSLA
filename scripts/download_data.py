"""Download the Airline Passenger Satisfaction dataset into data/raw/.

Source: Kaggle - "Airline Passenger Satisfaction" (teejmahal20/airline-passenger-satisfaction),
shipped as train.csv (103,904 rows) and test.csv (25,976 rows).

Two download paths are tried in order:
  1. Kaggle API  - needs `pip install kaggle` and ~/.kaggle/kaggle.json credentials.
  2. Public GitHub mirror of the same two files (no credentials needed).

Usage:
    python scripts/download_data.py            # try Kaggle, fall back to mirror
    python scripts/download_data.py --mirror   # skip Kaggle, use mirror only

Manual alternative: download the zip from
https://www.kaggle.com/datasets/teejmahal20/airline-passenger-satisfaction
and extract train.csv and test.csv into data/raw/.
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = ROOT / "data" / "raw"
FILES = ("train.csv", "test.csv")

KAGGLE_DATASET = "teejmahal20/airline-passenger-satisfaction"
# Pinned commit of a public mirror holding the unmodified Kaggle files.
MIRROR_BASE = (
    "https://raw.githubusercontent.com/RodzanIskandar/Airline_Passenger_satisfaction/"
    "25a8cb2c94e3c8e601fa408f78caf97dd149871c/"
)
EXPECTED_ROWS = {"train.csv": 103_904, "test.csv": 25_976}


def already_downloaded() -> bool:
    return all((RAW_DIR / f).exists() for f in FILES)


def download_kaggle() -> bool:
    if shutil.which("kaggle") is None:
        print("Kaggle CLI not found - skipping Kaggle download.")
        return False
    print(f"Downloading {KAGGLE_DATASET} via Kaggle API ...")
    result = subprocess.run(
        ["kaggle", "datasets", "download", "-d", KAGGLE_DATASET, "-p", str(RAW_DIR)],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        print(f"Kaggle download failed: {result.stderr.strip()}")
        return False
    for zip_path in RAW_DIR.glob("*.zip"):
        with zipfile.ZipFile(zip_path) as zf:
            zf.extractall(RAW_DIR)
        zip_path.unlink()
    return already_downloaded()


def download_mirror() -> bool:
    for name in FILES:
        url = MIRROR_BASE + name
        dest = RAW_DIR / name
        print(f"Downloading {url}")
        try:
            urllib.request.urlretrieve(url, dest)
        except Exception as exc:  # noqa: BLE001 - report and fail cleanly
            print(f"Mirror download failed for {name}: {exc}")
            return False
    return already_downloaded()


def verify() -> None:
    for name in FILES:
        with open(RAW_DIR / name, encoding="utf-8") as fh:
            rows = sum(1 for _ in fh) - 1
        status = "OK" if rows == EXPECTED_ROWS[name] else f"expected {EXPECTED_ROWS[name]:,}"
        print(f"  {name}: {rows:,} rows ({status})")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--mirror", action="store_true", help="skip Kaggle and use the GitHub mirror")
    parser.add_argument("--force", action="store_true", help="re-download even if files exist")
    args = parser.parse_args()

    RAW_DIR.mkdir(parents=True, exist_ok=True)
    if already_downloaded() and not args.force:
        print("Raw files already present in data/raw/.")
        verify()
        return 0

    ok = (not args.mirror and download_kaggle()) or download_mirror()
    if not ok:
        print("Download failed. See the module docstring for manual instructions.")
        return 1
    print("Done.")
    verify()
    return 0


if __name__ == "__main__":
    sys.exit(main())
