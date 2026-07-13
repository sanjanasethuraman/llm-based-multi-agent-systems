import json
import sys
import time
import inspect
import logging
import subprocess
import asyncio
import copy
import socket
import uuid
from collections import defaultdict
from pprint import pformat

from backend.nodes import get_node_executor
from backend.utils import topological_order, preview_text
from backend.mcp_registry import McpClientRegistry, McpServerConfig

logger = logging.getLogger(__name__)

VALID_NODE_TYPES = {"input", "agent", "tool", "output", "retriever", "vector_db", "sub_agent"}
VALID_AGENT_PROVIDERS = {"ollama", "huggingface"}
VALID_VECTOR_BACKENDS = {"auto", "chroma", "local-json-fallback", "faiss"}
VALID_RETRIEVAL_MODES = {"vector", "graph", "hybrid"}
VALID_GRAPH_ANSWER_MODES = {"grounded", "hybrid"}


def normalize_agent_provider(provider):
    if provider in {"mock", "api", None, ""}:
        return "ollama"
    return provider


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
        if node_type == "mcp_tool":
            if not config.get("toolId") and not config.get("toolName"):
                warnings.append(f"MCP tool node {node_id} has no tool selected.")
            if config.get("arguments"):
                try:
                    parsed_arguments = json.loads(config.get("arguments"))
                    if not isinstance(parsed_arguments, dict):
                        errors.append(f"MCP tool node {node_id} arguments must be a JSON object.")
                except Exception as exc:
                    errors.append(f"MCP tool node {node_id} has invalid arguments JSON: {exc}.")
        if node_type == "retriever":
            retrieval_mode = config.get("retrievalMode", "vector")
            if retrieval_mode not in VALID_RETRIEVAL_MODES:
                errors.append(f"Retriever node {node_id} has unsupported retrieval mode: {retrieval_mode}.")
            if retrieval_mode in {"graph", "hybrid"}:
                answer_mode = config.get("graphAnswerMode", "grounded")
                if answer_mode not in VALID_GRAPH_ANSWER_MODES:
                    errors.append(f"Retriever node {node_id} has unsupported Graph-RAG answer mode: {answer_mode}.")
                warnings.append(
                    f"Retriever node {node_id} uses Neo4j Graph RAG; ensure Neo4j is running "
                    "and the biomedical demo graph or ingested graph index exists."
                )
            query_edges = [
                edge for edge in raw_edges
                if edge.get("target") == node_id and nodes.get(edge.get("source"), {}).get("type") != "vector_db"
            ]
            if not query_edges:
                warnings.append(f"Retriever node {node_id} has no query input.")
            if not config.get("collection"):
                warnings.append(f"Retriever node {node_id} has no collection configured.")
        if node_type in {"retriever", "vector_db"}:
            vector_backend = config.get("vectorBackend", "auto")
            if vector_backend not in VALID_VECTOR_BACKENDS:
                errors.append(
                    f"Node {node_id} has unsupported vector backend: {vector_backend}."
                )
            if vector_backend == "faiss":
                warnings.append(
                    f"Node {node_id} selects FAISS, which is scaffolded but not implemented."
                )
        if node_type == "agent":
            provider = normalize_agent_provider(config.get("provider"))
            if provider not in VALID_AGENT_PROVIDERS:
                errors.append(f"Agent node {node_id} has unsupported provider: {provider}.")
            if provider == "ollama" and not config.get("model"):
                warnings.append(f"Agent node {node_id} uses Ollama without a model name.")
            if provider == "huggingface":
                if not config.get("model"):
                    warnings.append(f"Agent node {node_id} uses Hugging Face without a model id.")
                if not config.get("huggingFaceToken"):
                    warnings.append(
                        f"Agent node {node_id} uses Hugging Face without a saved token; "
                        "the backend will look for HF_TOKEN or HUGGING_FACE_API_TOKEN."
                    )

    if not errors:
        try:
            topological_order(nodes, raw_edges)
        except ValueError as exc:
            errors.append(str(exc))

    return {"valid": not errors, "errors": errors, "warnings": warnings}


