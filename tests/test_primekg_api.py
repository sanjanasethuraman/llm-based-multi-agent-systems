import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import backend.primekg_api as primekg_api
from backend.primekg_api import PrimeKGApiError


ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests" / "fixtures" / "primekg_fake_sample.csv"


class PrimeKGApiTests(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.primekg_dir = Path(self.tmpdir.name) / "primekg"
        self.preview_dir = self.primekg_dir / "previews"
        self.last_import_path = self.primekg_dir / "last_import_summary.json"
        self.primekg_dir.mkdir(parents=True, exist_ok=True)
        self.sample_csv = self.primekg_dir / "api_fake_sample.csv"
        shutil.copyfile(FIXTURE, self.sample_csv)
        self.patches = [
            patch.object(primekg_api, "PRIMEKG_DIR", self.primekg_dir),
            patch.object(primekg_api, "DEFAULT_CSV_PATH", self.primekg_dir / "kg.csv"),
            patch.object(primekg_api, "PREVIEW_DIR", self.preview_dir),
            patch.object(primekg_api, "LAST_IMPORT_PATH", self.last_import_path),
        ]
        for item in self.patches:
            item.start()

    def tearDown(self):
        for item in reversed(self.patches):
            item.stop()
        self.tmpdir.cleanup()

    def test_resolve_primekg_path_blocks_outside_paths(self):
        with self.assertRaises(PrimeKGApiError):
            primekg_api.resolve_primekg_path("tests/fixtures/primekg_fake_sample.csv", ".csv")

    def test_filter_preview_writes_bounded_project_local_output(self):
        preview = primekg_api.filter_preview({
            "csvPath": str(self.sample_csv),
            "disease": "Example Migraine",
            "depth": 2,
            "maxNodes": 10,
            "maxRelationships": 20,
        })

        self.assertTrue(preview["ok"])
        self.assertEqual(preview["nodeCount"], 4)
        self.assertEqual(preview["relationshipCount"], 3)
        self.assertTrue(Path(preview["outputPath"]).exists())
        self.assertTrue(str(Path(preview["outputPath"]).resolve()).startswith(str(self.primekg_dir.resolve())))

    def test_import_filtered_dry_run_returns_summary_and_updates_status(self):
        preview = primekg_api.filter_preview({
            "csvPath": str(self.sample_csv),
            "disease": "Example Migraine",
            "depth": 1,
            "maxNodes": 10,
            "maxRelationships": 20,
        })

        summary = primekg_api.import_filtered({
            "filteredPath": preview["outputPath"],
            "dryRun": True,
            "clearExistingPrimeKG": False,
        })
        status = primekg_api.primekg_status()

        self.assertEqual(summary["status"], "dry_run")
        self.assertEqual(summary["nodeCount"], 3)
        self.assertEqual(status["lastImportSummary"]["status"], "dry_run")

    def test_filter_preview_rejects_bad_filter_type(self):
        with self.assertRaises(PrimeKGApiError):
            primekg_api.filter_preview({
                "csvPath": str(self.sample_csv),
                "disease": "Example Migraine",
                "allowedNodeTypes": {"bad": "shape"},
            })

    def test_visual_graph_from_rows_returns_bounded_viewer_shape(self):
        graph = primekg_api.visual_graph_from_rows(
            rows=[
                {
                    "nodes": [
                        {"id": "DISEASE:fake-migraine", "name": "Example Migraine", "type": "disease"},
                        {"id": "DRUG:fake-cgrp", "name": "Fictional CGRP Blocker", "type": "drug"},
                    ],
                    "relationships": [
                        {
                            "id": "rel-1",
                            "source": "DISEASE:fake-migraine",
                            "target": "DRUG:fake-cgrp",
                            "displayRelation": "indication",
                        }
                    ],
                }
            ],
            disease="Example Migraine",
            depth=1,
            max_nodes=10,
            max_relationships=10,
            seeds=[{"id": "DISEASE:fake-migraine", "name": "Example Migraine", "type": "disease"}],
        )

        self.assertEqual(graph["status"], "available")
        self.assertEqual(graph["stats"]["nodeCount"], 2)
        self.assertEqual(graph["stats"]["relationshipCount"], 1)
        self.assertEqual(graph["nodes"][0]["type"], "disease")
        self.assertEqual(graph["relationships"][0]["label"], "indication")

    def test_search_diseases_returns_case_insensitive_suggestions_from_csv(self):
        result = primekg_api.search_diseases(query="mig", limit=20, csv_path=self.sample_csv)

        self.assertTrue(result["available"])
        self.assertEqual(result["query"], "mig")
        self.assertGreaterEqual(result["count"], 1)
        self.assertEqual(result["diseases"][0]["id"], "DISEASE:fake-migraine")
        self.assertEqual(result["diseases"][0]["node_type"], "disease")
        self.assertEqual(result["diseases"][0]["match"], "contains")
        self.assertNotIn("searchName", result["diseases"][0])

    def test_search_diseases_sorts_exact_before_prefix_and_contains(self):
        extra = self.primekg_dir / "diseases.csv"
        extra.write_text(
            "relation,display_relation,x_id,x_name,x_type,x_source,y_id,y_name,y_type,y_source\n"
            "rel,rel,D:1,Mig,disease,test,G:1,Gene,gene,test\n"
            "rel,rel,D:2,Migraine Aura,disease,test,G:1,Gene,gene,test\n"
            "rel,rel,D:3,Chronic Migraine,disease,test,G:1,Gene,gene,test\n",
            encoding="utf-8",
        )

        result = primekg_api.search_diseases(query="mig", limit=10, csv_path=extra)

        self.assertEqual([item["id"] for item in result["diseases"]], ["D:1", "D:2", "D:3"])
        self.assertEqual([item["match"] for item in result["diseases"]], ["exact", "prefix", "contains"])

    def test_search_diseases_enforces_limit_cap(self):
        result = primekg_api.search_diseases(query="example", limit=999, csv_path=self.sample_csv)

        self.assertTrue(result["available"])
        self.assertLessEqual(result["count"], 50)
        self.assertEqual(result["count"], 2)

    def test_search_diseases_missing_csv_returns_unavailable(self):
        result = primekg_api.search_diseases(query="mig", limit=20, csv_path=self.primekg_dir / "missing.csv")

        self.assertFalse(result["available"])
        self.assertEqual(result["count"], 0)
        self.assertEqual(result["diseases"], [])
        self.assertIn("kg.csv not found", result["message"])


if __name__ == "__main__":
    unittest.main()
