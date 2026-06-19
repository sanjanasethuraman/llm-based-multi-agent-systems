from .base import AgentProvider
from backend.utils import summarize

class MockProvider(AgentProvider):
    name = "mock"

    async def run(self, config, incoming, mcp_registry, available_tools):
        name = config.get("name", "Agent")
        prompt = config.get("systemPrompt", "You are a helpful assistant.")

        return (
            f"[{name} | mock]\n"
            f"System prompt: {prompt}\n"
            f"Input: {incoming}\n"
            "Response: This is a deterministic prototype response."
        ), 0