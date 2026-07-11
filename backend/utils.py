import time
from collections import defaultdict, deque
from .tools import get_tool

def summarize(text, limit=180):
    cleaned = " ".join(text.split())
    if len(cleaned) <= limit:
        return cleaned
    return cleaned[:limit] + "..."

def topological_order(nodes, edges):
    indegree = {node_id: 0 for node_id in nodes}
    outgoing = defaultdict(list)

    for edge in edges:
        source = edge["source"]
        target = edge["target"]
        if source not in nodes or target not in nodes:
            raise ValueError(f"Edge references missing node: {source} -> {target}")
        outgoing[source].append(target)
        indegree[target] += 1

    queue = deque([node_id for node_id, degree in indegree.items() if degree == 0])
    order = []

    while queue:
        node_id = queue.popleft()
        order.append(node_id)
        for target in outgoing[node_id]:
            indegree[target] -= 1
            if indegree[target] == 0:
                queue.append(target)

    if len(order) != len(nodes):
        raise ValueError("Workflow contains a cycle. The first prototype supports directed acyclic graphs.")
    return order


def collect_incoming_map(node_id, edges, values, nodes, skip_types=None):
    parts = {}
    for edge in edges:
        if edge["target"] != node_id:
            continue
        src = edge["source"]
        if src not in values:
            continue
        if nodes and skip_types and get_node_type(src, nodes) in skip_types:
            continue

        # Collect structured metadata per source node id so callers can preserve provenance
        label = None
        if isinstance(nodes, dict):
            label = nodes.get(src, {}).get("label")
        else:
            for n in nodes:
                if isinstance(n, dict) and n.get("id") == src:
                    label = n.get("label")
                    break

        parts[src] = {
            "text": values[src],
            "type": get_node_type(src, nodes),
            "label": label,
        }
    return parts


def collect_incoming(node_id, edges, values, nodes=None, skip_types=None):
    """Convenience wrapper that returns the incoming content as a single joined string.
    Uses `collect_incoming_map` under the hood and joins the `text` fields in source order.
    """
    mapping = collect_incoming_map(node_id, edges, values, nodes or {}, skip_types=skip_types)
    # Preserve insertion order of edges: iterate edges and pick mapped texts
    parts = []
    for edge in edges:
        if edge["target"] == node_id:
            src = edge["source"]
            item = mapping.get(src)
            if item and item.get("text"):
                parts.append(item.get("text"))
    return "\n\n".join(parts)



def merge_vector_db_config(node_id, edges, nodes, config):
    merged = {}
    for edge in edges:
        if edge["target"] == node_id:
            source = nodes.get(edge["source"])
            if source and source.get("type") == "vector_db":
                merged.update(source.get("config", {}))
    merged.update(config)
    return merged


def estimate_tokens(text):
    return max(1, len(text.split()))

def preview_text(text, limit=220):
    cleaned = " ".join(str(text).split())
    if limit is None or len(cleaned) <= limit:
        return cleaned
    return cleaned[:limit] + "..."

def log_node(node_id, context, message, status="info", node_type=None):
    if "nodeLogs" not in context:
        context["nodeLogs"] = defaultdict(list)
    context["nodeLogs"].setdefault(node_id, []).append({
        "nodeId": node_id,
        "type": node_type,
        "status": status,
        "message": message,
        "time": round(time.time(), 3),
    })
    return context["nodeLogs"][node_id]

def get_all_tools(nodes, edges) -> list[dict]:
    """Return a list of all tool and sub-agent nodes in the workflow."""
    tools = []
    for node_id, node in nodes.items() if isinstance(nodes, dict) else ((n.get("id"), n) for n in nodes):
        if not isinstance(node, dict):
            continue
        if node.get("type") == "tool":
            config = node.get("config", {})
            tools.append({
                "type": "tool",
                "node_id": node_id,
                "server_id": config.get("serverId", "internal"),
                "tool_name": config.get("toolName") or config.get("toolType"),
                "config": config,
            })
        elif node.get("type") == "sub_agent":
            config = node.get("config", {})
            tools.append({
                "type": "sub_agent",
                "node_id": node_id,
                "server_id": f"sub-agent-{node_id}",
                "tool_name": f"run_{config.get('name', 'agent')}",
                "config": config,
            })
    return tools

def get_available_tools(node_id, edges, nodes) -> list[dict]:
    """Return a list of server_id & tool_name for tool & sub-agent nodes directly outgoing from `node_id`."""
    tools = []
    for edge in edges:
        if edge["source"] != node_id:
            continue
        target_node = None
        if isinstance(nodes, dict):
            target_node = nodes.get(edge["target"])
        else:
            for n in nodes:
                if isinstance(n, dict) and n.get("id") == edge["target"]:
                    target_node = n
                    break
        if not target_node or (target_node.get("type") != "tool" and target_node.get("type") != "sub_agent"):
            continue
        config = target_node.get("config", {})
        if target_node.get("type") == "tool":
            tools.append({
                "type": "tool",
                "node_id": target_node.get("id"),
                "server_id": config.get("serverId", "internal"),
                "tool_name": config.get("toolName") or config.get("toolType"),
                "config": config,
            })
        elif target_node.get("type") == "sub_agent":
            tools.append({
                "type": "sub_agent",
                "node_id": target_node.get("id"),
                "server_id": f"sub-agent-{target_node.get('id')}",
                "tool_name": f"run_{config.get('name', 'agent')}",
                "config": config,
            })
    return tools

def is_tool_managed_by_agent(node_id, edges, nodes):
    return any(
        edge["target"] == node_id and nodes.get(edge["source"], {}).get("type") in {"agent", "sub_agent"}
        for edge in edges
    )

def get_node_type(node_id, nodes):
    # Support both a mapping of node_id -> node (dict) and a list of node dicts.
    if isinstance(nodes, dict):
        node = nodes.get(node_id)
        if isinstance(node, dict):
            return node.get("type", "unknown")
        return "unknown"

    for node in nodes:
        if isinstance(node, dict) and node.get("id") == node_id:
            return node.get("type", "unknown")
    return "unknown"

def get_node_id_from_server_id(server_id, nodes):
    for node_id, node in nodes.items() if isinstance(nodes, dict) else ((n.get("id"), n) for n in nodes):
        if not isinstance(node, dict):
            continue
        config = node.get("config", {})
        if node.get("type") == "tool" and config.get("serverId") == server_id:
            return node_id
        elif node.get("type") == "sub_agent" and f"sub-agent-{node_id}" == server_id:
            return node_id
    return None
