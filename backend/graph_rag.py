import hashlib
import json
import os
import re
import time
from pathlib import Path
from urllib.parse import urlparse
from urllib.parse import urlparse


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_URI = "bolt://127.0.0.1:7687"
DEFAULT_USER = "neo4j"
DEFAULT_PASSWORD = "visualmas"
DEFAULT_DATABASE = "neo4j"
GRAPH_RAG_DISABLED_MESSAGE = "Neo4j Graph RAG is disabled."

BIOMEDICAL_TERMS = {
    "Disease": [
        "Alzheimer disease",
        "breast cancer",
        "colorectal cancer",
        "diabetes",
        "glioblastoma",
        "hypertension",
        "migraine",
        "Parkinson disease",
        "rheumatoid arthritis",
        "type 2 diabetes",
    ],
    "Drug": [
        "aducanumab",
        "aspirin",
        "erenumab",
        "gefitinib",
        "insulin",
        "lecanemab",
        "metformin",
        "methotrexate",
        "osimertinib",
        "trastuzumab",
    ],
    "Gene": [
        "ABCA1",
        "ACE",
        "APOE",
        "BRCA1",
        "BRCA2",
        "CGRP",
        "EGFR",
        "ERBB2",
        "HER2",
        "IL6",
        "INS",
        "TNF",
        "VEGFA",
    ],
    "Pathway": [
        "amyloid beta pathway",
        "CGRP signaling",
        "EGFR signaling",
        "HER2 signaling",
        "immune response",
        "insulin signaling",
        "TNF signaling",
    ],
}

RELATION_PATTERNS = [
    ("TREATS", re.compile(r"\b(treats?|used to treat|therapy for|approved for)\b", re.I)),
    ("TARGETS", re.compile(r"\b(targets?|inhibits?|blocks?|antagonizes?)\b", re.I)),
    ("ASSOCIATED_WITH", re.compile(r"\b(associated with|linked to|correlates with|risk factor for)\b", re.I)),
    ("INVESTIGATED_FOR", re.compile(r"\b(investigated for|trial for|studied for|evaluated for)\b", re.I)),
    ("PARTICIPATES_IN", re.compile(r"\b(participates in|part of|involved in|mediates)\b", re.I)),
]

COMMON_ENTITY_WORDS = {
    "A",
    "An",
    "And",
    "For",
    "From",
    "In",
    "It",
    "The",
    "This",
    "Visual",
}

PRIMEKG_DEFAULT_NODE_TYPES = {
    "disease",
    "drug",
    "gene/protein",
    "pathway",
    "phenotype",
    "biological_process",
    "molecular_function",
    "anatomy",
    "exposure",
    "other",
}

PRIMEKG_NODE_TYPE_ALIASES = {
    "gene": "gene/protein",
    "protein": "gene/protein",
    "gene_protein": "gene/protein",
    "gene/protein": "gene/protein",
    "mechanism": "biological_process",
    "biological process": "biological_process",
    "biological_process": "biological_process",
    "molecular function": "molecular_function",
    "molecular_function": "molecular_function",
    "symptom": "phenotype",
    "treatment": "drug",
}

PRIMEKG_NODE_TYPE_WEIGHTS = {
    "disease": 8,
    "drug": 7,
    "gene/protein": 6,
    "pathway": 6,
    "biological_process": 6,
    "molecular_function": 5,
    "phenotype": 5,
    "anatomy": 2,
    "exposure": 2,
    "other": 1,
}

PRIMEKG_RELATION_KEYWORDS = {
    "indication": 8,
    "treat": 8,
    "therapy": 8,
    "target": 7,
    "associated": 6,
    "mechanism": 6,
    "pathway": 6,
    "phenotype": 5,
    "symptom": 5,
    "process": 4,
}

PRIMEKG_QUERY_STOPWORDS = {
    "about",
    "answer",
    "available",
    "biological",
    "connected",
    "connection",
    "connections",
    "disease",
    "diseases",
    "drug",
    "drugs",
    "evidence",
    "explain",
    "graph",
    "linked",
    "mechanism",
    "mechanisms",
    "path",
    "paths",
    "phenotype",
    "phenotypes",
    "question",
    "show",
    "symptom",
    "symptoms",
    "treat",
    "treatment",
    "treatments",
    "what",
    "which",
    "with",
}


def graph_store_status(config=None):
    settings = neo4j_settings(config)
    enabled = graph_rag_enabled(config)
    host_info = neo4j_host_info(settings["uri"])
    status = {
        "backend": "neo4j",
        "enabled": enabled,
        "available": False,
        "uri": redact_uri(settings["uri"]),
        "host": host_info["host"],
        "port": host_info["port"],
        "database": settings["database"],
        "configured": bool(settings["uri"] and settings["user"] and settings["password"]),
        "driverInstalled": False,
        "connected": False,
        "error": "",
        "message": "",
        "setupHint": "",
    }
    if not enabled:
        status["message"] = GRAPH_RAG_DISABLED_MESSAGE
        status["setupHint"] = "Set GRAPH_RAG_ENABLED=true and start Neo4j to enable graph retrieval."
        return status

    try:
        import neo4j  # noqa: F401

        status["driverInstalled"] = True
    except Exception:
        status["message"] = "Install the neo4j Python package to enable Graph RAG."
        status["error"] = status["message"]
        status["setupHint"] = "Run `python -m pip install -r requirements.txt`."
        return status

    if not status["configured"]:
        status["message"] = "Set NEO4J_URI, NEO4J_USER, and NEO4J_PASSWORD."
        status["error"] = status["message"]
        status["setupHint"] = "Copy .env.example values or export Neo4j environment variables before starting the backend."
        return status

    try:
        with get_driver(config) as driver:
            with driver.session(database=settings["database"]) as session:
                session.run("RETURN 1 AS ok").single()
        status["connected"] = True
        status["available"] = True
        status["message"] = "Neo4j is reachable."
    except Exception as exc:
        status["message"] = str(exc)
        status["error"] = str(exc)
        status["setupHint"] = "Start Neo4j with `docker compose -f docker-compose.neo4j.yml up -d`, then retry Graph Status."
    return status


def graph_rag_enabled(config=None):
    config = config or {}
    if "graphRagEnabled" in config:
        return truthy(config.get("graphRagEnabled"))
    if "graphEnabled" in config:
        return truthy(config.get("graphEnabled"))
    return truthy(os.environ.get("GRAPH_RAG_ENABLED", "true"))


def truthy(value):
    return str(value).strip().lower() not in {"0", "false", "no", "off", "disabled"}


def neo4j_settings(config=None):
    config = config or {}
    return {
        "uri": config.get("neo4jUri") or os.environ.get("NEO4J_URI") or DEFAULT_URI,
        "user": config.get("neo4jUser") or os.environ.get("NEO4J_USER") or DEFAULT_USER,
        "password": config.get("neo4jPassword") or os.environ.get("NEO4J_PASSWORD") or DEFAULT_PASSWORD,
        "database": config.get("neo4jDatabase") or os.environ.get("NEO4J_DATABASE") or DEFAULT_DATABASE,
    }


