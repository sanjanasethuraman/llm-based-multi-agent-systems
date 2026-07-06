from .base import NodeExecutor
from backend.utils import collect_incoming_map, get_available_tools
from backend.agents import get_agent_provider

class AgentNodeExecutor(NodeExecutor):
    node_type = "agent"

    async def execute(self, node, context):
        config = node.get("config", {})
        incoming = collect_incoming_map(node["id"], context["edges"], context["values"], context["nodes"])
        registry = context["mcp_registry"]
        available_tools = get_available_tools(node["id"], context["edges"], context["nodes"])
        print(f"Available Tools: {available_tools}")
        provider_name = config.get("provider", "mock")
        provider = get_agent_provider(provider_name)

        if not provider:
            return "", {"status": "error", "message": f"Agent provider '{provider_name}' not found."}

        provider_result = await provider.run(config, incoming, mcp_registry=registry, available_tools=available_tools)
        result, tool_calls, sub_agent_calls = normalize_provider_result(provider_result)
        context["stats"]["agentCalls"] += 1
        context["stats"]["toolCalls"] += tool_calls
        context["stats"]["subAgentCalls"] += sub_agent_calls
        message = f"Agent '{config.get('name') or provider_name}' executed successfully."
        return result, {"status": "completed", "message": message}


def normalize_provider_result(provider_result):
    if isinstance(provider_result, tuple):
        if len(provider_result) == 3:
            return provider_result
        if len(provider_result) == 2:
            result, tool_calls = provider_result
            return result, tool_calls, 0
        if len(provider_result) == 1:
            return provider_result[0], 0, 0
    return provider_result, 0, 0
