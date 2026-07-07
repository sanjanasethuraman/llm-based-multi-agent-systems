import httpx
import os
import logging

logger = logging.getLogger(__name__)


class _SchemaTool:
    def __init__(self, schema: dict):
        self.name = schema["name"]
        self.description = schema["description"]
        self.inputSchema = schema["inputSchema"]


class ProxyToolClient:
    """
    Calls tools via the main server's proxy endpoints.
    No MCP, no anyio, no cancel scopes — plain httpx POST.
    Safe to use inside uvicorn's event loop.
    """

    def __init__(self, server_id: str, tools: list[dict]):
        self.server_id = server_id
        self._tools = tools

    @classmethod
    async def create(cls, server_id: str) -> "ProxyToolClient":
        """Fetch tool schemas from main server and return a ready client."""
        main_url = os.environ.get("MAIN_SERVER_URL", "http://127.0.0.1:8000")
        async with httpx.AsyncClient() as client:
            r = await client.post(
                f"{main_url}/api/internal/list-tools",
                json={"server_id": server_id},
                timeout=10.0,
            )
            tools = r.json().get("tools", [])
        logger.info(f"ProxyToolClient for {server_id}: {[t['name'] for t in tools]}")
        return cls(server_id, tools)

    async def list_tools(self) -> list:
        return [_SchemaTool(t) for t in self._tools]

    async def call_tool(self, name: str, arguments: dict) -> str:
        main_url = os.environ.get("MAIN_SERVER_URL", "http://127.0.0.1:8000")
        async with httpx.AsyncClient() as client:
            r = await client.post(
                f"{main_url}/api/internal/call-tool",
                json={
                    "server_id": self.server_id,
                    "tool_name": name,
                    "arguments": arguments,
                },
                timeout=300.0,
            )
        data = r.json()
        if "error" in data:
            logger.error(f"Proxy error {self.server_id}/{name}: {data['error']}")
            return f"Error: {data['error']}"
        return data.get("result", "")