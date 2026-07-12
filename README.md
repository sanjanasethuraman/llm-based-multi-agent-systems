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
- Run Neo4j-backed Graph RAG retrieval modes: vector, graph, and hybrid.
- Seed a curated biomedical knowledge graph demo with diseases, drugs, genes, pathways, trials, publications, and evidence chunks.
- Run agents through live Ollama or Hugging Face providers.
- Surface Ollama availability from the configured local provider URL.
- Load example workflows for demos and evaluation.

## Project Layout

- `backend/` contains the standard-library Python server, workflow runner, SQLite helpers, and RAG helpers.
    - `agents/` contains live agent providers (Ollama, Hugging Face, ...)
    - `nodes/` contains node executors (for all node types)
    - `tools/` tool implementations
    - `vector_db/` optional vector DB connectors / adapters
- `frontend/` contains the Vite/React app.
- `examples/` contains presentation/demo workflows.
- `docker-compose.neo4j.yml` starts the optional Neo4j backend for Graph RAG.
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

For live local LLM output or Ollama embeddings, start Ollama and pull the models used by the workflows:

```bash
ollama pull llama3.2:1b
ollama pull nomic-embed-text
```

If Ollama embeddings are unavailable, ingestion uses a local fallback embedding index so retrieval can still run without an external embedding service.

## Optional Neo4j Graph RAG Support

Graph RAG uses Neo4j as an actual property graph backend. The default app settings expect:

```bash
GRAPH_RAG_ENABLED=true
NEO4J_URI=bolt://127.0.0.1:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=visualmas
NEO4J_DATABASE=neo4j
```

Copy `.env.example` as a reference if you want to export these values manually. Neo4j is optional: the app, vector RAG, local JSON fallback, and normal workflow execution still run when `GRAPH_RAG_ENABLED=false` or when Neo4j is offline.

Start Neo4j with Docker:

```bash
docker compose -f docker-compose.neo4j.yml up -d
```

Then start the app and use the `Documents / RAG Ingestion` panel:

1. Check `Neo4j Graph RAG` status.
2. Click `Seed Biomedical KG`.
3. Load the `Biomedical Graph RAG` example workflow.
4. Run it with the retriever in `Graph` or `Hybrid` mode.

Retriever nodes support:

- `vector`: current vector RAG retrieval.
- `graph`: Neo4j entity/relationship traversal only.
- `hybrid`: vector retrieval plus Neo4j graph evidence.

Open Neo4j Browser at `http://127.0.0.1:7474` and log in with `neo4j` / `visualmas` to inspect the generated graph.

## Optional PrimeKG Dataset Setup

PrimeKG is not downloaded or imported during normal app startup. If you want to prepare the real dataset for future filtered biomedical subgraph work, manually place the official `kg.csv` at:

```text
data/primekg/kg.csv
```

See `docs/primekg_data_setup.md` for Windows PowerShell, Git Bash/Linux/macOS, and Python download options. Large PrimeKG files under `data/primekg/` are ignored by Git.

### Recommended: full PrimeKG import (Graph-RAG searches the complete graph)

Architecture: **Neo4j holds the complete PrimeKG dataset**; Graph-RAG and entity detection search all of it, and **disease selection is a read-only, bounded visualization query** — it never imports or mutates data.

```text
kg.csv  ── streamed, batched, idempotent ─▶  Neo4j (:PrimeNode / :PRIME_REL)   ← Graph-RAG searches all of this
selected disease  ── read-only bounded traversal ─▶  local subgraph for the viewer only
```

Run the one-time full import (streams the CSV in batches; memory stays bounded to one batch; safe to re-run because it uses `MERGE`):

```bash
docker compose -f docker-compose.neo4j.yml up -d
python -m backend.scripts.import_full_primekg                 # full import
python -m backend.scripts.import_full_primekg --batch-size 10000
python -m backend.scripts.import_full_primekg --status        # print progress/summary JSON
```

- **Environment variables:** `NEO4J_URI`, `NEO4J_USER`, `NEO4J_PASSWORD`, `NEO4J_DATABASE` (connection); `PRIMEKG_IMPORT_BATCH_SIZE` (default `5000`); `PRIMEKG_IMPORT_PROGRESS_EVERY` (default `20` batches).
- **Monitor progress:** watch the console, run `--status`, or read `data/primekg/full_import_status.json` (tracks source file + fingerprint, started/completed times, rows/nodes/relationships processed, created-vs-matched, skipped rows, current batch, constraints created, errors). Graph-RAG is only considered "complete" once `status == "completed"` (surfaced as `datasetComplete` in `/api/primekg/status`).
- **Restart safely after a failure:** `python -m backend.scripts.import_full_primekg --resume` (skips rows already recorded in the status file; `MERGE` makes re-processing harmless anyway).
- **Migrate an old partial disease-slice database:** replace only the PrimeKG data, leaving unrelated Neo4j data intact:

  ```bash
  python -m backend.scripts.import_full_primekg --replace-primekg
  ```

  The full import re-keys nodes by PrimeKG **node index** (`prime_id`), so use `--replace-primekg` once when migrating from the older ontology-id-keyed slices.
