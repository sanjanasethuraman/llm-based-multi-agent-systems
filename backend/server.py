from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import errno
import json
import mimetypes
import os
import sys
import asyncio
import threading
from pathlib import Path
import time
from urllib.parse import parse_qs, urlparse
from backend.logging_config import setup_logging
import logging

logger = logging.getLogger(__name__)
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

try:
    from app_database import (
        get_summary,
        init_db,
        list_document_collections,
        load_workflow,
        save_run,
        save_workflow,
    )
    from agents.huggingface import check_huggingface_status
    from rag import check_ollama_status, ingest_documents, list_vector_collections, vector_store_status
    from workflow import generate_python, run_workflow, validate_workflow
    from mcp_registry import registry, McpServerConfig, _list_all_tools
    from graph_rag import graph_store_status, import_seed_graph, load_seed_file
    from batch_workflow import run_workflow_batch, generate_comparison_summary
    from vector_db import VectorDatabaseRegistry
except ModuleNotFoundError:
    from backend.app_database import (
        get_summary,
        init_db,
        list_document_collections,
        load_workflow,
        save_run,
        save_workflow,
    )
    from backend.agents.huggingface import check_huggingface_status
    from backend.rag import check_ollama_status, ingest_documents, list_vector_collections, vector_store_status
    from backend.workflow import generate_python, run_workflow, validate_workflow
    from backend.mcp_registry import registry, McpServerConfig, _list_all_tools
    from backend.graph_rag import graph_store_status, import_seed_graph, load_seed_file
    from backend.batch_workflow import run_workflow_batch, generate_comparison_summary
    from backend.vector_db import VectorDatabaseRegistry


ROOT = Path(__file__).resolve().parents[1]
FRONTEND = ROOT / "frontend"
FRONTEND_DIST = FRONTEND / "dist"
DATA_DIR = ROOT / "data"
GENERATED_DIR = ROOT / "generated"
EXAMPLES_DIR = ROOT / "examples"
WORKFLOW_FILE = DATA_DIR / "current_workflow.json"
PYTHON_EXPORT_FILE = GENERATED_DIR / "generated_workflow.py"

_mcp_client = None
_loop: asyncio.AbstractEventLoop = None

def _start_background_loop():
    global _loop
    _loop = asyncio.new_event_loop()
    asyncio.set_event_loop(_loop)
    _loop.run_forever()

async def _init_mcp_clients():
    registry.add_server(McpServerConfig(
        id="internal",
        label="Internal Tools",
        transport="stdio",
        command="python3",
        args=["-m", "backend.tools.run_mcp_server"]
    ))
    try:
        await registry.connect_all()
    except ModuleNotFoundError as exc:
        print(f"MCP tools unavailable during startup: {exc}")
    except Exception as exc:
        print(f"MCP tools failed to connect during startup: {exc}")


