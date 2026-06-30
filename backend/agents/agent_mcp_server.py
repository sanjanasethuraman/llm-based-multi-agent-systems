import sys, asyncio, logging
from mcp.server.fastmcp import FastMCP
from backend.agents.tool_client import McpToolClient
from backend.mcp_registry import McpClientRegistry, McpServerConfig
from backend.agents import get_agent_provider
from backend.utils import get_available_tools
from backend.logging_config import setup_logging

def _run_agent_sync(node_id, agent_config, edges, nodes, user_input):
    """Runs in a dedicated thread with its own event loop."""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(
            _run_agent(node_id, agent_config, edges, nodes, user_input)
        )
    finally:
        # cancel all remaining tasks before closing
        pending = asyncio.all_tasks(loop)
        for task in pending:
            task.cancel()
        if pending:
            loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
        loop.close()

def create_sub_agent_server(node_id, agent_config, edges, nodes):
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
        loop = asyncio.get_event_loop()
        # run in dedicated thread so its event loop is fully isolated
        return await loop.run_in_executor(
            None,
            _run_agent_sync,
            node_id, agent_config, edges, nodes, input
        )

    return mcp

async def _run_agent(node_id, agent_config, edges, nodes, user_input):
    registry = McpClientRegistry()
    registry.set_loop(asyncio.get_event_loop())

    registry.add_server(McpServerConfig(
        id="internal",
        label="Internal Tools",
        transport="stdio",
        command=sys.executable,
        args=["-m", "backend.tools.run_mcp_server"],
    ))

    available = get_available_tools(node_id, edges, nodes)
    logger.info(f"Available tools: {available}")

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
                    json.dumps(entry["node_id"]),
                    json.dumps(entry["config"]),
                    json.dumps(edges),
                    json.dumps(nodes),
                ],
            ))
    
    clients = {}
    try:
        # Connect all MCP servers upfront before provider execution
        logger.info(f"Connecting {len(registry._configs)} MCP servers for agent {agent_config.get('name')}")
        for server_id, config in registry._configs.items():
            client = McpToolClient.from_config(config)
            await client.__aenter__()
            clients[server_id] = client
            logger.info(f"  ✓ Connected: {server_id} ({config.label})")
        registry._clients = clients
        
        logger.info(f"All servers connected. Available tools: {[t['tool_name'] for t in available]}")

        provider = get_agent_provider(agent_config.get("provider", "mock"))
        result, _, _ = await provider.run(
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
                logger.warning(f"Client cleanup error (expected): {e}")

if __name__ == "__main__":
    import json

    try:
        raw_node_id = sys.argv[1]
        try:
            node_id = json.loads(raw_node_id)
        except json.JSONDecodeError:
            node_id = raw_node_id
        agent_config = json.loads(sys.argv[2])
        edges = json.loads(sys.argv[3])
        nodes = json.loads(sys.argv[4])

        setup_logging(f"sub-agent-{node_id}")
        logger = logging.getLogger(__name__)
        logger.info(f"Sub-Agent {node_id} starting.")

        mcp = create_sub_agent_server(node_id, agent_config, edges, nodes)
        mcp.run(transport="stdio")
    except Exception as e:
        raise