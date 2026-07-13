"""API helpers for PrimeKG search and read-only visualization."""

from __future__ import annotations

import json
import re
import time
import csv
from pathlib import Path

try:
    from graph_rag import get_driver, graph_store_status, neo4j_settings
    from primekg_import import (
        PrimeKGImportError,
        full_dataset_available,
        import_filtered_primekg_subgraph,
        read_full_import_status,
    )
except ImportError:
    from backend.graph_rag import get_driver, graph_store_status, neo4j_settings
    from backend.primekg_import import (
        PrimeKGImportError,
        full_dataset_available,
        import_filtered_primekg_subgraph,
        read_full_import_status,
    )

try:
    from scripts.filter_primekg_subgraph import (
        PrimeKGFilterError,
        detect_columns,
        filter_subgraph,
        normalize_text,
        parse_allowed_types,
        parse_csv_list,
        row_node,
        write_json,
    )
except ImportError:
    PrimeKGFilterError = ValueError
    detect_columns = None
    filter_subgraph = None
    normalize_text = None
    parse_allowed_types = None
    parse_csv_list = None
    row_node = None
    write_json = None


ROOT = Path(__file__).resolve().parents[1]
PRIMEKG_DIR = ROOT / "data" / "primekg"
APP_PRIMEKG_DIR = PRIMEKG_DIR
DEFAULT_CSV_PATH = PRIMEKG_DIR / "kg.csv"
PREVIEW_DIR = PRIMEKG_DIR / "previews"
LAST_IMPORT_PATH = PRIMEKG_DIR / "last_import_summary.json"
DEPRECATED_FILTER_IMPORT_MESSAGE = (
    "Disease-filtered PrimeKG importing is deprecated. Neo4j is expected to "
    "contain the complete PrimeKG dataset; use /api/primekg/graph for bounded "
    "read-only visualization."
)

API_MAX_DEPTH = 3
API_MAX_NODES = 5000
API_MAX_RELATIONSHIPS = 15000
API_DEFAULT_NODES = 1000
API_DEFAULT_RELATIONSHIPS = 3000
SAMPLE_LIMIT = 25
VISUAL_MAX_NODES = 300
VISUAL_MAX_RELATIONSHIPS = 600
VISUAL_DEFAULT_NODES = 120
VISUAL_DEFAULT_RELATIONSHIPS = 250
DISEASE_SEARCH_DEFAULT_LIMIT = 20
DISEASE_SEARCH_MAX_LIMIT = 50
DISEASE_FULL_CACHE_MAX_BYTES = 50 * 1024 * 1024
DISEASE_FAST_SCAN_ROWS = 250_000
FAKE_DATA_MARKERS = ("fake-test-only", "fake test data only")
FAKE_ANCHOR_MARKERS = (*FAKE_DATA_MARKERS, "fake-")

_disease_cache = {}
_disease_query_cache = {}


class PrimeKGApiError(Exception):
    """Raised for safe, user-facing PrimeKG API errors."""


def primekg_status():
    csv_path = DEFAULT_CSV_PATH
    graph_status = graph_store_status()
    full_import = read_full_import_status()
    dataset_complete = full_dataset_available()
    return {
        "configured": csv_path.exists(),
        "defaultCsvPath": relative_path(csv_path),
        "fileExists": csv_path.exists(),
        "neo4jConnected": bool(graph_status.get("connected")),
        "fullImport": full_import,
        "datasetComplete": dataset_complete,
        "datasetMode": "full" if dataset_complete else "partial-or-empty",
        "neo4j": {
            "enabled": graph_status.get("enabled"),
            "available": graph_status.get("available"),
            "connected": graph_status.get("connected"),
            "uri": graph_status.get("uri"),
            "database": graph_status.get("database"),
            "driverInstalled": graph_status.get("driverInstalled"),
            "message": graph_status.get("message"),
            "setupHint": graph_status.get("setupHint"),
        },
        "lastImportSummary": load_last_import_summary(),
        "limits": {
            "maxDepth": API_MAX_DEPTH,
            "maxNodes": API_MAX_NODES,
            "maxRelationships": API_MAX_RELATIONSHIPS,
        },
        "message": (
            "PrimeKG kg.csv is available."
            if csv_path.exists()
            else "PrimeKG kg.csv is missing. Place it at data/primekg/kg.csv."
        ),
    }


