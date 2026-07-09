import sys
import asyncio
import logging
import json
import os

from mcp.server.fastmcp import FastMCP
from contextlib import asynccontextmanager
from backend.agents import get_agent_provider
from backend.utils import get_available_tools
from backend.logging_config import setup_logging
from backend.agents.direct_registry import SubAgentRegistry

logger = logging.getLogger(__name__)

_registry: SubAgentRegistry | None = None
_registry_lock: asyncio.Lock | None = None


async def _ensure_registry(node_id, edges, nodes) -> SubAgentRegistry:
    """
    Build registry once on first tool call, reuse for all subsequent calls.
    All processes are already running (started by setup_sub_agent_servers).
    Just creates proxy clients pointing at the main server.
    """
    global _registry, _registry_lock

    if _registry is not None:
        return _registry

    if _registry_lock is None:
        _registry_lock = asyncio.Lock()

    async with _registry_lock:
        if _registry is not None:
            return _registry

        logger.info("Building registry (first call)...")
        available = get_available_tools(node_id, edges, nodes)
        registry = SubAgentRegistry()

        seen_servers = set()
        for entry in available:
            if entry["type"] == "tool":
                server_id = entry["server_id"]
                if server_id not in seen_servers:
                    await registry.add_proxy_client(server_id)
                    seen_servers.add(server_id)

            elif entry["type"] == "sub_agent":
                server_id = f"sub-agent-{entry['node_id']}"
                if server_id not in seen_servers:
                    # already running — just proxy through main server
                    await registry.add_proxy_client(server_id)
                    seen_servers.add(server_id)

        _registry = registry
        logger.info(f"Registry ready: {list(registry._clients.keys())}")
        return _registry


async def _run_agent(node_id, agent_config, edges, nodes, user_input):
    registry = await _ensure_registry(node_id, edges, nodes)
    available = get_available_tools(node_id, edges, nodes)

    provider = get_agent_provider(agent_config.get("provider", "mock"))
    result, stats = await provider.run(
        config=agent_config,
        incoming=user_input,
        mcp_registry=registry,
        available_tools=available,
    )
    logger.info(f"Sub-agent '{agent_config.get('name')}' returning result")
    payload = json.dumps({
        "text": result,
        "stats": stats,
    })
    return payload


def create_sub_agent_server(node_id, agent_config, edges, nodes):

    @asynccontextmanager
    async def lifespan(app):
        logger.info(f"Sub-agent '{agent_config.get('name')}' ready.")
        yield
        # clear registry on shutdown — no processes to terminate
        global _registry
        _registry = None
        logger.info(f"Sub-agent '{agent_config.get('name')}' shut down.")

    mcp = FastMCP(
        f"agent-{agent_config['name']}",
        lifespan=lifespan,
        json_response=True,
    )

    @mcp.tool(
        name=f"run_{agent_config.get('name', 'agent')}",
        description=(
            f"Run the {agent_config.get('name', 'agent')} agent. "
            f"System prompt: {agent_config.get('systemPrompt', '')[:100]}"
        )
    )
    async def run(input: str) -> str:
        try:
            return await asyncio.wait_for(
                _run_agent(node_id, agent_config, edges, nodes, input),
                timeout=600.0,
            )
        except asyncio.TimeoutError:
            logger.error(f"Sub-agent '{agent_config.get('name')}' timed out")
            return "Error: sub-agent timed out"
        except Exception as e:
            logger.error(
                f"Sub-agent '{agent_config.get('name')}' failed: {e}",
                exc_info=True,
            )
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

        _log(f"args ok node_id={node_id} port={port}")

        setup_logging(f"sub-agent-{node_id}")
        logger = logging.getLogger(__name__)
        logger.info(f"Sub-Agent {node_id} starting, port={port}")

        mcp = create_sub_agent_server(node_id, agent_config, edges, nodes)
        _log("mcp created, starting server")

        if port:
            mcp.settings.host = "127.0.0.1"
            mcp.settings.port = port
            mcp.run(transport="streamable-http")
        else:
            mcp.run(transport="stdio")

    except Exception:
        import traceback
        traceback.print_exc(file=_crash_log)
        _crash_log.flush()
        sys.exit(1)
