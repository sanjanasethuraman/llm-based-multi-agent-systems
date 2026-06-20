import sys, asyncio, logging
import concurrent.futures
from mcp.server.fastmcp import FastMCP
from backend.agents.tool_client import McpToolClient
from backend.mcp_registry import McpClientRegistry, McpServerConfig
from backend.agents import get_agent_provider
from backend.utils import get_available_tools
from backend.logging_config import setup_logging

async def _run_agent(node_id: str, agent_config: dict, edges: list[dict], nodes: list[dict], user_input: str) -> str:
    # spin up the agent's own tool registry
        registry = McpClientRegistry()
        registry.set_loop(asyncio.get_event_loop())

        # always connect to internal tools
        registry.add_server(McpServerConfig(
            id="internal",
            label="Internal Tools",
            transport="stdio",
            command=sys.executable,
            args=["-m","backend.tools.run_mcp_server"],
        ))

        available = get_available_tools(node_id, edges, nodes)
        for entry in available:
            if entry["type"] == "sub_agent":
                sub_id = f"sub-agent-{entry['node_id']}"
                registry.add_server(McpServerConfig(
                    id=sub_id,
                    label=entry["config"].get("name", sub_id),
                    transport="stdio",
                    command=sys.executable,
                    args=[
                        "-m", "backend.agents.agent_mcp_server",
                        entry["node_id"],
                        json.dumps(entry["config"]),
                        json.dumps(edges),
                        json.dumps(nodes)
                    ],
                ))
        clients = {}
        try:
            for server_id, config in registry._configs.items():
                client = McpToolClient.from_config(config)
                await client.__aenter__()
                clients[server_id] = client
            registry._clients = clients

            provider = get_agent_provider(agent_config.get("provider", "mock"))
            result, _ = await provider.run(
                config=agent_config,
                incoming=user_input,
                mcp_registry=registry,
                available_tools=available,
            )
            return result
        finally:
            for client in clients.values():
                try:
                    await client.__aexit__(None, None, None)
                except Exception as e:
                    logger.error(f"Client cleanup error: {e}")

def create_sub_agent_server(node_id: str, agent_config: dict, edges: list[dict], nodes: list[dict]):
    """
    Creates an MCP server that wraps a single sub-agent.
    node_id: the sub-agent node's id
    agent_config: the sub-agent node's config (model, provider, systemPrompt, etc.)
    edges: all edges of the workflow
    nodes: all nodes of the workflow
    """
    mcp = FastMCP(f"agent-{agent_config['name']}")

    @mcp.tool(
        name=f"run_{agent_config.get('name', 'agent')}",
        description=f"Run the {agent_config.get('name', 'agent')} agent. "
                    f"System prompt: {agent_config.get('systemPrompt', '')[:100]}"
    )
    async def run(input: str) -> str:
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
             future = executor.submit(
                  asyncio.run,
                  _run_agent(node_id, agent_config, edges, nodes, input)
             )
             return future.result()

    return mcp


if __name__ == "__main__":
    import json

    # called as: python agent_mcp_server.py '{"name": "summarizer", ...}' '[{"server_id":...}]'
    node_id = json.loads(sys.argv[1])
    agent_config = json.loads(sys.argv[2])
    edges = json.loads(sys.argv[3])
    nodes = json.loads(sys.argv[4])

    setup_logging(f"sub-agent-{node_id}")
    logger = logging.getLogger(__name__)
    logger.info(f"Sub-Agent {node_id} starting.")


    mcp = create_sub_agent_server(node_id, agent_config, edges, nodes)
    mcp.run(transport="stdio")