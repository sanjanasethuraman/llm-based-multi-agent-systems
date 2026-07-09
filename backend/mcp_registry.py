from dataclasses import dataclass, field
from typing import Any
import asyncio
import subprocess
import logging

logger = logging.getLogger(__name__)


@dataclass
class McpServerConfig:
    id: str
    label: str
    transport: str          # "stdio" or "http"
    command: str = None     # stdio only
    args: list = field(default_factory=list)
    url: str = None         # http only
    headers: dict = field(default_factory=dict)


class McpClientRegistry:
    def __init__(self):
        self._configs: dict[str, McpServerConfig] = {}
        self._clients: dict[str, Any] = {}
        self._processes: dict[str, subprocess.Popen] = {}
        self._loop = None

    def set_loop(self, loop):
        self._loop = loop

    def add_server(self, config: McpServerConfig):
        self._configs[config.id] = config

    def register_process(self, server_id: str, proc: subprocess.Popen):
        """Track a subprocess so it can be cleaned up on shutdown."""
        self._processes[server_id] = proc

    def remove_server(self, server_id: str):
        if server_id == "internal":
            return
        self._clients.pop(server_id, None)
        self._configs.pop(server_id, None)
        proc = self._processes.pop(server_id, None)
        if proc:
            proc.terminate()
            logger.info(f"Terminated process for {server_id}")

    async def connect(self, server_id: str):
        from backend.agents.tool_client import McpToolClient
        config = self._configs[server_id]
        client = McpToolClient.from_config(config)
        await client.__aenter__()
        self._clients[server_id] = client
        logger.info(f"Connected: {server_id}")

    async def connect_all(self):
        for server_id in list(self._configs.keys()):
            await self.connect(server_id)

    def get_client(self, server_id: str):
        return self._clients.get(server_id)

    def all_clients(self) -> dict:
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

    async def shutdown(self):
        """Call from within _loop only — clean shutdown."""
        for client in list(self._clients.values()):
            try:
                await client.__aexit__(None, None, None)
            except Exception as e:
                logger.debug(f"Client shutdown: {e}")
        self._clients.clear()
        self._configs.clear()
        for server_id, proc in self._processes.items():
            proc.terminate()
            logger.info(f"Terminated {server_id}")
        self._processes.clear()


# singleton used by server.py
registry = McpClientRegistry()


async def _list_all_tools():
    tools = []
    for server_id, client in registry.all_clients().items():
        try:
            server_tools = await client.list_tools()
            for tool in server_tools:
                tools.append({
                    "serverId": server_id,
                    "name": tool.name,
                    "description": tool.description,
                    "inputSchema": tool.inputSchema,
                })
        except Exception as e:
            logger.error(f"Failed to list tools from {server_id}: {e}")
    return tools