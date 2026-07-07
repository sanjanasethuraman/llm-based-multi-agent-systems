"""Import filtered PrimeKG subgraphs into Neo4j.

This module imports only the small JSON files produced by
scripts/filter_primekg_subgraph.py. It intentionally does not import the full
PrimeKG kg.csv file and does not touch the existing Entity/Chunk demo graph.
"""

from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from pathlib import Path

try:
    from graph_rag import get_driver, graph_store_status, neo4j_settings
except ImportError:
    from backend.graph_rag import get_driver, graph_store_status, neo4j_settings


DEFAULT_BATCH_SIZE = 500
PRIMEKG_IMPORT_SOURCE = "filtered_primekg_subgraph"


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
