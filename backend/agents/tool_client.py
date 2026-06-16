from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.client.streamable_http import streamable_http_client
from httpx import AsyncClient

class McpToolClient:
    """Wraps an MCP stdio server. Call .call_tool() to call a tool on the server."""

    def __init__(self, server_script: str = None):
        self._config = {"transport": "stdio", "command": "python3", "args": ["-m", server_script]}
        self._session: None

    @classmethod
    def from_config(cls, config):
        """Create from a McpServerConfig."""
        instance = cls.__new__(cls)
        instance._config = {
            "transport": config.transport,
            "command": getattr(config, "command", None),
            "args": getattr(config, "args", []),
            "url": getattr(config, "url", None),
            "headers": getattr(config, "headers", {}),
        }
        instance._session = None
        return instance

    async def __aenter__(self):
        if self._config["transport"] == "stdio":
            params = StdioServerParameters(
                command=self._config["command"],
                args=self._config["args"],
            )
            self._streams = stdio_client(params)
            read, write = await self._streams.__aenter__()
        else:
            asyncClient =AsyncClient(headers=self._config["headers"])
            self._streams = streamable_http_client(
                self._config["url"],
                http_client=asyncClient,
            )
            read, write, _ = await self._streams.__aenter__()
        self._session = ClientSession(read, write)
        await self._session.__aenter__()
        await self._session.initialize()
        return self
    
    async def __aexit__(self, *args):
        await self._session.__aexit__(*args)
        await self._streams.__aexit__(*args)

    async def list_tools(self) -> list[dict]:
        """Returns all tools the server exposes — name, description, schema."""
        result = await self._session.list_tools()
        return result.tools

    async def call_tool(self, name: str, arguments: dict):
        result = await self._session.call_tool(name, arguments)
        # result.content is a list of content blocks; extract text
        return "\n".join(
            block.text for block in result.content if hasattr(block, "text")
        )