def contains_fake_marker(*values):
    text = " ".join(str(value or "") for value in values).casefold()
    return any(marker in text for marker in FAKE_DATA_MARKERS)


def contains_fake_anchor_marker(*values):
    text = " ".join(str(value or "") for value in values).casefold()
    return any(marker in text for marker in FAKE_ANCHOR_MARKERS)


def is_runtime_primekg_path(path):
    try:
        resolved = Path(path).resolve()
        runtime_dir = APP_PRIMEKG_DIR.resolve()
    except OSError:
        return False
    return resolved == runtime_dir / "kg.csv" or runtime_dir in resolved.parents


def is_fake_primekg_node(node):
    return contains_fake_marker(
        node.get("id"),
        node.get("prime_id"),
        node.get("name"),
        node.get("source"),
        node.get("disease_context"),
        node.get("diseaseContext"),
    )


def is_fake_primekg_relationship(relationship):
    return contains_fake_marker(
        relationship.get("id"),
        relationship.get("source"),
        relationship.get("target"),
        relationship.get("sourceName"),
        relationship.get("targetName"),
        relationship.get("prime_source"),
    )


def search_diseases_from_neo4j(query_text, limit):
    """Fast disease lookup from the imported graph (node_type index).

    Returns a response dict when Neo4j is usable, else None so the caller can
    fall back to the CSV scan. Preferred once the full graph is imported: the
    ~982MB kg.csv is front-loaded with gene-gene rows, so a linear CSV scan for
    disease matches is pathologically slow.
    """
    try:
        status = graph_store_status()
        if not status.get("connected"):
            return None
        settings = neo4j_settings()
        q = query_text.strip().lower()
        with get_driver() as driver:
            with driver.session(database=settings["database"]) as session:
                if not session.run(
                    "MATCH (n:PrimeNode {node_type:'disease'}) RETURN n LIMIT 1"
                ).single():
                    return None
                fetch = min(int(limit) * 5, 250)  # over-fetch so dedup still fills `limit`
                if q:
                    rows = session.run(
                        """
                        MATCH (n:PrimeNode)
                        WHERE n.node_type = 'disease'
                          AND NOT toLower(coalesce(n.source,'')) CONTAINS 'fake-test-only'
                          AND toLower(n.name) CONTAINS $q
                        RETURN coalesce(n.prime_id, n.id) AS id, n.name AS name, n.source AS source,
                               CASE WHEN toLower(n.name) = $q THEN 'exact'
                                    WHEN toLower(n.name) STARTS WITH $q THEN 'prefix'
                                    ELSE 'contains' END AS match
                        ORDER BY CASE WHEN toLower(n.name) = $q THEN 0
                                      WHEN toLower(n.name) STARTS WITH $q THEN 1 ELSE 2 END,
                                 size(n.name)
                        LIMIT $fetch
                        """,
                        q=q, fetch=fetch,
                    ).data()
                else:
                    rows = session.run(
                        """
                        MATCH (n:PrimeNode)
                        WHERE n.node_type = 'disease'
                          AND NOT toLower(coalesce(n.source,'')) CONTAINS 'fake-test-only'
                        RETURN coalesce(n.prime_id, n.id) AS id, n.name AS name, n.source AS source,
                               'contains' AS match
                        ORDER BY size(n.name)
                        LIMIT $fetch
                        """,
                        fetch=fetch,
                    ).data()
    except Exception:
        return None

    diseases = []
    seen_names = set()
    for r in rows:
        rid, name = r.get("id"), r.get("name")
        if not rid or not name:
            continue
        key = name.strip().lower()
        if key in seen_names:  # collapse same-named disease nodes (multiple indices)
            continue
        seen_names.add(key)
        diseases.append({"id": rid, "name": name, "node_type": "disease",
                         "source": r.get("source") or "", "match": r.get("match") or "contains"})
        if len(diseases) >= int(limit):
            break
    return {
        "available": True,
        "query": query_text,
        "count": len(diseases),
        "diseases": diseases,
        "csvPath": "",
        "cacheMode": "neo4j",
    }


