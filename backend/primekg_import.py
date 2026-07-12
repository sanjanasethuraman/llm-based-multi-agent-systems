"""Import filtered PrimeKG subgraphs into Neo4j.

This module imports only the small JSON files produced by
scripts/filter_primekg_subgraph.py. It intentionally does not import the full
PrimeKG kg.csv file and does not touch the existing Entity/Chunk demo graph.
"""

from __future__ import annotations

import csv
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path

try:
    from graph_rag import get_driver, graph_store_status, neo4j_settings
except ImportError:
    from backend.graph_rag import get_driver, graph_store_status, neo4j_settings


DEFAULT_BATCH_SIZE = 500
PRIMEKG_IMPORT_SOURCE = "filtered_primekg_subgraph"

ROOT = Path(__file__).resolve().parents[1]
FULL_IMPORT_SOURCE = "primekg_full"
FULL_IMPORT_STATUS_PATH = ROOT / "data" / "primekg" / "full_import_status.json"
DEFAULT_FULL_CSV_PATH = ROOT / "data" / "primekg" / "kg.csv"
DEFAULT_FULL_BATCH_SIZE = int(os.environ.get("PRIMEKG_IMPORT_BATCH_SIZE", "500") or "500")
DEFAULT_CLEAR_BATCH_SIZE = int(os.environ.get("PRIMEKG_CLEAR_BATCH_SIZE", "1000") or "1000")
FULL_PROGRESS_EVERY = int(os.environ.get("PRIMEKG_IMPORT_PROGRESS_EVERY", "20") or "20")

# Logical column -> accepted CSV header aliases for the full kg.csv importer.
_FULL_COLUMN_CANDIDATES = {
    "relation": ["relation", "rel", "predicate", "edge_type"],
    "display_relation": ["display_relation", "relation_name", "display_rel"],
    "x_index": ["x_index", "x_idx", "source_index"],
    "x_id": ["x_id", "source_id", "subject_id"],
    "x_type": ["x_type", "source_type", "subject_type"],
    "x_name": ["x_name", "source_name", "subject_name"],
    "x_source": ["x_source", "source_source", "subject_source"],
    "y_index": ["y_index", "y_idx", "target_index"],
    "y_id": ["y_id", "target_id", "object_id"],
    "y_type": ["y_type", "target_type", "object_type"],
    "y_name": ["y_name", "target_name", "object_name"],
    "y_source": ["y_source", "target_source", "object_source"],
}
_FULL_REQUIRED = ["relation", "x_id", "x_name", "x_type", "y_id", "y_name", "y_type"]


class PrimeKGImportError(Exception):
    """Raised for user-fixable PrimeKG import errors."""