def neo4j_host_info(uri):
    parsed = urlparse(uri or "")
    return {
        "host": parsed.hostname or "",
        "port": parsed.port,
        "scheme": parsed.scheme or "",
    }


def redact_uri(uri):
    parsed = urlparse(uri or "")
    if not parsed.username and not parsed.password:
        return uri
    host = parsed.hostname or ""
    if parsed.port:
        host = f"{host}:{parsed.port}"
    return parsed._replace(netloc=host).geturl()


def get_driver(config=None):
    from neo4j import GraphDatabase

    settings = neo4j_settings(config)
    return GraphDatabase.driver(settings["uri"], auth=(settings["user"], settings["password"]))


def ensure_schema(session):
    session.run("CREATE CONSTRAINT graph_document_id IF NOT EXISTS FOR (d:Document) REQUIRE d.id IS UNIQUE")
    session.run("CREATE CONSTRAINT graph_chunk_id IF NOT EXISTS FOR (c:Chunk) REQUIRE c.id IS UNIQUE")
    session.run("CREATE CONSTRAINT graph_entity_id IF NOT EXISTS FOR (e:Entity) REQUIRE e.id IS UNIQUE")
    session.run("CREATE INDEX graph_entity_name IF NOT EXISTS FOR (e:Entity) ON (e.name)")
    session.run("CREATE INDEX graph_entity_collection IF NOT EXISTS FOR (e:Entity) ON (e.collection)")
    session.run("CREATE INDEX graph_chunk_collection IF NOT EXISTS FOR (c:Chunk) ON (c.collection)")


def upsert_graph_chunks(collection, chunks, config=None):
    if not chunks:
        return {"status": "skipped", "message": "No chunks available for graph indexing."}
    status = graph_store_status(config)
    if not status["enabled"]:
        return {"status": "disabled", "message": status["message"], "store": status}
    if not status["connected"]:
        return {"status": "unavailable", "message": status["message"], "store": status}

    settings = neo4j_settings(config)
    started = time.perf_counter()
    total_entities = 0
    total_relationships = 0
    try:
        with get_driver(config) as driver:
            with driver.session(database=settings["database"]) as session:
                ensure_schema(session)
                for chunk in chunks:
                    entities = extract_entities(chunk.get("text", ""))
                    for entity in entities:
                        entity["id"] = entity_id_for(collection, entity["name"], entity["type"])
                    relationships = extract_relationships(chunk.get("text", ""), entities)
                    total_entities += len(entities)
                    total_relationships += len(relationships)
                    session.execute_write(
                        _upsert_chunk_tx,
                        collection,
                        chunk,
                        entities,
                        relationships,
                    )
    except Exception as exc:
        return {
            "status": "unavailable",
            "backend": "neo4j",
            "message": f"Graph indexing skipped because Neo4j failed during indexing: {exc}",
            "store": graph_store_status(config),
        }

    return {
        "status": "indexed",
        "backend": "neo4j",
        "chunks": len(chunks),
        "entities": total_entities,
        "relationships": total_relationships,
        "durationMs": round((time.perf_counter() - started) * 1000, 2),
    }


def _upsert_chunk_tx(tx, collection, chunk, entities, relationships):
    metadata = chunk.get("metadata", {})
    title = metadata.get("title") or "Untitled document"
    source = metadata.get("source") or "manual"
    document_id = stable_id(collection, source, title)
    chunk_id = chunk["id"]
    tx.run(
        """
        MERGE (d:Document {id: $documentId})
        SET d.collection = $collection,
            d.title = $title,
            d.source = $source,
            d.updatedAt = timestamp()
        MERGE (c:Chunk {id: $chunkId})
        SET c.collection = $collection,
            c.text = $text,
            c.title = $title,
            c.source = $source,
            c.chunkIndex = $chunkIndex,
            c.updatedAt = timestamp()
        MERGE (d)-[:HAS_CHUNK]->(c)
        """,
        documentId=document_id,
        chunkId=chunk_id,
        collection=collection,
        title=title,
        source=source,
        text=chunk.get("text", ""),
        chunkIndex=metadata.get("chunkIndex", 0),
    )
    for entity in entities:
        tx.run(
            """
            MERGE (e:Entity {id: $id})
            SET e.name = $name,
                e.type = $type,
                e.collection = $collection,
                e.updatedAt = timestamp()
            WITH e
            MATCH (c:Chunk {id: $chunkId})
            MERGE (c)-[:MENTIONS]->(e)
            """,
            id=entity["id"],
            name=entity["name"],
            type=entity["type"],
            collection=collection,
            chunkId=chunk_id,
        )
    entity_by_name = {normalize_name(entity["name"]): entity for entity in entities}
    for relationship in relationships:
        source = entity_by_name.get(normalize_name(relationship["source"]))
        target = entity_by_name.get(normalize_name(relationship["target"]))
        if not source or not target or source["id"] == target["id"]:
            continue
        tx.run(
            """
            MATCH (source:Entity {id: $sourceId})
            MATCH (target:Entity {id: $targetId})
            MERGE (source)-[r:RELATED {collection: $collection, type: $type}]->(target)
            ON CREATE SET r.createdAt = timestamp(), r.evidenceChunkIds = []
            SET r.updatedAt = timestamp(),
                r.evidenceChunkIds = CASE
                    WHEN $chunkId IN coalesce(r.evidenceChunkIds, []) THEN r.evidenceChunkIds
                    ELSE coalesce(r.evidenceChunkIds, []) + $chunkId
                END
            """,
            sourceId=source["id"],
            targetId=target["id"],
            collection=collection,
            type=relationship["type"],
            chunkId=chunk_id,
        )


