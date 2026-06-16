from backend.agents.tool_client import McpToolClient
from dataclasses import dataclass, field
import asyncio
import json
import time

MOCK_MCP_TOOLS = {
    "demo.weather": {
        "server": "demo",
        "name": "weather",
        "description": "Returns deterministic weather-like context for a city.",
        "schema": {"city": "string", "unit": "celsius|fahrenheit"},
    },
    "demo.lookup": {
        "server": "demo",
        "name": "lookup",
        "description": "Returns a deterministic project note for a topic.",
        "schema": {"topic": "string"},
    },
    "demo.score": {
        "server": "demo",
        "name": "score",
        "description": "Scores text with a deterministic presentation-readiness rubric.",
        "schema": {"text": "string"},
    },
}

@dataclass
class McpServerConfig:
    id: str
    label: str
    transport: str      # "stdio" or "http"
    #stdio
    command: str = None
    args: list = field(default_factory=list)
    #http
    url: str = None
    headers: dict = field(default_factory=dict)

class McpClientRegistry:
    def __init__(self):
        self._configs: dict[str, McpServerConfig] = {}
        self._clients: dict[str, McpToolClient] = {}
        self._loop = None

    def set_loop(self, loop):
        self._loop = loop

    def add_server(self, config: McpServerConfig):
        """Register a server config. Call connect() after to bring it online"""
        self._configs[config.id] = config

    def remove_server(self, server_id: str):
        if server_id == "internal":
            return
        self._clients.pop(server_id, None)
        self._configs.pop(server_id, None)

    async def connect(self, server_id: str):
        config = self._configs[server_id]
        client = McpToolClient.from_config(config)
        await client.__aenter__()
        self._clients[server_id] = client

    async def connect_all(self):
        for server_id in self._configs:
            await self.connect(server_id)

    def get_client(self, server_id: str) -> McpToolClient:
        return self._clients.get(server_id)

    def all_clients(self) -> dict[str, McpToolClient]:
        return dict(self._clients)

    def list_servers(self) -> list[dict]:
        return [
            {
                "id": sid,
                "label": cfg.label,
                "transport": cfg.transport,
                "connected": sid in self._clients,
            }
            for sid, cfg in self._configs.items()
        ]

# singleton
registry = McpClientRegistry()

async def _list_all_tools():
    tools = []
    for server_id, client in registry.all_clients().items():
        server_tools = await client.list_tools()
        for tool in server_tools:
            tools.append({
                "serverId": server_id,
                "name": tool.name,
                "description": tool.description,
                "inputSchema": tool.inputSchema,
            })
    return tools
    
    
    
def call_mcp_tool(tool_id, arguments=None, incoming=""):
    if tool_id not in MOCK_MCP_TOOLS:
        raise ValueError(f"MCP tool '{tool_id}' is not registered.")

    args = normalize_arguments(arguments)
    if tool_id == "demo.weather":
        city = args.get("city") or "Berlin"
        unit = args.get("unit") or "celsius"
        suffix = "C" if unit == "celsius" else "F"
        temperature = 18 if unit == "celsius" else 64
        result = f"Weather for {city}: {temperature}{suffix}, light wind, good conditions for a field demo."
    elif tool_id == "demo.lookup":
        topic = args.get("topic") or incoming or "visual multi-agent systems"
        result = (
            f"Lookup result for {topic}: emphasize visual orchestration, transparent execution, "
            "and provider/tool modularity."
        )
    elif tool_id == "demo.score":
        text = args.get("text") or incoming
        words = len(str(text).split())
        score = min(100, 60 + words)
        result = f"Presentation readiness score: {score}/100. Basis: {words} words of input context."
    else:
        result = f"MCP tool {tool_id} executed."

    return {
        "toolId": tool_id,
        "arguments": args,
        "result": result,
        "timestamp": round(time.time(), 3),
    }


def normalize_arguments(arguments):
    if isinstance(arguments, dict):
        return dict(arguments)
    if not arguments:
        return {}
    if isinstance(arguments, str):
        parsed = json.loads(arguments)
        if not isinstance(parsed, dict):
            raise ValueError("MCP arguments must be a JSON object.")
        return parsed
    raise ValueError("MCP arguments must be a JSON object.")


