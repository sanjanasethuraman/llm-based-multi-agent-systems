import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from backend import primekg_import
from backend.graph_rag import (
    compute_primekg_concept_coverage,
    diversify_primekg_seeds,
)

CSV_HEADER = "relation,display_relation,x_index,x_id,x_type,x_name,x_source,y_index,y_id,y_type,y_name,y_source"
CSV_ROWS = [
    "associated,associated with,0,101,disease,migraine,MONDO,1,201,gene/protein,CGRP,NCBI",
    "target,targets,1,201,gene/protein,CGRP,NCBI,2,301,drug,erenumab,DrugBank",
    "associated,associated with,0,101,disease,migraine,MONDO,1,201,gene/protein,CGRP,NCBI",  # duplicate row
    "associated,associated with,3,401,disease,rheumatoid arthritis,MONDO,4,501,gene/protein,TNF,NCBI",
]


class FakeCounters(SimpleNamespace):
    pass


class FakeResult:
    def __init__(self, nodes_created=0, relationships_created=0, rows=None):
        self._counters = FakeCounters(nodes_created=nodes_created, relationships_created=relationships_created)
        self._rows = rows or []

    def consume(self):
        return SimpleNamespace(counters=self._counters)

    def single(self):
        return self._rows[0] if self._rows else None


class FakeTx:
    def __init__(self, store):
        self.store = store

    def run(self, query, **params):
        if "nodes" in params:
            created = 0
            for node in params["nodes"]:
                if node["prime_id"] not in self.store["nodes"]:
                    created += 1
                self.store["nodes"][node["prime_id"]] = dict(node)
            return FakeResult(nodes_created=created)
        if "relationships" in params:
            created = 0
            for rel in params["relationships"]:
                if rel["source_id"] not in self.store["nodes"] or rel["target_id"] not in self.store["nodes"]:
                    continue
                if rel["prime_key"] not in self.store["rels"]:
                    created += 1
                self.store["rels"][rel["prime_key"]] = dict(rel)
            return FakeResult(relationships_created=created)
        if "MATCH ()-[r:PRIME_REL]-()" in query:
            limit = int(params.get("limit") or 1000)
            keys = list(self.store["rels"].keys())[:limit]
            for key in keys:
                self.store["rels"].pop(key, None)
            return FakeResult(rows=[{"deleted": len(keys)}])
        if "MATCH (n:PrimeNode)" in query and "DELETE n" in query:
            limit = int(params.get("limit") or 1000)
            keys = list(self.store["nodes"].keys())[:limit]
            for key in keys:
                self.store["nodes"].pop(key, None)
            return FakeResult(rows=[{"deleted": len(keys)}])
        if "DETACH DELETE" in query:
            raise AssertionError("PrimeKG clear must be batched, not DETACH DELETE all-at-once")
        return FakeResult()


class FakeSession:
    """Minimal Neo4j session emulating MERGE/dedupe semantics for :PrimeNode."""

    def __init__(self):
        self.store = {"nodes": {}, "rels": {}, "other": {"App:1": {"label": "unrelated"}}}
        self.schema_calls = 0

    def run(self, query, **params):  # ensure_primekg_schema uses direct run()
        self.schema_calls += 1
        return FakeResult()

    def execute_write(self, fn, *args):
        return fn(FakeTx(self.store), *args)


class FailingRelationshipSession(FakeSession):
    def execute_write(self, fn, *args):
        if fn is primekg_import._merge_full_relationships_tx:
            raise RuntimeError("transaction memory exceeded")
        return super().execute_write(fn, *args)


def _write_csv(tmpdir, rows=CSV_ROWS):
    path = Path(tmpdir) / "kg.csv"
    path.write_text("\n".join([CSV_HEADER, *rows]) + "\n", encoding="utf-8")
    return path


