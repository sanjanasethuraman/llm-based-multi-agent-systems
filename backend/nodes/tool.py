from backend.tools import get_tool
from .base import NodeExecutor
from backend.utils import collect_incoming
from backend.utils import is_tool_managed_by_agent

class ToolNodeExecutor(NodeExecutor):
    node_type = "tool"

    def execute(self, node, context):
        if is_tool_managed_by_agent(node["id"], context["edges"], context["nodes"]):
            called_tools = context.get("agentToolCalls", [])
            if node["id"] in called_tools:
                return "", {
                    "status": "completed",
                    "message": "Tool is managed by an agent and was executed by the agent.",
                }
            return "", {
                "status": "skipped",
                "message": "Tool is managed by an agent and was not executed automatically.",
            }

        config = node.get("config", {})
        incoming = collect_incoming(node["id"], context["edges"], context["values"], context["nodes"])
        tool = get_tool(config.get("toolType", "echo"))
        if not tool:
            return "", {"status": "error", "message": f"Tool '{config.get('toolType')}' not found."}
        result = tool.execute(incoming)
        print(f"Executed tool '{config.get('name') or config.get('toolType')}' with input: {incoming} and got result: {result}")
        return result, {"status": "completed", "message": f"Tool '{config.get('name') or config.get('toolType')}' executed successfully."}
