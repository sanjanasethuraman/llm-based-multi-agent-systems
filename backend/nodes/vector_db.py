from .base import NodeExecutor
from backend.utils import log_node

class VectorDBNodeExecutor(NodeExecutor):
    node_type = "vector_db"

    def execute(self, node, context):
        # For now, this node type is just a placeholder and doesn't perform any operations.
        return "", {"status": "completed", "message": "VectorDB config loaded."}