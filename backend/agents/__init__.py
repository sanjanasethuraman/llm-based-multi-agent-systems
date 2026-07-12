AGENT_PROVIDERS = {}


def _load_default_provider(name):
    if name == "huggingface":
        from .huggingface import HuggingFaceProvider

        return HuggingFaceProvider()
    if name == "mock":
        name = "ollama"
    if name == "ollama":
        from .ollama import OllamaProvider

        return OllamaProvider()
    return None

def get_agent_provider(name):
    if name not in AGENT_PROVIDERS:
        provider = _load_default_provider(name)
        if provider is not None:
            AGENT_PROVIDERS[name] = provider
    return AGENT_PROVIDERS.get(name)

def register_agent_provider(name, provider):
    AGENT_PROVIDERS[name] = provider
