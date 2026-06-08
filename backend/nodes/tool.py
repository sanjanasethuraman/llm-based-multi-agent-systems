from backend.tools import get_tool
from .base import NodeExecutor
from backend.utils import collect_incoming

class ToolNodeExecutor(NodeExecutor):
    node_type = "tool"

    def execute(self, node, context):
        config = node.get("config", {})
        incoming = collect_incoming(node["id"], context["edges"], context["values"], context["nodes"])
        tool = get_tool(config.get("toolType", "echo"))
        if not tool:
            return "", {"status": "error", "message": f"Tool '{config.get('toolType')}' not found."}
        result = tool.run(incoming, config)
        context["stats"]["toolCalls"] += 1
        return result, {"status": "completed", "message": f"Tool '{config.get('name') or config.get('toolType')}' executed successfully."}
