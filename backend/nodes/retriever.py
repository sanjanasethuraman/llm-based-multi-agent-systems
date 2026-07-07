from .base import NodeExecutor
from backend.utils import collect_incoming, merge_vector_db_config, log_node
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
            log_node(node["id"], context, str(exc), status="error", node_type=node.get("type"))
            return "", {"status": "error", "message": str(exc), "matches": []}

        matches = retrieval.get("matches", [])
        result = retrieval.get("context", "")
        graph_evidence = retrieval.get("graphEvidence") or {}
        context["stats"]["retrieverCalls"] += 1
        if graph_evidence:
            context["stats"]["graphEntities"] = context["stats"].get("graphEntities", 0) + len(graph_evidence.get("entities", []))
            context["stats"]["graphRelationships"] = context["stats"].get("graphRelationships", 0) + len(graph_evidence.get("relationships", []))
        context["retrievals"].append({
            "nodeId": node["id"],
            "nodeType": node["type"],
            "nodeName": config.get("name") or node.get("label") or node["id"],
            "stage": "retriever",
            "collection": merged_config.get("collection"),
            "retrievalMode": retrieval.get("retrievalMode"),
            "vectorBackend": retrieval.get("vectorBackend"),
            "embeddingBackend": retrieval.get("embeddingBackend"),
            "graphBackend": retrieval.get("graphBackend"),
            "graphEvidence": graph_evidence,
            "context": retrieval.get("context"),
            "matches": matches,
        })
        mode = retrieval.get("retrievalMode") or "vector"
        message = (
            f"Retriever '{config.get('name', 'unnamed')}' used {mode} retrieval "
            f"and found {len(matches)} matches."
        )
        log_node(node["id"], context, message, status="completed", node_type=node.get("type"))
        return result, {"status": "completed", "message": message, "matches": matches}