async def run_workflow(workflow, mcp_registry: McpClientRegistry):
    validation = validate_workflow(workflow)
    if validation["errors"]:
        raise ValueError("Workflow validation failed: " + " ".join(validation["errors"]))

    started = time.perf_counter()
    run_id = uuid.uuid4().hex[:8]
    scoped_workflow = copy.deepcopy(workflow)
    nodes = {node["id"]: node for node in scoped_workflow.get("nodes", [])}
    edges = workflow.get("edges", [])
    order = topological_order(nodes, edges)
    sub_agent_server_ids = _assign_sub_agent_server_ids(nodes, run_id)

    values = {}
    logs = []
    node_logs = defaultdict(list)

    node_results = {}
    retrievals = []
    stats = {
        "agentCalls": 0,
        "toolCalls": 0,
        "retrieverCalls": 0,
        "mcpCalls": 0,
        "estimatedTokens": 0,
        "subAgentCalls": 0,
        "durations": {},
        "tokens": {},
    }

    context = {
        "workflow": scoped_workflow,
        "nodes": nodes,
        "edges": edges,
        "values": values,
        "logs": logs,
        "nodeLogs": node_logs,
        "stats": stats,
        "retrievals": retrievals,
        "mcpCalls": [],
        "agentToolCalls": [],
        "mcp_registry": mcp_registry,
        }

    result_payload = None
    workflow_completed = False

    try:
        await setup_sub_agent_servers(nodes, edges, mcp_registry)

        for node_id in order:
            node_started = time.perf_counter()
            node = nodes[node_id]
            executor = get_node_executor(node.get("type"))

            if executor is None:
                node_results[node_id] = {
                    "status": "error",
                    "type": node.get("type"),
                    "label": node["label"],
                    "message": f"Unsupported node type: {node.get('type')}",
                    "durationMs": round((time.perf_counter() - node_started) * 1000, 2),
                    "outputPreview": "",
                    "matches": [],
                }
                continue
            else:
                try:
                    if inspect.iscoroutinefunction(executor.execute):
                        result, metadata = await executor.execute(node, context)
                    else:
                        result, metadata = executor.execute(node, context)
                except Exception as exc:
                    logger.exception(f"Node {node_id} ({node.get('type')}) failed")
                    result = ""
                    metadata = {"status": "error", "message": f"{node.get('type')} node failed: {exc}"}
                status = metadata.get("status", "completed")
                message = metadata.get("message", "")
                stats.update(metadata.get("stats", {}))


            values[node_id] = result
            node_results[node_id] = {
                "status": status,
                "type": node["type"],
                "label": node["label"],
                "message": message,
                "durationMs": round((time.perf_counter() - node_started) * 1000, 2),
                "outputPreview": preview_text(result, limit=None),
                "matches": metadata.get("matches", []),
                "mcpCall": metadata.get("mcpCall"),
                "logs": context["nodeLogs"].get(node_id, []),
            }
            logs.append(log_item(node_id, node.get("type"), message or f"{node.get('type')} node executed.", status))

        final_output = "\n\n".join(values.get(node_id, "") for node_id in nodes if nodes[node_id].get("type") == "output")
        runtime_ms = round((time.perf_counter() - started) * 1000, 2)

        result_payload = {
            "output": final_output,
            "logs": context["nodeLogs"],
            "stats": {
                **stats,
                "runtimeMs": runtime_ms,
                "nodesExecuted": len(order),
            },
            "executionOrder": order,
            "nodeResults": node_results,
            "retrievals": retrievals,
            "mcpCalls": context["mcpCalls"],
            "validation": validation,
        }
        workflow_completed = True
    finally:
        await _cleanup_sub_agents_on_exit(
            mcp_registry,
            sub_agent_server_ids,
            suppress_cancellation=workflow_completed,
        )

    if workflow_completed:
        cleared = _clear_current_task_cancellation()
        if cleared:
            logger.debug(
                "Cleared %s pending cancellation request(s) before returning workflow result.",
                cleared,
            )

    return result_payload

