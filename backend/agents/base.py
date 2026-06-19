class AgentProvider:
    name = "base"

    async def run(self, config, incoming, mcp_client, available_tools):
        raise NotImplementedError("Subclasses must implement the run method.")