def retrieve_graph_context(collection, query, top_k=5, hops=1, config=None):
    status = graph_store_status(config)
    if not status["enabled"]:
        return graph_unavailable_result(status, "disabled")
    if not status["connected"]:
        return graph_unavailable_result(status, "unavailable")

    hops = max(1, min(int(hops or 1), 3))
    top_k = max(1, min(int(top_k or 5), 20))
    primekg_retrieval = retrieve_primekg_paths_for_question(
        query,
        selected_disease=(config or {}).get("disease") or (config or {}).get("graphDisease"),
        top_k=top_k,
        max_depth=hops,
        max_paths=max(top_k, 5),
        allowed_node_types=(config or {}).get("primekgAllowedNodeTypes") or (config or {}).get("allowedNodeTypes"),
        config=config,
        checked_status=status,
    )
    if primekg_retrieval.get("status") == "ok" and primekg_retrieval.get("paths"):
        return primekg_question_retrieval_result(primekg_retrieval)

    terms = query_terms(query)
    query_entities = extract_entities(query)
    terms.extend(normalize_name(entity["name"]) for entity in query_entities)
    terms = sorted({term for term in terms if term})

    if not terms:
        return empty_graph_result(collection, "No query terms were available for graph lookup.")

    settings = neo4j_settings(config)
    try:
        with get_driver(config) as driver:
            with driver.session(database=settings["database"]) as session:
                seeds = session.run(
                    """
                    MATCH (e:Entity {collection: $collection})
                    WHERE any(term IN $terms WHERE toLower(e.name) CONTAINS term OR term CONTAINS toLower(e.name))
                    RETURN e.id AS id, e.name AS name, e.type AS type
                    ORDER BY size(e.name) DESC
                    LIMIT $topK
                    """,
                    collection=collection,
                    terms=terms,
                    topK=top_k,
                ).data()
                seed_ids = [item["id"] for item in seeds]
                if not seed_ids:
                    return empty_graph_result(collection, "No graph entities matched the query.")

                path_query = f"""
                MATCH (seed:Entity)
                WHERE seed.id IN $seedIds
                MATCH path = (seed)-[:RELATED*1..{hops}]-(neighbor:Entity {{collection: $collection}})
                RETURN
                  [node IN nodes(path) | node {{.id, .name, .type, .collection}}] AS nodes,
                  [rel IN relationships(path) | {{
                    source: startNode(rel).id,
                    sourceName: startNode(rel).name,
                    target: endNode(rel).id,
                    targetName: endNode(rel).name,
                    type: rel.type,
                    evidenceChunkIds: rel.evidenceChunkIds
                  }}] AS relationships
                LIMIT $topK
                """
                paths = session.run(
                    path_query,
                    seedIds=seed_ids,
                    collection=collection,
                    topK=top_k,
                ).data()

                entity_ids = set(seed_ids)
                entities_by_id = {item["id"]: item for item in seeds}
                relationships_by_key = {}
                for item in paths:
                    for entity in item.get("nodes", []):
                        entity_ids.add(entity["id"])
                        entities_by_id[entity["id"]] = entity
                    for relationship in item.get("relationships", []):
                        key = (relationship["source"], relationship["target"], relationship["type"])
                        relationships_by_key[key] = relationship

                chunk_rows = session.run(
                    """
                    MATCH (chunk:Chunk {collection: $collection})-[:MENTIONS]->(entity:Entity)
                    WHERE entity.id IN $entityIds
                    RETURN chunk {
                        .id,
                        .text,
                        .title,
                        .source,
                        .collection,
                        .chunkIndex
                    } AS chunk,
                    collect(DISTINCT entity {.id, .name, .type}) AS entities
                    LIMIT $topK
                    """,
                    collection=collection,
                    entityIds=list(entity_ids),
                    topK=top_k,
                ).data()
    except Exception as exc:
        failed_status = graph_store_status(config)
        failed_status["message"] = f"Neo4j graph retrieval failed: {exc}"
        failed_status["error"] = str(exc)
        return graph_unavailable_result(failed_status, "unavailable")

    entities = sorted(entities_by_id.values(), key=lambda item: (item.get("type", ""), item.get("name", "")))
    relationships = sorted(
        relationships_by_key.values(),
        key=lambda item: (item.get("sourceName", ""), item.get("type", ""), item.get("targetName", "")),
    )
    matches = graph_matches(chunk_rows)
    context = format_graph_context(collection, entities, relationships, matches)
    return {
        "context": context,
        "matches": matches,
        "graphEvidence": {
            "status": "available",
            "backend": "neo4j",
            "collection": collection,
            "queryTerms": terms,
            "seedEntities": seeds,
            "entities": entities,
            "relationships": relationships,
            "chunks": [row.get("chunk") for row in chunk_rows],
        },
        "graphBackend": "neo4j",
    }


def retrieve_primekg_paths(query, disease=None, top_k=5, max_depth=2, allowed_node_types=None, config=None, checked_status=None):
    status = checked_status or graph_store_status(config)
    if not status["enabled"]:
        return graph_unavailable_result(status, "disabled")
    if not status["connected"]:
        return graph_unavailable_result(status, "unavailable")

    top_k = max(1, min(int(top_k or 5), 20))
    max_depth = max(1, min(int(max_depth or 2), 3))
    allowed_types = normalize_primekg_allowed_types(allowed_node_types)
    terms = primekg_query_terms(query, disease)
    if not terms:
        return empty_primekg_result("No query terms were available for PrimeKG graph lookup.")

    settings = neo4j_settings(config)
    try:
        with get_driver(config) as driver:
            with driver.session(database=settings["database"]) as session:
                has_primekg = session.run("MATCH (n:PrimeNode) RETURN n.prime_id AS id LIMIT 1").single()
                if not has_primekg:
                    return empty_primekg_result("No imported PrimeKG :PrimeNode graph was found.", reason="no_primekg")

                seeds = find_primekg_seed_nodes(session, terms, disease, allowed_types, top_k)
                if not seeds:
                    return empty_primekg_result("No PrimeKG nodes matched the query.", reason="no_seed", query_terms=terms)

                rows = query_primekg_path_rows(session, seeds, allowed_types, top_k, max_depth)
    except Exception as exc:
        failed_status = graph_store_status(config)
        failed_status["message"] = f"PrimeKG graph retrieval failed: {exc}"
        failed_status["error"] = str(exc)
        return graph_unavailable_result(failed_status, "unavailable")

    if not rows:
        return empty_primekg_result("PrimeKG seeds matched, but no bounded paths were found.", reason="no_paths", query_terms=terms, seed_entities=seeds)
    return primekg_result_from_path_rows(rows, seeds, query, terms, top_k, max_depth)


def retrieve_primekg_paths_for_question(
    query,
    selected_disease=None,
    top_k=5,
    max_depth=2,
    max_paths=20,
    allowed_node_types=None,
    config=None,
    checked_status=None,
):
    status = checked_status or graph_store_status(config)
    top_k = max(1, min(int(top_k or 5), 20))
    max_depth = max(1, min(int(max_depth or 2), 3))
    max_paths = max(1, min(int(max_paths or 20), 50))
    query = query or ""
    selected_disease = (selected_disease or "").strip()

    if not status.get("enabled") or not status.get("connected"):
        return empty_primekg_question_result(
            "unavailable",
            query,
            selected_disease,
            status.get("message") or "Neo4j is not reachable for PrimeKG graph retrieval.",
            max_depth=max_depth,
        )

    detection = detect_primekg_query_entities(
        query,
        selected_disease=selected_disease,
        limit=min(max(top_k * 3, 8), 20),
        config=config,
        checked_status=status,
    )
    if detection.get("status") != "ok":
        return empty_primekg_question_result(
            detection.get("status") or "empty",
            query,
            selected_disease,
            detection.get("message") or "No PrimeKG entities were detected.",
            detected_entities=detection.get("detectedEntities", []),
            max_depth=max_depth,
        )

    detected_entities = detection.get("detectedEntities", [])
    seeds = [
        {
            "id": entity.get("id"),
            "name": entity.get("name"),
            "type": entity.get("node_type") or entity.get("type"),
            "source": entity.get("source"),
            "score": entity.get("score", 0),
            "matchType": entity.get("matchType"),
        }
        for entity in detected_entities
        if entity.get("id")
    ][: min(max(top_k * 2, 6), 20)]
    if not seeds:
        return empty_primekg_question_result(
            "empty",
            query,
            selected_disease,
            "No usable PrimeKG anchor IDs were detected.",
            detected_entities=detected_entities,
            max_depth=max_depth,
        )

    allowed_types = normalize_primekg_allowed_types(allowed_node_types)
    settings = neo4j_settings(config)
    try:
        with get_driver(config) as driver:
            with driver.session(database=settings["database"]) as session:
                rows = query_primekg_path_rows(session, seeds, allowed_types, max_paths, max_depth)
    except Exception as exc:
        return empty_primekg_question_result(
            "unavailable",
            query,
            selected_disease,
            f"PrimeKG graph path retrieval failed: {exc}",
            detected_entities=detected_entities,
            max_depth=max_depth,
        )

    if not rows:
        return empty_primekg_question_result(
            "empty",
            query,
            selected_disease,
            "Detected PrimeKG entities, but no bounded evidence paths were found.",
            detected_entities=detected_entities,
            max_depth=max_depth,
        )

    return primekg_question_result_from_path_rows(
        rows,
        detected_entities,
        query,
        selected_disease,
        max_paths=max_paths,
        max_depth=max_depth,
    )


