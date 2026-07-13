// PrimeKG full-import verification queries.
// Run in the Neo4j Browser or cypher-shell after `python -m backend.scripts.import_full_primekg`.

// 1. Total PrimeKG node count.
MATCH (n:PrimeNode) RETURN count(n) AS totalNodes;

// 2. Total PrimeKG relationship count.
MATCH (:PrimeNode)-[r:PRIME_REL]->(:PrimeNode) RETURN count(r) AS totalRelationships;

// 3. Node counts grouped by node type.
MATCH (n:PrimeNode)
RETURN n.node_type AS nodeType, count(*) AS nodes
ORDER BY nodes DESC;

// 4. Duplicate node identifiers (should return NO rows; prime_id is unique).
MATCH (n:PrimeNode)
WITH n.prime_id AS primeId, count(*) AS c
WHERE c > 1
RETURN primeId, c ORDER BY c DESC LIMIT 25;

// 5. Migraine-related nodes exist.
MATCH (n:PrimeNode)
WHERE toLower(n.name) CONTAINS 'migraine'
RETURN n.node_type AS type, n.name AS name LIMIT 25;

// 6. Autoimmune-related nodes exist (absent under a migraine-only slice; present after full import).
MATCH (n:PrimeNode)
WHERE toLower(n.name) CONTAINS 'autoimmune'
   OR toLower(n.name) CONTAINS 'rheumatoid arthritis'
   OR toLower(n.name) CONTAINS 'lupus'
RETURN n.node_type AS type, n.name AS name LIMIT 25;

// 7. Confirm the selected disease does not change total graph size.
//    Record these two counts, change the disease in the viewer, then re-run:
//    the totals must stay identical (the viewer is read-only).
MATCH (n:PrimeNode) WITH count(n) AS nodes
MATCH (:PrimeNode)-[r:PRIME_REL]->(:PrimeNode)
RETURN nodes, count(r) AS relationships;

// 8. Constraints / indexes present.
SHOW CONSTRAINTS YIELD name, labelsOrTypes, properties
  WHERE 'PrimeNode' IN labelsOrTypes RETURN name, properties;
