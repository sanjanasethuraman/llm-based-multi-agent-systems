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

        result = await provider.run(config, incoming, mcp_registry=registry, available_tools=available_tools)
        if len(result) == 4:
            result, tool_calls, sub_agent_calls, called_tools = result
        else:
            result, tool_calls, sub_agent_calls = result
            called_tools = []

        context["stats"]["agentCalls"] += 1
        context["stats"]["toolCalls"] += tool_calls
        context["stats"]["subAgentCalls"] += sub_agent_calls

        for call in called_tools:
            matches = [tool for tool in available_tools if tool.get("tool_name") == call.get("tool_name") and tool.get("server_id") == call.get("server_id")]
            for tool in matches:
                context.setdefault("agentToolCalls", []).append(tool.get("node_id"))

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
