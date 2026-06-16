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
- Select a vector backend per ingestion/retriever path (auto, Chroma, local JSON, FAISS scaffold).
- Show retrieved chunks from retriever nodes.
- Display retrieval metadata on each chunk card, including stage, collection, chunk index, score, and vector backend.
- Show retrieval chunk usage on the workflow graph with retriever node badges and edge labels.
- Add retrieval-aware workflow metrics: retrieved chunks, retriever nodes, collections retrieved, and hit retrievals.
- Show retriever execution results even when zero matches are returned.
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

## Setup & Run The App
### 1. Install Python dependencies
Create and activate a Python virtual environment:
```bash
python -m venv .venv
source .venv/bin/activate
```
Install backend dependencies:
```bash
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

### 2. Install Node dependencies, build the React frontend, and start the Python backend:

```bash
npm install
npm run build
python3 backend/server.py
```
(If you get ModuleNotFoundErrors try "python3 -m backend.server" instead of "python3 backend/server.py)
For richer document ingestion support (PDF, DOCX, PPTX), install the optional backend dependencies:

```bash
pip install -r requirements.txt
```
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

## Optional Hugging Face Support

Agent nodes can use hosted Hugging Face models through the OpenAI-compatible Hugging Face router at `https://router.huggingface.co/v1/chat/completions`. Select `Hugging Face` as the agent provider, set a model ID such as `mistralai/Mistral-7B-Instruct-v0.3`, and either enter a token in the node settings or start the backend with:

```bash
HF_TOKEN=hf_your_token python3 backend/server.py
```

The backend also accepts `HUGGING_FACE_API_TOKEN`. Leaving the token field empty keeps saved workflows cleaner when the token is supplied through the environment.

## Vector Backend Options

- `auto` uses Chroma when `chromadb` is installed, otherwise local JSON.
- `chroma` uses a persistent Chroma store in `data/chroma`.
- `local-json-fallback` stores vectors in `data/vector_store.json`.
- `faiss` is selectable as an adapter scaffold; ingestion/retrieval implementation is pending.
