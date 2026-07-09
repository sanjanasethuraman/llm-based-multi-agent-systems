import json
import tempfile
import unittest
from pathlib import Path

from scripts.filter_primekg_subgraph import (
    DEFAULT_NODE_TYPES,
    PrimeKGFilterError,
    detect_columns,
    filter_subgraph,
    parse_allowed_types,
    write_json,
)


ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests" / "fixtures" / "primekg_fake_sample.csv"


class PrimeKGFilterTests(unittest.TestCase):
    def test_detect_columns_accepts_primekg_schema(self):
        columns = detect_columns([
            "relation",
            "display_relation",
            "x_id",
            "x_name",
            "x_type",
            "x_source",
            "y_id",
            "y_name",
            "y_type",
            "y_source",
        ])

        self.assertEqual(columns["relation"], "relation")
        self.assertEqual(columns["x_id"], "x_id")
        self.assertEqual(columns["y_type"], "y_type")

    def test_detect_columns_accepts_common_aliases(self):
        columns = detect_columns([
            "predicate",
            "source_id",
            "source_name",
            "source_type",
            "target_id",
            "target_name",
            "target_type",
        ])

        self.assertEqual(columns["relation"], "predicate")
        self.assertEqual(columns["x_id"], "source_id")
        self.assertEqual(columns["y_name"], "target_name")

    def test_detect_columns_reports_missing_required_columns(self):
        with self.assertRaises(PrimeKGFilterError):
            detect_columns(["relation", "x_id", "x_name"])

    def test_disease_filtering_produces_bounded_output_schema(self):
        result = filter_subgraph(
            input_path=FIXTURE,
            disease_query="Example Migraine",
            depth=2,
            max_nodes=10,
            max_relationships=20,
            allowed_types=set(DEFAULT_NODE_TYPES),
            allowed_relations=None,
        )

        self.assertTrue(result["ok"])
        self.assertEqual(result["diseaseQuery"], "Example Migraine")
        self.assertEqual(len(result["nodes"]), 4)
        self.assertEqual(len(result["relationships"]), 3)
        self.assertIn("metadata", result)
        self.assertIn("matchedDiseaseNodes", result)
        self.assertIn("statsByNodeType", result)
        self.assertIn("statsByRelationType", result)

    def test_output_json_round_trips(self):
        result = filter_subgraph(
            input_path=FIXTURE,
            disease_query="Example Migraine",
            depth=1,
            max_nodes=10,
            max_relationships=20,
            allowed_types=parse_allowed_types(["disease,drug,gene/protein"]),
            allowed_relations=None,
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            output = Path(tmpdir) / "filtered.json"
            write_json(result, output)
            loaded = json.loads(output.read_text(encoding="utf-8"))

        self.assertTrue(loaded["ok"])
        self.assertEqual(len(loaded["nodes"]), 3)
        self.assertEqual(len(loaded["relationships"]), 2)


if __name__ == "__main__":
    unittest.main()
