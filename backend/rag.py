import hashlib
import json
import math
import time
from pathlib import Path
from urllib import error, request

try:
    from app_database import save_document_metadata
except ModuleNotFoundError:
    from backend.app_database import save_document_metadata


ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
CHROMA_DIR = DATA_DIR / "chroma"
FALLBACK_VECTOR_FILE = DATA_DIR / "vector_store.json"
DEFAULT_COLLECTION = "course_docs"
DEFAULT_EMBEDDING_MODEL = "nomic-embed-text"
DEFAULT_BASE_URL = "http://127.0.0.1:11434"


def vector_store_status():
    return {
        "backend": "chroma" if chroma_available() else "local-json-fallback",
        "chromaInstalled": chroma_available(),
        "chromaPath": str(CHROMA_DIR),
        "fallbackPath": str(FALLBACK_VECTOR_FILE),
    }


def chroma_available():
    try:
        import chromadb  # noqa: F401

        return True
    except Exception:
        return False


def list_vector_collections():
    collections = {}

    if chroma_available():
        try:
            import chromadb

            client = chromadb.PersistentClient(path=str(CHROMA_DIR))
            for collection in client.list_collections():
                name = collection.name if hasattr(collection, "name") else str(collection)
                count = None
                try:
                    count = client.get_collection(name).count()
                except Exception:
                    pass
                collections[name] = {
                    "name": name,
                    "vectorCount": count,
                    "backend": "chroma",
                }
        except Exception as exc:
            collections["_chroma_error"] = {
                "name": "_chroma_error",
                "error": str(exc),
                "backend": "chroma",
            }

    fallback_store = load_fallback_store()
    for name, items in fallback_store.get("collections", {}).items():
        existing = collections.setdefault(
            name,
            {
                "name": name,
                "vectorCount": 0,
                "backend": "local-json-fallback",
            },
        )
        existing["fallbackCount"] = len(items)
        if existing.get("vectorCount") is None:
            existing["vectorCount"] = len(items)

    return {
        "store": vector_store_status(),
        "collections": [
            value
            for key, value in sorted(collections.items())
            if key != "_chroma_error"
        ],
        "errors": [
            value["error"]
            for key, value in collections.items()
            if key == "_chroma_error" and value.get("error")
        ],
    }


def check_ollama_status(base_url=None):
    endpoint = (base_url or DEFAULT_BASE_URL).rstrip("/")
    try:
        req = request.Request(f"{endpoint}/api/tags", method="GET")
        with request.urlopen(req, timeout=2) as response:
            payload = json.loads(response.read().decode("utf-8"))
        models = [
            item.get("name")
            for item in payload.get("models", [])
            if item.get("name")
        ]
        return {
            "available": True,
            "baseUrl": endpoint,
            "models": models,
        }
    except Exception as exc:
        return {
            "available": False,
            "baseUrl": endpoint,
            "message": str(exc),
        }


def ingest_documents(payload):
    collection = payload.get("collection") or DEFAULT_COLLECTION
    embedding_model = payload.get("embeddingModel") or DEFAULT_EMBEDDING_MODEL
    base_url = payload.get("baseUrl") or DEFAULT_BASE_URL
    chunk_size = int(payload.get("chunkSize") or 700)
    chunk_overlap = int(payload.get("chunkOverlap") or 120)
    documents = payload.get("documents") or []

    if not documents and payload.get("text"):
        documents = [
            {
                "title": payload.get("title") or "Untitled document",
                "source": payload.get("source") or "manual",
                "text": payload.get("text"),
            }
        ]

    if not documents:
        raise ValueError("No documents were provided for ingestion.")

    chunks = []
    for doc in documents:
        text = doc.get("text", "")
        title = doc.get("title") or "Untitled document"
        source = doc.get("source") or "manual"
        doc_chunks = chunk_text(text, chunk_size, chunk_overlap)
        for index, chunk in enumerate(doc_chunks):
            chunks.append(
                {
                    "id": stable_id(collection, source, title, index, chunk),
                    "text": chunk,
                    "metadata": {
                        "title": title,
                        "source": source,
                        "chunkIndex": index,
                        "createdAt": time.time(),
                    },
                }
            )
        save_document_metadata(collection, title, source, len(doc_chunks))

    texts = [chunk["text"] for chunk in chunks]
    embeddings, embedding_backend = embed_texts(texts, embedding_model, base_url)

    if chroma_available():
        upsert_chroma(collection, chunks, embeddings)
        vector_backend = "chroma"
    else:
        upsert_fallback(collection, chunks, embeddings)
        vector_backend = "local-json-fallback"

    return {
        "status": "ingested",
        "collection": collection,
        "chunks": len(chunks),
        "vectorBackend": vector_backend,
        "embeddingBackend": embedding_backend,
        "store": vector_store_status(),
    }


