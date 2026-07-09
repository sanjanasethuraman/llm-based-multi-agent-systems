import json
import tempfile
import unittest
from pathlib import Path

from backend.primekg_import import build_primekg_import_payload, import_filtered_primekg_subgraph


class PrimeKGImportMappingTests(unittest.TestCase):
    def sample_payload(self):
        return {
            "ok": True,
            "metadata": {"input": "tests/fixtures/primekg_fake_sample.csv"},
            "diseaseQuery": "Example Migraine",
            "matchedDiseaseNodes": [{"id": "DISEASE:fake-migraine", "name": "Example Migraine"}],
            "nodes": [
                {
                    "id": "DISEASE:fake-migraine",
                    "name": "Example Migraine",
                    "type": "disease",
                    "source": "fake-test-only",
                },
                {
                    "id": "GENE:fake-cgrp",
                    "name": "CALCA Example Gene",
                    "type": "gene/protein",
                    "source": "fake-test-only",
                },
            ],
            "relationships": [
                {
                    "id": "DISEASE:fake-migraine|associated_with|GENE:fake-cgrp",
                    "source": "DISEASE:fake-migraine",
                    "target": "GENE:fake-cgrp",
                    "relation": "associated_with",
                    "displayRelation": "associated with",
                    "depth": 1,
                }
            ],
        }

    def test_build_primekg_import_payload_maps_nodes_and_relationships(self):
        payload = build_primekg_import_payload(self.sample_payload(), input_path="filtered.json")

        self.assertEqual(len(payload["nodes"]), 2)
        self.assertEqual(len(payload["relationships"]), 1)
        self.assertEqual(payload["nodes"][0]["prime_id"], "DISEASE:fake-migraine")
        self.assertEqual(payload["nodes"][0]["node_type"], "disease")
        self.assertEqual(payload["nodes"][0]["disease_context"], "Example Migraine")
        self.assertEqual(payload["relationships"][0]["relation"], "associated_with")
        self.assertEqual(payload["relationships"][0]["display_relation"], "associated with")
        self.assertEqual(payload["relationships"][0]["source_id"], "DISEASE:fake-migraine")
        self.assertEqual(payload["relationships"][0]["target_id"], "GENE:fake-cgrp")
        self.assertEqual(payload["skippedNodes"], [])
        self.assertEqual(payload["skippedRelationships"], [])

    def test_invalid_relationship_is_skipped(self):
        sample = self.sample_payload()
        sample["relationships"].append({
            "source": "DISEASE:fake-migraine",
            "target": "MISSING:NODE",
            "relation": "bad_edge",
        })

        payload = build_primekg_import_payload(sample)

        self.assertEqual(len(payload["relationships"]), 1)
        self.assertEqual(len(payload["skippedRelationships"]), 1)
        self.assertEqual(payload["skippedRelationships"][0]["reason"], "source or target node missing from filtered nodes")

    def test_dry_run_does_not_require_neo4j(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "filtered.json"
            path.write_text(json.dumps(self.sample_payload()), encoding="utf-8")

            summary = import_filtered_primekg_subgraph(path, dry_run=True)

        self.assertEqual(summary["status"], "dry_run")
        self.assertEqual(summary["nodeCount"], 2)
        self.assertEqual(summary["relationshipCount"], 1)
        self.assertEqual(summary["nodesImported"], 0)


if __name__ == "__main__":
    unittest.main()
