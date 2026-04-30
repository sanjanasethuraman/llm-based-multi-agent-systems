import json
import time
from collections import defaultdict, deque
from pprint import pformat
from urllib import error, request

try:
    from rag import retrieve_context
except ModuleNotFoundError:
    from backend.rag import retrieve_context


VALID_NODE_TYPES = {"input", "agent", "tool", "output", "retriever", "vector_db"}


def validate_workflow(workflow):
    errors = []
    warnings = []
    raw_nodes = workflow.get("nodes", [])
    raw_edges = workflow.get("edges", [])

    if not isinstance(raw_nodes, list):
        return {"valid": False, "errors": ["Workflow nodes must be a list."], "warnings": warnings}
    if not isinstance(raw_edges, list):
        return {"valid": False, "errors": ["Workflow edges must be a list."], "warnings": warnings}
    if not raw_nodes:
        return {"valid": False, "errors": ["Workflow must contain at least one node."], "warnings": warnings}

    nodes = {}
    seen_ids = set()
    for index, node in enumerate(raw_nodes, start=1):
        node_id = node.get("id")
        node_type = node.get("type")
        if not node_id:
            errors.append(f"Node {index} is missing an id.")
            continue
        if node_id in seen_ids:
            errors.append(f"Duplicate node id: {node_id}.")
        seen_ids.add(node_id)
        nodes[node_id] = node
        if node_type not in VALID_NODE_TYPES:
            errors.append(f"Node {node_id} has unsupported type: {node_type}.")

    if not any(node.get("type") == "input" for node in nodes.values()):
        warnings.append("Workflow has no input node.")
    if not any(node.get("type") == "output" for node in nodes.values()):
        errors.append("Workflow must contain at least one output node.")

    incoming = defaultdict(int)
    outgoing = defaultdict(int)
    edge_pairs = set()
    for index, edge in enumerate(raw_edges, start=1):
        source = edge.get("source")
        target = edge.get("target")
        if not source or not target:
            errors.append(f"Edge {index} must include source and target.")
            continue
        if source not in nodes:
            errors.append(f"Edge {index} references missing source node: {source}.")
        if target not in nodes:
            errors.append(f"Edge {index} references missing target node: {target}.")
        if source == target:
            errors.append(f"Edge {index} connects {source} to itself.")
        if (source, target) in edge_pairs:
            warnings.append(f"Duplicate edge ignored by execution: {source} -> {target}.")
        edge_pairs.add((source, target))
        outgoing[source] += 1
        incoming[target] += 1

    for node_id, node in nodes.items():
        node_type = node.get("type")
        config = node.get("config", {})
        if node_type == "output" and incoming[node_id] == 0:
            warnings.append(f"Output node {node_id} has no incoming edge.")
        if node_type not in {"input", "output"} and incoming[node_id] == 0 and outgoing[node_id] == 0:
            warnings.append(f"Node {node_id} is disconnected.")
        if node_type == "retriever":
            query_edges = [
                edge for edge in raw_edges
                if edge.get("target") == node_id and nodes.get(edge.get("source"), {}).get("type") != "vector_db"
            ]
            if not query_edges:
                warnings.append(f"Retriever node {node_id} has no query input.")
            if not config.get("collection"):
                warnings.append(f"Retriever node {node_id} has no collection configured.")
        if node_type == "agent":
            provider = config.get("provider", "mock")
            if provider == "api":
                warnings.append(f"Agent node {node_id} uses the placeholder api provider.")
            if provider == "ollama" and not config.get("model"):
                warnings.append(f"Agent node {node_id} uses Ollama without a model name.")

    if not errors:
        try:
            topological_order(nodes, raw_edges)
        except ValueError as exc:
            errors.append(str(exc))

    return {"valid": not errors, "errors": errors, "warnings": warnings}