def search_diseases(query="", limit=DISEASE_SEARCH_DEFAULT_LIMIT, csv_path=None):
    """Return bounded disease suggestions from the imported graph, or kg.csv."""

    path = Path(csv_path) if csv_path else DEFAULT_CSV_PATH
    if not path.is_absolute():
        path = ROOT / path
    limit = bounded_int(limit, 1, DISEASE_SEARCH_MAX_LIMIT, "limit")
    query_text = str(query or "").strip()

    # Prefer the indexed graph; fall back to the CSV scan only if Neo4j is down.
    if not csv_path:
        graph_result = search_diseases_from_neo4j(query_text, limit)
        if graph_result is not None:
            return graph_result

    if not path.exists():
        return {
            "available": False,
            "query": query_text,
            "count": 0,
            "diseases": [],
            "csvPath": relative_path(path),
            "message": "PrimeKG kg.csv not found. Download/place it in data/primekg/kg.csv.",
        }
    if not path.is_file():
        return {
            "available": False,
            "query": query_text,
            "count": 0,
            "diseases": [],
            "csvPath": relative_path(path),
            "message": "PrimeKG disease search path is not a file.",
        }

    try:
        stat = path.stat()
        if stat.st_size <= DISEASE_FULL_CACHE_MAX_BYTES:
            diseases = load_cached_diseases(path)
            ranked = rank_disease_matches(diseases, query_text, limit)
            cache_mode = "complete"
            total_diseases = len(diseases)
        else:
            ranked, total_diseases, cache_mode = fast_search_diseases(path, query_text, limit, stat)
    except PrimeKGApiError as exc:
        return {
            "available": False,
            "query": query_text,
            "count": 0,
            "diseases": [],
            "csvPath": relative_path(path),
            "message": str(exc),
        }

    return {
        "available": True,
        "query": query_text,
        "count": len(ranked),
        "totalDiseases": total_diseases,
        "diseases": ranked,
        "csvPath": relative_path(path),
        "cacheMode": cache_mode,
    }


def load_cached_diseases(path):
    if detect_columns is None or row_node is None:
        raise PrimeKGApiError("PrimeKG disease search is unavailable because CSV helpers could not be imported.")

    resolved = Path(path).resolve()
    try:
        stat = resolved.stat()
    except OSError as exc:
        raise PrimeKGApiError(f"PrimeKG kg.csv could not be read: {exc}") from exc

    cache_key = str(resolved)
    cached = _disease_cache.get(cache_key)
    if cached and cached.get("mtime") == stat.st_mtime and cached.get("size") == stat.st_size:
        return cached["diseases"]

    diseases_by_id = {}
    try:
        with resolved.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            columns = detect_columns(reader.fieldnames)
            for row in reader:
                for side in ("x", "y"):
                    node = row_node(row, columns, side)
                    if is_runtime_primekg_path(path) and is_fake_primekg_node(node):
                        continue
                    if node.get("type") != "disease" or not node.get("id"):
                        continue
                    disease_id = str(node.get("id") or "").strip()
                    if not disease_id or disease_id in diseases_by_id:
                        continue
                    disease_name = str(node.get("name") or disease_id).strip() or disease_id
                    diseases_by_id[disease_id] = {
                        "id": disease_id,
                        "name": disease_name,
                        "node_type": "disease",
                        "source": node.get("source") or "",
                        "searchName": normalize_text(disease_name) if normalize_text else disease_name.casefold(),
                        "searchId": normalize_text(disease_id) if normalize_text else disease_id.casefold(),
                    }
    except PrimeKGFilterError as exc:
        raise PrimeKGApiError(str(exc)) from exc
    except OSError as exc:
        raise PrimeKGApiError(f"PrimeKG kg.csv could not be read: {exc}") from exc

    diseases = sorted(diseases_by_id.values(), key=lambda item: item["searchName"])
    _disease_cache[cache_key] = {
        "mtime": stat.st_mtime,
        "size": stat.st_size,
        "diseases": diseases,
    }
    return diseases