- **Verify the full dataset is loaded** with the Cypher queries in `docs/primekg_verification.cypher` (total node/relationship counts, counts by node type, duplicate-id check, presence of migraine- and autoimmune-related nodes, and confirmation that changing the selected disease does not change total counts).
- **Resource notes (measured on this repo's data; totals unknown/unmeasured here):** `kg.csv` is ~982 MB; a 5,000-row sample streamed to ~5,564 unique nodes with 0 skipped rows. Full PrimeKG is ~8M relationships, so a complete import is long-running and disk-/CPU-bound on Neo4j — measure wall-clock and DB size in your environment rather than assuming.

Disease-specific visualization now uses the read-only `POST /api/primekg/graph` endpoint (bounded depth/node/relationship limits; returns `readOnly: true` and `datasetComplete`). Selecting a disease queries the already-imported full graph and never writes.

### KG answer hardening (evidence-grounded, relation-aware)

On the full graph, retrieval is grounded by a centralized semantics layer so it
fails safely instead of manufacturing answers:

- **Relation semantics registry** ([backend/kg_semantics.py](backend/kg_semantics.py)) — every PrimeKG relation has a category, polarity, and which claim types it supports. `contraindication` can never be presented as `indication`; ontology `parent-child` edges never become therapeutic claims. All relations in the imported graph are mapped.
- **Intent classification** — questions are classified (treatment / contraindication / association / drug-target / phenotype / …) before retrieval; prevalence and causal questions are marked **unsupported** because PrimeKG has no relation for them.
- **Structured entity resolution** ([backend/kg_entity_resolution.py](backend/kg_entity_resolution.py)) — tiered exact → alias → token-boundary → controlled-fuzzy matching replaces substring matching, so `the` no longer matches `thecoma`; ambiguous mentions are reported, not guessed.
- **Alias layer** ([backend/kg_aliases.py](backend/kg_aliases.py) + [data/primekg/kg_aliases.json](data/primekg/kg_aliases.json)) — extensible, versioned, provenance-tracked (CGRP→CALCA, HER2→ERBB2, PD-1→PDCD1, …). Coverage is not claimed complete; unresolved abbreviations are reported.
- **Component-based ranking + evidence gate** ([backend/kg_evidence.py](backend/kg_evidence.py)) — explicit score components, semantic dedup, per-anchor/relation/target caps, ontology/generic/hub penalties, and a structured status (`supported` / `partially_supported` / `insufficient_evidence` / `ambiguous_entity` / `unsupported_intent` / `conflicting_evidence`) that the answer prompt must obey.

Run the full-graph evaluation harness (fixed corpus + random disease sampling, invariant checks, saved report):

```bash
python -m backend.scripts.eval_kg_pipeline                 # fixed corpus
python -m backend.scripts.eval_kg_pipeline --sample 25     # + random diseases
# report -> data/primekg/kg_eval_report.json
```

Run the KG unit/invariant tests:

```bash
python -m pytest tests/test_kg_pipeline.py tests/test_primekg_retrieval.py -q
```

### Legacy: small disease-centered slice (does mutate Neo4j)

The older `filter → import` path imports only a capped disease slice and is kept for offline experiments. Prefer the full import above for Graph-RAG. To create a small disease-centered file for import experiments without touching Neo4j:

```bash
python scripts/filter_primekg_subgraph.py --input data/primekg/kg.csv --disease "migraine" --depth 2 --max-nodes 1000 --max-relationships 3000 --output data/primekg/filtered_migraine.json
```

Dry-run and import only that filtered file:

```bash
python scripts/import_primekg_subgraph.py --input data/primekg/filtered_migraine.json --dry-run
docker compose -f docker-compose.neo4j.yml up -d
python scripts/import_primekg_subgraph.py --input data/primekg/filtered_migraine.json --clear-primekg-subgraph false
```

The backend also exposes optional PrimeKG workflow APIs for future frontend controls:

```bash
curl http://127.0.0.1:8000/api/primekg/status
curl -X POST http://127.0.0.1:8000/api/primekg/filter-preview -H "Content-Type: application/json" -d "{\"csvPath\":\"data/primekg/kg.csv\",\"disease\":\"migraine\",\"depth\":2,\"maxNodes\":1000,\"maxRelationships\":3000}"
curl -X POST http://127.0.0.1:8000/api/primekg/import-filtered -H "Content-Type: application/json" -d "{\"filteredPath\":\"data/primekg/previews/filtered_migraine.json\",\"dryRun\":true,\"clearExistingPrimeKG\":false}"
```

For a polished end-to-end demo, use `examples/primekg_migraine_graph_rag_workflow.json` and follow `docs/primekg_demo.md`.

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
