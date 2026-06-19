"""Vector Database Provider Registry and Factory."""

from typing import Dict, Any, Optional, Type
from .base import VectorDatabaseProvider
from .pinecone import PineconeProvider
from .weaviate import WeaviateProvider
from .qdrant import QdrantProvider
from .milvus import MilvusProvider
from .supabase import SupabasePgVectorProvider
from .lancedb import LanceDBProvider


class VectorDatabaseRegistry:
    """Registry and factory for vector database providers."""

    _providers: Dict[str, Type[VectorDatabaseProvider]] = {
        "pinecone": PineconeProvider,
        "weaviate": WeaviateProvider,
        "qdrant": QdrantProvider,
        "milvus": MilvusProvider,
        "supabase": SupabasePgVectorProvider,
        "lancedb": LanceDBProvider,
    }

    @classmethod
    def register_provider(
        cls,
        name: str,
        provider_class: Type[VectorDatabaseProvider]
    ) -> None:
        """Register a new vector database provider.
        
        Args:
            name: Name of the provider
            provider_class: Provider class implementing VectorDatabaseProvider
        """
        cls._providers[name.lower()] = provider_class

    @classmethod
    def get_provider(
        cls,
        provider_name: str,
        config: Dict[str, Any]
    ) -> Optional[VectorDatabaseProvider]:
        """Get a provider instance.
        
        Args:
            provider_name: Name of the provider
            config: Provider configuration
            
        Returns:
            Provider instance or None if not found
        """
        provider_class = cls._providers.get(provider_name.lower())
        if not provider_class:
            raise ValueError(f"Unknown vector database provider: {provider_name}")
        
        return provider_class(config)

    @classmethod
    def get_available_providers(cls) -> Dict[str, Dict[str, Any]]:
        """Get information about all available providers.
        
        Returns:
            Dictionary mapping provider names to their information
        """
        return {
            name: provider_class.get_provider_info()
            for name, provider_class in cls._providers.items()
        }

    @classmethod
    def list_providers(cls) -> list:
        """List all registered provider names.
        
        Returns:
            List of provider names
        """
        return list(cls._providers.keys())

    @classmethod
    def provider_exists(cls, name: str) -> bool:
        """Check if a provider is registered.
        
        Args:
            name: Provider name
            
        Returns:
            True if provider exists
        """
        return name.lower() in cls._providers


# Auto-detect and register Chroma if available (for backward compatibility)
try:
    from .chroma import ChromaProvider
    VectorDatabaseRegistry.register_provider("chroma", ChromaProvider)
except ImportError:
    pass