def fast_search_diseases(path, query_text, limit, stat):
    resolved = Path(path).resolve()
    normalized_query = normalize_text(query_text) if normalize_text else query_text.casefold()
    cache_key = (str(resolved), stat.st_mtime, stat.st_size, normalized_query, limit)
    cached = _disease_query_cache.get(cache_key)
    if cached:
        return cached["diseases"], cached["total"], "query-cache"

    diseases_by_id = {}
    rows_scanned = 0
    try:
        with resolved.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            columns = detect_columns(reader.fieldnames)
            for row in reader:
                rows_scanned += 1
                for side in ("x", "y"):
                    node = row_node(row, columns, side)
                    if is_runtime_primekg_path(path) and is_fake_primekg_node(node):
                        continue
                    if node.get("type") != "disease" or not node.get("id"):
                        continue
                    disease_id = str(node.get("id") or "").strip()
                    disease_name = str(node.get("name") or disease_id).strip() or disease_id
                    disease = {
                        "id": disease_id,
                        "name": disease_name,
                        "node_type": "disease",
                        "source": node.get("source") or "",
                        "searchName": normalize_text(disease_name) if normalize_text else disease_name.casefold(),
                        "searchId": normalize_text(disease_id) if normalize_text else disease_id.casefold(),
                    }
                    match = disease_match_kind(disease, normalized_query)
                    if match and disease_id not in diseases_by_id:
                        diseases_by_id[disease_id] = {**disease, "match": match}
                if rows_scanned >= DISEASE_FAST_SCAN_ROWS and len(diseases_by_id) >= limit:
                    break
    except PrimeKGFilterError as exc:
        raise PrimeKGApiError(str(exc)) from exc
    except OSError as exc:
        raise PrimeKGApiError(f"PrimeKG kg.csv could not be read: {exc}") from exc

    ranked = [public_disease(item) for item in sorted(diseases_by_id.values(), key=disease_sort_key)[:limit]]
    _disease_query_cache[cache_key] = {"diseases": ranked, "total": len(diseases_by_id)}
    return ranked, len(diseases_by_id), "bounded-query-scan"


def rank_disease_matches(diseases, query_text, limit):
    normalized_query = normalize_text(query_text) if normalize_text else query_text.casefold()
    matches = []
    for disease in diseases:
        match = disease_match_kind(disease, normalized_query)
        if match:
            matches.append({**disease, "match": match})
    return [public_disease(item) for item in sorted(matches, key=disease_sort_key)[:limit]]


def disease_match_kind(disease, normalized_query):
    if not normalized_query:
        return "contains"
    if disease["searchName"] == normalized_query or disease["searchId"] == normalized_query:
        return "exact"
    if disease["searchName"].startswith(normalized_query) or disease["searchId"].startswith(normalized_query):
        return "prefix"
    if normalized_query in disease["searchName"] or normalized_query in disease["searchId"]:
        return "contains"
    return ""


def disease_sort_key(disease):
    priority = {"exact": 0, "prefix": 1, "contains": 2}
    return (priority.get(disease.get("match"), 3), disease.get("name", "").casefold(), disease.get("id", ""))


def public_disease(disease):
    return {
        "id": disease.get("id", ""),
        "name": disease.get("name", ""),
        "node_type": disease.get("node_type", "disease"),
        "source": disease.get("source", ""),
        "match": disease.get("match", "contains"),
    }


def filter_preview(payload):
    disease = str(payload.get("disease") or "").strip()
    return {
        "ok": False,
        "status": "deprecated",
        "deprecated": True,
        "disease": disease,
        "outputPath": "",
        "nodeCount": 0,
        "relationshipCount": 0,
        "warnings": [DEPRECATED_FILTER_IMPORT_MESSAGE],
        "message": DEPRECATED_FILTER_IMPORT_MESSAGE,
        "replacementEndpoint": "/api/primekg/graph",
    }


def import_filtered(payload):
    return {
        "status": "deprecated",
        "deprecated": True,
        "nodesImported": 0,
        "relationshipsImported": 0,
        "message": DEPRECATED_FILTER_IMPORT_MESSAGE,
        "replacementEndpoint": "/api/primekg/graph",
    }


def filter_and_import(payload):
    return {
        "status": "deprecated",
        "deprecated": True,
        "preview": filter_preview(payload),
        "importSummary": import_filtered(payload),
        "message": DEPRECATED_FILTER_IMPORT_MESSAGE,
        "replacementEndpoint": "/api/primekg/graph",
    }