def load_filtered_subgraph(path):
    input_path = Path(path)
    if not input_path.exists():
        raise PrimeKGImportError(f"Filtered PrimeKG subgraph file not found: {input_path}")
    if not input_path.is_file():
        raise PrimeKGImportError(f"Filtered PrimeKG subgraph path is not a file: {input_path}")

    try:
        payload = json.loads(input_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise PrimeKGImportError(f"Filtered PrimeKG subgraph is not valid JSON: {exc}") from exc

    if not payload.get("ok", True):
        raise PrimeKGImportError(
            "Filtered PrimeKG subgraph is a status/error file, not an importable subgraph: "
            f"{payload.get('error') or payload.get('message') or 'unknown error'}"
        )
    if not isinstance(payload.get("nodes"), list) or not isinstance(payload.get("relationships"), list):
        raise PrimeKGImportError("Filtered PrimeKG JSON must contain 'nodes' and 'relationships' lists.")
    return payload


def build_primekg_import_payload(filtered_payload, input_path=""):
    nodes = []
    node_ids = set()
    skipped_nodes = []

    for index, node in enumerate(filtered_payload.get("nodes") or []):
        prime_id = clean_text(node.get("id") or node.get("prime_id"))
        name = clean_text(node.get("name"))
        node_type = clean_text(node.get("type") or node.get("node_type") or "other")
        if not prime_id or not name:
            skipped_nodes.append({"index": index, "reason": "missing id or name", "node": node})
            continue
        if prime_id in node_ids:
            skipped_nodes.append({"index": index, "reason": "duplicate node id in input", "prime_id": prime_id})
            continue
        node_ids.add(prime_id)
        nodes.append({
            "prime_id": prime_id,
            "name": name,
            "node_type": node_type,
            "source": clean_text(node.get("source")),
            "original_type": clean_text(node.get("originalType") or node.get("original_type")),
            "disease_context": clean_text(filtered_payload.get("diseaseQuery")),
            "raw": safe_json(node),
        })

    relationships = []
    relationship_keys = set()
    skipped_relationships = []
    metadata = filtered_payload.get("metadata") or {}
    import_source = clean_text(metadata.get("input")) or clean_text(input_path) or PRIMEKG_IMPORT_SOURCE

    for index, relationship in enumerate(filtered_payload.get("relationships") or []):
        source_id = clean_text(relationship.get("source"))
        target_id = clean_text(relationship.get("target"))
        relation = clean_text(relationship.get("relation") or relationship.get("type") or "related_to")
        display_relation = clean_text(
            relationship.get("displayRelation")
            or relationship.get("display_relation")
            or relation
        )
        if not source_id or not target_id or not relation:
            skipped_relationships.append({
                "index": index,
                "reason": "missing source, target, or relation",
                "relationship": relationship,
            })
            continue
        if source_id not in node_ids or target_id not in node_ids:
            skipped_relationships.append({
                "index": index,
                "reason": "source or target node missing from filtered nodes",
                "source": source_id,
                "target": target_id,
            })
            continue
        relationship_key = clean_text(relationship.get("id")) or f"{source_id}|{relation}|{target_id}"
        if relationship_key in relationship_keys:
            skipped_relationships.append({
                "index": index,
                "reason": "duplicate relationship id in input",
                "id": relationship_key,
            })
            continue
        relationship_keys.add(relationship_key)
        relationships.append({
            "prime_key": relationship_key,
            "source_id": source_id,
            "target_id": target_id,
            "relation": relation,
            "display_relation": display_relation,
            "source": PRIMEKG_IMPORT_SOURCE,
            "prime_source": import_source,
            "depth": relationship.get("depth"),
            "raw": safe_json(relationship),
        })

    return {
        "nodes": nodes,
        "relationships": relationships,
        "skippedNodes": skipped_nodes,
        "skippedRelationships": skipped_relationships,
        "metadata": {
            "diseaseQuery": filtered_payload.get("diseaseQuery"),
            "matchedDiseaseNodes": filtered_payload.get("matchedDiseaseNodes") or [],
            "input": str(input_path) if input_path else "",
            "sourceMetadata": metadata,
        },
    }


def import_filtered_primekg_subgraph(path, clear_primekg_subgraph=False, dry_run=False, batch_size=DEFAULT_BATCH_SIZE, config=None):
    started = time.perf_counter()
    input_path = Path(path)
    filtered_payload = load_filtered_subgraph(input_path)
    import_payload = build_primekg_import_payload(filtered_payload, input_path=str(input_path.resolve()))
    imported_at = datetime.now(timezone.utc).isoformat()
    summary = {
        "status": "dry_run" if dry_run else "pending",
        "backend": "neo4j",
        "input": str(input_path.resolve()),
        "dryRun": bool(dry_run),
        "clearPrimekgSubgraph": bool(clear_primekg_subgraph),
        "nodesImported": 0,
        "relationshipsImported": 0,
        "skippedNodes": len(import_payload["skippedNodes"]),
        "skippedRelationships": len(import_payload["skippedRelationships"]),
        "nodeCount": len(import_payload["nodes"]),
        "relationshipCount": len(import_payload["relationships"]),
        "errors": [],
        "details": {
            "skippedNodes": import_payload["skippedNodes"][:25],
            "skippedRelationships": import_payload["skippedRelationships"][:25],
            "metadata": import_payload["metadata"],
        },
    }

    if dry_run:
        summary["status"] = "dry_run"
        summary["durationMs"] = round((time.perf_counter() - started) * 1000, 2)
        return summary

    status = graph_store_status(config)
    if not status.get("enabled"):
        summary["status"] = "disabled"
        summary["errors"].append(status.get("message") or "Neo4j Graph RAG is disabled.")
        summary["store"] = status
        summary["durationMs"] = round((time.perf_counter() - started) * 1000, 2)
        return summary
    if not status.get("connected"):
        summary["status"] = "unavailable"
        summary["errors"].append(status.get("message") or "Neo4j is not reachable.")
        summary["store"] = status
        summary["durationMs"] = round((time.perf_counter() - started) * 1000, 2)
        return summary

    settings = neo4j_settings(config)
    try:
        with get_driver(config) as driver:
            with driver.session(database=settings["database"]) as session:
                ensure_primekg_schema(session)
                if clear_primekg_subgraph:
                    session.execute_write(_clear_primekg_subgraph_tx)
                for batch in chunked(import_payload["nodes"], int(batch_size or DEFAULT_BATCH_SIZE)):
                    session.execute_write(_merge_primekg_nodes_tx, batch, imported_at)
                    summary["nodesImported"] += len(batch)
                for batch in chunked(import_payload["relationships"], int(batch_size or DEFAULT_BATCH_SIZE)):
                    session.execute_write(_merge_primekg_relationships_tx, batch, imported_at)
                    summary["relationshipsImported"] += len(batch)
    except Exception as exc:
        summary["status"] = "failed"
        summary["errors"].append(str(exc))
        summary["store"] = graph_store_status(config)
        summary["durationMs"] = round((time.perf_counter() - started) * 1000, 2)
        return summary

    summary["status"] = "imported"
    summary["durationMs"] = round((time.perf_counter() - started) * 1000, 2)
    return summary


def ensure_primekg_schema(session):
    session.run("CREATE CONSTRAINT prime_node_prime_id IF NOT EXISTS FOR (n:PrimeNode) REQUIRE n.prime_id IS UNIQUE")
    session.run("CREATE INDEX prime_node_name IF NOT EXISTS FOR (n:PrimeNode) ON (n.name)")
    session.run("CREATE INDEX prime_node_type IF NOT EXISTS FOR (n:PrimeNode) ON (n.node_type)")


def _clear_primekg_subgraph_tx(tx):
    tx.run("MATCH (n:PrimeNode) DETACH DELETE n")


def _clear_primekg_relationships_batch_tx(tx, limit):
    result = tx.run(
        """
        MATCH ()-[r:PRIME_REL]-()
        WITH r LIMIT $limit
        DELETE r
        RETURN count(r) AS deleted
        """,
        limit=int(limit),
    )
    row = result.single()
    return int(row["deleted"] if row else 0)


def _clear_primekg_nodes_batch_tx(tx, limit):
    result = tx.run(
        """
        MATCH (n:PrimeNode)
        WITH n LIMIT $limit
        DELETE n
        RETURN count(n) AS deleted
        """,
        limit=int(limit),
    )
    row = result.single()
    return int(row["deleted"] if row else 0)


def clear_primekg_in_batches(session, batch_size=None):
    batch_size = max(1, int(batch_size or DEFAULT_CLEAR_BATCH_SIZE))
    deleted_relationships = 0
    deleted_nodes = 0
    while True:
        deleted = session.execute_write(_clear_primekg_relationships_batch_tx, batch_size)
        deleted_relationships += deleted
        if deleted == 0:
            break
    while True:
        deleted = session.execute_write(_clear_primekg_nodes_batch_tx, batch_size)
        deleted_nodes += deleted
        if deleted == 0:
            break
    return {"relationships": deleted_relationships, "nodes": deleted_nodes}


def _merge_primekg_nodes_tx(tx, nodes, imported_at):
    tx.run(
        """
        UNWIND $nodes AS node
        MERGE (n:PrimeNode {prime_id: node.prime_id})
        SET n.name = node.name,
            n.node_type = node.node_type,
            n.source = node.source,
            n.original_type = node.original_type,
            n.disease_context = node.disease_context,
            n.raw = node.raw,
            n.imported_at = $importedAt,
            n.updated_at = $importedAt
        """,
        nodes=nodes,
        importedAt=imported_at,
    )


def _merge_primekg_relationships_tx(tx, relationships, imported_at):
    tx.run(
        """
        UNWIND $relationships AS relationship
        MATCH (source:PrimeNode {prime_id: relationship.source_id})
        MATCH (target:PrimeNode {prime_id: relationship.target_id})
        MERGE (source)-[r:PRIME_REL {prime_key: relationship.prime_key}]->(target)
        SET r.relation = relationship.relation,
            r.display_relation = relationship.display_relation,
            r.source = relationship.source,
            r.prime_source = relationship.prime_source,
            r.depth = relationship.depth,
            r.raw = relationship.raw,
            r.imported_at = $importedAt,
            r.updated_at = $importedAt
        """,
        relationships=relationships,
        importedAt=imported_at,
    )


def chunked(items, size):
    safe_size = max(1, int(size or DEFAULT_BATCH_SIZE))
    for index in range(0, len(items), safe_size):
        yield items[index:index + safe_size]


def clean_text(value):
    if value is None:
        return ""
    return str(value).strip()


def safe_json(value):
    return json.dumps(value or {}, sort_keys=True, ensure_ascii=True)


# ---------------------------------------------------------------------------
# Full PrimeKG import (streams the complete kg.csv into Neo4j in batches).
# ---------------------------------------------------------------------------


def _normalize_header(name):
    return " ".join(str(name or "").strip().casefold().replace("_", " ").split())


def detect_full_columns(fieldnames):
    if not fieldnames:
        raise PrimeKGImportError("PrimeKG kg.csv has no header row.")
    by_normalized = {_normalize_header(name): name for name in fieldnames}
    detected = {}
    for logical, candidates in _FULL_COLUMN_CANDIDATES.items():
        for candidate in candidates:
            actual = by_normalized.get(_normalize_header(candidate))
            if actual:
                detected[logical] = actual
                break
    missing = [field for field in _FULL_REQUIRED if field not in detected]
    if missing:
        raise PrimeKGImportError(
            "Could not detect required PrimeKG columns: "
            f"{', '.join(missing)}. Found: {', '.join(fieldnames)}"
        )
    return detected


def _node_key(index_value, node_type, node_id):
    """Stable, collision-free PrimeKG node id.

    PrimeKG node indexes are globally unique per node; ontology ids can repeat
    across node types, so we prefer the index and fall back to a typed id.
    """
    index_value = clean_text(index_value)
    if index_value:
        return index_value
    return f"{clean_text(node_type)}:{clean_text(node_id)}"


def _row_to_full_records(row, columns):
    """Return (x_node, y_node, relationship) dicts for one kg.csv row, or None."""
    x_id = clean_text(row.get(columns["x_id"]))
    y_id = clean_text(row.get(columns["y_id"]))
    x_name = clean_text(row.get(columns["x_name"]))
    y_name = clean_text(row.get(columns["y_name"]))
    relation = clean_text(row.get(columns["relation"])) or "related_to"
    if not x_name or not y_name or not (x_id or row.get(columns.get("x_index", ""))):
        return None
    x_key = _node_key(row.get(columns.get("x_index", "")), row.get(columns["x_type"]), x_id)
    y_key = _node_key(row.get(columns.get("y_index", "")), row.get(columns["y_type"]), y_id)
    if not x_key or not y_key:
        return None
    display = clean_text(row.get(columns.get("display_relation", ""))) if columns.get("display_relation") else ""
    x_node = {
        "prime_id": x_key,
        "prime_index": clean_text(row.get(columns.get("x_index", ""))),
        "id": x_id,
        "name": x_name,
        "node_type": clean_text(row.get(columns["x_type"])) or "other",
        "source": clean_text(row.get(columns.get("x_source", ""))) if columns.get("x_source") else "",
    }
    y_node = {
        "prime_id": y_key,
        "prime_index": clean_text(row.get(columns.get("y_index", ""))),
        "id": y_id,
        "name": y_name,
        "node_type": clean_text(row.get(columns["y_type"])) or "other",
        "source": clean_text(row.get(columns.get("y_source", ""))) if columns.get("y_source") else "",
    }
    relationship = {
        "prime_key": f"{x_key}|{relation}|{y_key}",
        "source_id": x_key,
        "target_id": y_key,
        "relation": relation,
        "display_relation": display or relation,
        "source": FULL_IMPORT_SOURCE,
    }
    return x_node, y_node, relationship


def source_file_fingerprint(path):
    """Cheap, deterministic source-file metadata (avoids hashing ~1GB)."""
    resolved = Path(path)
    try:
        stat = resolved.stat()
    except OSError:
        return {"path": str(resolved), "available": False}
    return {
        "path": str(resolved),
        "available": True,
        "sizeBytes": stat.st_size,
        "modifiedAt": datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat(),
        "fingerprint": f"{stat.st_size}:{int(stat.st_mtime)}",
        "fingerprintMethod": "size:mtime",
    }


def read_full_import_status(status_path=None):
    path = Path(status_path or FULL_IMPORT_STATUS_PATH)
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"status": "unreadable", "path": str(path)}