def run_workflow(workflow):
    validation = validate_workflow(workflow)
    if validation["errors"]:
        raise ValueError("Workflow validation failed: " + " ".join(validation["errors"]))

    started = time.perf_counter()
    nodes = {node["id"]: node for node in workflow.get("nodes", [])}
    edges = workflow.get("edges", [])
    order = topological_order(nodes, edges)

    values = {}
    logs = []
    agent_calls = 0
    tool_calls = 0
    retriever_calls = 0
    token_estimate = 0
    node_results = {}
    retrievals = []

    for node_id in order:
        node_started = time.perf_counter()
        node = nodes[node_id]
        node_type = node.get("type")
        config = node.get("config", {})
        incoming = collect_incoming(node_id, edges, values, nodes)
        status = "completed"
        message = ""
        matches = []

        if node_type == "input":
            result = config.get("text", "")
            message = "Loaded user input."
            logs.append(log_item(node_id, "input", message, status))
        elif node_type == "vector_db":
            result = ""
            collection = config.get("collection", "course_docs")
            message = f"Configured Vector DB collection '{collection}'."
            logs.append(log_item(node_id, "vector_db", message, status))
        elif node_type == "retriever":
            retriever_calls += 1
            retriever_config = merge_vector_db_config(node_id, edges, nodes, config)
            query = collect_incoming(node_id, edges, values, nodes, skip_types={"vector_db"})
            retrieved = retrieve_context(retriever_config, query)
            result = retrieved["context"]
            matches = retrieved.get("matches", [])
            retrievals.append({
                "nodeId": node_id,
                "collection": retriever_config.get("collection", "course_docs"),
                "matches": matches,
                "vectorBackend": retrieved.get("vectorBackend", "unknown"),
                "embeddingBackend": retrieved.get("embeddingBackend", "unknown"),
            })
            token_estimate += estimate_tokens(query + " " + result)
            if not matches:
                status = "warning"
            message = (
                f"Retrieved {len(matches)} chunks from "
                f"{retriever_config.get('collection', 'course_docs')} using "
                f"{retrieved.get('vectorBackend', 'unknown')}."
            )
            logs.append(
                log_item(
                    node_id,
                    "retriever",
                    message,
                    status,
                )
            )
        elif node_type == "agent":
            agent_calls += 1
            result = run_agent(config, incoming)
            token_estimate += estimate_tokens(config.get("systemPrompt", "") + " " + incoming + " " + result)
            provider = config.get("provider", "mock")
            if provider == "ollama" and "ollama unavailable" in result.lower():
                status = "warning"
            if provider == "ollama" and "ollama error" in result.lower():
                status = "error"
            message = (
                f"{config.get('name', 'Agent')} ran with "
                f"{provider} / {config.get('model', 'n/a')}."
            )
            logs.append(
                log_item(
                    node_id,
                    "agent",
                    message,
                    status,
                )
            )
        elif node_type == "tool":
            tool_calls += 1
            result = run_tool(config, incoming)
            token_estimate += estimate_tokens(incoming + " " + result)
            message = f"{config.get('name', 'Tool')} returned a result."
            logs.append(log_item(node_id, "tool", message, status))
        elif node_type == "output":
            result = incoming
            message = "Collected final output."
            logs.append(log_item(node_id, "output", message, status))
        else:
            result = incoming
            status = "warning"
            message = f"Passed through unknown node type: {node_type}"
            logs.append(log_item(node_id, "unknown", message, status))

        values[node_id] = result
        node_results[node_id] = {
            "status": status,
            "type": node_type,
            "message": message,
            "durationMs": round((time.perf_counter() - node_started) * 1000, 2),
            "outputPreview": preview_text(result),
            "matches": matches,
        }

    output_nodes = [node["id"] for node in nodes.values() if node.get("type") == "output"]
    final_output = "\n\n".join(values.get(node_id, "") for node_id in output_nodes) or ""
    runtime_ms = round((time.perf_counter() - started) * 1000, 2)

    return {
        "output": final_output,
        "logs": logs,
        "stats": {
            "runtimeMs": runtime_ms,
            "agentCalls": agent_calls,
            "toolCalls": tool_calls,
            "retrieverCalls": retriever_calls,
            "estimatedTokens": token_estimate,
            "nodesExecuted": len(order),
        },
        "executionOrder": order,
        "nodeResults": node_results,
        "retrievals": retrievals,
        "validation": validation,
    }


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


def run_agent(config, incoming):
    provider = config.get("provider", "mock")
    name = config.get("name", "Agent")
    prompt = config.get("systemPrompt", "You are a helpful assistant.")

    if provider == "mock":
        return (
            f"[{name} | mock]\n"
            f"System prompt: {prompt}\n"
            f"Input summary: {summarize(incoming)}\n"
            "Response: This is a deterministic prototype response."
        )

    if provider == "ollama":
        return call_ollama(config, incoming)

    return f"[{name} | {provider}] Provider is not implemented yet."