def primekg_graph(payload):
    """Return a bounded visual graph from the imported PrimeKG subgraph."""

    graph_status = graph_store_status()
    if not graph_status.get("enabled"):
        return empty_visual_graph(
            "disabled",
            graph_status.get("message") or "Neo4j Graph RAG is disabled.",
            graph_status,
        )
    if not graph_status.get("connected"):
        return empty_visual_graph(
            "unavailable",
            graph_status.get("message") or "Neo4j is not reachable.",
            graph_status,
        )

    disease = str(payload.get("disease") or "").strip()
    anchor_node_ids = normalize_anchor_values(payload.get("anchorNodeIds") or payload.get("anchorIds") or [])
    anchor_node_names = normalize_anchor_values(payload.get("anchorNodeNames") or payload.get("anchorNames") or [])
    answer_graph_requested = bool(anchor_node_ids or anchor_node_names)
    if (
        answer_graph_requested
        and graph_status.get("backend") == "neo4j"
        and any(contains_fake_anchor_marker(anchor) for anchor in [*anchor_node_ids, *anchor_node_names])
    ):
        return empty_visual_graph("unavailable", "Fake PrimeKG test anchors are not shown in the app graph.", graph_status, disease=disease)
    max_depth = 2 if answer_graph_requested else API_MAX_DEPTH
    depth = bounded_int(payload.get("depth", 2), 1, max_depth, "depth")
    max_nodes = bounded_int(payload.get("maxNodes", VISUAL_DEFAULT_NODES), 1, VISUAL_MAX_NODES, "maxNodes")
    max_relationships = bounded_int(
        payload.get("maxRelationships", VISUAL_DEFAULT_RELATIONSHIPS),
        1,
        VISUAL_MAX_RELATIONSHIPS,
        "maxRelationships",
    )

    try:
        settings = neo4j_settings()
        with get_driver() as driver:
            with driver.session(database=settings["database"]) as session:
                has_primekg = session.run("MATCH (n:PrimeNode) RETURN count(n) AS count LIMIT 1").single()
                if not has_primekg or not int(has_primekg.get("count") or 0):
                    return empty_visual_graph(
                        "empty",
                        "No PrimeKG graph was found in Neo4j. Import the complete PrimeKG dataset first.",
                        graph_status,
                    )

                seeds = find_visual_anchor_nodes(session, anchor_node_ids, anchor_node_names) if answer_graph_requested else find_visual_seed_nodes(session, disease)
                if answer_graph_requested and not seeds:
                    return empty_visual_graph(
                        "empty",
                        "No imported PrimeKG nodes matched the answer graph anchors.",
                        graph_status,
                        disease=disease,
                    )
                if disease and not seeds:
                    return empty_visual_graph(
                        "empty",
                        f"No imported PrimeKG nodes matched disease '{disease}'.",
                        graph_status,
                        disease=disease,
                    )

                rows = query_visual_graph_rows(session, seeds, depth, max_nodes, max_relationships)
    except Exception as exc:
        return empty_visual_graph("error", f"PrimeKG graph viewer failed: {exc}", graph_status, disease=disease)

    graph = visual_graph_from_rows(rows, disease, depth, max_nodes, max_relationships, seeds)
    if answer_graph_requested:
        graph["mode"] = "answer"
        graph["label"] = "Answer Graph"
        graph["answerGraph"] = {
            "anchorNodeIds": anchor_node_ids,
            "anchorNodeNames": anchor_node_names,
            "questionSnippet": str(payload.get("question") or "")[:220],
        }
        graph["message"] = "Answer graph loaded." if graph.get("status") == "available" else graph.get("message")
    else:
        graph["mode"] = "disease"
        graph["label"] = "Disease Graph"
    graph["neo4j"] = {
        "connected": graph_status.get("connected"),
        "uri": graph_status.get("uri"),
        "database": graph_status.get("database"),
    }
    # This viewer is strictly read-only and bounded; it never imports or mutates.
    graph["readOnly"] = True
    graph["datasetComplete"] = full_dataset_available()
    return graph


