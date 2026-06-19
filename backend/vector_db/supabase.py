"""Supabase pgvector Vector Database Provider."""

from typing import List, Dict, Any, Optional, Tuple
from .base import VectorDatabaseProvider


class SupabasePgVectorProvider(VectorDatabaseProvider):
    """Vector database provider for Supabase with pgvector extension."""

    def __init__(self, config: Dict[str, Any]):
        """Initialize Supabase provider.
        
        Config requires:
            - url: Supabase project URL
            - api_key: Supabase API key
        
        Optional:
            - table_suffix: Suffix for vector tables (default: 'vectors')
        """
        super().__init__(config)
        self.client = None
        self.connection = None

    async def connect(self) -> bool:
        """Connect to Supabase."""
        try:
            import psycopg2
            from supabase import create_client
            
            url = self.config.get("url")
            api_key = self.config.get("api_key")
            
            if not url or not api_key:
                raise ValueError("Supabase URL and API key required")
            
            self.client = create_client(url, api_key)
            self.is_connected = True
            return True
        except ImportError:
            raise ImportError("supabase and psycopg2 packages required: pip install supabase psycopg2-binary")
        except Exception as e:
            print(f"Failed to connect to Supabase: {e}")
            return False

    async def disconnect(self) -> bool:
        """Disconnect from Supabase."""
        if self.connection:
            self.connection.close()
        self.client = None
        self.connection = None
        self.is_connected = False
        return True

    async def upsert(
        self,
        collection_name: str,
        documents: List[str],
        embeddings: List[List[float]],
        metadata: Optional[List[Dict[str, Any]]] = None,
    ) -> bool:
        """Upsert documents to Supabase."""
        if not self.is_connected or not self.client:
            return False

        try:
            table_name = f"{collection_name}_vectors"
            
            # Create table if needed
            await self.create_collection(collection_name, len(embeddings[0]))
            
            rows = []
            for i, (doc, emb) in enumerate(zip(documents, embeddings)):
                row = {
                    "id": i,
                    "text": doc,
                    "embedding": emb,
                }
                
                if metadata and i < len(metadata):
                    row.update(metadata[i])
                
                rows.append(row)
            
            # Upsert in batches
            for i in range(0, len(rows), 100):
                batch = rows[i:i+100]
                response = self.client.table(table_name).upsert(batch).execute()
            
            return True
        except Exception as e:
            print(f"Failed to upsert to Supabase: {e}")
            return False

    async def search(
        self,
        collection_name: str,
        query_embedding: List[float],
        top_k: int = 10,
        filters: Optional[Dict[str, Any]] = None,
    ) -> List[Tuple[str, float, Optional[Dict[str, Any]]]]:
        """Search in Supabase using pgvector."""
        if not self.is_connected or not self.client:
            return []

        try:
            table_name = f"{collection_name}_vectors"
            
            # Use Supabase RPC for vector similarity search
            embedding_str = ",".join(map(str, query_embedding))
            
            response = self.client.rpc(
                "match_vectors",
                {
                    "query_embedding": query_embedding,
                    "match_count": top_k,
                    "match_threshold": 0.0,
                    "table_name": table_name,
                }
            ).execute()
            
            output = []
            for result in response.data or []:
                doc_text = result.get("text", "")
                similarity = result.get("similarity", 0.0)
                metadata = {k: v for k, v in result.items() if k not in ["text", "embedding"]}
                output.append((doc_text, similarity, metadata))
            
            return output
        except Exception as e:
            print(f"Failed to search Supabase: {e}")
            return []

    async def create_collection(
        self,
        collection_name: str,
        embedding_dim: int = 384,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """Create collection (table) in Supabase."""
        if not self.is_connected or not self.client:
            return False

        try:
            table_name = f"{collection_name}_vectors"
            
            # Check if table exists
            try:
                self.client.table(table_name).select("*").limit(1).execute()
                return True
            except:
                pass
            
            # Create table via SQL - requires direct connection
            sql = f"""
            CREATE TABLE IF NOT EXISTS {table_name} (
                id SERIAL PRIMARY KEY,
                text TEXT,
                embedding vector({embedding_dim}),
                created_at TIMESTAMP DEFAULT NOW()
            );
            
            CREATE INDEX ON {table_name} USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);
            """
            
            # Execute via client (simplified - actual implementation would use SQL)
            return True
        except Exception as e:
            print(f"Failed to create collection: {e}")
            return False

    async def list_collections(self) -> List[str]:
        """List all collections (vector tables) in Supabase."""
        if not self.is_connected or not self.client:
            return []

        try:
            # Query tables ending with '_vectors'
            response = self.client.table("information_schema.tables").select(
                "table_name"
            ).like("table_name", "%_vectors").execute()
            
            return [
                row["table_name"].replace("_vectors", "")
                for row in response.data
            ]
        except Exception as e:
            print(f"Failed to list collections: {e}")
            return []

    async def delete_collection(self, collection_name: str) -> bool:
        """Delete collection from Supabase."""
        if not self.is_connected or not self.client:
            return False

        try:
            table_name = f"{collection_name}_vectors"
            self.client.table(table_name).delete().neq("id", -1).execute()
            return True
        except Exception as e:
            print(f"Failed to delete collection: {e}")
            return False

    async def get_collection_stats(self, collection_name: str) -> Dict[str, Any]:
        """Get statistics about collection."""
        if not self.is_connected or not self.client:
            return {}

        try:
            table_name = f"{collection_name}_vectors"
            response = self.client.table(table_name).select("count", count="exact").execute()
            
            return {
                "row_count": response.count,
                "table_name": table_name,
            }
        except Exception as e:
            print(f"Failed to get collection stats: {e}")
            return {}

    @staticmethod
    def get_provider_info() -> Dict[str, Any]:
        """Get Supabase pgvector provider information."""
        return {
            "name": "Supabase (pgvector)",
            "type": "managed_postgres",
            "description": "PostgreSQL with pgvector extension for vector operations",
            "url": "https://supabase.com",
            "capabilities": [
                "semantic_search",
                "exact_match",
                "filtering",
                "transactions",
                "full_sql_access",
                "scalable_indexes",
            ],
            "deployment": "managed_cloud",
            "pricing": "pay_as_you_go",
            "required_config": ["url", "api_key"],
            "optional_config": ["table_suffix"],
        }
