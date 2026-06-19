"""Qdrant Vector Database Provider."""

from typing import List, Dict, Any, Optional, Tuple
from .base import VectorDatabaseProvider


class QdrantProvider(VectorDatabaseProvider):
    """Vector database provider for Qdrant (production-ready semantic search)."""

    def __init__(self, config: Dict[str, Any]):
        """Initialize Qdrant provider.
        
        Config requires either:
            - For in-memory: mode='memory'
            - For persistent: path='/path/to/db'
            - For server: url='http://localhost:6333'
        
        Optional:
            - api_key: API key for Qdrant Cloud
        """
        super().__init__(config)
        self.client = None

    async def connect(self) -> bool:
        """Connect to Qdrant."""
        try:
            from qdrant_client import QdrantClient
            
            mode = self.config.get("mode", "server")
            url = self.config.get("url")
            path = self.config.get("path")
            api_key = self.config.get("api_key")
            
            if mode == "memory":
                self.client = QdrantClient(":memory:")
            elif mode == "persistent" and path:
                self.client = QdrantClient(path=path)
            elif url:
                self.client = QdrantClient(
                    url=url,
                    api_key=api_key if api_key else None
                )
            else:
                raise ValueError("Qdrant configuration incomplete")
            
            self.is_connected = True
            return True
        except ImportError:
            raise ImportError("qdrant-client package required: pip install qdrant-client")
        except Exception as e:
            print(f"Failed to connect to Qdrant: {e}")
            return False

    async def disconnect(self) -> bool:
        """Disconnect from Qdrant."""
        if self.client:
            self.client.close()
        self.client = None
        self.is_connected = False
        return True

    async def upsert(
        self,
        collection_name: str,
        documents: List[str],
        embeddings: List[List[float]],
        metadata: Optional[List[Dict[str, Any]]] = None,
    ) -> bool:
        """Upsert documents to Qdrant."""
        if not self.is_connected or not self.client:
            return False

        try:
            # Create collection if needed
            await self.create_collection(collection_name, len(embeddings[0]))
            
            from qdrant_client.models import PointStruct
            
            points = []
            for i, (doc, emb) in enumerate(zip(documents, embeddings)):
                payload = {
                    "text": doc,
                    "document_index": i,
                    "collection": collection_name,
                }
                
                if metadata and i < len(metadata):
                    payload.update(metadata[i])
                
                points.append(PointStruct(
                    id=i,
                    vector=emb,
                    payload=payload
                ))
            
            self.client.upsert(
                collection_name=collection_name,
                points=points
            )
            
            return True
        except Exception as e:
            print(f"Failed to upsert to Qdrant: {e}")
            return False

    async def search(
        self,
        collection_name: str,
        query_embedding: List[float],
        top_k: int = 10,
        filters: Optional[Dict[str, Any]] = None,
    ) -> List[Tuple[str, float, Optional[Dict[str, Any]]]]:
        """Search in Qdrant."""
        if not self.is_connected or not self.client:
            return []

        try:
            results = self.client.search(
                collection_name=collection_name,
                query_vector=query_embedding,
                limit=top_k,
                query_filter=filters
            )
            
            output = []
            for result in results:
                doc_text = result.payload.get("text", "")
                similarity = result.score
                metadata = {k: v for k, v in result.payload.items() if k != "text"}
                output.append((doc_text, similarity, metadata))
            
            return output
        except Exception as e:
            print(f"Failed to search Qdrant: {e}")
            return []

    async def create_collection(
        self,
        collection_name: str,
        embedding_dim: int = 384,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """Create collection in Qdrant."""
        if not self.is_connected or not self.client:
            return False

        try:
            from qdrant_client.models import Distance, VectorParams
            
            # Check if collection exists
            try:
                self.client.get_collection(collection_name)
                return True
            except:
                pass
            
            self.client.recreate_collection(
                collection_name=collection_name,
                vectors_config=VectorParams(
                    size=embedding_dim,
                    distance=Distance.COSINE
                )
            )
            
            return True
        except Exception as e:
            print(f"Failed to create collection: {e}")
            return False

    async def list_collections(self) -> List[str]:
        """List all collections in Qdrant."""
        if not self.is_connected or not self.client:
            return []

        try:
            collections = self.client.get_collections()
            return [col.name for col in collections.collections]
        except Exception as e:
            print(f"Failed to list collections: {e}")
            return []

    async def delete_collection(self, collection_name: str) -> bool:
        """Delete collection from Qdrant."""
        if not self.is_connected or not self.client:
            return False

        try:
            self.client.delete_collection(collection_name)
            return True
        except Exception as e:
            print(f"Failed to delete collection: {e}")
            return False

    async def get_collection_stats(self, collection_name: str) -> Dict[str, Any]:
        """Get statistics about collection."""
        if not self.is_connected or not self.client:
            return {}

        try:
            collection_info = self.client.get_collection(collection_name)
            return {
                "points_count": collection_info.points_count,
                "vector_size": collection_info.config.params.vectors.size,
                "distance": str(collection_info.config.params.vectors.distance),
            }
        except Exception as e:
            print(f"Failed to get collection stats: {e}")
            return {}

    @staticmethod
    def get_provider_info() -> Dict[str, Any]:
        """Get Qdrant provider information."""
        return {
            "name": "Qdrant",
            "type": "open_source_production_ready",
            "description": "High-performance, production-ready vector search engine",
            "url": "https://qdrant.tech",
            "capabilities": [
                "semantic_search",
                "filtering",
                "payload_storage",
                "batch_operations",
                "replication",
                "high_performance",
            ],
            "deployment": ["self_hosted", "cloud", "in_memory"],
            "pricing": "open_source_and_managed",
            "required_config": ["url"],
            "optional_config": ["api_key", "mode", "path"],
        }
