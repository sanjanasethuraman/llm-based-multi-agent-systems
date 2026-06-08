from .mock import MockProvider
from .ollama import OllamaProvider
from .huggingface import HuggingFaceProvider

AGENT_PROVIDERS = {
    "huggingface": HuggingFaceProvider(),
    "mock": MockProvider(),
    "ollama": OllamaProvider(),
}

def get_agent_provider(name):
    return AGENT_PROVIDERS.get(name)

def register_agent_provider(name, provider):
    AGENT_PROVIDERS[name] = provider
