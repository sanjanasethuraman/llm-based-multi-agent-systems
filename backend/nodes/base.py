class NodeExecutor:
    node_type = None

    def execute(self, node, context):
        raise NotImplementedError("Subclasses must implement the execute method.")