def call_ollama(config, incoming):
    name = config.get("name", "Agent")
    model = config.get("model", "llama3.2:1b")
    base_url = config.get("baseUrl", "http://127.0.0.1:11434").rstrip("/")
    prompt = build_llm_prompt(config, incoming)
    payload = {
        "model": model,
        "prompt": prompt,
        "stream": False,
        "options": {"temperature": float(config.get("temperature", 0.2))},
    }

    try:
        data = json.dumps(payload).encode("utf-8")
        req = request.Request(
            f"{base_url}/api/generate",
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with request.urlopen(req, timeout=90) as response:
            result = json.loads(response.read().decode("utf-8"))
        return result.get("response", "").strip() or f"[{name} | ollama] Empty response from {model}."
    except error.URLError as exc:
        return (
            f"[{name} | ollama unavailable]\n"
            f"Could not reach Ollama at {base_url} for model {model}.\n"
            "Start Ollama and pull the model, for example: ollama pull llama3.2:1b\n"
            f"Details: {exc}"
        )
    except Exception as exc:
        return f"[{name} | ollama error]\n{exc}"


def build_llm_prompt(config, incoming):
    system_prompt = config.get("systemPrompt", "You are a helpful assistant.")
    return (
        f"System instructions:\n{system_prompt}\n\n"
        f"Workflow input:\n{incoming}\n\n"
        "Respond with the result for this agent node."
    )


def run_tool(config, incoming):
    name = config.get("name", "Tool")
    tool_type = config.get("toolType", "echo")

    if tool_type == "uppercase":
        return incoming.upper()
    if tool_type == "word_count":
        return f"{name} counted {len(incoming.split())} words."
    return f"{name} received:\n{incoming}"


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


def log_item(node_id, node_type, message, status="completed"):
    return {
        "nodeId": node_id,
        "type": node_type,
        "message": message,
        "status": status,
        "time": round(time.time(), 3),
    }


def generate_python(workflow):
    serialized = pformat(workflow, width=100, sort_dicts=False)
    return f'''"""
Executable workflow generated by the Visual MAS prototype.

Run:
    python3 generated_workflow.py
"""

import json
import hashlib
import math
from pathlib import Path
from collections import defaultdict, deque
from urllib import error, request


WORKFLOW = {serialized}
ROOT = Path(__file__).resolve().parents[1]
FALLBACK_VECTOR_FILE = ROOT / "data" / "vector_store.json"


def main():
    result = run_workflow(WORKFLOW)
    print("\\n=== Final Output ===\\n")
    print(result["output"])
    print("\\n=== Stats ===\\n")
    print(json.dumps(result["stats"], indent=2))


def run_workflow(workflow):
    nodes = {{node["id"]: node for node in workflow.get("nodes", [])}}
    edges = workflow.get("edges", [])
    order = topological_order(nodes, edges)
    values = {{}}
    stats = {{
        "agentCalls": 0,
        "toolCalls": 0,
        "retrieverCalls": 0,
        "estimatedTokens": 0,
        "nodesExecuted": len(order),
    }}

    for node_id in order:
        node = nodes[node_id]
        incoming = collect_incoming(node_id, edges, values, nodes)
        config = node.get("config", {{}})
        node_type = node.get("type")

        if node_type == "input":
            result = config.get("text", "")
        elif node_type == "vector_db":
            result = ""
        elif node_type == "retriever":
            stats["retrieverCalls"] += 1
            retriever_config = merge_vector_db_config(node_id, edges, nodes, config)
            query = collect_incoming(node_id, edges, values, nodes, skip_types={{"vector_db"}})
            result = retrieve_context(retriever_config, query)
            stats["estimatedTokens"] += len((query + " " + result).split())
        elif node_type == "agent":
            stats["agentCalls"] += 1
            result = run_agent(config, incoming)
            stats["estimatedTokens"] += len((incoming + " " + result).split())
        elif node_type == "tool":
            stats["toolCalls"] += 1
            result = run_tool(config, incoming)
        elif node_type == "output":
            result = incoming
        else:
            result = incoming

        values[node_id] = result

    output_ids = [node["id"] for node in nodes.values() if node.get("type") == "output"]
    return {{"output": "\\n\\n".join(values.get(node_id, "") for node_id in output_ids), "stats": stats}}


def topological_order(nodes, edges):
    indegree = {{node_id: 0 for node_id in nodes}}
    outgoing = defaultdict(list)
    for edge in edges:
        outgoing[edge["source"]].append(edge["target"])
        indegree[edge["target"]] += 1

    queue = deque([node_id for node_id, degree in indegree.items() if degree == 0])
    order = []
    while queue:
        node_id = queue.popleft()
        order.append(node_id)
        for target in outgoing[node_id]:
            indegree[target] -= 1
            if indegree[target] == 0:
                queue.append(target)
    return order


def collect_incoming(node_id, edges, values, nodes=None, skip_types=None):
    parts = []
    for edge in edges:
        if edge["target"] == node_id and edge["source"] in values:
            if nodes and skip_types and nodes[edge["source"]].get("type") in skip_types:
                continue
            parts.append(values.get(edge["source"], ""))
    return "\\n\\n".join(part for part in parts if part)


def merge_vector_db_config(node_id, edges, nodes, config):
    merged = {{}}
    for edge in edges:
        if edge["target"] == node_id:
            source = nodes.get(edge["source"])
            if source and source.get("type") == "vector_db":
                merged.update(source.get("config", {{}}))
    merged.update(config)
    return merged


def retrieve_context(config, query):
    collection = config.get("collection", "course_docs")
    top_k = int(config.get("topK") or 3)
    query_embedding = hash_embedding(query)
    store = load_vector_store()
    items = store.get("collections", {{}}).get(collection, [])
    matches = []
    for item in items:
        matches.append({{
            "text": item.get("text", ""),
            "metadata": item.get("metadata", {{}}),
            "score": cosine_similarity(query_embedding, item.get("embedding", [])),
        }})
    matches.sort(key=lambda item: item["score"], reverse=True)
    matches = matches[:top_k]

    if not matches:
        return (
            f"No retrieved context found in collection '{{collection}}'. "
            "Ingest documents in the Visual MAS app first."
        )

    lines = [f"Retrieved context from collection '{{collection}}':"]
    for index, match in enumerate(matches, start=1):
        title = match["metadata"].get("title", "Untitled")
        score = round(match.get("score", 0), 4)
        lines.append(f"[{{index}}] {{title}} (score: {{score}})\\n{{match['text']}}")
    return "\\n\\n".join(lines)


def load_vector_store():
    if not FALLBACK_VECTOR_FILE.exists():
        return {{"collections": {{}}}}
    return json.loads(FALLBACK_VECTOR_FILE.read_text(encoding="utf-8"))


def hash_embedding(text, dimensions=64):
    vector = [0.0] * dimensions
    for token in text.lower().split():
        digest = hashlib.sha256(token.encode("utf-8")).digest()
        index = int.from_bytes(digest[:2], "big") % dimensions
        sign = 1.0 if digest[2] % 2 == 0 else -1.0
        vector[index] += sign
    return normalize(vector)


def normalize(vector):
    magnitude = math.sqrt(sum(value * value for value in vector))
    if magnitude == 0:
        return vector
    return [value / magnitude for value in vector]


def cosine_similarity(left, right):
    return sum(a * b for a, b in zip(left, right))


def run_agent(config, incoming):
    name = config.get("name", "Agent")
    system_prompt = config.get("systemPrompt", "You are a helpful assistant.")
    provider = config.get("provider", "mock")
    if provider == "ollama":
        return call_ollama(config, incoming)
    return f"[{{name}} | {{provider}}]\\nSystem prompt: {{system_prompt}}\\nInput: {{incoming}}\\nResponse: generated prototype answer"


def call_ollama(config, incoming):
    name = config.get("name", "Agent")
    model = config.get("model", "llama3.2:1b")
    base_url = config.get("baseUrl", "http://127.0.0.1:11434").rstrip("/")
    payload = {{
        "model": model,
        "prompt": build_llm_prompt(config, incoming),
        "stream": False,
        "options": {{"temperature": float(config.get("temperature", 0.2))}},
    }}

    try:
        data = json.dumps(payload).encode("utf-8")
        req = request.Request(
            f"{{base_url}}/api/generate",
            data=data,
            headers={{"Content-Type": "application/json"}},
            method="POST",
        )
        with request.urlopen(req, timeout=90) as response:
            result = json.loads(response.read().decode("utf-8"))
        return result.get("response", "").strip() or f"[{{name}} | ollama] Empty response from {{model}}."
    except error.URLError as exc:
        return (
            f"[{{name}} | ollama unavailable]\\n"
            f"Could not reach Ollama at {{base_url}} for model {{model}}.\\n"
            "Start Ollama and pull the model, for example: ollama pull llama3.2:1b\\n"
            f"Details: {{exc}}"
        )
    except Exception as exc:
        return f"[{{name}} | ollama error]\\n{{exc}}"


def build_llm_prompt(config, incoming):
    return (
        f"System instructions:\\n{{config.get('systemPrompt', 'You are a helpful assistant.')}}\\n\\n"
        f"Workflow input:\\n{{incoming}}\\n\\n"
        "Respond with the result for this agent node."
    )


def run_tool(config, incoming):
    if config.get("toolType") == "word_count":
        return f"Word count: {{len(incoming.split())}}"
    if config.get("toolType") == "uppercase":
        return incoming.upper()
    return incoming


if __name__ == "__main__":
    main()
'''
