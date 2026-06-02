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


def collect_incoming(node_id, edges, values, nodes=None, skip_types=None):
    #TODO: optimize
    parts = []
    for edge in edges:
        if edge["target"] == node_id and edge["source"] in values:
            if nodes and skip_types and nodes[edge["source"]].get("type") in skip_types:
                continue
            parts.append(values[edge["source"]])
    return "\n\n".join(part for part in parts if part)


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


def summarize(text, limit=180):
    cleaned = " ".join(text.split())
    if len(cleaned) <= limit:
        return cleaned
    return cleaned[:limit] + "..."

def preview_text(text, limit=220):
    cleaned = " ".join(str(text).split())
    if len(cleaned) <= limit:
        return cleaned
    return cleaned[:limit] + "..."

def get_available_tools(node_id, edges, nodes):
    tools = []
    for edge in edges:
        if edge["source"] == node_id:
            target_node = nodes.get(edge["target"])
            if target_node and target_node.get("type") == "tool":
                tool_type = target_node.get("config", {}).get("toolType")
                if tool_type:
                    tools.append(get_tool(tool_type))
    return tools