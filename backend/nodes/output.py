from .base import NodeExecutor
from backend.utils import collect_incoming_map, log_node

class OutputNodeExecutor(NodeExecutor):
    node_type = "output"

    def execute(self, node, context):
        config = node.get("config", {})
        incoming_map = collect_incoming_map(node["id"], context["edges"], context["values"], context["nodes"])
        node_label = node.get("label") or node.get("id")

        if not incoming_map:
            output_text = f"--- Output from {node_label} ({node['id']}) ---\n(no incoming data)"
        else:
            parts = []
            for src, item in incoming_map.items():
                text = item.get("text", "") if isinstance(item, dict) else str(item)
                label = item.get("label") if isinstance(item, dict) else None
                ntype = item.get("type") if isinstance(item, dict) else None
                source_label = label or src
                source_type = f"{ntype}" if ntype else "unknown"
                parts.append(
                    f"--- From {source_label} ({source_type}, {src}) ---\n{text}"
                )
            output_text = "\n\n".join(parts)

        message = f"Output node collected results from {len(incoming_map)} incoming sources."
        log_node(node["id"], context, message, status="completed", node_type=node.get("type"))
        return output_text, {"status": "completed", "message": message}