def _write_full_import_status(status, status_path=None):
    path = Path(status_path or FULL_IMPORT_STATUS_PATH)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(status, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)


def full_dataset_available(status_path=None):
    status = read_full_import_status(status_path)
    return bool(status and status.get("status") == "completed")


def _merge_full_nodes_tx(tx, nodes, imported_at):
    result = tx.run(
        """
        UNWIND $nodes AS node
        MERGE (n:PrimeNode {prime_id: node.prime_id})
        SET n.name = node.name,
            n.node_type = node.node_type,
            n.source = node.source,
            n.id = node.id,
            n.prime_index = node.prime_index,
            n.imported_at = coalesce(n.imported_at, $importedAt),
            n.updated_at = $importedAt
        """,
        nodes=nodes,
        importedAt=imported_at,
    )
    return result.consume().counters.nodes_created


def _merge_full_relationships_tx(tx, relationships, imported_at):
    result = tx.run(
        """
        UNWIND $relationships AS rel
        MATCH (source:PrimeNode {prime_id: rel.source_id})
        MATCH (target:PrimeNode {prime_id: rel.target_id})
        MERGE (source)-[r:PRIME_REL {prime_key: rel.prime_key}]->(target)
        SET r.relation = rel.relation,
            r.display_relation = rel.display_relation,
            r.source = rel.source,
            r.prime_source = rel.source,
            r.imported_at = coalesce(r.imported_at, $importedAt),
            r.updated_at = $importedAt
        """,
        relationships=relationships,
        importedAt=imported_at,
    )
    return result.consume().counters.relationships_created