def log_item(node_id, node_type, message, status="completed"):
    return {
        "nodeId": node_id,
        "type": node_type,
        "message": message,
        "status": status,
        "time": round(time.time(), 3),
    }

def find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _assign_sub_agent_server_ids(nodes: dict, run_id: str) -> set[str]:
    server_ids = set()
    for node in nodes.values():
        if node.get("type") != "sub_agent":
            continue
        node_id = node["id"]
        config = node.setdefault("config", {})
        server_id = f"sub-agent-{run_id}-{node_id}"
        config["_serverId"] = server_id
        server_ids.add(server_id)
    return server_ids


async def _wait_for_port(port: int, timeout: float = 15.0):
    deadline = asyncio.get_event_loop().time() + timeout
    while asyncio.get_event_loop().time() < deadline:
        try:
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection("127.0.0.1", port),
                timeout=1.0,
            )
            writer.close()
            await writer.wait_closed()
            return
        except Exception:
            await asyncio.sleep(0.2)
    raise TimeoutError(f"Sub-agent on port {port} did not start within {timeout}s")


async def _connect_sub_agent_with_retry(
    mcp_registry: McpClientRegistry,
    server_id: str,
    timeout: float = 15.0,
):
    deadline = asyncio.get_event_loop().time() + timeout
    last_exc = None
    while asyncio.get_event_loop().time() < deadline:
        try:
            await mcp_registry.connect(server_id)
            return
        except Exception as exc:
            last_exc = exc
            mcp_registry._clients.pop(server_id, None)
            await asyncio.sleep(0.25)
    raise TimeoutError(f"Sub-agent {server_id} MCP connection failed: {last_exc}")


async def setup_sub_agent_servers(nodes: dict, edges: list, mcp_registry: McpClientRegistry):
    """
    Scan all nodes for sub_agent type.
    Spawn each as an HTTP MCP server on a free port.
    Register in mcp_registry so orchestrator agents can call them.
    """
    from backend.utils import get_available_tools
    from backend.mcp_registry import McpServerConfig

    for node in nodes.values():
        if node["type"] != "sub_agent":
            continue

        node_id = node["id"]
        config = node.get("config", {})
        server_id = config.get("_serverId") or f"sub-agent-{node_id}"

        # skip if already connected (e.g. workflow re-run)
        if server_id in mcp_registry.all_clients():
            logger.info(f"Sub-agent {server_id} already connected, skipping.")
            continue

        port = find_free_port()

        logger.info(f"Spawning sub-agent '{config.get('name')}' ({node_id}) on port {port}")

        proc = subprocess.Popen([
            sys.executable, "-m", "backend.agents.agent_mcp_server",
            node_id,
            json.dumps(config),
            json.dumps(edges),
            json.dumps(list(nodes.values())),  # pass as list
            str(port),
        ])

        mcp_registry.register_process(server_id, proc)

        try:
            await _wait_for_port(port)
        except TimeoutError as exc:
            logger.error(f"Sub-agent {server_id} failed to start on port {port}")
            raise RuntimeError(f"Sub-agent {server_id} failed to start on port {port}") from exc

        mcp_registry.add_server(McpServerConfig(
            id=server_id,
            label=config.get("name", node_id),
            transport="http",
            url=f"http://127.0.0.1:{port}/mcp",
        ))

        await _connect_sub_agent_with_retry(mcp_registry, server_id)
        logger.info(f"Sub-agent {server_id} ready at http://127.0.0.1:{port}/mcp")

