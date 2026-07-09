# PrimeKG Migraine Demo Questions

Use these with `examples/primekg_migraine_graph_rag_workflow.json` after importing a filtered migraine PrimeKG subgraph.

## Primary Questions

1. What drugs are connected to migraine?
2. What biological mechanisms are connected to migraine?
3. Which phenotypes or symptoms are linked to migraine?
4. Show the graph evidence path for migraine treatment.

## Good Follow-Ups

1. Which genes or proteins appear in migraine treatment paths?
2. Which pathways connect migraine to candidate treatments?
3. Which graph relationships are most common in the migraine subgraph?
4. What is missing from the graph evidence for migraine?

## Expected Behavior

- If vector data exists in `primekg_migraine_demo`, hybrid retrieval combines vector context with PrimeKG graph paths.
- If the filtered PrimeKG migraine subgraph exists in Neo4j, graph evidence should include readable paths such as disease-to-gene/protein-to-drug or disease-to-mechanism paths.
- If Neo4j is offline, the retriever should return a clear Neo4j unavailable message instead of crashing.
- If the PrimeKG subgraph has not been imported, the retriever should fall back to the existing generic graph retrieval behavior or report that no PrimeKG paths were found.
- This demo is for biomedical research exploration, not medical advice.
