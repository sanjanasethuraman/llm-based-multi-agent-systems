"""Vector Database Providers Module."""

from .base import VectorDatabaseProvider
from .registry import VectorDatabaseRegistry
from .pinecone import PineconeProvider
from .weaviate import WeaviateProvider
from .qdrant import QdrantProvider
from .milvus import MilvusProvider
from .supabase import SupabasePgVectorProvider
from .lancedb import LanceDBProvider

try:
    from .chroma import ChromaProvider
except ImportError:
    ChromaProvider = None

__all__ = [
    "VectorDatabaseProvider",
    "VectorDatabaseRegistry",
    "PineconeProvider",
    "WeaviateProvider",
    "QdrantProvider",
    "MilvusProvider",
    "SupabasePgVectorProvider",
    "LanceDBProvider",
    "ChromaProvider",
]