async def _cleanup_sub_agents_on_exit(
    mcp_registry,
    server_ids: set[str],
    suppress_cancellation: bool = False,
):
    try:
        await cleanup_sub_agent_servers(
            mcp_registry,
            server_ids,
            suppress_cancellation=suppress_cancellation,
        )
    except asyncio.CancelledError:
        if suppress_cancellation:
            cleared = _clear_current_task_cancellation()
            logger.debug(
                "Sub-agent cleanup cancellation suppressed after workflow completion. "
                f"Cleared {cleared} pending cancellation request(s)."
            )
            return
        raise
    finally:
        if suppress_cancellation:
            cleared = _clear_current_task_cancellation()
            if cleared:
                logger.debug(
                    "Cleared %s pending cancellation request(s) after completed workflow cleanup.",
                    cleared,
                )


def _clear_current_task_cancellation() -> int:
    task = asyncio.current_task()
    if task is None or not hasattr(task, "uncancel"):
        return 0

    cleared = 0
    while task.cancelling():
        task.uncancel()
        cleared += 1
    return cleared


def _terminate_process(server_id: str, proc: subprocess.Popen, timeout: float = 5.0):
    if proc.poll() is not None:
        return
    proc.terminate()
    try:
        proc.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait(timeout=timeout)
    logger.info(f"Terminated sub-agent: {server_id} pid={proc.pid}")


async def cleanup_sub_agent_servers(mcp_registry, server_ids=None, suppress_cancellation=False):
    """
    Remove sub-agent servers from the registry and terminate their subprocesses.
    When server_ids is provided, only those workflow-owned sub-agents are touched.
    """
    if server_ids is None:
        sub_agent_ids = {
            sid
            for sid in set(mcp_registry._clients) | set(mcp_registry._processes) | set(mcp_registry._configs)
            if sid.startswith("sub-agent-")
        }
    else:
        sub_agent_ids = set(server_ids)

    propagate_cancellation = False

    for server_id in sub_agent_ids:
        client = mcp_registry._clients.pop(server_id, None)
        mcp_registry._configs.pop(server_id, None)

        if client is not None:
            try:
                await client.__aexit__(None, None, None)
            except asyncio.CancelledError:
                propagate_cancellation = propagate_cancellation or not suppress_cancellation
            except BaseException as exc:
                if isinstance(exc, (KeyboardInterrupt, SystemExit)):
                    raise
                logger.debug(f"Sub-agent client cleanup failed for {server_id}: {exc}")
            finally:
                cleared = _clear_current_task_cancellation()
                if cleared:
                    if not suppress_cancellation:
                        propagate_cancellation = True
                    logger.debug(
                        f"Cleared {cleared} pending cancellation request(s) after "
                        f"sub-agent client cleanup for {server_id}."
                    )

        proc = mcp_registry._processes.pop(server_id, None)
        if proc:
            _terminate_process(server_id, proc)

        logger.info(f"Removed sub-agent from registry: {server_id}")

    if suppress_cancellation:
        cleared = _clear_current_task_cancellation()
        if cleared:
            logger.debug(
                "Cleared %s pending cancellation request(s) after sub-agent cleanup.",
                cleared,
            )

    if propagate_cancellation:
        raise asyncio.CancelledError()

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
import os
from pathlib import Path
from collections import defaultdict, deque
from urllib import error, parse, request


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
        "mcpCalls": 0,
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
        elif node_type == "mcp_tool":
            stats["mcpCalls"] += 1
            result = run_mcp_tool(config, incoming)
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
    vector_backend = config.get("vectorBackend", "auto")
    if vector_backend == "auto":
        vector_backend = "local-json-fallback"
    if vector_backend != "local-json-fallback":
        return (
            f"Generated Python export supports local-json-fallback retrieval only. "
            f"The workflow selected '{{vector_backend}}' for collection '{{collection}}'."
        )
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


