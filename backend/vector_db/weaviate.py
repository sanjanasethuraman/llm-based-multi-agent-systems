"""Weaviate Vector Database Provider."""

from typing import List, Dict, Any, Optional, Tuple
from .base import VectorDatabaseProvider


class WeaviateProvider(VectorDatabaseProvider):
    """Vector database provider for Weaviate (cloud-native, open-source)."""

    def __init__(self, config: Dict[str, Any]):
        """Initialize Weaviate provider.
        
        Config requires:
            - url: Weaviate instance URL (e.g., 'http://localhost:8080')
        
        Optional:
            - api_key: For Weaviate Cloud Service
            - headers: Custom headers for authentication
        """
        super().__init__(config)
        self.client = None

    async def connect(self) -> bool:
        """Connect to Weaviate."""
        try:
            import weaviate
            
            url = self.config.get("url", "http://localhost:8080")
            api_key = self.config.get("api_key")
            headers = self.config.get("headers", {})
            
            if api_key:
                headers["Authorization"] = f"Bearer {api_key}"
            
            self.client = weaviate.Client(
                url=url,
                additional_headers=headers if headers else None
            )
            
            # Verify connection
            if not self.client.is_ready():
                raise ConnectionError("Weaviate instance not ready")
            
            self.is_connected = True
            return True
        except ImportError:
            raise ImportError("weaviate-client package required: pip install weaviate-client")
        except Exception as e:
            print(f"Failed to connect to Weaviate: {e}")
            return False

    async def disconnect(self) -> bool:
        """Disconnect from Weaviate."""
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
        """Upsert documents to Weaviate."""
        if not self.is_connected or not self.client:
            return False

        try:
            # Ensure collection exists
            await self.create_collection(collection_name, len(embeddings[0]))
            
            for i, (doc, emb) in enumerate(zip(documents, embeddings)):
                data_object = {
                    "text": doc,
                    "document_index": i,
                }
                
                if metadata:
                    data_object.update(metadata[i])
                
                self.client.data_object.create(
                    data_object,
                    class_name=collection_name.capitalize(),
                    vector=emb,
                )
            
            return True
        except Exception as e:
            print(f"Failed to upsert to Weaviate: {e}")
            return False

    async def search(
        self,
        collection_name: str,
        query_embedding: List[float],
        top_k: int = 10,
        filters: Optional[Dict[str, Any]] = None,
    ) -> List[Tuple[str, float, Optional[Dict[str, Any]]]]:
        """Search in Weaviate."""
        if not self.is_connected or not self.client:
            return []

        try:
            results = self.client.query.get(
                collection_name.capitalize(),
                ["text", "_additional {distance vector}"]
            ).with_near_vector({"vector": query_embedding}).with_limit(top_k).do()
            
            output = []
            for item in results.get("data", {}).get("Get", {}).get(collection_name.capitalize(), []):
                doc_text = item.get("text", "")
                distance = item.get("_additional", {}).get("distance", 1.0)
                # Convert distance to similarity score
                similarity = 1 - (distance / 2)
                metadata = {k: v for k, v in item.items() if k not in ["text", "_additional"]}
                output.append((doc_text, similarity, metadata))
            
            return output
        except Exception as e:
            print(f"Failed to search Weaviate: {e}")
            return []

    async def create_collection(
        self,
        collection_name: str,
        embedding_dim: int = 384,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """Create collection in Weaviate."""
        if not self.is_connected or not self.client:
            return False

        try:
            class_name = collection_name.capitalize()
            
            # Check if class already exists
            if self.client.schema.get(class_name):
                return True
            
            class_obj = {
                "class": class_name,
                "properties": [
                    {
                        "name": "text",
                        "dataType": ["text"]
                    },
                    {
                        "name": "document_index",
                        "dataType": ["int"]
                    }
                ],
                "vectorizer": "none",  # We provide vectors directly
            }
            
            self.client.schema.create_class(class_obj)
            return True
        except Exception as e:
            print(f"Failed to create collection: {e}")
            return False

    async def list_collections(self) -> List[str]:
        """List all collections in Weaviate."""
        if not self.is_connected or not self.client:
            return []

        try:
            schema = self.client.schema.get()
            return [cls["class"].lower() for cls in schema.get("classes", [])]
        except Exception as e:
            print(f"Failed to list collections: {e}")
            return []

    async def delete_collection(self, collection_name: str) -> bool:
        """Delete collection from Weaviate."""
        if not self.is_connected or not self.client:
            return False

        try:
            self.client.schema.delete_class(collection_name.capitalize())
            return True
        except Exception as e:
            print(f"Failed to delete collection: {e}")
            return False

    async def get_collection_stats(self, collection_name: str) -> Dict[str, Any]:
        """Get statistics about collection."""
        if not self.is_connected or not self.client:
            return {}

        try:
            class_name = collection_name.capitalize()
            result = self.client.query.aggregate(class_name).with_meta_count().do()
            count = result.get("data", {}).get("Aggregate", {}).get(class_name, [{}])[0].get("meta", {}).get("count", 0)
            
            return {
                "document_count": count,
                "collection_name": collection_name,
            }
        except Exception as e:
            print(f"Failed to get collection stats: {e}")
            return {}

    @staticmethod
    def get_provider_info() -> Dict[str, Any]:
        """Get Weaviate provider information."""
        return {
            "name": "Weaviate",
            "type": "open_source_cloud_native",
            "description": "Cloud-native, open-source vector database with powerful queries",
            "url": "https://weaviate.io",
            "capabilities": [
                "semantic_search",
                "hybrid_search",
                "metadata_filtering",
                "graphql_queries",
                "multi_tenancy",
                "replication",
            ],
            "deployment": ["self_hosted", "cloud"],
            "pricing": "open_source_and_managed",
            "required_config": ["url"],
            "optional_config": ["api_key", "headers"],
        }
