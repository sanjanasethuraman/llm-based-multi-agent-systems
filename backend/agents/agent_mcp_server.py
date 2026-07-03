import sys
import asyncio
import logging
import json
import socket
import subprocess
import httpx
import os

from mcp.server.fastmcp import FastMCP
from backend.mcp_registry import McpServerConfig
from backend.agents import get_agent_provider
from backend.utils import get_available_tools
from backend.logging_config import setup_logging
from backend.agents.direct_registry import SubAgentRegistry


logger = logging.getLogger(__name__)


def find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


async def _wait_for_mcp_ready(port: int, timeout: float = 15.0):
    """Wait until the MCP server is fully initialized and ready."""
    deadline = asyncio.get_event_loop().time() + timeout

    while asyncio.get_event_loop().time() < deadline:
        try:
            # Simple TCP connection check to see if the server is listening
            # This avoids protocol-specific issues and doesn't trigger anyio cancel scope conflicts
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection("127.0.0.1", port),
                timeout=2.0
            )
            writer.close()
            await writer.wait_closed()
            logger.info(f"MCP server ready on port {port}")
            return
        except Exception as e:
            logger.debug(f"MCP server not ready on port {port}: {e}")
        
        await asyncio.sleep(0.3)

    raise TimeoutError(f"MCP server on port {port} did not become ready within {timeout}s")


async def _run_agent(node_id, agent_config, edges, nodes, user_input):
    from backend.agents.direct_registry import SubAgentRegistry

    available = get_available_tools(node_id, edges, nodes)
    logger.info(f"Available tools: {available}")

    registry = SubAgentRegistry()

    # internal tools — HTTP to the internal MCP server
    # INTERNAL_MCP_PORT is set at startup in server.py and passed via env var
    internal_port = int(os.environ.get("INTERNAL_MCP_PORT", "0"))
    if internal_port and any(e["server_id"] == "internal" for e in available if e["type"] == "tool"):
        await registry.add_http_client("internal", McpServerConfig(
            id="internal",
            label="Internal Tools",
            transport="http",
            url=f"http://127.0.0.1:{internal_port}/mcp",
        ))
        logger.info(f"Internal MCP server connected via HTTP on port {internal_port}")

    # external HTTP tool servers
    external_server_ids = {
        e["server_id"] for e in available
        if e["type"] == "tool" and e["server_id"] != "internal"
    }
    for server_id in external_server_ids:
        entry = next(e for e in available if e["server_id"] == server_id)
        config = McpServerConfig(
            id=server_id,
            label=server_id,
            transport="http",
            url=entry.get("url", ""),
            headers=entry.get("headers", {}),
        )
        await registry.add_http_client(server_id, config)

    # sub-sub-agents — spawn as HTTP servers
    spawned = {}  # server_id → proc
    for entry in available:
        if entry["type"] != "sub_agent":
            continue

        sub_id = f"sub-agent-{entry['node_id']}"
        port = find_free_port()

        logger.info(f"Spawning sub-agent {sub_id} on port {port}")
        proc = subprocess.Popen(
            [
                sys.executable, "-m", "backend.agents.agent_mcp_server",
                entry["node_id"],
                json.dumps(entry["config"]),
                json.dumps(edges),
                json.dumps(nodes),
                str(port),
            ],
            env={**os.environ},  # passes INTERNAL_MCP_PORT through
        )
        spawned[sub_id] = proc

        await _wait_for_mcp_ready(port)

        await registry.add_http_client(sub_id, McpServerConfig(
            id=sub_id,
            label=entry["config"].get("name", sub_id),
            transport="http",
            url=f"http://127.0.0.1:{port}/mcp",
        ))
        logger.info(f"Sub-agent {sub_id} ready on port {port}")

    try:
        provider = get_agent_provider(agent_config.get("provider", "mock"))
        result, _, _ = await provider.run(
            config=agent_config,
            incoming=user_input,
            mcp_registry=registry,
            available_tools=available,
        )
        return result
    finally:  
        # Clear registry clients carefully — suppress cancel scope errors that can occur
        # when exiting HTTP client contexts within an MCP HTTP request handler
        try:
            registry._clients.clear()
        except RuntimeError as e:
            if "cancel scope" in str(e):
                logger.debug(f"Suppressed cancel scope error during cleanup: {e}")
            else:
                raise

        # Terminate sub-agents immediately without async sleep
        # (which can be cancelled by anyio cancel scope teardown)
        for sub_id, proc in spawned.items():
            try:
                proc.terminate()
                logger.info(f"Terminated sub-agent {sub_id}")
            except Exception as e:
                logger.debug(f"Error terminating sub-agent {sub_id}: {e}")


def create_sub_agent_server(node_id, agent_config, edges, nodes):
    mcp = FastMCP(f"agent-{agent_config['name']}")

    @mcp.tool(
        name=f"run_{agent_config.get('name', 'agent')}",
        description=(
            f"Run the {agent_config.get('name', 'agent')} agent. "
            f"System prompt: {agent_config.get('systemPrompt', '')[:100]}"
        )
    )
    async def run(input: str) -> str:
        try:
            result = await _run_agent(node_id, agent_config, edges, nodes, input)
            return result
        except asyncio.TimeoutError:
            logger.error(f"Sub-agent {agent_config.get('name')} timed out")
            return "Error: Sub-agent timed out"
        except Exception as e:
            logger.error(f"Sub-agent {agent_config.get('name')} failed: {e}", exc_info=True)
            return f"Error: {e}"

    return mcp


if __name__ == "__main__":
    _crash_log = open("/tmp/sub-agent-startup.log", "w", buffering=1)

    def _log(msg):
        print(msg, file=_crash_log, flush=True)

    try:
        node_id = sys.argv[1]
        agent_config = json.loads(sys.argv[2])
        edges = json.loads(sys.argv[3])
        nodes = json.loads(sys.argv[4])
        port = int(sys.argv[5]) if len(sys.argv) > 5 else None

        _log(f"args ok, node_id={node_id}, port={port}")

        setup_logging(f"sub-agent-{node_id}")
        logger = logging.getLogger(__name__)
        logger.info(f"Sub-Agent {node_id} starting, port={port}")

        mcp = create_sub_agent_server(node_id, agent_config, edges, nodes)
        _log("mcp created, starting run()")

        if port:
            mcp.settings.host = "127.0.0.1"
            mcp.settings.port = port
            mcp.run(transport="streamable-http")
        else:
            mcp.run(transport="stdio")  # fallback for direct CLI testing

    except Exception:
        import traceback
        traceback.print_exc(file=_crash_log)
        _crash_log.flush()
        sys.exit(1)