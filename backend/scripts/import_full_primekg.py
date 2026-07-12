"""Import the COMPLETE PrimeKG kg.csv into Neo4j (streamed, batched, idempotent).

Unlike scripts/import_primekg_subgraph.py (which imports a small disease-filtered
slice), this loads the full dataset so Graph-RAG and entity detection can search
all of PrimeKG. Disease selection then becomes a read-only visualization query.

Examples:
    python -m backend.scripts.import_full_primekg
    python -m backend.scripts.import_full_primekg --batch-size 10000
    python -m backend.scripts.import_full_primekg --replace-primekg   # migrate old partial slices
    python -m backend.scripts.import_full_primekg --resume            # continue after a failure
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.primekg_import import (  # noqa: E402
    DEFAULT_FULL_BATCH_SIZE,
    DEFAULT_FULL_CSV_PATH,
    PrimeKGImportError,
    import_full_primekg,
    read_full_import_status,
)


def _print_progress(status):
    print(
        f"  batch {status['currentBatch']:>6} | rows {status['rowsProcessed']:>10,} "
        f"| nodes+{status['nodesCreated']:>9,} | rels+{status['relationshipsCreated']:>10,}",
        flush=True,
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--input", default=str(DEFAULT_FULL_CSV_PATH), help="PrimeKG kg.csv path.")
    parser.add_argument("--batch-size", type=int, default=DEFAULT_FULL_BATCH_SIZE,
                        help="CSV rows per Neo4j transaction (env: PRIMEKG_IMPORT_BATCH_SIZE).")
    parser.add_argument("--replace-primekg", action="store_true",
                        help="Delete existing :PrimeNode/:PRIME_REL data first (unrelated Neo4j data is untouched).")
    parser.add_argument("--resume", action="store_true",
                        help="Skip rows already processed per full_import_status.json after a failure.")
    parser.add_argument("--progress-every", type=int, default=20, help="Write status/print every N batches.")
    parser.add_argument("--max-rows", type=int, default=None, help="Stop after N data rows (smoke tests).")
    parser.add_argument("--status", action="store_true", help="Print the current full-import status and exit.")
    args = parser.parse_args()

    if args.status:
        import json
        print(json.dumps(read_full_import_status() or {"status": "none"}, indent=2))
        return 0

    try:
        summary = import_full_primekg(
            csv_path=args.input,
            batch_size=args.batch_size,
            replace_primekg=args.replace_primekg,
            resume=args.resume,
            progress_every=args.progress_every,
            max_rows=args.max_rows,
            progress_callback=_print_progress,
        )
    except PrimeKGImportError as exc:
        print(f"PrimeKG full import error: {exc}", file=sys.stderr)
        return 1

    print(
        f"\nDone: status={summary['status']} "
        f"rows={summary['rowsProcessed']:,} nodesCreated={summary['nodesCreated']:,} "
        f"relsCreated={summary['relationshipsCreated']:,} skipped={summary['skippedRows']:,} "
        f"durationMs={summary.get('durationMs')}"
    )
    return 0 if summary.get("status") == "completed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
