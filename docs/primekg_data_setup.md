# PrimeKG Dataset Setup

PrimeKG is optional. The app does not download it during startup, and Graph RAG demos continue to work with the curated biomedical seed data when PrimeKG is not present.

Expected local path:

```text
data/primekg/kg.csv
```

Official download URL from the PrimeKG README:

```text
https://dataverse.harvard.edu/api/access/datafile/6180620
```

## Windows PowerShell

From the repository root:

```powershell
New-Item -ItemType Directory -Force data\primekg
Invoke-WebRequest `
  -Uri "https://dataverse.harvard.edu/api/access/datafile/6180620" `
  -OutFile "data\primekg\kg.csv"
```

Verify:

```powershell
python scripts\check_primekg_data.py
```

## Git Bash / Linux / macOS

From the repository root:

```bash
mkdir -p data/primekg
curl -L "https://dataverse.harvard.edu/api/access/datafile/6180620" \
  -o data/primekg/kg.csv
```

If `curl` is unavailable:

```bash
mkdir -p data/primekg
wget -O data/primekg/kg.csv \
  "https://dataverse.harvard.edu/api/access/datafile/6180620"
```

Verify:

```bash
python scripts/check_primekg_data.py
```

## Python Fallback

Use this when shell download tools are unavailable:

```bash
python - <<'PY'
from pathlib import Path
from urllib.request import urlretrieve

url = "https://dataverse.harvard.edu/api/access/datafile/6180620"
target = Path("data/primekg/kg.csv")
target.parent.mkdir(parents=True, exist_ok=True)
urlretrieve(url, target)
print(f"Downloaded {target} ({target.stat().st_size} bytes)")
PY
```

On Windows `cmd.exe`, use:

```cmd
python -c "from pathlib import Path; from urllib.request import urlretrieve; target=Path('data/primekg/kg.csv'); target.parent.mkdir(parents=True, exist_ok=True); urlretrieve('https://dataverse.harvard.edu/api/access/datafile/6180620', target); print(f'Downloaded {target} ({target.stat().st_size} bytes)')"
```

## Notes

- Do not commit `kg.csv` or other downloaded PrimeKG files.
- `data/primekg/.gitignore` keeps large local data out of Git.
- The tiny CSV under `tests/fixtures/` is fake test data only. It is not real PrimeKG and should not be used for biomedical demos.
- Future PrimeKG import scripts should check for `data/primekg/kg.csv` first and print a setup hint instead of crashing when it is missing.

## Filter A Disease-Centered Subgraph

After placing the real dataset at `data/primekg/kg.csv`, create a bounded JSON subgraph for later Neo4j import work:

```bash
python scripts/filter_primekg_subgraph.py \
  --input data/primekg/kg.csv \
  --disease "migraine" \
  --depth 2 \
  --max-nodes 1000 \
  --max-relationships 3000 \
  --output data/primekg/filtered_migraine.json \
  --csv-output-dir data/primekg/filtered_migraine_csv
```

Windows PowerShell uses the same arguments with backticks for line continuation:

```powershell
python scripts\filter_primekg_subgraph.py `
  --input data\primekg\kg.csv `
  --disease "migraine" `
  --depth 2 `
  --max-nodes 1000 `
  --max-relationships 3000 `
  --output data\primekg\filtered_migraine.json `
  --csv-output-dir data\primekg\filtered_migraine_csv
```

Depth behavior:

- `--depth 1` includes direct neighbors of the matched disease node.
- `--depth 2` includes neighbors of those neighbors.
- `--depth 3` is allowed, but the script prints a warning because the result can grow quickly.

Useful filters:

```bash
python scripts/filter_primekg_subgraph.py \
  --input data/primekg/kg.csv \
  --disease "migraine" \
  --allowed-node-types disease,drug,gene/protein,pathway,phenotype \
  --allowed-relations indication,associated_with,participates_in \
  --output data/primekg/filtered_migraine.json
```

The script does not import into Neo4j. It only writes filtered JSON and optional CSV files.

## Import The Filtered Subgraph Into Neo4j

The import step only accepts the bounded JSON output from `filter_primekg_subgraph.py`. It does not import the full PrimeKG CSV.

Dry-run first:

```bash
python scripts/import_primekg_subgraph.py \
  --input data/primekg/filtered_migraine.json \
  --dry-run
```

Start Neo4j:

```bash
docker compose -f docker-compose.neo4j.yml up -d
```

Import:

```bash
python scripts/import_primekg_subgraph.py \
  --input data/primekg/filtered_migraine.json \
  --clear-primekg-subgraph false
```

The importer uses `:PrimeNode` and `:PRIME_REL`, so it does not overwrite the existing curated biomedical `:Entity` / `:Chunk` demo graph.

Useful Neo4j verification queries:

```cypher
MATCH (n:PrimeNode) RETURN count(n) AS prime_nodes;
MATCH ()-[r:PRIME_REL]->() RETURN count(r) AS prime_relationships;
MATCH (n:PrimeNode) RETURN n.node_type AS node_type, count(*) AS count ORDER BY count DESC;
MATCH (:PrimeNode {node_type: "disease"})-[r:PRIME_REL]-(:PrimeNode) RETURN r.display_relation AS relation, count(*) AS count ORDER BY count DESC LIMIT 20;
```

## Backend API Workflow

The API endpoints are optional and keep all file paths under `data/primekg`.

Check support:

```bash
curl http://127.0.0.1:8000/api/primekg/status
```

Preview and write a bounded filtered JSON file:

```bash
curl -X POST http://127.0.0.1:8000/api/primekg/filter-preview \
  -H "Content-Type: application/json" \
  -d '{"csvPath":"data/primekg/kg.csv","disease":"migraine","depth":2,"maxNodes":1000,"maxRelationships":3000,"allowedNodeTypes":[],"allowedRelationTypes":[]}'
```

Dry-run import the preview output:

```bash
curl -X POST http://127.0.0.1:8000/api/primekg/import-filtered \
  -H "Content-Type: application/json" \
  -d '{"filteredPath":"data/primekg/previews/filtered_migraine_123.json","dryRun":true,"clearExistingPrimeKG":false}'
```

Live import after Neo4j is running:

```bash
curl -X POST http://127.0.0.1:8000/api/primekg/import-filtered \
  -H "Content-Type: application/json" \
  -d '{"filteredPath":"data/primekg/previews/filtered_migraine_123.json","dryRun":false,"clearExistingPrimeKG":false}'
```
