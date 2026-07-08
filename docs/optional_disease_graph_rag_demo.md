# Optional-Disease PrimeKG Graph RAG Demo

This demo shows the split between Explore Mode and Ask Mode.

- Explore Mode: select a disease to preview, import, and inspect a disease-centered graph.
- Ask Mode: ask a natural-language question without selecting a disease first. Graph RAG auto-detects imported PrimeKG entities and returns bounded evidence paths.

Full PrimeKG is never imported. The app uses only filtered subgraphs.

## Setup

Start Neo4j:

```bash
docker compose -f docker-compose.neo4j.yml up -d
```

Use the local Neo4j settings from `.env.example`:

```powershell
$env:GRAPH_RAG_ENABLED="true"
$env:NEO4J_URI="bolt://127.0.0.1:7687"
$env:NEO4J_USER="neo4j"
$env:NEO4J_PASSWORD="visualmas"
$env:NEO4J_DATABASE="neo4j"
```

Place the real PrimeKG CSV here:

```text
data/primekg/kg.csv
```

Filter and import a migraine subgraph:

```powershell
python scripts/filter_primekg_subgraph.py `
  --input data/primekg/kg.csv `
  --disease "migraine" `
  --depth 2 `
  --max-nodes 1000 `
  --max-relationships 3000 `
  --output data/primekg/filtered_migraine.json

python scripts/import_primekg_subgraph.py `
  --input data/primekg/filtered_migraine.json `
  --clear-primekg-subgraph false
```

Start the app:

```powershell
npm.cmd install
npm.cmd run build
python -m backend.server
```

Open the URL printed by the backend, usually:

```text
http://127.0.0.1:8000
```

## Demo A: Ask Without Selecting Disease

Goal: prove disease selection is optional for answering.

1. Load a workflow with a retriever node.
2. Set the retriever `retrievalMode` to `graph` or `hybrid`.
3. Ask:

```text
What drugs are connected to migraine?
```

Expected result:

- The answer can run without requiring the Explore Disease selector.
- The Graph Evidence Routes panel shows detected entity `Migraine`.
- Route cards show readable paths, scores, reasons, and stats.
- The LLM context contains a bounded `Graph evidence paths:` section, not raw graph JSON.
- If the path is not in the currently visible graph, click `Load answer graph`.

## Demo B: Explore Selected Disease

Goal: prove Explore Mode still controls the graph viewer.

1. In Biomedical Knowledge Graph, choose `Migraine` under `Explore disease`.
2. Click `Preview Subgraph`.
3. Click `Import Filtered Subgraph` if needed.
4. Click `Load In-App Graph`.
5. Switch between 2D Focus Mode and 3D Explore Mode.
6. Select the disease node and inspect neighbors, relationships, and type filters.

Expected result:

- The graph viewer loads a migraine-centered bounded graph.
- The selected disease controls visual graph focus only.
- Ask Mode can still auto-detect entities from questions independently.

## Demo C: Hybrid Retrieval Fallback

Goal: prove Neo4j is optional and vector retrieval still works.

1. Stop Neo4j:

```bash
docker compose -f docker-compose.neo4j.yml down
```

2. Keep a workflow retriever in `hybrid` mode.
3. Ask:

```text
What drugs are connected to migraine?
```

Expected result:

- Vector retrieval still returns results if vector data is available.
- Graph evidence shows an unavailable/offline message.
- The app does not crash.
- Neo4j setup hints remain visible.

Restart Neo4j when finished:

```bash
docker compose -f docker-compose.neo4j.yml up -d
```

## Useful Verification Commands

Check Graph RAG status:

```powershell
Invoke-WebRequest http://127.0.0.1:8000/api/graph-rag/status -UseBasicParsing
```

Check PrimeKG status:

```powershell
Invoke-WebRequest http://127.0.0.1:8000/api/primekg/status -UseBasicParsing
```

Verify imported PrimeKG counts in Neo4j Browser:

```cypher
MATCH (n:PrimeNode) RETURN count(n) AS nodes;
MATCH ()-[r:PRIME_REL]->() RETURN count(r) AS relationships;
```

## Troubleshooting

- `kg.csv missing`: place the real PrimeKG file at `data/primekg/kg.csv`.
- `Neo4j offline`: start Neo4j and confirm `/api/graph-rag/status` reports connected.
- `No entity detected`: import a subgraph for the disease/entity in the question, or use Explore disease as a hint.
- `No paths found`: increase filter depth to 2, import more relationships, or ask a question closer to the imported subgraph.
- `Path outside current visual focus`: click `Load answer graph` to load a bounded graph around answer evidence.
