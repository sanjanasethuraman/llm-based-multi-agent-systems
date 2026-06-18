import hashlib
import json
import os
import re
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_URI = "bolt://127.0.0.1:7687"
DEFAULT_USER = "neo4j"
DEFAULT_PASSWORD = "visualmas"
DEFAULT_DATABASE = "neo4j"

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


def graph_store_status(config=None):
    settings = neo4j_settings(config)
    status = {
        "backend": "neo4j",
        "uri": settings["uri"],
        "database": settings["database"],
        "configured": bool(settings["uri"] and settings["user"] and settings["password"]),
        "driverInstalled": False,
        "connected": False,
        "message": "",
    }
    try:
        import neo4j  # noqa: F401

        status["driverInstalled"] = True
    except Exception:
        status["message"] = "Install the neo4j Python package to enable Graph RAG."
        return status

    if not status["configured"]:
        status["message"] = "Set NEO4J_URI, NEO4J_USER, and NEO4J_PASSWORD."
        return status

    try:
        with get_driver(config) as driver:
            with driver.session(database=settings["database"]) as session:
                session.run("RETURN 1 AS ok").single()
        status["connected"] = True
        status["message"] = "Neo4j is reachable."
    except Exception as exc:
        status["message"] = str(exc)
    return status


def neo4j_settings(config=None):
    config = config or {}
    return {
        "uri": config.get("neo4jUri") or os.environ.get("NEO4J_URI") or DEFAULT_URI,
        "user": config.get("neo4jUser") or os.environ.get("NEO4J_USER") or DEFAULT_USER,
        "password": config.get("neo4jPassword") or os.environ.get("NEO4J_PASSWORD") or DEFAULT_PASSWORD,
        "database": config.get("neo4jDatabase") or os.environ.get("NEO4J_DATABASE") or DEFAULT_DATABASE,
    }


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
    if not status["connected"]:
        return {"status": "unavailable", "message": status["message"], "store": status}

    settings = neo4j_settings(config)
    started = time.perf_counter()
    total_entities = 0
    total_relationships = 0
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
    if not status["connected"]:
        return {
            "context": f"Graph RAG unavailable: {status['message']}",
            "matches": [],
            "graphEvidence": {"status": "unavailable", "message": status["message"], "entities": [], "relationships": []},
            "graphBackend": "neo4j",
        }

    hops = max(1, min(int(hops or 1), 3))
    top_k = max(1, min(int(top_k or 5), 20))
    terms = query_terms(query)
    query_entities = extract_entities(query)
    terms.extend(normalize_name(entity["name"]) for entity in query_entities)
    terms = sorted({term for term in terms if term})

    if not terms:
        return empty_graph_result(collection, "No query terms were available for graph lookup.")

    settings = neo4j_settings(config)
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


def empty_graph_result(collection, message):
    return {
        "context": f"Graph context from Neo4j collection '{collection}': {message}",
        "matches": [],
        "graphEvidence": {"status": "empty", "message": message, "entities": [], "relationships": []},
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
    if not status["connected"]:
        raise ValueError(f"Neo4j is not available: {status['message']}")

    entities = payload.get("entities") or []
    relationships = payload.get("relationships") or []
    documents = payload.get("documents") or []
    settings = neo4j_settings(config)
    with get_driver(config) as driver:
        with driver.session(database=settings["database"]) as session:
            ensure_schema(session)
            session.execute_write(_import_seed_tx, collection, entities, relationships, documents)
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
