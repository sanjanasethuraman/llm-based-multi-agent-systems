"""Base Vector Database Provider Interface."""

from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional, Tuple


class VectorDatabaseProvider(ABC):
    """Abstract base class for vector database providers."""

    def __init__(self, config: Dict[str, Any]):
        """Initialize provider with configuration.
        
        Args:
            config: Provider-specific configuration dictionary
        """
        self.config = config
        self.is_connected = False

    @abstractmethod
    async def connect(self) -> bool:
        """Establish connection to the vector database.
        
        Returns:
            True if connection successful, False otherwise
        """
        pass

    @abstractmethod
    async def disconnect(self) -> bool:
        """Close connection to the vector database.
        
        Returns:
            True if disconnection successful, False otherwise
        """
        pass

    @abstractmethod
    async def upsert(
        self,
        collection_name: str,
        documents: List[str],
        embeddings: List[List[float]],
        metadata: Optional[List[Dict[str, Any]]] = None,
    ) -> bool:
        """Store or update documents with embeddings in collection.
        
        Args:
            collection_name: Name of the collection
            documents: List of document texts
            embeddings: List of embedding vectors
            metadata: Optional list of metadata dicts for each document
            
        Returns:
            True if successful, False otherwise
        """
        pass

    @abstractmethod
    async def search(
        self,
        collection_name: str,
        query_embedding: List[float],
        top_k: int = 10,
        filters: Optional[Dict[str, Any]] = None,
    ) -> List[Tuple[str, float, Optional[Dict[str, Any]]]]:
        """Search for similar documents.
        
        Args:
            collection_name: Name of the collection
            query_embedding: Query embedding vector
            top_k: Number of results to return
            filters: Optional metadata filters
            
        Returns:
            List of tuples: (document_text, similarity_score, metadata)
        """
        pass

    @abstractmethod
    async def create_collection(
        self,
        collection_name: str,
        embedding_dim: int = 384,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """Create a new collection.
        
        Args:
            collection_name: Name of the collection
            embedding_dim: Dimension of embeddings
            metadata: Optional collection metadata
            
        Returns:
            True if successful, False otherwise
        """
        pass

    @abstractmethod
    async def list_collections(self) -> List[str]:
        """List all available collections.
        
        Returns:
            List of collection names
        """
        pass

    @abstractmethod
    async def delete_collection(self, collection_name: str) -> bool:
        """Delete a collection.
        
        Args:
            collection_name: Name of the collection
            
        Returns:
            True if successful, False otherwise
        """
        pass

    @abstractmethod
    async def get_collection_stats(self, collection_name: str) -> Dict[str, Any]:
        """Get statistics about a collection.
        
        Args:
            collection_name: Name of the collection
            
        Returns:
            Dictionary with collection stats
        """
        pass

    @staticmethod
    @abstractmethod
    def get_provider_info() -> Dict[str, Any]:
        """Get provider metadata and capabilities.
        
        Returns:
            Dictionary with provider information
        """
        pass
