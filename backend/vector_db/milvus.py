"""Milvus Vector Database Provider."""

from typing import List, Dict, Any, Optional, Tuple
from .base import VectorDatabaseProvider


class MilvusProvider(VectorDatabaseProvider):
    """Vector database provider for Milvus (highly scalable open-source)."""

    def __init__(self, config: Dict[str, Any]):
        """Initialize Milvus provider.
        
        Config requires:
            - host: Milvus host (default: 'localhost')
            - port: Milvus port (default: 19530)
        
        Optional:
            - db_name: Database name (default: 'default')
            - user: Username for authentication
            - password: Password for authentication
        """
        super().__init__(config)
        self.client = None

    async def connect(self) -> bool:
        """Connect to Milvus."""
        try:
            from pymilvus import connections, Collection
            
            host = self.config.get("host", "localhost")
            port = self.config.get("port", 19530)
            db_name = self.config.get("db_name", "default")
            user = self.config.get("user")
            password = self.config.get("password")
            
            # Prepare connection parameters
            conn_params = {
                "alias": "default",
                "host": host,
                "port": port,
            }
            
            if user and password:
                conn_params["user"] = user
                conn_params["password"] = password
            
            connections.connect(**conn_params)
            self.db_name = db_name
            self.is_connected = True
            return True
        except ImportError:
            raise ImportError("pymilvus package required: pip install pymilvus")
        except Exception as e:
            print(f"Failed to connect to Milvus: {e}")
            return False

    async def disconnect(self) -> bool:
        """Disconnect from Milvus."""
        try:
            from pymilvus import connections
            connections.disconnect(alias="default")
        except Exception:
            pass
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
        """Upsert documents to Milvus."""
        if not self.is_connected:
            return False

        try:
            from pymilvus import Collection
            
            # Create collection if needed
            await self.create_collection(collection_name, len(embeddings[0]))
            
            collection = Collection(collection_name)
            
            entities = [
                list(range(len(documents))),  # id
                documents,  # text
                embeddings,  # embedding
            ]
            
            if metadata:
                # Add metadata fields
                for i in range(len(metadata)):
                    if "title" in metadata[i]:
                        entities.append([m.get("title", "") for m in metadata])
            
            collection.insert(entities)
            collection.flush()
            
            return True
        except Exception as e:
            print(f"Failed to upsert to Milvus: {e}")
            return False

    async def search(
        self,
        collection_name: str,
        query_embedding: List[float],
        top_k: int = 10,
        filters: Optional[Dict[str, Any]] = None,
    ) -> List[Tuple[str, float, Optional[Dict[str, Any]]]]:
        """Search in Milvus."""
        if not self.is_connected:
            return []

        try:
            from pymilvus import Collection
            
            collection = Collection(collection_name)
            collection.load()
            
            search_params = {"metric_type": "COSINE_SIM", "params": {"nprobe": 10}}
            
            results = collection.search(
                [query_embedding],
                "embedding",
                search_params,
                limit=top_k,
                output_fields=["text"]
            )
            
            output = []
            for hits in results:
                for hit in hits:
                    doc_text = hit.entity.get("text", "")
                    similarity = hit.score
                    output.append((doc_text, similarity, {}))
            
            collection.release()
            return output
        except Exception as e:
            print(f"Failed to search Milvus: {e}")
            return []

    async def create_collection(
        self,
        collection_name: str,
        embedding_dim: int = 384,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """Create collection in Milvus."""
        if not self.is_connected:
            return False

        try:
            from pymilvus import Collection, CollectionSchema, FieldSchema, DataType
            
            # Check if collection exists
            try:
                Collection(collection_name)
                return True
            except:
                pass
            
            fields = [
                FieldSchema(name="id", dtype=DataType.INT64, is_primary=True),
                FieldSchema(name="text", dtype=DataType.VARCHAR, max_length=5000),
                FieldSchema(name="embedding", dtype=DataType.FLOAT_VECTOR, dim=embedding_dim),
            ]
            
            schema = CollectionSchema(fields=fields)
            Collection(collection_name, schema=schema)
            
            return True
        except Exception as e:
            print(f"Failed to create collection: {e}")
            return False

    async def list_collections(self) -> List[str]:
        """List all collections in Milvus."""
        if not self.is_connected:
            return []

        try:
            from pymilvus import utility
            return utility.list_collections()
        except Exception as e:
            print(f"Failed to list collections: {e}")
            return []

    async def delete_collection(self, collection_name: str) -> bool:
        """Delete collection from Milvus."""
        if not self.is_connected:
            return False

        try:
            from pymilvus import utility
            utility.drop_collection(collection_name)
            return True
        except Exception as e:
            print(f"Failed to delete collection: {e}")
            return False

    async def get_collection_stats(self, collection_name: str) -> Dict[str, Any]:
        """Get statistics about collection."""
        if not self.is_connected:
            return {}

        try:
            from pymilvus import Collection
            collection = Collection(collection_name)
            stats = collection.num_entities
            
            return {
                "entity_count": stats,
                "collection_name": collection_name,
            }
        except Exception as e:
            print(f"Failed to get collection stats: {e}")
            return {}

    @staticmethod
    def get_provider_info() -> Dict[str, Any]:
        """Get Milvus provider information."""
        return {
            "name": "Milvus",
            "type": "open_source_scalable",
            "description": "Highly scalable, cloud-native vector database",
            "url": "https://milvus.io",
            "capabilities": [
                "semantic_search",
                "dynamic_fields",
                "batch_processing",
                "scalability",
                "fault_tolerance",
                "compression",
            ],
            "deployment": ["self_hosted", "cloud_kubernetes"],
            "pricing": "open_source",
            "required_config": ["host", "port"],
            "optional_config": ["db_name", "user", "password"],
        }
