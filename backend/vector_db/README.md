# Vector Database Support Guide

This guide explains how to configure and use different vector database providers with the Visual MAS Tool.

## Supported Providers

### 1. **Chroma** (Default - Local/Persistent)
The default vector database. No configuration needed for basic usage.

```json
{
  "type": "vector_db",
  "config": {
    "vectorBackend": "chroma",
    "embeddingModel": "nomic-embed-text",
    "baseUrl": "http://127.0.0.1:11434"
  }
}
```

**Features:**
- Local storage (no external service)
- Persistent data
- Lightweight and easy to use
- Perfect for development and testing

---

### 2. **Pinecone** (Serverless Managed)
Production-grade serverless vector database with high availability.

```json
{
  "type": "vector_db",
  "config": {
    "vectorBackend": "pinecone",
    "apiKey": "YOUR_PINECONE_API_KEY",
    "indexName": "your-index-name",
    "environment": "us-west4-gcp"
  }
}
```

**Features:**
- Serverless, fully managed
- Global redundancy
- Real-time indexing
- Metadata filtering
- Hybrid search

**Setup:**
```bash
pip install pinecone-client
```

**Pricing:** Pay-as-you-go (requests and storage)

---

### 3. **Weaviate** (Cloud-Native, Open Source)
GraphQL-based vector database with advanced querying capabilities.

```json
{
  "type": "vector_db",
  "config": {
    "vectorBackend": "weaviate",
    "url": "http://localhost:8080",
    "apiKey": "OPTIONAL_API_KEY_FOR_CLOUD_SERVICE"
  }
}
```

**Features:**
- Cloud-native architecture
- GraphQL queries
- Multi-tenancy support
- Replication
- Works both self-hosted and managed

**Setup (Self-Hosted with Docker):**
```bash
docker run -d -p 8080:8080 semitechnologies/weaviate:latest
```

**Setup (Cloud Service):**
Visit https://weaviate.io/cloud and create an account.

**Installation:**
```bash
pip install weaviate-client
```

**Pricing:** Open-source (self-hosted) or managed cloud service

---

### 4. **Qdrant** (Production-Ready Semantic Search)
High-performance vector engine with excellent filtering capabilities.

```json
{
  "type": "vector_db",
  "config": {
    "vectorBackend": "qdrant",
    "url": "http://localhost:6333",
    "apiKey": "OPTIONAL_API_KEY_FOR_QDRANT_CLOUD"
  }
}
```

**Features:**
- High performance
- Advanced filtering
- Batch operations
- Replication support
- In-memory, persistent, or hosted

**Setup (Docker - In-Memory):**
```bash
docker run -p 6333:6333 qdrant/qdrant:latest
```

**Setup (Docker - Persistent):**
```bash
docker run -p 6333:6333 -v qdrant_storage:/qdrant/storage qdrant/qdrant:latest
```

**Installation:**
```bash
pip install qdrant-client
```

**Pricing:** Open-source (self-hosted) or Qdrant Cloud (managed)

---

### 5. **Milvus** (Highly Scalable Open Source)
Enterprise-grade vector database built for large-scale deployments.

```json
{
  "type": "vector_db",
  "config": {
    "vectorBackend": "milvus",
    "host": "localhost",
    "port": 19530,
    "dbName": "default"
  }
}
```

**Features:**
- Highly scalable (handles billions of vectors)
- Fault tolerance
- Support for 50+ index types
- GPU acceleration support
- Cloud-native Kubernetes deployment

**Setup (Docker):**
```bash
docker-compose -f milvus-docker-compose.yml up -d
```

**Installation:**
```bash
pip install pymilvus
```

**Pricing:** Open-source

---

### 6. **Supabase (pgvector)** (PostgreSQL-based)
Leverages PostgreSQL's pgvector extension for vector operations.

```json
{
  "type": "vector_db",
  "config": {
    "vectorBackend": "supabase",
    "url": "https://your-project.supabase.co",
    "apiKey": "YOUR_SUPABASE_API_KEY"
  }
}
```

**Features:**
- Full SQL access
- Transactional guarantees
- Integrated with PostgreSQL ecosystem
- pgvector for vector operations
- Managed cloud service

**Setup:**
1. Create account at https://supabase.com
2. Create a new project
3. Enable pgvector extension in SQL editor:
   ```sql
   CREATE EXTENSION IF NOT EXISTS vector;
   ```

**Installation:**
```bash
pip install supabase psycopg2-binary
```

**Pricing:** Managed cloud service with free tier available

---

### 7. **LanceDB** (Local Efficient)
Fast, efficient vector database built on Apache Lance format.

```json
{
  "type": "vector_db",
  "config": {
    "vectorBackend": "lancedb",
    "dbPath": "./lancedb_data"
  }
}
```

