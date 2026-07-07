from backend.tools import get_tool
from .base import NodeExecutor
from backend.utils import collect_incoming, is_tool_managed_by_agent, log_node

class ToolNodeExecutor(NodeExecutor):
    node_type = "tool"

    def execute(self, node, context):
        if is_tool_managed_by_agent(node["id"], context["edges"], context["nodes"]):
            called_tools = context.get("agentToolCalls", [])
            if node["id"] in called_tools:
                log_node(node["id"], context, "Tool is managed by an agent and was executed by the agent.", status="completed", node_type=node.get("type"))
                return "", {
                    "status": "completed",
                    "message": "Tool is managed by an agent and was executed by the agent.",
                }
            log_node(node["id"], context, "Tool is managed by an agent and was not executed automatically.", status="warning", node_type=node.get("type"))
            return "", {
                "status": "skipped",
                "message": "Tool is managed by an agent and was not executed automatically.",
            }

        config = node.get("config", {})
        incoming = collect_incoming(node["id"], context["edges"], context["values"], context["nodes"])
        tool = get_tool(config.get("toolType", "echo"))
        if not tool:
            log_node(node["id"], context, f"Tool '{config.get('toolType')}' not found.", status="error", node_type=node.get("type"))
            return "", {"status": "error", "message": f"Tool '{config.get('toolType')}' not found."}
        result = tool.execute(incoming)
        log_node(node["id"], context, f"Tool '{config.get('name') or config.get('toolType')}' executed with input length {len(str(incoming))}.", status="completed", node_type=node.get("type"))
        return result, {"status": "completed", "message": f"Tool '{config.get('name') or config.get('toolType')}' executed successfully."}