class AppHandler(BaseHTTPRequestHandler):

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == "/api/health":
            return self._send_json({"status": "ok", "time": time.time()})
        if parsed.path == "/api/load-workflow":
            return self._load_workflow()
        if parsed.path == "/api/db-summary":
            return self._send_json(get_summary())
        if parsed.path == "/api/vector-store/status":
            return self._send_json(vector_store_status())
        if parsed.path == "/api/vector-store/collections":
            return self._send_json(list_vector_collections())
        if parsed.path == "/api/graph-rag/status":
            return self._send_json(graph_store_status())
        if parsed.path == "/api/documents/collections":
            return self._send_json(self._collections_payload())
        if parsed.path == "/api/mcp/tools":
            future = asyncio.run_coroutine_threadsafe(_list_all_tools(), _loop)
            return self._send_json({"tools": future.result(timeout=10)})
        if parsed.path == "/api/mcp/servers":
            return self._send_json({"servers": registry.list_servers()})
        if parsed.path == "/api/provider/ollama-status":
            params = parse_qs(parsed.query)
            base_url = params.get("baseUrl", [None])[0]
            return self._send_json(check_ollama_status(base_url))
        if parsed.path == "/api/provider/huggingface-status":
            params = parse_qs(parsed.query)
            model = params.get("model", [None])[0]
            token = params.get("token", [None])[0]
            base_url = params.get("baseUrl", [None])[0]
            return self._send_json(check_huggingface_status(model, token, base_url))
        if parsed.path == "/api/vector-db/providers":
            return self._send_json({
                "providers": VectorDatabaseRegistry.get_available_providers(),
                "list": VectorDatabaseRegistry.list_providers(),
            })
        if parsed.path == "/api/examples":
            return self._send_json(self._list_examples())
        if parsed.path == "/api/example":
            params = parse_qs(parsed.query)
            return self._load_example(params.get("name", [""])[0])
        return self._serve_frontend(parsed.path)

    def do_POST(self):
        try:
            payload = self._read_json()
            if self.path == "/api/run":
                validation = validate_workflow(payload)
                if validation["errors"]:
                    return self._send_json({
                        "error": "Workflow validation failed.",
                        "validation": validation,
                    }, status=400)
                future = asyncio.run_coroutine_threadsafe(
                    run_workflow(payload, registry),
                    _loop
                )
                result = future.result()
                save_run(payload, result)
                return self._send_json(result)
            if self.path == "/api/run-batch":
                workflows = payload.get("workflows", [])
                mode = payload.get("mode", "sequential")
                if not workflows:
                    return self._send_json({"error": "No workflows provided"}, status=400)
                for wf in workflows:
                    validation = validate_workflow(wf)
                    if validation["errors"]:
                        return self._send_json({
                            "error": "Workflow validation failed.",
                            "validation": validation,
                        }, status=400)
                future = asyncio.run_coroutine_threadsafe(
                    run_workflow_batch(workflows, registry, mode),
                    _loop
                )
                batch_result = future.result()
                summary = generate_comparison_summary(batch_result)
                return self._send_json({
                    "batchResult": batch_result,
                    "summary": summary,
                })
            if self.path == "/api/mcp/connect":
                try:
                    config = McpServerConfig(**payload)
                    registry.add_server(config)
                    future = asyncio.run_coroutine_threadsafe(
                        registry.connect(config.id), _loop
                    )
                    future.result(timeout=10)
                    return self._send_json({"status": "connected", "id": config.id})
                except Exception as e:
                    import traceback
                    traceback.print_exc()
                    return self._send_json({"error": str(e)}, status=500)
            if self.path == "/api/mcp/disconnect":
                registry.remove_server(payload["id"])
                return self._send_json({"status": "disconnected"})
            if self.path == "/api/graph-rag/seed-demo":
                seed_file = EXAMPLES_DIR / "biomedical_kg_seed.json"
                seed_payload = load_seed_file(seed_file)
                return self._send_json(import_seed_graph(seed_payload, payload))
            if self.path == "/api/generate-python":
                return self._send_json({"code": generate_python(payload)})
            if self.path == "/api/validate":
                return self._send_json(validate_workflow(payload))
            if self.path == "/api/provider/huggingface-status":
                return self._send_json(check_huggingface_status(
                    payload.get("model"),
                    payload.get("token"),
                    payload.get("baseUrl"),
                ))
            if self.path == "/api/save-workflow":
                return self._save_workflow(payload)
            if self.path == "/api/export-python-file":
                return self._export_python_file(payload)
            if self.path == "/api/ingest-document":
                return self._send_json(ingest_documents(payload))
            self.send_error(404, "Not found")
        except Exception as exc:
            self._send_json({"error": str(exc)}, status=400)

    def _read_json(self):
        length = int(self.headers.get("content-length", "0"))
        body = self.rfile.read(length).decode("utf-8")
        if not body:
            return {}
        return json.loads(body)

    def _serve_file(self, path, content_type):
        if not path.exists():
            self.send_error(404, "Not found")
            return
        data = path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _serve_frontend(self, request_path):
        if not FRONTEND_DIST.exists():
            return self._send_json({
                "error": "React frontend has not been built yet.",
                "hint": "Run npm install, then npm run build.",
            }, status=503)

        relative_path = request_path.lstrip("/") or "index.html"
        candidate = (FRONTEND_DIST / relative_path).resolve()
        if not str(candidate).startswith(str(FRONTEND_DIST.resolve())):
            self.send_error(404, "Not found")
            return

        if candidate.exists() and candidate.is_file():
            content_type = mimetypes.guess_type(candidate)[0] or "application/octet-stream"
            return self._serve_file(candidate, content_type)

        return self._serve_file(FRONTEND_DIST / "index.html", "text/html")

    def _load_workflow(self):
        db_workflow = load_workflow()
        if db_workflow:
            return self._send_json({
                "workflow": db_workflow,
                "path": str(WORKFLOW_FILE),
                "database": str(DATA_DIR / "app.sqlite"),
            })
        if not WORKFLOW_FILE.exists():
            return self._send_json({"workflow": None, "path": str(WORKFLOW_FILE)})
        return self._send_json({
            "workflow": json.loads(WORKFLOW_FILE.read_text(encoding="utf-8")),
            "path": str(WORKFLOW_FILE),
        })

    def _collections_payload(self):
        document_collections = list_document_collections()
        vector_collections = list_vector_collections()
        vectors_by_name = {
            item["name"]: item
            for item in vector_collections.get("collections", [])
        }
        collections = []
        seen = set()
        for collection in document_collections["collections"]:
            name = collection["name"]
            seen.add(name)
            vector_info = vectors_by_name.get(name, {})
            collections.append({
                **collection,
                "vectorCount": vector_info.get("vectorCount"),
                "vectorBackend": vector_info.get("backend"),
            })
        for name, vector_info in vectors_by_name.items():
            if name in seen:
                continue
            collections.append({
                "name": name,
                "documents": 0,
                "chunks": 0,
                "updatedAt": None,
                "vectorCount": vector_info.get("vectorCount"),
                "vectorBackend": vector_info.get("backend"),
            })
        return {
            "collections": collections,
            "recentDocuments": document_collections["recentDocuments"],
            "store": vector_collections["store"],
            "errors": vector_collections.get("errors", []),
        }

    def _list_examples(self):
        examples = []
        if not EXAMPLES_DIR.exists():
            return {"examples": examples}
        for path in sorted(EXAMPLES_DIR.glob("*.json")):
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                continue
            workflow = payload.get("workflow", payload)
            if not isinstance(workflow, dict) or "nodes" not in workflow or "edges" not in workflow:
                continue
            examples.append({
                "name": path.stem,
                "label": payload.get("label") or path.stem.replace("_", " ").title(),
                "description": payload.get("description", ""),
            })
        return {"examples": examples}

    def _load_example(self, name):
        safe_name = "".join(char for char in name if char.isalnum() or char in {"_", "-"})
        if not safe_name:
            return self._send_json({"error": "Missing example name."}, status=400)
        path = EXAMPLES_DIR / f"{safe_name}.json"
        if not path.exists():
            return self._send_json({"error": f"Example not found: {safe_name}"}, status=404)
        payload = json.loads(path.read_text(encoding="utf-8"))
        workflow = payload.get("workflow", payload)
        if not isinstance(workflow, dict) or "nodes" not in workflow or "edges" not in workflow:
            return self._send_json({"error": f"Example is not a workflow: {safe_name}"}, status=400)
        return self._send_json({
            "name": safe_name,
            "workflow": workflow,
            "label": payload.get("label", safe_name),
            "description": payload.get("description", ""),
        })

    def _save_workflow(self, workflow):
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        save_workflow(workflow)
        WORKFLOW_FILE.write_text(json.dumps(workflow, indent=2), encoding="utf-8")
        return self._send_json({
            "status": "saved",
            "path": str(WORKFLOW_FILE),
            "database": str(DATA_DIR / "app.sqlite"),
        })

    def _export_python_file(self, workflow):
        GENERATED_DIR.mkdir(parents=True, exist_ok=True)
        code = generate_python(workflow)
        PYTHON_EXPORT_FILE.write_text(code, encoding="utf-8")
        return self._send_json({
            "status": "exported",
            "path": str(PYTHON_EXPORT_FILE),
            "code": code,
        })

    def _send_json(self, data, status=200):
        body = json.dumps(data, indent=2).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def main():
    init_db()

    # Start persistent event loop in background thread
    thread = threading.Thread(target=_start_background_loop, daemon=True)
    thread.start()

    while _loop is None:
        time.sleep(0.01)
    registry.set_loop(_loop)
    
    future = asyncio.run_coroutine_threadsafe(_init_mcp_clients(), _loop)
    future.result(timeout=10)

    host = os.environ.get("VISUAL_MAS_HOST", "127.0.0.1")
    preferred_port = int(os.environ.get("VISUAL_MAS_PORT", "8000"))
    server, port = create_server(host, preferred_port)
    print(f"Serving prototype at http://{host}:{port}")
    server.serve_forever()


def create_server(host, preferred_port):
    for port in range(preferred_port, preferred_port + 20):
        try:
            return ThreadingHTTPServer((host, port), AppHandler), port
        except OSError as exc:
            if exc.errno != errno.EADDRINUSE:
                raise
    raise OSError(f"No available port found from {preferred_port} to {preferred_port + 19}")


if __name__ == "__main__":
    setup_logging("server")
    logger.info("Starting server...")
    main()