**Features:**
- Local-first design
- Extremely fast queries
- Low memory overhead
- Pandas integration
- Great for local development

**Setup:**
```bash
pip install lancedb
```

**Pricing:** Open-source, free

---

## Configuration in Workflows

### Example: RAG with Pinecone

```json
{
  "nodes": [
    {
      "id": "retriever-1",
      "type": "retriever",
      "config": {
        "vectorBackend": "pinecone",
        "apiKey": "YOUR_API_KEY",
        "indexName": "rag-documents",
        "embeddingModel": "nomic-embed-text",
        "topK": 5
      }
    }
  ]
}
```

### Example: RAG with Qdrant

```json
{
  "nodes": [
    {
      "id": "retriever-1",
      "type": "retriever",
      "config": {
        "vectorBackend": "qdrant",
        "url": "http://localhost:6333",
        "collectionName": "my_documents",
        "topK": 5
      }
    }
  ]
}
```

---

## Comparison Table

| Provider | Type | Deployment | Cost | Best For |
|----------|------|-----------|------|----------|
| **Chroma** | Local | Self-hosted | Free | Development, Testing |
| **Pinecone** | Managed | Cloud | Pay-as-you-go | Production, Scaling |
| **Weaviate** | Open Source | Both | Free/Managed | GraphQL queries, Advanced filtering |
| **Qdrant** | Open Source | Both | Free/Managed | Performance, Filtering |
| **Milvus** | Open Source | Self-hosted | Free | Large-scale deployments |
| **Supabase** | Managed | Cloud | Pay-as-you-go | SQL-first, PostgreSQL integration |
| **LanceDB** | Open Source | Local | Free | Local efficiency, Development |

---

## Getting Provider Info

### API Endpoint
```bash
curl http://localhost:8000/api/vector-db/providers
```

**Response:**
```json
{
  "providers": {
    "pinecone": {
      "name": "Pinecone",
      "type": "serverless_managed",
      "capabilities": ["semantic_search", "hybrid_search", "metadata_filtering"],
      "required_config": ["api_key", "index_name"],
      "optional_config": ["environment"]
    },
    "qdrant": { ... },
    ...
  },
  "list": ["pinecone", "weaviate", "qdrant", "milvus", "supabase", "lancedb", "chroma"]
}
```

---

## Migration Guide

### From Chroma to Pinecone

1. **Export data from Chroma**
2. **Create Pinecone index** with same embedding dimension (384 for nomic-embed-text)
3. **Update workflow config:**
   ```json
   "vectorBackend": "pinecone",
   "apiKey": "YOUR_KEY",
   "indexName": "your-index"
   ```

### From Chroma to Qdrant

1. **Start Qdrant instance** (Docker or cloud)
2. **Update config:**
   ```json
   "vectorBackend": "qdrant",
   "url": "http://localhost:6333"
   ```

---

## Performance Considerations

### Query Speed
**Fast:** LanceDB (local), Qdrant, Pinecone
**Medium:** Milvus, Weaviate
**Slower:** Chroma (local), Supabase (network overhead)

### Scalability
**Best:** Pinecone, Milvus, Weaviate
**Good:** Qdrant, Supabase
**Limited:** Chroma, LanceDB (local)

### Memory Usage
**Lowest:** LanceDB
**Low:** Qdrant
**Medium:** Milvus, Pinecone
**High:** Chroma (for large datasets)

---

## Troubleshooting

### Connection Issues
- Verify provider is running/accessible
- Check firewall and network settings
- Validate API keys and credentials

### Performance Issues
- Adjust index parameters for your provider
- Use batching for large ingestions
- Monitor resource usage

### Data Migration
- Export embeddings and metadata
- Create new collection/index
- Re-ingest data with new provider

---

## Extending with Custom Providers

Create a custom provider by extending `VectorDatabaseProvider`:

```python
from backend.vector_db import VectorDatabaseProvider, VectorDatabaseRegistry

class CustomProvider(VectorDatabaseProvider):
    async def connect(self): ...
    async def disconnect(self): ...
    async def upsert(self, ...): ...
    async def search(self, ...): ...
    # ... implement other methods
    
    @staticmethod
    def get_provider_info():
        return {"name": "Custom", ...}

# Register
VectorDatabaseRegistry.register_provider("custom", CustomProvider)
```

---

## Resources

- **Pinecone:** https://www.pinecone.io/docs
- **Weaviate:** https://weaviate.io/developers/weaviate
- **Qdrant:** https://qdrant.tech/documentation
- **Milvus:** https://milvus.io/docs
- **Supabase pgvector:** https://supabase.com/docs/guides/ai/vector-columns
- **LanceDB:** https://lancedb.com/docs
- **Chroma:** https://docs.trychroma.com
