from .base import AgentProvider
from backend.utils import summarize

class MockProvider(AgentProvider):
    name = "mock"

    def run(self, config, incoming, available_tools):
        name = config.get("name", "Agent")
        prompt = config.get("systemPrompt", "You are a helpful assistant.")

        return (
            f"[{name} | mock]\n"
            f"System prompt: {prompt}\n"
            f"Input summary: {summarize(incoming)}\n"
            "Response: This is a deterministic prototype response."
        )