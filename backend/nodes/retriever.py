from .base import NodeExecutor
from backend.utils import collect_incoming, merge_vector_db_config
from backend.rag import retrieve_context

class RetrieverNodeExecutor(NodeExecutor):
    node_type = "retriever"

    def execute(self, node, context):
        config = node.get("config", {})
        query = collect_incoming(node["id"], context["edges"], context["values"], context["nodes"])
        merged_config = merge_vector_db_config(node["id"], context["edges"], context["nodes"], config)

        try:
            retrieval = retrieve_context(merged_config, query)
        except ValueError as exc:
            return "", {"status": "error", "message": str(exc), "matches": []}

        matches = retrieval.get("matches", [])
        result = retrieval.get("context", "")
        context["stats"]["retrieverCalls"] += 1
        context["retrievals"].append({
            "nodeId": node["id"],
            "nodeType": node["type"],
            "nodeName": config.get("name") or node.get("label") or node["id"],
            "stage": "retriever",
            "collection": merged_config.get("collection"),
            "vectorBackend": retrieval.get("vectorBackend"),
            "embeddingBackend": retrieval.get("embeddingBackend"),
            "context": retrieval.get("context"),
            "matches": matches,
        })
        message = (
            f"Retriever '{config.get('name', 'unnamed')}' used "
            f"{retrieval.get('vectorBackend')} and found {len(matches)} matches."
        )
        return result, {"status": "completed", "message": message, "matches": matches}
