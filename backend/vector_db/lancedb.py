"""LanceDB Vector Database Provider."""

from typing import List, Dict, Any, Optional, Tuple
from .base import VectorDatabaseProvider


class LanceDBProvider(VectorDatabaseProvider):
    """Vector database provider for LanceDB (Apache Lance-based)."""

    def __init__(self, config: Dict[str, Any]):
        """Initialize LanceDB provider.
        
        Config requires:
            - db_path: Path to LanceDB database directory
        
        Optional:
            - mode: 'overwrite' or 'append' (default: 'append')
        """
        super().__init__(config)
        self.client = None
        self.db = None

    async def connect(self) -> bool:
        """Connect to LanceDB."""
        try:
            import lancedb
            
            db_path = self.config.get("db_path", "./lance_db")
            
            self.db = lancedb.connect(db_path)
            self.is_connected = True
            return True
        except ImportError:
            raise ImportError("lancedb package required: pip install lancedb")
        except Exception as e:
            print(f"Failed to connect to LanceDB: {e}")
            return False

    async def disconnect(self) -> bool:
        """Disconnect from LanceDB."""
        self.db = None
        self.is_connected = False
        return True

    async def upsert(
        self,
        collection_name: str,
        documents: List[str],
        embeddings: List[List[float]],
        metadata: Optional[List[Dict[str, Any]]] = None,
    ) -> bool:
        """Upsert documents to LanceDB."""
        if not self.is_connected or not self.db:
            return False

        try:
            data = []
            for i, (doc, emb) in enumerate(zip(documents, embeddings)):
                record = {
                    "id": i,
                    "text": doc,
                    "vector": emb,
                }
                
                if metadata and i < len(metadata):
                    record.update(metadata[i])
                
                data.append(record)
            
            # Create or update table
            table = self.db.create_table(
                collection_name,
                data=data,
                mode="overwrite"
            )
            
            return True
        except Exception as e:
            print(f"Failed to upsert to LanceDB: {e}")
            return False

    async def search(
        self,
        collection_name: str,
        query_embedding: List[float],
        top_k: int = 10,
        filters: Optional[Dict[str, Any]] = None,
    ) -> List[Tuple[str, float, Optional[Dict[str, Any]]]]:
        """Search in LanceDB."""
        if not self.is_connected or not self.db:
            return []

        try:
            table = self.db.open_table(collection_name)
            
            results = table.search(query_embedding).limit(top_k).to_list()
            
            output = []
            for result in results:
                doc_text = result.get("text", "")
                # LanceDB returns _distance, convert to similarity
                distance = result.get("_distance", 0.0)
                similarity = 1.0 - distance
                metadata = {k: v for k, v in result.items() if k not in ["text", "vector", "_distance"]}
                output.append((doc_text, similarity, metadata))
            
            return output
        except Exception as e:
            print(f"Failed to search LanceDB: {e}")
            return []

    async def create_collection(
        self,
        collection_name: str,
        embedding_dim: int = 384,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """Create collection (table) in LanceDB."""
        # LanceDB creates tables on-demand
        try:
            self.db.open_table(collection_name)
            return True
        except:
            # Table doesn't exist yet, will be created on first upsert
            return True

    async def list_collections(self) -> List[str]:
        """List all collections (tables) in LanceDB."""
        if not self.is_connected or not self.db:
            return []

        try:
            return self.db.table_names()
        except Exception as e:
            print(f"Failed to list collections: {e}")
            return []

    async def delete_collection(self, collection_name: str) -> bool:
        """Delete collection from LanceDB."""
        if not self.is_connected or not self.db:
            return False

        try:
            self.db.drop_table(collection_name)
            return True
        except Exception as e:
            print(f"Failed to delete collection: {e}")
            return False

    async def get_collection_stats(self, collection_name: str) -> Dict[str, Any]:
        """Get statistics about collection."""
        if not self.is_connected or not self.db:
            return {}

        try:
            table = self.db.open_table(collection_name)
            return {
                "row_count": len(table.to_pandas()),
                "table_name": collection_name,
            }
        except Exception as e:
            print(f"Failed to get collection stats: {e}")
            return {}

    @staticmethod
    def get_provider_info() -> Dict[str, Any]:
        """Get LanceDB provider information."""
        return {
            "name": "LanceDB",
            "type": "local_efficient",
            "description": "Fast, efficient vector database built on Apache Lance",
            "url": "https://lancedb.com",
            "capabilities": [
                "semantic_search",
                "local_storage",
                "low_latency",
                "efficient_updates",
                "pandas_integration",
            ],
            "deployment": "local_only",
            "pricing": "open_source",
            "required_config": ["db_path"],
            "optional_config": ["mode"],
        }