def normalize_agent_provider(provider):
    if provider in {{"mock", "api", None, ""}}:
        return "ollama"
    return provider


def run_agent(config, incoming):
    provider = normalize_agent_provider(config.get("provider"))
    if provider == "ollama":
        return call_ollama({{**config, "provider": "ollama"}}, incoming)
    if provider == "huggingface":
        return call_huggingface(config, incoming)
    return call_ollama({{**config, "provider": "ollama"}}, incoming)


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


def call_huggingface(config, incoming):
    name = config.get("name", "Agent")
    model = config.get("model") or "mistralai/Mistral-7B-Instruct-v0.3"
    token = (
        config.get("huggingFaceToken")
        or config.get("hfToken")
        or os.environ.get("HF_TOKEN")
        or os.environ.get("HUGGING_FACE_API_TOKEN")
        or ""
    ).strip()
    base_url = normalize_huggingface_base_url(config.get("baseUrl"))
    if not token:
        return (
            f"[{{name}} | huggingface unavailable]\\n"
            "No Hugging Face token was configured. Add a token or set HF_TOKEN / HUGGING_FACE_API_TOKEN."
        )

    payload = {{
        "model": model,
        "messages": [
            {{
                "role": "system",
                "content": config.get("systemPrompt", "You are a helpful assistant."),
            }},
            {{"role": "user", "content": incoming}},
        ],
        "temperature": float(config.get("temperature", 0.2)),
        "max_tokens": int(config.get("maxNewTokens") or 512),
    }}
    try:
        data = json.dumps(payload).encode("utf-8")
        req = request.Request(
            f"{{base_url}}/chat/completions",
            data=data,
            headers={{
                "Authorization": f"Bearer {{token}}",
                "Content-Type": "application/json",
            }},
            method="POST",
        )
        with request.urlopen(req, timeout=120) as response:
            result = json.loads(response.read().decode("utf-8"))
        text = parse_huggingface_chat_completion(result)
        return text or f"[{{name}} | huggingface] Empty response from {{model}}."
    except error.HTTPError as exc:
        return f"[{{name}} | huggingface error]\\nHTTP {{exc.code}}: {{read_error_detail(exc)}}"
    except error.URLError as exc:
        return f"[{{name}} | huggingface unavailable]\\nCould not reach Hugging Face for {{model}}.\\nDetails: {{exc}}"
    except Exception as exc:
        return f"[{{name}} | huggingface error]\\n{{exc}}"


def normalize_huggingface_base_url(base_url=None):
    endpoint = (base_url or "https://router.huggingface.co/v1").rstrip("/")
    if endpoint == "https://api-inference.huggingface.co":
        return "https://router.huggingface.co/v1"
    return endpoint


def parse_huggingface_chat_completion(result):
    if isinstance(result, dict):
        if result.get("error"):
            raise ValueError(result["error"])
        choices = result.get("choices") or []
        if choices:
            message = choices[0].get("message") or {{}}
            return str(message.get("content") or choices[0].get("text") or "").strip()
    return ""


def read_error_detail(exc):
    try:
        body = exc.read().decode("utf-8")
        payload = json.loads(body)
        return payload.get("error") or payload.get("message") or body
    except Exception:
        return str(exc)


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


def run_mcp_tool(config, incoming):
    tool_id = config.get("toolId") or config.get("toolName") or ""
    arguments = parse_mcp_arguments(config.get("arguments", "{{}}"))
    if config.get("includeInput", True) and incoming and "input" not in arguments:
        arguments["input"] = incoming
    return "No live MCP server is connected for this tool node. Connect a real MCP server before running this workflow."


def parse_mcp_arguments(value):
    if isinstance(value, dict):
        return dict(value)
    if not value:
        return {{}}
    parsed = json.loads(value)
    if not isinstance(parsed, dict):
        raise ValueError("MCP arguments must be a JSON object.")
    return parsed


if __name__ == "__main__":
    main()
'''
