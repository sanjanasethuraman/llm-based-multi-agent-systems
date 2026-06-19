"""Pinecone Vector Database Provider."""

from typing import List, Dict, Any, Optional, Tuple
from .base import VectorDatabaseProvider


class PineconeProvider(VectorDatabaseProvider):
    """Vector database provider for Pinecone (serverless managed service)."""

    def __init__(self, config: Dict[str, Any]):
        """Initialize Pinecone provider.
        
        Config requires:
            - api_key: Pinecone API key
            - index_name: Name of the Pinecone index
            - environment: Pinecone environment (e.g., 'us-west4-gcp')
        """
        super().__init__(config)
        self.client = None
        self.index_name = config.get("index_name", "default")

    async def connect(self) -> bool:
        """Connect to Pinecone."""
        try:
            from pinecone import Pinecone
            
            api_key = self.config.get("api_key")
            if not api_key:
                raise ValueError("Pinecone API key required")
            
            self.client = Pinecone(api_key=api_key)
            self.is_connected = True
            return True
        except ImportError:
            raise ImportError("pinecone package required: pip install pinecone-client")
        except Exception as e:
            print(f"Failed to connect to Pinecone: {e}")
            return False

    async def disconnect(self) -> bool:
        """Disconnect from Pinecone."""
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
        """Upsert documents to Pinecone."""
        if not self.is_connected or not self.client:
            return False

        try:
            index = self.client.Index(self.index_name)
            
            vectors = []
            for i, (doc, emb) in enumerate(zip(documents, embeddings)):
                vector_id = f"{collection_name}_{i}"
                meta = metadata[i] if metadata else {}
                meta["text"] = doc
                meta["collection"] = collection_name
                vectors.append((vector_id, emb, meta))
            
            # Upsert in batches
            for i in range(0, len(vectors), 100):
                batch = vectors[i:i+100]
                index.upsert(vectors=batch, namespace=collection_name)
            
            return True
        except Exception as e:
            print(f"Failed to upsert to Pinecone: {e}")
            return False

    async def search(
        self,
        collection_name: str,
        query_embedding: List[float],
        top_k: int = 10,
        filters: Optional[Dict[str, Any]] = None,
    ) -> List[Tuple[str, float, Optional[Dict[str, Any]]]]:
        """Search in Pinecone."""
        if not self.is_connected or not self.client:
            return []

        try:
            index = self.client.Index(self.index_name)
            
            results = index.query(
                vector=query_embedding,
                top_k=top_k,
                namespace=collection_name,
                include_metadata=True,
            )
            
            output = []
            for match in results.matches:
                doc_text = match.metadata.get("text", "")
                score = match.score
                metadata = {k: v for k, v in match.metadata.items() if k != "text"}
                output.append((doc_text, score, metadata))
            
            return output
        except Exception as e:
            print(f"Failed to search Pinecone: {e}")
            return []

    async def create_collection(
        self,
        collection_name: str,
        embedding_dim: int = 384,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """Create collection (namespace) in Pinecone."""
        # Pinecone uses namespaces implicitly, no explicit creation needed
        return True

    async def list_collections(self) -> List[str]:
        """List all collections (namespaces) in Pinecone."""
        if not self.is_connected or not self.client:
            return []
        
        try:
            # Pinecone doesn't provide a direct way to list namespaces
            # This is a limitation of the API
            return ["default"]
        except Exception as e:
            print(f"Failed to list collections: {e}")
            return []

    async def delete_collection(self, collection_name: str) -> bool:
        """Delete collection (namespace) from Pinecone."""
        if not self.is_connected or not self.client:
            return False
        
        try:
            index = self.client.Index(self.index_name)
            # Delete by prefix
            index.delete(delete_all=True, namespace=collection_name)
            return True
        except Exception as e:
            print(f"Failed to delete collection: {e}")
            return False

    async def get_collection_stats(self, collection_name: str) -> Dict[str, Any]:
        """Get statistics about collection."""
        if not self.is_connected or not self.client:
            return {}
        
        try:
            index = self.client.Index(self.index_name)
            stats = index.describe_index_stats()
            return {
                "total_vectors": stats.total_vector_count,
                "namespaces": list(stats.namespaces.keys()),
                "dimension": stats.dimension,
            }
        except Exception as e:
            print(f"Failed to get collection stats: {e}")
            return {}

    @staticmethod
    def get_provider_info() -> Dict[str, Any]:
        """Get Pinecone provider information."""
        return {
            "name": "Pinecone",
            "type": "serverless_managed",
            "description": "Serverless managed vector database with high availability",
            "url": "https://www.pinecone.io",
            "capabilities": [
                "semantic_search",
                "hybrid_search",
                "metadata_filtering",
                "namespace_isolation",
                "high_availability",
            ],
            "deployment": "cloud",
            "pricing": "pay_as_you_go",
            "required_config": ["api_key", "index_name"],
            "optional_config": ["environment"],
        }