def detect_primekg_query_entities(query, selected_disease=None, limit=10, config=None, checked_status=None):
    """Detect likely PrimeKG anchor nodes for a natural-language question."""

    status = checked_status or graph_store_status(config)
    if not status.get("enabled") or not status.get("connected"):
        return {
            "status": "unavailable",
            "query": query or "",
            "selectedDiseaseHint": selected_disease or "",
            "detectedEntities": [],
            "message": status.get("message") or "Neo4j is not reachable for PrimeKG entity detection.",
        }

    query = query or ""
    selected_disease = (selected_disease or "").strip()
    limit = max(1, min(int(limit or 10), 50))
    terms = primekg_detection_terms(query, selected_disease)
    if not terms:
        return {
            "status": "empty",
            "query": query,
            "selectedDiseaseHint": selected_disease,
            "detectedEntities": [],
            "message": "No searchable biomedical terms were found in the question.",
        }

    settings = neo4j_settings(config)
    try:
        with get_driver(config) as driver:
            with driver.session(database=settings["database"]) as session:
                rows = []
                if selected_disease:
                    rows.extend(query_primekg_detection_rows(
                        session,
                        [normalize_name(selected_disease)],
                        limit=min(max(limit, 5), 20),
                        disease_only=True,
                    ))
                rows.extend(query_primekg_detection_rows(
                    session,
                    terms,
                    limit=min(max(limit * 6, 20), 100),
                    disease_only=False,
                ))
    except Exception as exc:
        return {
            "status": "unavailable",
            "query": query,
            "selectedDiseaseHint": selected_disease,
            "detectedEntities": [],
            "message": f"PrimeKG entity detection failed: {exc}",
        }

    detected = rank_primekg_detected_entities(rows, terms, selected_disease, limit)
    if not detected:
        return {
            "status": "empty",
            "query": query,
            "selectedDiseaseHint": selected_disease,
            "detectedEntities": [],
            "message": "No imported PrimeKG nodes matched the question. Import a relevant filtered subgraph or select a disease as a hint.",
        }

    return {
        "status": "ok",
        "query": query,
        "selectedDiseaseHint": selected_disease,
        "detectedEntities": detected,
        "message": None,
    }


def query_primekg_detection_rows(session, terms, limit=50, disease_only=False):
    terms = [term for term in terms if term]
    if not terms:
        return []
    node_type_filter = "AND coalesce(n.node_type, n.type, 'other') = 'disease'" if disease_only else ""
    query = f"""
    MATCH (n:PrimeNode)
    WHERE any(term IN $terms WHERE
        toLower(coalesce(n.name, '')) = term
        OR toLower(coalesce(n.name, '')) STARTS WITH term
        OR toLower(coalesce(n.name, '')) CONTAINS term
        OR term CONTAINS toLower(coalesce(n.name, ''))
    )
    {node_type_filter}
    RETURN coalesce(n.prime_id, n.id) AS id,
           n.name AS name,
           coalesce(n.node_type, n.type, 'other') AS node_type,
           n.source AS source
    ORDER BY CASE coalesce(n.node_type, n.type, 'other') WHEN 'disease' THEN 0 ELSE 1 END,
             size(coalesce(n.name, '')) ASC
    LIMIT $limit
    """
    return session.run(query, terms=terms, limit=limit).data()


def primekg_detection_terms(query, selected_disease=None):
    terms = []
    if selected_disease:
        terms.append(normalize_name(selected_disease))

    normalized_query = normalize_name(query)
    if normalized_query:
        cleaned = normalized_query
        for stop in [
            "what drugs are connected to",
            "what biological mechanisms are connected to",
            "what mechanisms are connected to",
            "which phenotypes or symptoms are linked to",
            "show the graph evidence path for",
            "show graph evidence for",
            "graph evidence",
            "biological mechanisms",
        ]:
            cleaned = cleaned.replace(stop, " ")
        cleaned = normalize_name(cleaned)
        if cleaned and len(cleaned) >= 3 and cleaned not in PRIMEKG_QUERY_STOPWORDS:
            terms.append(cleaned)

    for token in re.findall(r"[A-Za-z][A-Za-z0-9+/-]{2,}", query or ""):
        term = normalize_name(token)
        if term and term not in PRIMEKG_QUERY_STOPWORDS:
            terms.append(term)

    entities = extract_entities(query or "")
    terms.extend(normalize_name(entity.get("name")) for entity in entities if entity.get("name"))

    unique_terms = []
    for term in terms:
        term = normalize_name(term)
        if term and term not in unique_terms:
            unique_terms.append(term)
    return unique_terms[:16]


def rank_primekg_detected_entities(rows, terms, selected_disease=None, limit=10):
    selected_term = normalize_name(selected_disease) if selected_disease else ""
    candidates = {}
    for row in rows or []:
        entity_id = row.get("id")
        name = row.get("name") or entity_id
        if not entity_id or not name:
            continue
        node_type = row.get("node_type") or row.get("type") or "other"
        match_type, match_score, matched_term = primekg_entity_match_score(name, terms, selected_term)
        if not match_type:
            continue
        type_score = PRIMEKG_NODE_TYPE_WEIGHTS.get(node_type, 1) / 10
        selected_boost = 0.35 if selected_term and normalize_name(name) == selected_term and node_type == "disease" else 0
        generic_penalty = 0.2 if is_generic_primekg_entity_name(name) else 0
        score = min(1.0, round(match_score + type_score + selected_boost - generic_penalty, 4))
        current = candidates.get(entity_id)
        if current and current.get("score", 0) >= score:
            continue
        candidates[entity_id] = {
            "id": entity_id,
            "name": name,
            "node_type": node_type,
            "matchType": "hint" if selected_boost else match_type,
            "matchedTerm": matched_term,
            "score": score,
            "source": row.get("source") or "neo4j",
        }

    ranked = sorted(
        candidates.values(),
        key=lambda item: (
            -item.get("score", 0),
            0 if item.get("node_type") == "disease" else 1,
            len(item.get("name") or ""),
            (item.get("name") or "").lower(),
        ),
    )
    return ranked[: max(1, min(int(limit or 10), 50))]


