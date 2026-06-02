from .base import NodeExecutor

class InputNodeExecutor(NodeExecutor):
    node_type = "input"

    def execute(self, node, context):
        config = node.get("config", {})
        text = config.get("text", "")
        message = f"Input node returning text (length: {len(text)} characters)."
        return text, {"status": "completed", "message": message}