def _dedupe_nodes(batch_rows):
    nodes_by_id = {}
    relationships = []
    for record in batch_rows:
        x_node, y_node, relationship = record
        nodes_by_id[x_node["prime_id"]] = x_node
        nodes_by_id[y_node["prime_id"]] = y_node
        relationships.append(relationship)
    return list(nodes_by_id.values()), relationships


def import_full_primekg(
    csv_path=None,
    batch_size=None,
    replace_primekg=False,
    resume=False,
    progress_every=None,
    config=None,
    session=None,
    status_path=None,
    max_rows=None,
    progress_callback=None,
):
    """Stream the complete PrimeKG kg.csv into Neo4j in idempotent batches.

    Memory stays bounded to one batch. Re-running is safe (MERGE). Pass
    ``session`` to reuse an open Neo4j session (used by tests); otherwise a
    driver is opened from config/env. ``replace_primekg`` clears only the
    existing :PrimeNode/:PRIME_REL data first, never unrelated Neo4j data.
    """
    csv_path = Path(csv_path or DEFAULT_FULL_CSV_PATH)
    batch_size = max(1, int(batch_size or DEFAULT_FULL_BATCH_SIZE))
    progress_every = max(1, int(progress_every or FULL_PROGRESS_EVERY))
    started_perf = time.perf_counter()

    if not csv_path.exists() or not csv_path.is_file():
        raise PrimeKGImportError(f"PrimeKG kg.csv not found at {csv_path}.")

    skip_rows = 0
    if resume:
        previous = read_full_import_status(status_path)
        if previous and previous.get("status") in {"running", "failed"}:
            skip_rows = int(previous.get("rowsProcessed") or 0)

    status = {
        "status": "running",
        "backend": "neo4j",
        "sourceFile": str(csv_path),
        "sourceFingerprint": source_file_fingerprint(csv_path),
        "batchSize": batch_size,
        "replacePrimekg": bool(replace_primekg),
        "resumedFromRow": skip_rows,
        "startedAt": datetime.now(timezone.utc).isoformat(),
        "completedAt": None,
        "rowsProcessed": skip_rows,
        "relationshipsProcessed": 0,
        "nodesMerged": 0,
        "nodesCreated": 0,
        "relationshipsCreated": 0,
        "skippedRows": 0,
        "currentBatch": 0,
        "constraintsCreated": False,
        "clearBatchSize": DEFAULT_CLEAR_BATCH_SIZE,
        "clearedPrimekg": {"nodes": 0, "relationships": 0},
        "errors": [],
    }
    _write_full_import_status(status, status_path)

    def _run(active_session):
        imported_at = datetime.now(timezone.utc).isoformat()
        ensure_primekg_schema(active_session)
        status["constraintsCreated"] = True
        if replace_primekg:
            status["clearedPrimekg"] = clear_primekg_in_batches(active_session)
            _write_full_import_status(status, status_path)

        with csv_path.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            columns = detect_full_columns(reader.fieldnames)
            batch = []
            rows_since_resume = 0
            data_row_index = 0
            for row in reader:
                data_row_index += 1
                if data_row_index <= skip_rows:
                    continue
                if max_rows is not None and rows_since_resume >= max_rows:
                    break
                rows_since_resume += 1
                record = _row_to_full_records(row, columns)
                if record is None:
                    status["rowsProcessed"] += 1
                    status["skippedRows"] += 1
                    continue
                batch.append(record)
                if len(batch) >= batch_size:
                    _flush_batch(active_session, batch, imported_at, status)
                    status["rowsProcessed"] += len(batch)
                    batch = []
                    if status["currentBatch"] % progress_every == 0:
                        _write_full_import_status(status, status_path)
                        if progress_callback:
                            progress_callback(status)
            if batch:
                _flush_batch(active_session, batch, imported_at, status)
                status["rowsProcessed"] += len(batch)

    try:
        if session is not None:
            _run(session)
        else:
            store = graph_store_status(config)
            if not store.get("enabled"):
                raise PrimeKGImportError(store.get("message") or "Neo4j Graph RAG is disabled.")
            if not store.get("connected"):
                raise PrimeKGImportError(store.get("message") or "Neo4j is not reachable.")
            settings = neo4j_settings(config)
            with get_driver(config) as driver:
                with driver.session(database=settings["database"]) as active_session:
                    _run(active_session)
    except Exception as exc:
        status["status"] = "failed"
        status["errors"].append(str(exc))
        status["durationMs"] = round((time.perf_counter() - started_perf) * 1000, 2)
        _write_full_import_status(status, status_path)
        raise PrimeKGImportError(str(exc)) if not isinstance(exc, PrimeKGImportError) else exc

    status["status"] = "completed"
    status["relationshipsProcessed"] = status["rowsProcessed"] - status["skippedRows"] - skip_rows
    status["completedAt"] = datetime.now(timezone.utc).isoformat()
    status["durationMs"] = round((time.perf_counter() - started_perf) * 1000, 2)
    _write_full_import_status(status, status_path)
    return status


def _flush_batch(active_session, batch, imported_at, status):
    nodes, relationships = _dedupe_nodes(batch)
    nodes_created = active_session.execute_write(_merge_full_nodes_tx, nodes, imported_at)
    rels_created = active_session.execute_write(_merge_full_relationships_tx, relationships, imported_at)
    status["currentBatch"] += 1
    status["nodesMerged"] += len(nodes)
    status["nodesCreated"] += int(nodes_created or 0)
    status["relationshipsCreated"] += int(rels_created or 0)