def primekg_entity_match_score(name, terms, selected_term=""):
    normalized = normalize_name(name)
    if not normalized:
        return None, 0, ""
    if selected_term and normalized == selected_term:
        return "hint", 0.95, selected_term

    best = (None, 0, "")
    for term in terms or []:
        term = normalize_name(term)
        if not term or term in PRIMEKG_QUERY_STOPWORDS:
            continue
        if normalized == term:
            candidate = ("exact", 0.9, term)
        elif normalized.startswith(term) or term.startswith(normalized):
            candidate = ("prefix", 0.7, term)
        elif normalized in term or term in normalized:
            candidate = ("contains", 0.5, term)
        else:
            continue
        if candidate[1] > best[1]:
            best = candidate
    return best


def is_generic_primekg_entity_name(name):
    normalized = normalize_name(name)
    if normalized in PRIMEKG_QUERY_STOPWORDS:
        return True
    return len(normalized) <= 2


def find_primekg_seed_nodes(session, terms, disease, allowed_types, top_k):
    seed_limit = min(max(top_k * 3, 6), 30)
    disease_terms = [normalize_name(disease)] if disease else []
    if disease_terms:
        disease_seeds = session.run(
            """
            MATCH (n:PrimeNode)
            WHERE n.node_type = 'disease'
              AND any(term IN $terms WHERE toLower(n.name) CONTAINS term OR term CONTAINS toLower(n.name))
            RETURN n.prime_id AS id, n.name AS name, n.node_type AS type, n.source AS source
            ORDER BY size(n.name) DESC
            LIMIT $limit
            """,
            terms=disease_terms,
            limit=seed_limit,
        ).data()
        if disease_seeds:
            return disease_seeds

    disease_matches = session.run(
        """
        MATCH (n:PrimeNode)
        WHERE n.node_type = 'disease'
          AND any(term IN $terms WHERE toLower(n.name) CONTAINS term OR term CONTAINS toLower(n.name))
        RETURN n.prime_id AS id, n.name AS name, n.node_type AS type, n.source AS source
        ORDER BY size(n.name) DESC
        LIMIT $limit
        """,
        terms=terms,
        limit=seed_limit,
    ).data()
    if disease_matches:
        return disease_matches

    return session.run(
        """
        MATCH (n:PrimeNode)
        WHERE n.node_type IN $allowedTypes
          AND any(term IN $terms WHERE toLower(n.name) CONTAINS term OR term CONTAINS toLower(n.name))
        RETURN n.prime_id AS id, n.name AS name, n.node_type AS type, n.source AS source
        ORDER BY
          CASE n.node_type
            WHEN 'disease' THEN 0
            WHEN 'drug' THEN 1
            WHEN 'gene/protein' THEN 2
            WHEN 'pathway' THEN 3
            WHEN 'biological_process' THEN 4
            WHEN 'phenotype' THEN 5
            ELSE 9
          END,
          size(n.name) DESC
        LIMIT $limit
        """,
        terms=terms,
        allowedTypes=sorted(allowed_types),
        limit=seed_limit,
    ).data()


def query_primekg_path_rows(session, seeds, allowed_types, top_k, max_depth):
    seed_ids = [seed["id"] for seed in seeds if seed.get("id")]
    path_limit = min(max(top_k * 6, 20), 100)
    path_query = f"""
    MATCH (seed:PrimeNode)
    WHERE seed.prime_id IN $seedIds
    MATCH path = (seed)-[:PRIME_REL*1..{max_depth}]-(neighbor:PrimeNode)
    WHERE all(n IN nodes(path) WHERE coalesce(n.node_type, 'other') IN $allowedTypes)
    WITH path, nodes(path) AS ns, relationships(path) AS rs
    WITH path, ns, rs,
      reduce(score = 0, n IN ns |
        score + CASE coalesce(n.node_type, 'other')
          WHEN 'disease' THEN 8
          WHEN 'drug' THEN 7
          WHEN 'gene/protein' THEN 6
          WHEN 'pathway' THEN 6
          WHEN 'biological_process' THEN 6
          WHEN 'molecular_function' THEN 5
          WHEN 'phenotype' THEN 5
          ELSE 1
        END
      ) +
      reduce(score = 0, r IN rs |
        score + CASE
          WHEN toLower(coalesce(r.display_relation, r.relation, '')) CONTAINS 'indication' THEN 8
          WHEN toLower(coalesce(r.display_relation, r.relation, '')) CONTAINS 'treat' THEN 8
          WHEN toLower(coalesce(r.display_relation, r.relation, '')) CONTAINS 'target' THEN 7
          WHEN toLower(coalesce(r.display_relation, r.relation, '')) CONTAINS 'associated' THEN 6
          WHEN toLower(coalesce(r.display_relation, r.relation, '')) CONTAINS 'pathway' THEN 6
          WHEN toLower(coalesce(r.display_relation, r.relation, '')) CONTAINS 'phenotype' THEN 5
          ELSE 1
        END
      ) AS score
    RETURN
      [node IN ns | node {{
        id: node.prime_id,
        prime_id: node.prime_id,
        name: node.name,
        type: node.node_type,
        node_type: node.node_type,
        source: node.source,
        disease_context: node.disease_context
      }}] AS nodes,
      [rel IN rs | {{
        id: coalesce(rel.prime_key, elementId(rel)),
        source: startNode(rel).prime_id,
        sourceName: startNode(rel).name,
        target: endNode(rel).prime_id,
        targetName: endNode(rel).name,
        relation: rel.relation,
        displayRelation: rel.display_relation,
        prime_source: rel.prime_source,
        depth: rel.depth
      }}] AS relationships,
      score AS score,
      length(path) AS length
    ORDER BY score DESC, length(path) ASC
    LIMIT $pathLimit
    """
    return session.run(
        path_query,
        seedIds=seed_ids,
        allowedTypes=sorted(allowed_types),
        pathLimit=path_limit,
    ).data()


def primekg_result_from_path_rows(rows, seed_entities, query, query_terms_list, top_k, max_depth):
    entities_by_id = {}
    relationships_by_key = {}
    paths = []
    seen_path_text = set()

    for row in rows:
        nodes = row.get("nodes") or []
        relationships = row.get("relationships") or []
        for node in nodes:
            node_id = node.get("id") or node.get("prime_id")
            if node_id:
                entities_by_id[node_id] = node
        for relationship in relationships:
            key = (
                relationship.get("source"),
                relationship.get("target"),
                relationship.get("relation") or relationship.get("displayRelation"),
            )
            relationships_by_key[key] = relationship
        path_text = format_primekg_path(nodes, relationships)
        if path_text and path_text not in seen_path_text:
            seen_path_text.add(path_text)
            paths.append({
                "path_text": path_text,
                "nodes": nodes,
                "relationships": relationships,
                "score": row.get("score", 0),
                "length": row.get("length", len(relationships)),
            })
        if len(paths) >= top_k:
            break

    entities = sorted(entities_by_id.values(), key=lambda item: primekg_node_sort_key(item))
    relationships = sorted(
        relationships_by_key.values(),
        key=lambda item: (item.get("sourceName", ""), item.get("displayRelation") or item.get("relation") or "", item.get("targetName", "")),
    )
    stats = {
        "pathCount": len(paths),
        "entityCount": len(entities),
        "relationshipCount": len(relationships),
        "byNodeType": count_by(entities, "type"),
        "byRelationType": count_by(relationships, "displayRelation", fallback_key="relation"),
        "maxDepth": max_depth,
    }
    context = format_primekg_context(paths, entities, relationships, stats)
    matches = primekg_path_matches(paths)
    return {
        "context": context,
        "matches": matches,
        "graphEvidence": {
            "status": "available",
            "backend": "neo4j-primekg",
            "query": query,
            "queryTerms": query_terms_list,
            "seedEntities": seed_entities,
            "entities": entities,
            "relationships": relationships,
            "paths": paths,
            "path_text": [path["path_text"] for path in paths],
            "stats": stats,
        },
        "graphBackend": "neo4j-primekg",
    }