def normalize_anchor_values(values, max_items=20):
    if isinstance(values, str):
        values = [values]
    if not isinstance(values, list):
        return []
    anchors = []
    for value in values:
        text = str(value or "").strip()
        if not text:
            continue
        text = text[:200]
        if text not in anchors:
            anchors.append(text)
        if len(anchors) >= max_items:
            break
    return anchors


def find_visual_anchor_nodes(session, anchor_node_ids=None, anchor_node_names=None):
    anchor_node_ids = normalize_anchor_values(anchor_node_ids or [])
    anchor_node_names = [value.lower() for value in normalize_anchor_values(anchor_node_names or [])]
    if not anchor_node_ids and not anchor_node_names:
        return []
    return session.run(
        """
        MATCH (n:PrimeNode)
        WHERE NOT toLower(coalesce(n.source, '')) CONTAINS 'fake-test-only'
          AND NOT toLower(coalesce(n.name, '')) CONTAINS 'fake test data only'
          AND (
            coalesce(n.prime_id, n.id) IN $anchorIds
            OR any(name IN $anchorNames WHERE toLower(coalesce(n.name, '')) = name)
            OR any(name IN $anchorNames WHERE toLower(coalesce(n.name, '')) CONTAINS name)
          )
        RETURN coalesce(n.prime_id, n.id) AS id,
               n.name AS name,
               coalesce(n.node_type, n.type, 'other') AS type
        ORDER BY CASE coalesce(n.node_type, n.type, 'other') WHEN 'disease' THEN 0 ELSE 1 END,
                 toLower(coalesce(n.name, ''))
        LIMIT 20
        """,
        anchorIds=anchor_node_ids,
        anchorNames=anchor_node_names,
    ).data()


def find_visual_seed_nodes(session, disease):
    if not disease:
        rows = session.run(
            """
        MATCH (n:PrimeNode)
        WHERE NOT toLower(coalesce(n.source, '')) CONTAINS 'fake-test-only'
          AND NOT toLower(coalesce(n.name, '')) CONTAINS 'fake test data only'
        RETURN coalesce(n.prime_id, n.id) AS id,
                   n.name AS name,
                   coalesce(n.node_type, n.type, 'other') AS type
            ORDER BY CASE coalesce(n.node_type, n.type, 'other') WHEN 'disease' THEN 0 ELSE 1 END,
                     toLower(coalesce(n.name, ''))
            LIMIT 5
            """
        ).data()
        return rows

    term = disease.lower()
    rows = session.run(
        """
        MATCH (n:PrimeNode)
        WHERE NOT toLower(coalesce(n.source, '')) CONTAINS 'fake-test-only'
          AND NOT toLower(coalesce(n.name, '')) CONTAINS 'fake test data only'
          AND (
            toLower(coalesce(n.name, '')) CONTAINS $term
            OR toLower(coalesce(n.disease_context, '')) CONTAINS $term
          )
        RETURN coalesce(n.prime_id, n.id) AS id,
               n.name AS name,
               coalesce(n.node_type, n.type, 'other') AS type
        ORDER BY CASE coalesce(n.node_type, n.type, 'other') WHEN 'disease' THEN 0 ELSE 1 END,
                 CASE WHEN toLower(coalesce(n.name, '')) CONTAINS $term THEN 0 ELSE 1 END,
                 size(coalesce(n.name, ''))
        LIMIT 8
        """,
        term=term,
    ).data()
    return rows


