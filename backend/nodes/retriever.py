from .base import NodeExecutor
from backend.utils import collect_incoming, merge_vector_db_config
from backend.rag import retrieve_context

class RetrieverNodeExecutor(NodeExecutor):
    node_type = "retriever"

    def execute(self, node, context):
        config = node.get("config", {})
        query = collect_incoming(node["id"], context["edges"], context["values"], context["nodes"])
        merged_config = merge_vector_db_config(node["id"], context["edges"], context["nodes"], config)

        matches = retrieve_context(query, merged_config)
        result = "\n\n".join(match["text"] for match in matches)
        context["stats"]["retrieverCalls"] += 1
        message = f"Retriever '{config.get('name', 'unnamed')}' executed successfully with {len(matches)} matches found."
        return result, {"status": "completed", "message": message, "matches": matches}