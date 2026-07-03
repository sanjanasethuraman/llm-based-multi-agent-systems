import logging
from backend.agents.tool_client import McpToolClient
from backend.mcp_registry import McpServerConfig

logger = logging.getLogger(__name__)


class SubAgentRegistry:
    """
    Registry for use inside sub-agent processes.
    All tools and sub-agents use HTTP MCP clients.
    """

    def __init__(self):
        self._clients: dict = {}

    async def add_http_client(self, server_id: str, config: McpServerConfig):
        client = McpToolClient.from_config(config)
        await client.__aenter__()
        self._clients[server_id] = client
        logger.info(f"HTTP MCP client connected: {server_id} → {config.url}")

    def all_clients(self) -> dict:
        return dict(self._clients)

    def get_client(self, server_id: str):
        return self._clients.get(server_id)

    async def close_all(self):
        self._clients.clear()
        logger.info("All HTTP MCP clients closed.")