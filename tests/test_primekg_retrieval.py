import unittest

from backend.graph_rag import (
    format_primekg_path,
    normalize_primekg_allowed_types,
    primekg_result_from_path_rows,
)


class PrimeKGRetrievalTests(unittest.TestCase):
    def test_format_primekg_path_is_readable(self):
        nodes = [
            {"id": "DISEASE:1", "name": "Migraine", "type": "disease"},
            {"id": "GENE:1", "name": "CGRP", "type": "gene/protein"},
            {"id": "DRUG:1", "name": "Erenumab", "type": "drug"},
        ]
        relationships = [
            {"source": "GENE:1", "target": "DISEASE:1", "displayRelation": "associated_with"},
            {"source": "DRUG:1", "target": "GENE:1", "displayRelation": "targets"},
        ]

        text = format_primekg_path(nodes, relationships)

        self.assertEqual(text, "Migraine --associated_with--> CGRP --targets--> Erenumab")

    def test_primekg_result_shape_from_mocked_rows(self):
        rows = [
            {
                "nodes": [
                    {"id": "DISEASE:1", "prime_id": "DISEASE:1", "name": "Migraine", "type": "disease"},
                    {"id": "GENE:1", "prime_id": "GENE:1", "name": "CGRP", "type": "gene/protein"},
                    {"id": "DRUG:1", "prime_id": "DRUG:1", "name": "Erenumab", "type": "drug"},
                ],
                "relationships": [
                    {
                        "source": "DISEASE:1",
                        "sourceName": "Migraine",
                        "target": "GENE:1",
                        "targetName": "CGRP",
                        "relation": "associated_with",
                        "displayRelation": "associated_with",
                    },
                    {
                        "source": "GENE:1",
                        "sourceName": "CGRP",
                        "target": "DRUG:1",
                        "targetName": "Erenumab",
                        "relation": "targeted_by",
                        "displayRelation": "targeted_by",
                    },
                ],
                "score": 42,
                "length": 2,
            }
        ]
        seeds = [{"id": "DISEASE:1", "name": "Migraine", "type": "disease"}]

        result = primekg_result_from_path_rows(rows, seeds, "What drugs are connected to migraine?", ["migraine"], 5, 2)

        evidence = result["graphEvidence"]
        self.assertEqual(evidence["status"], "available")
        self.assertEqual(evidence["backend"], "neo4j-primekg")
        self.assertEqual(evidence["stats"]["pathCount"], 1)
        self.assertEqual(evidence["stats"]["entityCount"], 3)
        self.assertEqual(evidence["paths"][0]["path_text"], "Migraine --associated_with--> CGRP --targeted_by--> Erenumab")
        self.assertEqual(result["matches"][0]["metadata"]["source"], "neo4j-primekg")

    def test_allowed_type_aliases_preserve_disease_anchor(self):
        allowed = normalize_primekg_allowed_types(["mechanism", "treatment"])

        self.assertIn("disease", allowed)
        self.assertIn("biological_process", allowed)
        self.assertIn("drug", allowed)


if __name__ == "__main__":
    unittest.main()
