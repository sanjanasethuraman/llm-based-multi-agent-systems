# Visual Tool for LLM-based Multi-Agent Systems

React + Python prototype for visually composing, running, and inspecting LLM-based multi-agent workflows.

## Features

- Drag nodes around on a React Flow canvas.
- Connect nodes visually with source/target handles.
- Delete selected nodes and edges.
- Validate workflows before execution.
- Show per-node execution status after a run.
- Ingest files into a RAG collection.
- List document/vector collections.
- Show retrieved chunks from retriever nodes.
- Switch agents between mock, Ollama, and placeholder API providers.
- Surface Ollama availability from the configured local provider URL.
- Load example workflows for demos and evaluation.

## Project Layout

- `backend/` contains the standard-library Python server, workflow runner, SQLite helpers, and RAG helpers.
    - `agents/` contains agent providers (mock, Ollama, ...)
    - `nodes/` contains node executors (for all node types)
    - `tools/` tool implementations
    - `vector_db/` optional vector DB connectors / adapters
- `frontend/` contains the Vite/React app.
- `examples/` contains presentation/demo workflows.
- `scripts/demo.sh` installs missing frontend dependencies, builds React, and starts the backend server.
- `data/` is runtime-only local state and is ignored by Git.
- `generated/` is runtime-only Python export output and is ignored by Git.

## Run The App

Install dependencies, build the React frontend, and start the Python backend:

```bash
npm install
npm run build
python3 backend/server.py
```
(If you get ModuleNotFoundErrors try "python3 -m backend.server" instead of "python3 backend/server.py)

The server defaults to `http://127.0.0.1:8000`. If that port is already taken, it automatically tries the next ports and prints the URL it selected.

Or run the demo helper:

```bash
./scripts/demo.sh
```

## Development

Run the backend:

```bash
python3 backend/server.py
```

Run the React dev server in another terminal:

```bash
VISUAL_MAS_API_TARGET=http://127.0.0.1:8001 npm run dev
```

Use the backend URL printed by `backend/server.py` as `VISUAL_MAS_API_TARGET` if it is not `8000`.

## Useful Checks

```bash
npm run build
PYTHONPYCACHEPREFIX=/private/tmp/visual-mas-pycache python3 -m py_compile backend/app_database.py backend/rag.py backend/server.py backend/workflow.py
curl -s http://127.0.0.1:8001/api/examples
curl -s http://127.0.0.1:8001/api/documents/collections
```

## Optional Ollama Support

Mock agents work without external services. For local LLM output or Ollama embeddings, start Ollama and pull the models used by the workflows:

```bash
ollama pull llama3.2:1b
ollama pull nomic-embed-text
```

If Ollama embeddings are unavailable, ingestion falls back to deterministic local hash embeddings so the prototype still runs.
