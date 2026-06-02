from .base import NodeExecutor
from backend.utils import collect_incoming, get_available_tools
from backend.agents import get_agent_provider

class AgentNodeExecutor(NodeExecutor):
    node_type = "agent"

    def execute(self, node, context):
        config = node.get("config", {})
        incoming = collect_incoming(node["id"], context["edges"], context["values"], context["nodes"])
        available_tools = get_available_tools(node["id"], context["edges"], context["nodes"])
        provider_name = config.get("provider", "mock")
        provider = get_agent_provider(provider_name)

        if not provider:
            return "", {"status": "error", "message": f"Agent provider '{provider_name}' not found."}
        
        result = provider.run(config, incoming, available_tools)
        context["stats"]["agentCalls"] += 1
        message = f"Agent '{config.get('name') or provider_name}' executed successfully."
        return result, {"status": "completed", "message": message}