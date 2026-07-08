from mcp import ClientSession, StdioServerParameters, Tool
from mcp.client.stdio import stdio_client
from mcp.client.streamable_http import streamable_http_client
from httpx import AsyncClient, Timeout
import logging
from backend.mcp_registry import McpServerConfig

logger = logging.getLogger(__name__)


def _is_process_exit(exc):
    return isinstance(exc, (KeyboardInterrupt, SystemExit))


class McpToolClient:

    def __init__(self, server_script: str = None):
        self._config = {
            "transport": "stdio",
            "command": "python3",
            "args": ["-m", server_script],
        }
        self._session = None

    @classmethod
    def from_config(cls, config: McpServerConfig):
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
            self._session = ClientSession(read, write)
            await self._session.__aenter__()
            await self._session.initialize()
        else:
            self._http_client = AsyncClient(
                headers=self._config["headers"],
                timeout=Timeout(650.0, connect=10.0),
            )
            self._streams = streamable_http_client(
                self._config["url"],
                http_client=self._http_client,
                terminate_on_close=True,
            )
            read, write, _ = await self._streams.__aenter__()
            self._session = ClientSession(read, write)
            await self._session.__aenter__()
            await self._session.initialize()
        return self

    async def __aexit__(self, *args):
        try:
            if self._session:
                await self._session.__aexit__(*args)
        except BaseException as e:
            if _is_process_exit(e):
                raise
            logger.debug(f"Session cleanup: {e}")
        finally:
            try:
                if getattr(self, "_streams", None):
                    await self._streams.__aexit__(*args)
            except BaseException as e:
                if _is_process_exit(e):
                    raise
                logger.debug(f"Stream cleanup: {e}")
            finally:
                if getattr(self, "_http_client", None):
                    try:
                        await self._http_client.aclose()
                    except BaseException as e:
                        if _is_process_exit(e):
                            raise
                        logger.debug(f"HTTP client cleanup: {e}")

    async def list_tools(self) -> list[Tool]:
        result = await self._session.list_tools()
        return result.tools

    async def call_tool(self, name: str, arguments: dict) -> str:
        result = await self._session.call_tool(name, arguments)
        return "\n".join(
            block.text for block in result.content if hasattr(block, "text")
        )