def query_visual_graph_rows(session, seeds, depth, max_nodes, max_relationships):
    seed_ids = [seed.get("id") for seed in seeds if seed.get("id")]
    if seed_ids:
        query = f"""
        MATCH (seed:PrimeNode)
        WHERE coalesce(seed.prime_id, seed.id) IN $seedIds
        MATCH path = (seed)-[:PRIME_REL*1..{depth}]-(neighbor:PrimeNode)
        WHERE all(node IN nodes(path)
          WHERE NOT toLower(coalesce(node.source, '')) CONTAINS 'fake-test-only'
            AND NOT toLower(coalesce(node.name, '')) CONTAINS 'fake test data only'
        )
          AND all(rel IN relationships(path)
            WHERE NOT toLower(coalesce(rel.prime_source, '')) CONTAINS 'fake-test-only'
          )
        WITH path
        ORDER BY length(path) ASC
        LIMIT $pathLimit
        RETURN
          [node IN nodes(path) | node {{
            .*,
            id: coalesce(node.prime_id, node.id),
            type: coalesce(node.node_type, node.type, 'other')
          }}] AS nodes,
          [rel IN relationships(path) | {{
            id: coalesce(rel.prime_key, elementId(rel)),
            source: coalesce(startNode(rel).prime_id, startNode(rel).id),
            target: coalesce(endNode(rel).prime_id, endNode(rel).id),
            relation: rel.relation,
            displayRelation: coalesce(rel.display_relation, rel.relation, type(rel)),
            sourceName: startNode(rel).name,
            targetName: endNode(rel).name
          }}] AS relationships
        """
        return session.run(
            query,
            seedIds=seed_ids,
            pathLimit=max(max_relationships * 2, max_nodes),
        ).data()

    query = """
    MATCH (source:PrimeNode)-[rel:PRIME_REL]->(target:PrimeNode)
    WHERE NOT toLower(coalesce(source.source, '')) CONTAINS 'fake-test-only'
      AND NOT toLower(coalesce(source.name, '')) CONTAINS 'fake test data only'
      AND NOT toLower(coalesce(target.source, '')) CONTAINS 'fake-test-only'
      AND NOT toLower(coalesce(target.name, '')) CONTAINS 'fake test data only'
      AND NOT toLower(coalesce(rel.prime_source, '')) CONTAINS 'fake-test-only'
    RETURN
      [
        source {
          .*,
          id: coalesce(source.prime_id, source.id),
          type: coalesce(source.node_type, source.type, 'other')
        },
        target {
          .*,
          id: coalesce(target.prime_id, target.id),
          type: coalesce(target.node_type, target.type, 'other')
        }
      ] AS nodes,
      [{ id: coalesce(rel.prime_key, elementId(rel)),
         source: coalesce(source.prime_id, source.id),
         target: coalesce(target.prime_id, target.id),
         relation: rel.relation,
         displayRelation: coalesce(rel.display_relation, rel.relation, type(rel)),
         sourceName: source.name,
         targetName: target.name
      }] AS relationships
    LIMIT $relationshipLimit
    """
    return session.run(query, relationshipLimit=max_relationships).data()


def visual_graph_from_rows(rows, disease, depth, max_nodes, max_relationships, seeds):
    nodes_by_id = {}
    relationships_by_id = {}
    capped_nodes = False
    capped_relationships = False

    for row in rows:
        for node in row.get("nodes") or []:
            if is_fake_primekg_node(node):
                continue
            node_id = str(node.get("id") or node.get("prime_id") or "").strip()
            if not node_id:
                continue
            if node_id not in nodes_by_id and len(nodes_by_id) >= max_nodes:
                capped_nodes = True
                continue
            nodes_by_id.setdefault(node_id, normalize_visual_node(node, node_id))

        for relationship in row.get("relationships") or []:
            if is_fake_primekg_relationship(relationship):
                continue
            source = str(relationship.get("source") or "").strip()
            target = str(relationship.get("target") or "").strip()
            if not source or not target:
                continue
            rel_id = str(relationship.get("id") or f"{source}|{relationship.get('relation') or 'related_to'}|{target}")
            if source not in nodes_by_id or target not in nodes_by_id:
                continue
            if rel_id not in relationships_by_id and len(relationships_by_id) >= max_relationships:
                capped_relationships = True
                continue
            relationships_by_id.setdefault(rel_id, normalize_visual_relationship(relationship, rel_id))

    nodes = sorted(nodes_by_id.values(), key=lambda item: (item.get("type") != "disease", item.get("name", "").lower()))
    relationships = sorted(relationships_by_id.values(), key=lambda item: (item.get("sourceName", ""), item.get("label", ""), item.get("targetName", "")))
    return {
        "status": "available" if nodes else "empty",
        "message": "PrimeKG graph loaded." if nodes else "No PrimeKG relationships matched the viewer request.",
        "source": "neo4j-primekg",
        "disease": disease,
        "depth": depth,
        "nodes": nodes,
        "relationships": relationships,
        "stats": {
            "nodeCount": len(nodes),
            "relationshipCount": len(relationships),
            "byNodeType": count_field(nodes, "type"),
            "byRelationType": count_field(relationships, "label"),
            "seedCount": len(seeds),
        },
        "seeds": seeds,
        "warnings": [
            warning
            for warning in [
                "Visual node cap reached; showing a bounded subset." if capped_nodes else "",
                "Visual relationship cap reached; showing a bounded subset." if capped_relationships else "",
                "Depth 3 can be visually dense; use filters or lower caps if the graph is crowded." if depth == 3 else "",
            ]
            if warning
        ],
    }


