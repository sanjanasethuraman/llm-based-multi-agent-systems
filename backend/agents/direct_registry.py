import logging

logger = logging.getLogger(__name__)


class SubAgentRegistry:
    """
    Registry for use inside sub-agent processes.
    Uses ProxyToolClient for all tool/sub-agent calls.
    No MCP clients, no process management — all handled by the main server.
    """

    def __init__(self):
        self._clients: dict = {}

    async def add_proxy_client(self, server_id: str):
        """Fetch tool schemas from main server and register a proxy client."""
        from backend.agents.proxy_tool_client import ProxyToolClient
        client = await ProxyToolClient.create(server_id)
        self._clients[server_id] = client
        logger.info(f"Proxy client registered: {server_id}")

    def all_clients(self) -> dict:
        return dict(self._clients)

    def get_client(self, server_id: str):
        return self._clients.get(server_id)