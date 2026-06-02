from .base import NodeExecutor
from backend.utils import collect_incoming

class OutputNodeExecutor(NodeExecutor):
    node_type = "output"

    def execute(self, node, context):
        config = node.get("config", {})
        incoming = collect_incoming(node["id"], context["edges"], context["values"], context["nodes"])
        message = f"Output node collected results from {len(incoming)} incoming edges."
        return incoming, {"status": "completed", "message": message}