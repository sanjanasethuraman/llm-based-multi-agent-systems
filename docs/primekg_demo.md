# PrimeKG Biomedical Graph RAG Demo

This demo shows a disease-centered Graph RAG workflow using only a filtered PrimeKG subgraph. It does not import full PrimeKG.

## Demo Files

- `examples/primekg_migraine_graph_rag_workflow.json`
- `examples/primekg_demo_questions.md`
- `docs/primekg_data_setup.md`

## Expected Demo Behavior

- With vector data available, the workflow can produce a hybrid answer that combines vector context and graph paths.
- With a filtered PrimeKG migraine subgraph imported into Neo4j, the Graph Evidence panel should show readable paths, graph entities, graph relationships, and graph stats.
- With missing data or offline services, the app should show a clear setup or unavailable message instead of failing.

## 1. Start Neo4j

```bash
docker compose -f docker-compose.neo4j.yml up -d
```

Neo4j Browser should be available at:

```text
http://127.0.0.1:7474
```

Default local credentials from `.env.example`:

```text
NEO4J_URI=bolt://127.0.0.1:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=visualmas
NEO4J_DATABASE=neo4j
GRAPH_RAG_ENABLED=true
```

## 2. Set Environment Variables

Use `.env.example` as the reference. In PowerShell:

```powershell
$env:GRAPH_RAG_ENABLED="true"
$env:NEO4J_URI="bolt://127.0.0.1:7687"
$env:NEO4J_USER="neo4j"
$env:NEO4J_PASSWORD="visualmas"
$env:NEO4J_DATABASE="neo4j"
```

In Git Bash, Linux, or macOS:

```bash
export GRAPH_RAG_ENABLED=true
export NEO4J_URI=bolt://127.0.0.1:7687
export NEO4J_USER=neo4j
export NEO4J_PASSWORD=visualmas
export NEO4J_DATABASE=neo4j
```

## 3. Download Or Place PrimeKG

The real PrimeKG CSV should be placed manually at:

```text
data/primekg/kg.csv
```

Download options are documented in:

```text
docs/primekg_data_setup.md
```

The app does not download PrimeKG during startup.

## 4. Filter The Migraine Subgraph

PowerShell:

```powershell
python scripts\filter_primekg_subgraph.py `
  --input data\primekg\kg.csv `
  --disease "migraine" `
  --depth 2 `
  --max-nodes 1000 `
  --max-relationships 3000 `
  --output data\primekg\filtered_migraine.json
```

Git Bash, Linux, or macOS:

```bash
python scripts/filter_primekg_subgraph.py \
  --input data/primekg/kg.csv \
  --disease "migraine" \
  --depth 2 \
  --max-nodes 1000 \
  --max-relationships 3000 \
  --output data/primekg/filtered_migraine.json
```

## 5. Import The Filtered Subgraph

Dry-run first:

```bash
python scripts/import_primekg_subgraph.py --input data/primekg/filtered_migraine.json --dry-run
```

Live import:

```bash
python scripts/import_primekg_subgraph.py --input data/primekg/filtered_migraine.json --clear-primekg-subgraph false
```

Verify in Neo4j Browser:

```cypher
MATCH (n:PrimeNode) RETURN count(n) AS prime_nodes;
MATCH ()-[r:PRIME_REL]->() RETURN count(r) AS prime_relationships;
MATCH (n:PrimeNode) RETURN n.node_type AS node_type, count(*) AS count ORDER BY count DESC;
```

## 6. Start Backend

```bash
python -m backend.server
```

If the backend selects a port other than `8000`, use the printed URL for API checks and frontend configuration.

## 7. Start Frontend

For the backend-served build:

```bash
npm install
npm run build
python -m backend.server
```

Then open the backend URL in a browser.

For Vite development in another terminal:

```bash
npm run dev
```

If the backend is not on port `8000`, set `VISUAL_MAS_API_TARGET` to the backend URL before starting Vite.

## 8. Run The Demo Workflow

1. Open the app.
2. Load `PrimeKG Migraine Graph RAG` from the examples menu.
3. Confirm the retriever uses `hybrid` mode, `graphDisease` is `migraine`, and `graphHops` is `2`.
4. Run the workflow.
5. Open the Graph Evidence section and look for readable PrimeKG paths.
6. Try questions from `examples/primekg_demo_questions.md`.

Recommended first question:

```text
What drugs are connected to migraine?
```

## Troubleshooting

### Neo4j Offline

Run:

```bash
docker compose -f docker-compose.neo4j.yml up -d
```

Then check:

```bash
curl http://127.0.0.1:8000/api/graph-rag/status
curl http://127.0.0.1:8000/api/primekg/status
```

### `kg.csv` Missing

Place the real dataset at:

```text
data/primekg/kg.csv
```

Then run:

```bash
python scripts/check_primekg_data.py
```

### No Disease Match

Try a simpler disease string:

```bash
python scripts/filter_primekg_subgraph.py --input data/primekg/kg.csv --disease "migraine" --output data/primekg/filtered_migraine.json
```

If the script prints suggestions, use one of the suggested disease names.

### Graph Retrieval Returns No Paths

Check that filtered PrimeKG data was imported:

```cypher
MATCH (n:PrimeNode) RETURN count(n);
MATCH ()-[r:PRIME_REL]->() RETURN count(r);
MATCH (n:PrimeNode) WHERE toLower(n.name) CONTAINS "migraine" RETURN n LIMIT 10;
```

Also confirm the retriever config includes:

```json
{
  "retrievalMode": "graph",
  "graphDisease": "migraine",
  "graphHops": 2
}
```

or uses `hybrid` instead of `graph`.

### Too Many Nodes Or Relationships

Lower the caps or depth:

```bash
python scripts/filter_primekg_subgraph.py \
  --input data/primekg/kg.csv \
  --disease "migraine" \
  --depth 1 \
  --max-nodes 500 \
  --max-relationships 1500 \
  --output data/primekg/filtered_migraine_small.json
```

Depth `2` is the best default for a polished demo. Depth `3` can become too broad.