def primekg_question_result_from_path_rows(rows, detected_entities, query, selected_disease, max_paths=20, max_depth=2):
    entities_by_id = {}
    relationships_by_key = {}
    paths = []
    seen_path_text = set()
    anchor_scores = {entity.get("id"): entity.get("score", 0) for entity in detected_entities or []}

    ranked_rows = sorted(
        rows or [],
        key=lambda row: primekg_question_row_sort_key(row, anchor_scores),
    )
    for index, row in enumerate(ranked_rows):
        nodes = row.get("nodes") or []
        relationships = row.get("relationships") or []
        path_text = format_primekg_path(nodes, relationships)
        if not path_text or path_text in seen_path_text:
            continue
        seen_path_text.add(path_text)
        for node in nodes:
            node_id = node.get("id") or node.get("prime_id")
            if node_id:
                entities_by_id[node_id] = node
        for relationship in relationships:
            rel_id = relationship.get("id")
            key = rel_id or (
                relationship.get("source"),
                relationship.get("target"),
                relationship.get("relation") or relationship.get("displayRelation"),
            )
            relationships_by_key[key] = relationship

        score = normalize_primekg_path_score(row, nodes, relationships, anchor_scores)
        paths.append({
            "pathId": stable_id("primekg-question-path", index, path_text),
            "score": score,
            "nodes": nodes,
            "relationships": relationships,
            "pathText": path_text,
            "path_text": path_text,
            "reason": primekg_path_reason(nodes, relationships, detected_entities),
            "length": row.get("length", len(relationships)),
        })
        if len(paths) >= max_paths:
            break

    entities = sorted(entities_by_id.values(), key=lambda item: primekg_node_sort_key(item))
    relationships = sorted(
        relationships_by_key.values(),
        key=lambda item: (item.get("sourceName", ""), item.get("displayRelation") or item.get("relation") or "", item.get("targetName", "")),
    )
    stats = {
        "detectedEntityCount": len(detected_entities or []),
        "pathCount": len(paths),
        "entityCount": len(entities),
        "relationshipCount": len(relationships),
        "maxDepth": max_depth,
        "byNodeType": count_by(entities, "type"),
        "byRelationType": count_by(relationships, "displayRelation", fallback_key="relation"),
    }
    return {
        "status": "ok" if paths else "empty",
        "query": query,
        "selectedDiseaseHint": selected_disease or "",
        "detectedEntities": detected_entities or [],
        "paths": paths,
        "entities": entities,
        "relationships": relationships,
        "pathText": [path["pathText"] for path in paths],
        "path_text": [path["pathText"] for path in paths],
        "stats": stats,
        "message": None if paths else "No bounded PrimeKG evidence paths were found.",
    }


def primekg_question_retrieval_result(question_result):
    paths = question_result.get("paths") or []
    context = format_primekg_context(paths, question_result.get("entities", []), question_result.get("relationships", []), question_result.get("stats", {}))
    matches = primekg_path_matches(paths)
    return {
        "context": context,
        "matches": matches,
        "graphEvidence": {
            "status": "available",
            "backend": "neo4j-primekg",
            "query": question_result.get("query", ""),
            "selectedDiseaseHint": question_result.get("selectedDiseaseHint", ""),
            "detectedEntities": question_result.get("detectedEntities", []),
            "seedEntities": question_result.get("detectedEntities", []),
            "entities": question_result.get("entities", []),
            "relationships": question_result.get("relationships", []),
            "paths": paths,
            "path_text": question_result.get("pathText", []),
            "pathText": question_result.get("pathText", []),
            "stats": question_result.get("stats", {}),
        },
        "graphBackend": "neo4j-primekg",
    }


def empty_primekg_question_result(status, query, selected_disease, message, detected_entities=None, max_depth=2):
    return {
        "status": status,
        "query": query or "",
        "selectedDiseaseHint": selected_disease or "",
        "detectedEntities": detected_entities or [],
        "paths": [],
        "entities": [],
        "relationships": [],
        "pathText": [],
        "path_text": [],
        "stats": {
            "detectedEntityCount": len(detected_entities or []),
            "pathCount": 0,
            "entityCount": 0,
            "relationshipCount": 0,
            "maxDepth": max_depth,
        },
        "message": message,
    }


def primekg_question_row_sort_key(row, anchor_scores):
    nodes = row.get("nodes") or []
    relationships = row.get("relationships") or []
    score = normalize_primekg_path_score(row, nodes, relationships, anchor_scores)
    return (-score, int(row.get("length") or len(relationships) or 0))


def normalize_primekg_path_score(row, nodes, relationships, anchor_scores):
    raw_score = float(row.get("score") or 0)
    node_bonus = sum(PRIMEKG_NODE_TYPE_WEIGHTS.get(node.get("type") or node.get("node_type") or "other", 1) for node in nodes)
    relation_bonus = sum(primekg_relation_relevance(relationship) for relationship in relationships)
    anchor_bonus = max([anchor_scores.get(node.get("id") or node.get("prime_id"), 0) for node in nodes] or [0]) * 10
    length_penalty = max(0, (len(relationships) - 1) * 2)
    normalized = (raw_score + node_bonus + relation_bonus + anchor_bonus - length_penalty) / 100
    return round(max(0.01, min(normalized, 1.0)), 4)


def primekg_relation_relevance(relationship):
    label = normalize_name(relationship.get("displayRelation") or relationship.get("relation") or "")
    score = 1
    for keyword, weight in PRIMEKG_RELATION_KEYWORDS.items():
        if keyword in label:
            score = max(score, weight)
    return score


def primekg_path_reason(nodes, relationships, detected_entities):
    node_types = {node.get("type") or node.get("node_type") or "other" for node in nodes}
    relation_text = " ".join(normalize_name(rel.get("displayRelation") or rel.get("relation") or "") for rel in relationships)
    if "drug" in node_types or "treat" in relation_text or "indication" in relation_text:
        return "Matched an anchor with treatment-related PrimeKG evidence."
    if {"gene/protein", "pathway", "biological_process", "molecular_function"} & node_types:
        return "Matched an anchor with mechanism-related PrimeKG evidence."
    if "phenotype" in node_types or "symptom" in relation_text:
        return "Matched an anchor with phenotype or symptom evidence."
    if detected_entities:
        return "Matched detected PrimeKG anchors with nearby biomedical paths."
    return "Matched bounded PrimeKG graph evidence."


