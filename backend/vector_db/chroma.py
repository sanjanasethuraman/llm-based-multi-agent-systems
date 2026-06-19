"""Chroma Vector Database Provider (Backward Compatibility)."""

from typing import List, Dict, Any, Optional, Tuple
from .base import VectorDatabaseProvider


class ChromaProvider(VectorDatabaseProvider):
    """Vector database provider for Chroma (existing support)."""

    def __init__(self, config: Dict[str, Any]):
        """Initialize Chroma provider.
        
        Config optional:
            - persist_directory: Directory for persistent storage
            - anonymized_telemetry: Enable telemetry (default: False)
        """
        super().__init__(config)
        self.client = None

    async def connect(self) -> bool:
        """Connect to Chroma."""
        try:
            import chromadb
            
            persist_dir = self.config.get("persist_directory", "./chroma_data")
            
            self.client = chromadb.Client(
                settings=chromadb.Settings(
                    persist_directory=persist_dir,
                    anonymized_telemetry=self.config.get("anonymized_telemetry", False),
                    is_persistent=True,
                )
            )
            
            self.is_connected = True
            return True
        except ImportError:
            raise ImportError("chromadb package required: pip install chromadb")
        except Exception as e:
            print(f"Failed to connect to Chroma: {e}")
            return False

    async def disconnect(self) -> bool:
        """Disconnect from Chroma."""
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
        """Upsert documents to Chroma."""
        if not self.is_connected or not self.client:
            return False

        try:
            collection = self.client.get_or_create_collection(name=collection_name)
            
            ids = [f"{collection_name}_{i}" for i in range(len(documents))]
            
            collection.upsert(
                ids=ids,
                embeddings=embeddings,
                documents=documents,
                metadatas=metadata or [{}] * len(documents)
            )
            
            return True
        except Exception as e:
            print(f"Failed to upsert to Chroma: {e}")
            return False

    async def search(
        self,
        collection_name: str,
        query_embedding: List[float],
        top_k: int = 10,
        filters: Optional[Dict[str, Any]] = None,
    ) -> List[Tuple[str, float, Optional[Dict[str, Any]]]]:
        """Search in Chroma."""
        if not self.is_connected or not self.client:
            return []

        try:
            collection = self.client.get_collection(name=collection_name)
            
            results = collection.query(
                query_embeddings=[query_embedding],
                n_results=top_k,
                where=filters
            )
            
            output = []
            for i, doc in enumerate(results["documents"][0]):
                distance = results["distances"][0][i]
                # Convert Chroma distance to similarity
                similarity = 1 - (distance / 2)
                metadata = results["metadatas"][0][i] if results["metadatas"] else {}
                output.append((doc, similarity, metadata))
            
            return output
        except Exception as e:
            print(f"Failed to search Chroma: {e}")
            return []

    async def create_collection(
        self,
        collection_name: str,
        embedding_dim: int = 384,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """Create collection in Chroma."""
        if not self.is_connected or not self.client:
            return False

        try:
            self.client.get_or_create_collection(
                name=collection_name,
                metadata=metadata or {}
            )
            return True
        except Exception as e:
            print(f"Failed to create collection: {e}")
            return False

    async def list_collections(self) -> List[str]:
        """List all collections in Chroma."""
        if not self.is_connected or not self.client:
            return []

        try:
            collections = self.client.list_collections()
            return [col.name for col in collections]
        except Exception as e:
            print(f"Failed to list collections: {e}")
            return []

    async def delete_collection(self, collection_name: str) -> bool:
        """Delete collection from Chroma."""
        if not self.is_connected or not self.client:
            return False

        try:
            self.client.delete_collection(name=collection_name)
            return True
        except Exception as e:
            print(f"Failed to delete collection: {e}")
            return False

    async def get_collection_stats(self, collection_name: str) -> Dict[str, Any]:
        """Get statistics about collection."""
        if not self.is_connected or not self.client:
            return {}

        try:
            collection = self.client.get_collection(name=collection_name)
            count = collection.count()
            
            return {
                "document_count": count,
                "collection_name": collection_name,
            }
        except Exception as e:
            print(f"Failed to get collection stats: {e}")
            return {}

    @staticmethod
    def get_provider_info() -> Dict[str, Any]:
        """Get Chroma provider information."""
        return {
            "name": "Chroma",
            "type": "open_source_local",
            "description": "Lightweight, in-memory or persistent vector database",
            "url": "https://www.trychroma.com",
            "capabilities": [
                "semantic_search",
                "persistent_storage",
                "metadata_filtering",
                "easy_to_use",
            ],
            "deployment": "self_hosted",
            "pricing": "open_source",
            "required_config": [],
            "optional_config": ["persist_directory", "anonymized_telemetry"],
        }