def normalize_visual_node(node, node_id):
    return {
        "id": node_id,
        "name": node.get("name") or node_id,
        "type": node.get("type") or node.get("node_type") or "other",
        "source": node.get("source") or "",
        "diseaseContext": node.get("disease_context") or "",
    }


def normalize_visual_relationship(relationship, rel_id):
    return {
        "id": rel_id,
        "source": relationship.get("source"),
        "target": relationship.get("target"),
        "label": relationship.get("displayRelation") or relationship.get("relation") or "related_to",
        "relation": relationship.get("relation") or relationship.get("displayRelation") or "related_to",
        "sourceName": relationship.get("sourceName") or "",
        "targetName": relationship.get("targetName") or "",
    }


def count_field(items, field):
    counts = {}
    for item in items:
        key = item.get(field) or "unknown"
        counts[key] = counts.get(key, 0) + 1
    return dict(sorted(counts.items(), key=lambda pair: (-pair[1], pair[0])))


def empty_visual_graph(status, message, graph_status, disease=""):
    return {
        "status": status,
        "message": message,
        "source": "neo4j-primekg",
        "disease": disease,
        "nodes": [],
        "relationships": [],
        "stats": {"nodeCount": 0, "relationshipCount": 0, "byNodeType": {}, "byRelationType": {}, "seedCount": 0},
        "seeds": [],
        "warnings": [],
        "neo4j": {
            "connected": graph_status.get("connected"),
            "uri": graph_status.get("uri"),
            "database": graph_status.get("database"),
            "message": graph_status.get("message"),
            "setupHint": graph_status.get("setupHint"),
        },
    }


def resolve_primekg_path(value, suffix):
    if not value:
        raise PrimeKGApiError(f"Missing required path ending in {suffix}.")
    candidate = Path(value)
    if not candidate.is_absolute():
        candidate = ROOT / candidate
    resolved = candidate.resolve()
    allowed_root = PRIMEKG_DIR.resolve()
    if resolved != allowed_root and allowed_root not in resolved.parents:
        raise PrimeKGApiError("PrimeKG API paths must stay under data/primekg.")
    if resolved.suffix.lower() != suffix:
        raise PrimeKGApiError(f"Expected a {suffix} file under data/primekg.")
    return resolved


def allowed_values_to_cli_list(value):
    if not value:
        return None
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        cleaned = [str(item).strip() for item in value if str(item).strip()]
        return cleaned or None
    raise PrimeKGApiError("Allowed type/relation filters must be strings or arrays.")


def bounded_int(value, minimum, maximum, field_name):
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise PrimeKGApiError(f"{field_name} must be an integer.") from exc
    if parsed < minimum:
        return minimum
    if parsed > maximum:
        return maximum
    return parsed


def truthy(value):
    return str(value).strip().lower() in {"1", "true", "yes", "y", "on"}


def load_last_import_summary():
    if not LAST_IMPORT_PATH.exists():
        return None
    try:
        return json.loads(LAST_IMPORT_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"status": "unreadable", "path": relative_path(LAST_IMPORT_PATH)}


def save_last_import_summary(summary):
    PRIMEKG_DIR.mkdir(parents=True, exist_ok=True)
    LAST_IMPORT_PATH.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")


def relative_path(path):
    if not path:
        return ""
    try:
        return str(Path(path).resolve().relative_to(ROOT)).replace("\\", "/")
    except ValueError:
        return str(path)


def slug(value):
    return re.sub(r"[^a-z0-9]+", "-", str(value).lower()).strip("-") or "primekg"