def format_primekg_path(nodes, relationships):
    if not nodes:
        return ""
    parts = [nodes[0].get("name") or nodes[0].get("id") or nodes[0].get("prime_id") or "Unknown"]
    for index, relationship in enumerate(relationships):
        relation = relationship.get("displayRelation") or relationship.get("relation") or "related_to"
        target_node = nodes[index + 1] if index + 1 < len(nodes) else {}
        target = (
            target_node.get("name")
            or relationship.get("targetName")
            or relationship.get("target")
            or "Unknown"
        )
        parts.append(f"--{relation}-->")
        parts.append(target)
    return " ".join(parts)


def format_primekg_context(paths, entities, relationships, stats):
    lines = ["Graph evidence paths:"]
    if paths:
        for index, path in enumerate(paths[:10], start=1):
            path_text = path.get("pathText") or path.get("path_text") or ""
            if len(path_text) > 1200:
                path_text = path_text[:1197].rstrip() + "..."
            lines.append(f"[PrimeKG Path {index}] {path_text}")
    else:
        lines.append("No PrimeKG paths found.")
    if stats:
        lines.append(
            "Stats: "
            f"{stats.get('pathCount', 0)} paths, "
            f"{stats.get('entityCount', len(entities))} entities, "
            f"{stats.get('relationshipCount', len(relationships))} relationships."
        )
    return "\n".join(lines)


def primekg_path_matches(paths):
    matches = []
    for index, path in enumerate(paths[:10], start=1):
        matches.append({
            "text": path.get("path_text", ""),
            "score": float(path.get("score") or 1.0),
            "metadata": {
                "id": stable_id("primekg-path", index, path.get("path_text", "")),
                "title": f"PrimeKG path {index}",
                "source": "neo4j-primekg",
                "stage": "graph",
                "pathLength": path.get("length"),
                "entities": path.get("nodes", []),
            },
        })
    return matches


def empty_primekg_result(message, reason="empty", query_terms=None, seed_entities=None):
    return {
        "context": f"PrimeKG graph retrieval: {message}",
        "matches": [],
        "graphEvidence": {
            "status": "empty",
            "reason": reason,
            "message": message,
            "queryTerms": query_terms or [],
            "seedEntities": seed_entities or [],
            "entities": [],
            "relationships": [],
            "paths": [],
            "path_text": [],
            "stats": {"pathCount": 0, "entityCount": 0, "relationshipCount": 0},
        },
        "graphBackend": "neo4j-primekg",
    }


def empty_graph_result(collection, message):
    return {
        "context": f"Graph context from Neo4j collection '{collection}': {message}",
        "matches": [],
        "graphEvidence": {"status": "empty", "message": message, "entities": [], "relationships": []},
        "graphBackend": "neo4j",
    }


def graph_unavailable_result(status, evidence_status="unavailable"):
    message = status.get("message") or "Neo4j Graph RAG is not available."
    return {
        "context": f"Graph RAG {evidence_status}: {message}",
        "matches": [],
        "graphEvidence": {
            "status": evidence_status,
            "message": message,
            "setupHint": status.get("setupHint", ""),
            "entities": [],
            "relationships": [],
            "paths": [],
            "pathText": [],
            "path_text": [],
            "stats": {"pathCount": 0, "entityCount": 0, "relationshipCount": 0},
        },
        "graphBackend": "neo4j",
    }


def graph_matches(chunk_rows):
    matches = []
    seen = set()
    for row in chunk_rows:
        chunk = row.get("chunk") or {}
        chunk_id = chunk.get("id")
        if not chunk_id or chunk_id in seen:
            continue
        seen.add(chunk_id)
        entities = row.get("entities") or []
        matches.append({
            "text": chunk.get("text", ""),
            "score": 1.0,
            "metadata": {
                "id": chunk_id,
                "title": chunk.get("title") or "Graph evidence",
                "source": chunk.get("source") or "neo4j",
                "chunkIndex": chunk.get("chunkIndex"),
                "stage": "graph",
                "entities": entities,
            },
        })
    return matches


def format_graph_context(collection, entities, relationships, matches):
    lines = [f"Graph context from Neo4j collection '{collection}':"]
    if entities:
        lines.append("Entities:")
        for entity in entities[:12]:
            lines.append(f"- {entity.get('type', 'Entity')}: {entity.get('name')}")
    if relationships:
        lines.append("Relationships:")
        for relationship in relationships[:12]:
            lines.append(
                f"- {relationship.get('sourceName')} -[{relationship.get('type')}]-> {relationship.get('targetName')}"
            )
    if matches:
        lines.append("Evidence chunks:")
        for index, match in enumerate(matches[:5], start=1):
            title = match["metadata"].get("title") or "Graph evidence"
            lines.append(f"[Graph {index}] {title}\n{match['text']}")
    if len(lines) == 1:
        lines.append("No graph evidence found.")
    return "\n\n".join(lines)


def import_seed_graph(payload, config=None):
    collection = payload.get("collection") or "biomedical_kg_demo"
    status = graph_store_status(config)
    if not status["enabled"]:
        return {"status": "disabled", "backend": "neo4j", "collection": collection, "message": status["message"], "store": status}
    if not status["connected"]:
        return {"status": "unavailable", "backend": "neo4j", "collection": collection, "message": status["message"], "store": status}

    entities = payload.get("entities") or []
    relationships = payload.get("relationships") or []
    documents = payload.get("documents") or []
    settings = neo4j_settings(config)
    try:
        with get_driver(config) as driver:
            with driver.session(database=settings["database"]) as session:
                ensure_schema(session)
                session.execute_write(_import_seed_tx, collection, entities, relationships, documents)
    except Exception as exc:
        return {
            "status": "unavailable",
            "backend": "neo4j",
            "collection": collection,
            "message": f"Seed import failed because Neo4j became unavailable: {exc}",
            "store": graph_store_status(config),
        }
    return {
        "status": "seeded",
        "backend": "neo4j",
        "collection": collection,
        "entities": len(entities),
        "relationships": len(relationships),
        "documents": len(documents),
    }


