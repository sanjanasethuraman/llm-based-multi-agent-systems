from .base import NodeExecutor
from backend.utils import collect_incoming_map, get_all_tools, get_available_tools, get_node_id_from_server_id, log_node
from backend.utils import is_tool_managed_by_agent
from backend.agents import get_agent_provider
import logging
logger = logging.getLogger(__name__)

class AgentNodeExecutor(NodeExecutor):
    node_type = "agent"

    async def execute(self, node, context):
        if node.get("type") == "sub_agent" and is_tool_managed_by_agent(node["id"], context["edges"], context["nodes"]):
            called_tools = context.get("agentToolCalls", [])
            if node["id"] in called_tools:
                log_node(node["id"], context, "Sub-Agent is managed by an agent and was executed by the agent.", status="completed", node_type=node.get("type"))
                return "", {
                    "status": "completed",
                    "message": "Sub-Agent is managed by an agent and was executed by the agent.",
                }
            log_node(node["id"], context, "Sub-Agent is managed by an agent and was not executed automatically.", status="warning", node_type=node.get("type"))
            return "", {
                "status": "skipped",
                "message": "Sub-Agent is managed by an agent and was not executed automatically.",
            }

        config = node.get("config", {})
        incoming = collect_incoming_map(node["id"], context["edges"], context["values"], context["nodes"])
        if config.get("requireGraphEvidence") and not has_incoming_graph_paths(incoming, context):
            result = config.get("graphEvidenceUnavailableMessage") or (
                "Graph evidence is unavailable. Start Neo4j, import a relevant PrimeKG subgraph, "
                "and run the workflow again."
            )
            message = "Agent skipped because its required graph evidence was unavailable."
            log_node(node["id"], context, message, status="warning", node_type=node.get("type"))
            return result, {"status": "warning", "message": message}

        registry = context["mcp_registry"]
        available_tools = get_available_tools(node["id"], context["edges"], context["nodes"])
        log_node(node["id"], context, f"Agent has access to {len(available_tools)} tool(s).", status="info", node_type=node.get("type"))
        provider_name = config.get("provider", "ollama")
        if provider_name in {"mock", "api"}:
            provider_name = "ollama"
        provider = get_agent_provider(provider_name)

        if not provider:
            log_node(node["id"], context, f"Agent provider '{provider_name}' not found.", status="error", node_type=node.get("type"))
            return "", {"status": "error", "message": f"Agent provider '{provider_name}' not found."}

        result, stats = await provider.run(config, incoming, mcp_registry=registry, available_tools=available_tools)

        context["stats"]["agentCalls"] += 1
        context["stats"]["toolCalls"] += stats.get("toolCalls", 0)
        context["stats"]["subAgentCalls"] += stats.get("subAgentCalls", 0)
        context["stats"]["durations"][node["id"]] = stats.get("totalDuration", 0)
        context["stats"]["tokens"][node["id"]] = {
            "inputTokens": stats.get("inputTokens", 0),
            "outputTokens": stats.get("outputTokens", 0),
        }

        #set sub-agent stats in context
        for server_id, sub_stats in stats.get("subAgentStats", {}).items():
            node_id = get_node_id_from_server_id(server_id, context["nodes"])
            context["stats"]["durations"][node_id] = sub_stats.get("totalDuration", 0)
            context["stats"]["tokens"][node_id] = {
                "inputTokens": sub_stats.get("inputTokens", 0),
                "outputTokens": sub_stats.get("outputTokens", 0),
            }

        called_tools = stats.get("calledTools", [])
        for call in called_tools:
            matches = [tool for tool in get_all_tools(context["nodes"], context["edges"]) if tool.get("tool_name") == call.get("tool_name") and tool.get("server_id") == call.get("server_id")]
            for tool in matches:
                context.setdefault("agentToolCalls", []).append(tool.get("node_id"))

        for provider_log in stats.get("providerLogs", []):
            log_node(
                node["id"],
                context,
                provider_log.get("message", ""),
                status=provider_log.get("status", "info"),
                node_type=node.get("type"),
            )

        if called_tools:
            log_node(node["id"], context, f"Agent executed {len(called_tools)} tool call(s).", status="info", node_type=node.get("type"))
        else:
            log_node(node["id"], context, "Agent executed with no tool calls.", status="info", node_type=node.get("type"))

        message = f"Agent '{config.get('name') or provider_name}' executed successfully."
        return result, {"status": "completed", "message": message}


def has_incoming_graph_paths(incoming, context):
    """Return whether a graph retriever feeding this agent produced real paths."""
    incoming_ids = set(incoming)
    for retrieval in context.get("retrievals", []):
        if retrieval.get("nodeId") not in incoming_ids or retrieval.get("retrievalMode") != "graph":
            continue
        graph_evidence = retrieval.get("graphEvidence") or {}
        if graph_evidence.get("paths") or graph_evidence.get("pathText") or graph_evidence.get("path_text"):
            return True
    return False


def normalize_provider_result(provider_result):
    if isinstance(provider_result, tuple):
        if len(provider_result) == 5:
            return provider_result
        if len(provider_result) == 4:
            return provider_result, []
        if len(provider_result) == 3:
            return provider_result, [], []
        if len(provider_result) == 2:
            result, tool_calls = provider_result
            return result, tool_calls, 0, [], []
        if len(provider_result) == 1:
            return provider_result[0], 0, 0, [], []
    return provider_result, 0, 0, [], []
