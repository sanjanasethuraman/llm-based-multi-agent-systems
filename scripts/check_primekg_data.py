"""Check whether the optional PrimeKG kg.csv dataset is present.

This helper never downloads PrimeKG and does not require the dataset for normal
app startup. By default, a missing file is reported clearly and exits 0 so demo
setup checks can be run on machines without the large dataset.
"""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path


DEFAULT_PATH = Path("data/primekg/kg.csv")
DOWNLOAD_URL = "https://dataverse.harvard.edu/api/access/datafile/6180620"
EXPECTED_COLUMNS = {
    "relation",
    "x_id",
    "x_name",
    "x_type",
    "y_id",
    "y_name",
    "y_type",
}


def inspect_primekg_csv(path: Path) -> dict:
    resolved = path.resolve()
    if not path.exists():
        return {
            "available": False,
            "path": str(resolved),
            "message": "PrimeKG kg.csv is not present.",
            "setupHint": (
                "Download it manually from "
                f"{DOWNLOAD_URL} and save it as data/primekg/kg.csv."
            ),
        }

    if not path.is_file():
        return {
            "available": False,
            "path": str(resolved),
            "message": "PrimeKG path exists but is not a file.",
            "setupHint": "Replace the path with the real PrimeKG kg.csv file.",
        }

    size_bytes = path.stat().st_size
    try:
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            columns = reader.fieldnames or []
            first_row = next(reader, None)
    except UnicodeDecodeError:
        return {
            "available": False,
            "path": str(resolved),
            "sizeBytes": size_bytes,
            "message": "PrimeKG kg.csv could not be decoded as UTF-8 CSV.",
            "setupHint": "Re-download kg.csv from the official Dataverse URL.",
        }
    except csv.Error as exc:
        return {
            "available": False,
            "path": str(resolved),
            "sizeBytes": size_bytes,
            "message": f"PrimeKG kg.csv could not be parsed: {exc}",
            "setupHint": "Check that the file is the official PrimeKG CSV.",
        }

    missing_columns = sorted(EXPECTED_COLUMNS.difference(columns))
    if missing_columns:
        return {
            "available": False,
            "path": str(resolved),
            "sizeBytes": size_bytes,
            "columns": columns,
            "missingColumns": missing_columns,
            "message": "PrimeKG kg.csv is present but does not match the expected schema.",
            "setupHint": "Use the official kg.csv file, not a derived export with renamed columns.",
        }

    return {
        "available": True,
        "path": str(resolved),
        "sizeBytes": size_bytes,
        "columns": columns,
        "hasRows": first_row is not None,
        "message": "PrimeKG kg.csv is present and has the expected core columns.",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--path",
        default=str(DEFAULT_PATH),
        help="Path to PrimeKG kg.csv. Defaults to data/primekg/kg.csv.",
    )
    parser.add_argument(
        "--require",
        action="store_true",
        help="Exit non-zero when kg.csv is missing or invalid.",
    )
    args = parser.parse_args()

    status = inspect_primekg_csv(Path(args.path))
    print(json.dumps(status, indent=2))
    if args.require and not status.get("available"):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
