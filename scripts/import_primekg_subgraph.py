"""Import a filtered PrimeKG subgraph JSON file into Neo4j.

This script imports only the bounded output produced by
scripts/filter_primekg_subgraph.py. It never imports the full PrimeKG kg.csv.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.primekg_import import PrimeKGImportError, import_filtered_primekg_subgraph


def parse_bool(value):
    if isinstance(value, bool):
        return value
    normalized = str(value).strip().lower()
    if normalized in {"1", "true", "yes", "y", "on"}:
        return True
    if normalized in {"0", "false", "no", "n", "off"}:
        return False
    raise argparse.ArgumentTypeError(f"Expected true or false, got '{value}'.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, help="Filtered PrimeKG JSON path.")
    parser.add_argument(
        "--clear-primekg-subgraph",
        type=parse_bool,
        default=False,
        help="Delete existing :PrimeNode subgraph before import. Default: false.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate and summarize the import payload without connecting to Neo4j.",
    )
    parser.add_argument("--batch-size", type=int, default=500, help="Neo4j transaction batch size.")
    args = parser.parse_args()

    try:
        summary = import_filtered_primekg_subgraph(
            path=args.input,
            clear_primekg_subgraph=args.clear_primekg_subgraph,
            dry_run=args.dry_run,
            batch_size=args.batch_size,
        )
    except PrimeKGImportError as exc:
        print(f"PrimeKG import error: {exc}", file=sys.stderr)
        return 1

    print(json.dumps(summary, indent=2))
    if summary.get("status") in {"failed"}:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