class FullImportTests(unittest.TestCase):
    def test_batched_import_dedupes_nodes_and_relationships(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            csv_path = _write_csv(tmpdir)
            status_path = Path(tmpdir) / "status.json"
            session = FakeSession()
            summary = primekg_import.import_full_primekg(
                csv_path=csv_path, batch_size=2, session=session, status_path=status_path,
            )
            self.assertTrue(status_path.exists())
        self.assertEqual(summary["status"], "completed")
        self.assertEqual(len(session.store["nodes"]), 5)   # 5 unique nodes
        self.assertEqual(len(session.store["rels"]), 3)    # duplicate row collapses
        self.assertEqual(summary["nodesCreated"], 5)
        self.assertEqual(summary["relationshipsCreated"], 3)
        self.assertTrue(summary["constraintsCreated"])

    def test_import_is_idempotent_on_rerun(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            csv_path = _write_csv(tmpdir)
            status_path = Path(tmpdir) / "status.json"
            session = FakeSession()
            primekg_import.import_full_primekg(csv_path=csv_path, batch_size=10, session=session, status_path=status_path)
            second = primekg_import.import_full_primekg(csv_path=csv_path, batch_size=10, session=session, status_path=status_path)
        self.assertEqual(len(session.store["nodes"]), 5)
        self.assertEqual(len(session.store["rels"]), 3)
        self.assertEqual(second["nodesCreated"], 0)         # nothing new on rerun
        self.assertEqual(second["relationshipsCreated"], 0)

    def test_node_ids_are_unique_and_index_keyed(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            csv_path = _write_csv(tmpdir)
            session = FakeSession()
            primekg_import.import_full_primekg(
                csv_path=csv_path, batch_size=10, session=session, status_path=Path(tmpdir) / "s.json",
            )
        self.assertEqual(sorted(session.store["nodes"].keys()), ["0", "1", "2", "3", "4"])
        self.assertEqual(session.store["nodes"]["0"]["name"], "migraine")

    def test_replace_primekg_keeps_unrelated_data(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            csv_path = _write_csv(tmpdir)
            session = FakeSession()
            primekg_import.import_full_primekg(
                csv_path=csv_path, batch_size=10, replace_primekg=True, session=session,
                status_path=Path(tmpdir) / "s.json",
            )
        self.assertIn("App:1", session.store["other"])       # non-PrimeKG data untouched
        self.assertEqual(len(session.store["nodes"]), 5)

    def test_resume_skips_already_processed_rows(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            csv_path = _write_csv(tmpdir)
            status_path = Path(tmpdir) / "status.json"
            status_path.write_text(json.dumps({"status": "failed", "rowsProcessed": 2}), encoding="utf-8")
            session = FakeSession()
            summary = primekg_import.import_full_primekg(
                csv_path=csv_path, batch_size=10, resume=True, session=session, status_path=status_path,
            )
        # First 2 rows skipped -> node "2" (erenumab, from row 2) is absent.
        self.assertNotIn("2", session.store["nodes"])
        self.assertEqual(summary["resumedFromRow"], 2)

    def test_failed_batch_does_not_mark_rows_processed_for_resume(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            csv_path = _write_csv(tmpdir)
            status_path = Path(tmpdir) / "status.json"
            session = FailingRelationshipSession()
            with self.assertRaises(primekg_import.PrimeKGImportError):
                primekg_import.import_full_primekg(
                    csv_path=csv_path, batch_size=2, session=session, status_path=status_path,
                )
            status = json.loads(status_path.read_text(encoding="utf-8"))
        self.assertEqual(status["status"], "failed")
        self.assertEqual(status["rowsProcessed"], 0)
        self.assertIn("transaction memory exceeded", status["errors"][0])


class CoverageTests(unittest.TestCase):
    def test_unmatched_concept_is_reported(self):
        entities = [{"name": "migraine"}, {"name": "CGRP"}, {"name": "erenumab"}]
        paths = [{"nodes": [{"name": "migraine"}, {"name": "CGRP"}]}]
        coverage = compute_primekg_concept_coverage(
            "which drugs connect migraine through cgrp? also autoimmune diseases",
            "migraine",
            entities,
            paths,
        )
        self.assertIn("migraine", coverage["matchedConcepts"])
        self.assertIn("autoimmune", coverage["unmatchedConcepts"])
        self.assertFalse(coverage["fullyGrounded"])
        self.assertTrue(coverage["partiallyGrounded"])

    def test_seed_diversification_covers_multiple_concepts(self):
        candidates = [
            {"id": "a1", "name": "migraine a", "matchedTerm": "migraine", "score": 0.9},
            {"id": "a2", "name": "migraine b", "matchedTerm": "migraine", "score": 0.8},
            {"id": "a3", "name": "migraine c", "matchedTerm": "migraine", "score": 0.7},
            {"id": "b1", "name": "rheumatoid arthritis", "matchedTerm": "autoimmune", "score": 0.6},
        ]
        seeds = diversify_primekg_seeds(candidates, limit=2)
        terms = {seed["matchedTerm"] for seed in seeds}
        self.assertEqual(terms, {"migraine", "autoimmune"})  # both concepts represented


if __name__ == "__main__":
    unittest.main()
