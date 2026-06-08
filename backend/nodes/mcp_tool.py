import json

from .base import NodeExecutor
from backend.mcp_registry import call_mcp_tool
from backend.utils import collect_incoming


class MCPToolNodeExecutor(NodeExecutor):
    node_type = "mcp_tool"

    def execute(self, node, context):
        config = node.get("config", {})
        incoming = collect_incoming(node["id"], context["edges"], context["values"], context["nodes"])
        tool_id = config.get("toolId") or config.get("toolName")
        if not tool_id:
            return "", {"status": "error", "message": "MCP tool node has no tool selected."}

        try:
            arguments = parse_arguments(config.get("arguments", "{}"))
            if config.get("includeInput", True) and incoming and "input" not in arguments:
                arguments["input"] = incoming
            call = call_mcp_tool(tool_id, arguments, incoming)
        except Exception as exc:
            return "", {"status": "error", "message": str(exc), "mcpCall": None}

        context["stats"]["mcpCalls"] += 1
        context["mcpCalls"].append({
            "nodeId": node["id"],
            "server": config.get("server", "demo"),
            **call,
        })
        return call["result"], {
            "status": "completed",
            "message": f"MCP tool '{tool_id}' executed successfully.",
            "mcpCall": call,
        }


def parse_arguments(value):
    if isinstance(value, dict):
        return dict(value)
    if not value:
        return {}
    parsed = json.loads(value)
    if not isinstance(parsed, dict):
        raise ValueError("MCP arguments must be a JSON object.")
    return parsed