def _import_seed_tx(tx, collection, entities, relationships, documents):
    for entity in entities:
        entity_id = entity.get("id") or entity_id_for(collection, entity.get("name", ""), entity.get("type", "Entity"))
        tx.run(
            """
            MERGE (e:Entity {id: $id})
            SET e.name = $name,
                e.type = $type,
                e.collection = $collection,
                e.description = $description,
                e.updatedAt = timestamp()
            """,
            id=entity_id,
            name=entity.get("name"),
            type=entity.get("type") or "Entity",
            description=entity.get("description") or "",
            collection=collection,
        )
    for doc in documents:
        document_id = doc.get("id") or stable_id(collection, doc.get("source", "seed"), doc.get("title", "Seed document"))
        chunk_id = doc.get("chunkId") or stable_id(document_id, doc.get("text", ""))
        tx.run(
            """
            MERGE (d:Document {id: $documentId})
            SET d.collection = $collection,
                d.title = $title,
                d.source = $source,
                d.updatedAt = timestamp()
            MERGE (c:Chunk {id: $chunkId})
            SET c.collection = $collection,
                c.text = $text,
                c.title = $title,
                c.source = $source,
                c.chunkIndex = 0,
                c.updatedAt = timestamp()
            MERGE (d)-[:HAS_CHUNK]->(c)
            """,
            documentId=document_id,
            chunkId=chunk_id,
            collection=collection,
            title=doc.get("title") or "Seed evidence",
            source=doc.get("source") or "seed",
            text=doc.get("text") or "",
        )
        for entity_id in doc.get("entityIds", []):
            tx.run(
                """
                MATCH (c:Chunk {id: $chunkId})
                MATCH (e:Entity {id: $entityId})
                MERGE (c)-[:MENTIONS]->(e)
                """,
                chunkId=chunk_id,
                entityId=entity_id,
            )
    for relationship in relationships:
        tx.run(
            """
            MATCH (source:Entity {id: $source})
            MATCH (target:Entity {id: $target})
            MERGE (source)-[r:RELATED {collection: $collection, type: $type}]->(target)
            ON CREATE SET r.createdAt = timestamp(), r.evidenceChunkIds = []
            SET r.updatedAt = timestamp(),
                r.evidence = $evidence,
                r.evidenceChunkIds = CASE
                    WHEN $evidenceChunkId IS NULL OR $evidenceChunkId IN coalesce(r.evidenceChunkIds, []) THEN coalesce(r.evidenceChunkIds, [])
                    ELSE coalesce(r.evidenceChunkIds, []) + $evidenceChunkId
                END
            """,
            source=relationship.get("source"),
            target=relationship.get("target"),
            type=relationship.get("type") or "RELATED",
            evidence=relationship.get("evidence") or "",
            evidenceChunkId=relationship.get("evidenceChunkId"),
            collection=collection,
        )


def load_seed_file(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def extract_entities(text):
    found = {}
    for entity_type, terms in BIOMEDICAL_TERMS.items():
        for term in terms:
            if re.search(rf"\b{re.escape(term)}\b", text, flags=re.I):
                found[normalize_name(term)] = {
                    "name": term,
                    "type": entity_type,
                    "id": entity_id_for("", term, entity_type),
                }

    for match in re.finditer(r"\b[A-Z][A-Za-z0-9+-]*(?:\s+[A-Z][A-Za-z0-9+-]*){0,3}\b", text):
        name = match.group(0).strip()
        if name in COMMON_ENTITY_WORDS or len(name) < 3:
            continue
        entity_type = infer_entity_type(name)
        found.setdefault(normalize_name(name), {
            "name": name,
            "type": entity_type,
            "id": entity_id_for("", name, entity_type),
        })

    return list(found.values())[:40]


def extract_relationships(text, entities):
    relationships = []
    if len(entities) < 2:
        return relationships
    sentences = re.split(r"(?<=[.!?])\s+", text)
    for sentence in sentences:
        positioned_entities = []
        for entity in entities:
            match = re.search(rf"\b{re.escape(entity['name'])}\b", sentence, flags=re.I)
            if match:
                positioned_entities.append((match.start(), match.end(), entity))
        accepted = []
        for start, end, entity in sorted(positioned_entities, key=lambda item: (item[0], -(item[1] - item[0]))):
            if any(start < accepted_end and end > accepted_start for accepted_start, accepted_end, _ in accepted):
                continue
            accepted.append((start, end, entity))
        sentence_entities = [
            entity
            for _, _, entity in sorted(accepted, key=lambda item: item[0])
        ]
        if len(sentence_entities) < 2:
            continue
        relation_type = "RELATED"
        for candidate, pattern in RELATION_PATTERNS:
            if pattern.search(sentence):
                relation_type = candidate
                break
        for index in range(len(sentence_entities) - 1):
            relationships.append({
                "source": sentence_entities[index]["name"],
                "target": sentence_entities[index + 1]["name"],
                "type": relation_type,
            })
    return relationships[:80]


def infer_entity_type(name):
    if name.isupper() and len(name) <= 8:
        return "Gene"
    lowered = name.lower()
    if "trial" in lowered or lowered.startswith("nct"):
        return "ClinicalTrial"
    if "pathway" in lowered or "signaling" in lowered:
        return "Pathway"
    return "Entity"


def query_terms(query):
    terms = []
    for token in re.findall(r"[A-Za-z][A-Za-z0-9+-]{2,}", query.lower()):
        if token not in {"what", "which", "with", "from", "about", "through", "between", "connected"}:
            terms.append(token)
    return terms[:12]


def primekg_query_terms(query, disease=None):
    terms = []
    if disease:
        terms.append(normalize_name(disease))
    terms.extend(query_terms(query))
    phrase = normalize_name(query)
    for stop in [
        "what drugs are connected to",
        "what mechanisms are connected to",
        "show graph evidence for",
        "treatment",
        "drugs",
        "mechanisms",
        "connected",
    ]:
        phrase = phrase.replace(stop, " ")
    phrase = normalize_name(phrase)
    if phrase and len(phrase) >= 3:
        terms.append(phrase)
    return sorted({term for term in terms if term})[:12]


def normalize_primekg_allowed_types(allowed_node_types=None):
    if not allowed_node_types:
        return set(PRIMEKG_DEFAULT_NODE_TYPES)
    if isinstance(allowed_node_types, str):
        raw_values = [item.strip() for item in allowed_node_types.split(",")]
    else:
        raw_values = [str(item).strip() for item in allowed_node_types]
    normalized = set()
    for value in raw_values:
        if not value:
            continue
        lowered = normalize_name(value).replace("_", " ")
        normalized_value = PRIMEKG_NODE_TYPE_ALIASES.get(lowered, lowered.replace(" ", "_"))
        if normalized_value in PRIMEKG_DEFAULT_NODE_TYPES:
            normalized.add(normalized_value)
    normalized.add("disease")
    return normalized or set(PRIMEKG_DEFAULT_NODE_TYPES)


def primekg_node_sort_key(node):
    node_type = node.get("type") or node.get("node_type") or "other"
    return (-PRIMEKG_NODE_TYPE_WEIGHTS.get(node_type, 1), node_type, node.get("name", ""))


def count_by(items, key, fallback_key=None):
    counts = {}
    for item in items:
        value = item.get(key) or (item.get(fallback_key) if fallback_key else None) or "unknown"
        counts[value] = counts.get(value, 0) + 1
    return dict(sorted(counts.items()))


def entity_id_for(collection, name, entity_type):
    prefix = f"{collection}:" if collection else ""
    return f"{prefix}{slug(entity_type)}:{slug(name)}:{stable_id(name, entity_type)[:8]}"


def stable_id(*parts):
    text = "::".join(str(part) for part in parts)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:24]


def normalize_name(value):
    return re.sub(r"\s+", " ", str(value).strip().lower())


def slug(value):
    return re.sub(r"[^a-z0-9]+", "-", str(value).lower()).strip("-") or "entity"