def retrieve_context(config, query):
    collection = config.get("collection") or DEFAULT_COLLECTION
    embedding_model = config.get("embeddingModel") or DEFAULT_EMBEDDING_MODEL
    base_url = config.get("baseUrl") or DEFAULT_BASE_URL
    top_k = int(config.get("topK") or 3)

    if not query.strip():
        return {
            "context": "Retriever received an empty query.",
            "matches": [],
            "vectorBackend": vector_store_status()["backend"],
        }

    query_embedding, embedding_backend = embed_texts([query], embedding_model, base_url)
    if chroma_available():
        matches = query_chroma(collection, query_embedding[0], top_k)
        vector_backend = "chroma"
    else:
        matches = query_fallback(collection, query_embedding[0], top_k)
        vector_backend = "local-json-fallback"

    if not matches:
        return {
            "context": (
                f"No retrieved context found in collection '{collection}'. "
                "Ingest documents first, then run the workflow again."
            ),
            "matches": [],
            "vectorBackend": vector_backend,
            "embeddingBackend": embedding_backend,
        }

    lines = [
        f"Retrieved context from collection '{collection}' using {vector_backend}:",
    ]
    for index, match in enumerate(matches, start=1):
        title = match["metadata"].get("title", "Untitled")
        score = round(match.get("score", 0), 4)
        lines.append(f"[{index}] {title} (score: {score})\n{match['text']}")

    return {
        "context": "\n\n".join(lines),
        "matches": matches,
        "vectorBackend": vector_backend,
        "embeddingBackend": embedding_backend,
    }


def chunk_text(text, chunk_size, overlap):
    cleaned = " ".join(text.split())
    if not cleaned:
        return []

    chunks = []
    start = 0
    while start < len(cleaned):
        end = min(start + chunk_size, len(cleaned))
        chunks.append(cleaned[start:end])
        if end == len(cleaned):
            break
        start = max(0, end - overlap)
    return chunks


def embed_texts(texts, model, base_url):
    try:
        payload = {"model": model, "input": texts}
        data = json.dumps(payload).encode("utf-8")
        req = request.Request(
            f"{base_url.rstrip('/')}/api/embed",
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with request.urlopen(req, timeout=90) as response:
            result = json.loads(response.read().decode("utf-8"))
        embeddings = result.get("embeddings")
        if embeddings and len(embeddings) == len(texts):
            return embeddings, f"ollama:{model}"
    except error.URLError:
        pass
    except Exception:
        pass

    return [hash_embedding(text) for text in texts], "local-hash-fallback"


def hash_embedding(text, dimensions=64):
    vector = [0.0] * dimensions
    for token in text.lower().split():
        digest = hashlib.sha256(token.encode("utf-8")).digest()
        index = int.from_bytes(digest[:2], "big") % dimensions
        sign = 1.0 if digest[2] % 2 == 0 else -1.0
        vector[index] += sign
    return normalize(vector)


def normalize(vector):
    magnitude = math.sqrt(sum(value * value for value in vector))
    if magnitude == 0:
        return vector
    return [value / magnitude for value in vector]


def cosine_similarity(left, right):
    return sum(a * b for a, b in zip(left, right))


def stable_id(*parts):
    text = "::".join(str(part) for part in parts)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:24]


def upsert_chroma(collection, chunks, embeddings):
    import chromadb

    CHROMA_DIR.mkdir(parents=True, exist_ok=True)
    client = chromadb.PersistentClient(path=str(CHROMA_DIR))
    chroma_collection = client.get_or_create_collection(name=collection)
    chroma_collection.upsert(
        ids=[chunk["id"] for chunk in chunks],
        documents=[chunk["text"] for chunk in chunks],
        embeddings=embeddings,
        metadatas=[chunk["metadata"] for chunk in chunks],
    )


def query_chroma(collection, query_embedding, top_k):
    import chromadb

    CHROMA_DIR.mkdir(parents=True, exist_ok=True)
    client = chromadb.PersistentClient(path=str(CHROMA_DIR))
    chroma_collection = client.get_or_create_collection(name=collection)
    result = chroma_collection.query(
        query_embeddings=[query_embedding],
        n_results=top_k,
        include=["documents", "metadatas", "distances"],
    )

    documents = result.get("documents", [[]])[0]
    metadatas = result.get("metadatas", [[]])[0]
    distances = result.get("distances", [[]])[0]
    matches = []
    for doc, metadata, distance in zip(documents, metadatas, distances):
        matches.append({
            "text": doc,
            "metadata": metadata or {},
            "score": 1 / (1 + float(distance)),
        })
    return matches


def load_fallback_store():
    if not FALLBACK_VECTOR_FILE.exists():
        return {"collections": {}}
    return json.loads(FALLBACK_VECTOR_FILE.read_text(encoding="utf-8"))


def save_fallback_store(store):
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    FALLBACK_VECTOR_FILE.write_text(json.dumps(store, indent=2), encoding="utf-8")


def upsert_fallback(collection, chunks, embeddings):
    store = load_fallback_store()
    existing = {
        item["id"]: item
        for item in store.setdefault("collections", {}).setdefault(collection, [])
    }
    for chunk, embedding in zip(chunks, embeddings):
        existing[chunk["id"]] = {
            "id": chunk["id"],
            "text": chunk["text"],
            "metadata": chunk["metadata"],
            "embedding": embedding,
        }
    store["collections"][collection] = list(existing.values())
    save_fallback_store(store)


def query_fallback(collection, query_embedding, top_k):
    store = load_fallback_store()
    items = store.get("collections", {}).get(collection, [])
    scored = []
    for item in items:
        scored.append({
            "text": item["text"],
            "metadata": item.get("metadata", {}),
            "score": cosine_similarity(query_embedding, item.get("embedding", [])),
        })
    return sorted(scored, key=lambda item: item["score"], reverse=True)[:top_k]
