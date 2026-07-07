"""API helpers for the optional PrimeKG filtered-subgraph workflow."""

from __future__ import annotations

import json
import re
import time
import csv
from pathlib import Path

try:
    from graph_rag import get_driver, graph_store_status, neo4j_settings
    from primekg_import import PrimeKGImportError, import_filtered_primekg_subgraph
except ImportError:
    from backend.graph_rag import get_driver, graph_store_status, neo4j_settings
    from backend.primekg_import import PrimeKGImportError, import_filtered_primekg_subgraph

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
DEFAULT_CSV_PATH = PRIMEKG_DIR / "kg.csv"
PREVIEW_DIR = PRIMEKG_DIR / "previews"
LAST_IMPORT_PATH = PRIMEKG_DIR / "last_import_summary.json"

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

_disease_cache = {}
_disease_query_cache = {}


class PrimeKGApiError(Exception):
    """Raised for safe, user-facing PrimeKG API errors."""


def primekg_status():
    csv_path = DEFAULT_CSV_PATH
    graph_status = graph_store_status()
    return {
        "configured": csv_path.exists(),
        "defaultCsvPath": relative_path(csv_path),
        "fileExists": csv_path.exists(),
        "neo4jConnected": bool(graph_status.get("connected")),
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


def search_diseases(query="", limit=DISEASE_SEARCH_DEFAULT_LIMIT, csv_path=None):
    """Return bounded disease suggestions from PrimeKG kg.csv."""

    path = Path(csv_path) if csv_path else DEFAULT_CSV_PATH
    if not path.is_absolute():
        path = ROOT / path
    limit = bounded_int(limit, 1, DISEASE_SEARCH_MAX_LIMIT, "limit")
    query_text = str(query or "").strip()

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
    if filter_subgraph is None:
        raise PrimeKGApiError("PrimeKG filter support is unavailable because the filter script could not be imported.")

    csv_path = resolve_primekg_path(payload.get("csvPath") or DEFAULT_CSV_PATH, suffix=".csv")
    disease = str(payload.get("disease") or "").strip()
    if not disease:
        raise PrimeKGApiError("Missing required field: disease.")
    depth = bounded_int(payload.get("depth", 2), 1, API_MAX_DEPTH, "depth")
    max_nodes = bounded_int(payload.get("maxNodes", API_DEFAULT_NODES), 1, API_MAX_NODES, "maxNodes")
    max_relationships = bounded_int(
        payload.get("maxRelationships", API_DEFAULT_RELATIONSHIPS),
        1,
        API_MAX_RELATIONSHIPS,
        "maxRelationships",
    )
    allowed_types = allowed_values_to_cli_list(payload.get("allowedNodeTypes"))
    allowed_relations = allowed_values_to_cli_list(payload.get("allowedRelationTypes"))

    try:
        result = filter_subgraph(
            input_path=csv_path,
            disease_query=disease,
            depth=depth,
            max_nodes=max_nodes,
            max_relationships=max_relationships,
            allowed_types=parse_allowed_types(allowed_types),
            allowed_relations=parse_csv_list(allowed_relations),
        )
    except PrimeKGFilterError as exc:
        raise PrimeKGApiError(str(exc)) from exc

    preview_path = None
    if result.get("ok"):
        PREVIEW_DIR.mkdir(parents=True, exist_ok=True)
        preview_path = PREVIEW_DIR / f"filtered_{slug(disease)}_{int(time.time())}.json"
        write_json(result, preview_path)

    nodes = result.get("nodes") or []
    relationships = result.get("relationships") or []
    metadata = result.get("metadata") or {}
    caps_reached = metadata.get("capsReached") or {}
    warnings = []
    if depth == 3:
        warnings.append("Depth 3 can produce large PrimeKG neighborhoods; API caps were enforced.")
    if caps_reached.get("nodes") or len(nodes) >= max_nodes:
        warnings.append("Node cap reached; preview may be truncated.")
    if caps_reached.get("relationships") or len(relationships) >= max_relationships:
        warnings.append("Relationship cap reached; preview may be truncated.")

    response = {
        "ok": bool(result.get("ok")),
        "disease": disease,
        "csvPath": relative_path(csv_path),
        "outputPath": relative_path(preview_path) if preview_path else "",
        "matchedDiseaseNodes": result.get("matchedDiseaseNodes") or [],
        "nodeCount": len(nodes),
        "relationshipCount": len(relationships),
        "statsByNodeType": result.get("statsByNodeType") or {},
        "statsByRelationType": result.get("statsByRelationType") or {},
        "sampleNodes": nodes[:SAMPLE_LIMIT],
        "sampleRelationships": relationships[:SAMPLE_LIMIT],
        "warnings": warnings,
        "limits": {
            "depth": depth,
            "maxNodes": max_nodes,
            "maxRelationships": max_relationships,
        },
    }
    if not result.get("ok"):
        response["error"] = result.get("error") or "PrimeKG filter preview failed."
        response["setupHint"] = result.get("setupHint", "")
        response["suggestions"] = result.get("suggestions", [])
    return response


def import_filtered(payload):
    filtered_path = resolve_primekg_path(payload.get("filteredPath") or "", suffix=".json")
    try:
        summary = import_filtered_primekg_subgraph(
            path=filtered_path,
            clear_primekg_subgraph=truthy(payload.get("clearExistingPrimeKG", False)),
            dry_run=truthy(payload.get("dryRun", False)),
        )
    except PrimeKGImportError as exc:
        raise PrimeKGApiError(str(exc)) from exc

    save_last_import_summary(summary)
    return summary


def filter_and_import(payload):
    strict_payload = dict(payload)
    strict_payload["depth"] = min(int(strict_payload.get("depth", 2) or 2), 2)
    strict_payload["maxNodes"] = min(int(strict_payload.get("maxNodes", API_DEFAULT_NODES) or API_DEFAULT_NODES), 1000)
    strict_payload["maxRelationships"] = min(
        int(strict_payload.get("maxRelationships", API_DEFAULT_RELATIONSHIPS) or API_DEFAULT_RELATIONSHIPS),
        3000,
    )
    preview = filter_preview(strict_payload)
    if not preview.get("ok"):
        return {"status": "filter_failed", "preview": preview}

    summary = import_filtered({
        "filteredPath": preview["outputPath"],
        "dryRun": truthy(payload.get("dryRun", True)),
        "clearExistingPrimeKG": truthy(payload.get("clearExistingPrimeKG", False)),
    })
    return {"status": summary.get("status"), "preview": preview, "importSummary": summary}


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
    depth = bounded_int(payload.get("depth", 2), 1, API_MAX_DEPTH, "depth")
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
                        "No imported PrimeKG graph was found. Preview and import a filtered subgraph first.",
                        graph_status,
                    )

                seeds = find_visual_seed_nodes(session, disease)
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
    graph["neo4j"] = {
        "connected": graph_status.get("connected"),
        "uri": graph_status.get("uri"),
        "database": graph_status.get("database"),
    }
    return graph


def find_visual_seed_nodes(session, disease):
    if not disease:
        rows = session.run(
            """
            MATCH (n:PrimeNode)
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
        WHERE toLower(coalesce(n.name, '')) CONTAINS $term
           OR toLower(coalesce(n.disease_context, '')) CONTAINS $term
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
            node_id = str(node.get("id") or node.get("prime_id") or "").strip()
            if not node_id:
                continue
            if node_id not in nodes_by_id and len(nodes_by_id) >= max_nodes:
                capped_nodes = True
                continue
            nodes_by_id.setdefault(node_id, normalize_visual_node(node, node_id))

        for relationship in row.get("relationships") or []:
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
