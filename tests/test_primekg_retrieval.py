import unittest
from unittest.mock import patch

from backend.graph_rag import (
    detect_primekg_query_entities,
    format_primekg_path,
    normalize_primekg_allowed_types,
    primekg_detection_concepts,
    primekg_detection_terms,
    rank_primekg_detected_entities,
    primekg_result_from_path_rows,
    retrieve_primekg_paths_for_question,
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

    def test_detect_entities_uses_selected_disease_hint_first(self):
        with patched_primekg_driver() as session:
            result = detect_primekg_query_entities(
                "What drugs are connected?",
                selected_disease="migraine",
                checked_status={"enabled": True, "connected": True},
            )

        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["detectedEntities"][0]["id"], "DISEASE:1")
        self.assertEqual(result["detectedEntities"][0]["matchType"], "hint")
        self.assertLessEqual(len(result["detectedEntities"]), 10)
        self.assertGreaterEqual(session.run_count, 2)

    def test_selected_disease_hint_does_not_pollute_explicit_question(self):
        rows = [
            {"id": "D:migraine", "name": "migraine disorder", "node_type": "disease", "source": "test"},
            {"id": "D:aids", "name": "AIDS", "node_type": "disease", "source": "test"},
        ]
        with patched_primekg_driver(rows_by_kind={"detect": rows}):
            result = detect_primekg_query_entities(
                "What drugs are connected to AIDS?",
                selected_disease="migraine",
                checked_status={"enabled": True, "connected": True},
            )

        concepts = {concept["id"] for concept in result["concepts"]}
        names = {entity["name"] for entity in result["detectedEntities"]}
        self.assertIn("aids", concepts)
        self.assertNotIn("migraine", concepts)
        self.assertEqual(names, {"AIDS"})

    def test_detect_entities_finds_disease_from_question_case_insensitive(self):
        with patched_primekg_driver():
            result = detect_primekg_query_entities(
                "Which treatments are connected to MIGRAINE?",
                checked_status={"enabled": True, "connected": True},
            )

        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["detectedEntities"][0]["name"], "Migraine")
        self.assertEqual(result["detectedEntities"][0]["node_type"], "disease")

    def test_detect_entities_returns_empty_when_no_match(self):
        with patched_primekg_driver(rows_by_kind={"detect": []}):
            result = detect_primekg_query_entities(
                "What drugs are connected to unknown condition?",
                checked_status={"enabled": True, "connected": True},
            )

        self.assertEqual(result["status"], "empty")
        self.assertEqual(result["detectedEntities"], [])
        self.assertIn("No PrimeKG nodes matched", result["message"])

    def test_detect_entities_returns_unavailable_when_neo4j_offline(self):
        result = detect_primekg_query_entities(
            "What drugs are connected to migraine?",
            checked_status={"enabled": True, "connected": False, "message": "offline"},
        )

        self.assertEqual(result["status"], "unavailable")
        self.assertEqual(result["detectedEntities"], [])
        self.assertIn("offline", result["message"])

    def test_detect_entities_enforces_limit(self):
        rows = [
            {"id": f"D:{index}", "name": f"Migraine {index}", "node_type": "disease", "source": "test"}
            for index in range(80)
        ]
        with patched_primekg_driver(rows_by_kind={"detect": rows}):
            result = detect_primekg_query_entities(
                "migraine",
                limit=999,
                checked_status={"enabled": True, "connected": True},
            )

        self.assertEqual(result["status"], "ok")
        self.assertLessEqual(len(result["detectedEntities"]), 50)

    def test_compound_disease_query_prefers_specific_anchors(self):
        query = "Which drugs are connected to migraine disorder? Which drugs are connected to autoimmune disease?"
        terms = primekg_detection_terms(query)
        self.assertIn("migraine disorder", terms)
        self.assertIn("autoimmune disease", terms)
        self.assertNotIn("disorder", terms)

        rows = [
            {"id": "D:mental", "name": "mental disorder", "node_type": "disease", "source": "test"},
            {"id": "D:migraine", "name": "migraine disorder", "node_type": "disease", "source": "test"},
            {"id": "D:autoimmune", "name": "autoimmune disease", "node_type": "disease", "source": "test"},
        ]
        ranked = rank_primekg_detected_entities(rows, terms, limit=2)
        self.assertEqual({item["name"] for item in ranked}, {"migraine disorder", "autoimmune disease"})

    def test_detection_terms_strip_question_punctuation(self):
        terms = primekg_detection_terms("What drugs are connected to AIDS?")

        self.assertIn("aids", terms)
        self.assertNotIn("aids?", terms)

    def test_compound_query_detection_keeps_independent_concepts(self):
        query = "Which CGRP treatments have contraindications, and what are common autoimmune diseases?"
        concepts = primekg_detection_concepts(query)
        concept_ids = {concept["id"] for concept in concepts}
        self.assertIn("cgrp", concept_ids)
        self.assertIn("autoimmune diseases", concept_ids)

        crowded_rows = [
            {"id": f"D:autoimmune:{index}", "name": f"autoimmune disease {index}", "node_type": "disease", "source": "test"}
            for index in range(20)
        ] + [
            {"id": "G:CALCA", "name": "CALCA", "node_type": "gene/protein", "source": "test"},
            {"id": "G:CGRP_RECEPTOR", "name": "CGRP receptor complex", "node_type": "gene/protein", "source": "test"},
        ]
        with patched_primekg_driver(rows_by_kind={"detect": crowded_rows}):
            result = detect_primekg_query_entities(
                query,
                limit=8,
                checked_status={"enabled": True, "connected": True},
            )

        names = {item["name"] for item in result["detectedEntities"]}
        self.assertTrue(any("autoimmune" in name for name in names))
        self.assertTrue({"CALCA", "CGRP receptor complex"} & names)
        self.assertIn("cgrp", {item["id"] for item in result["conceptResults"]})
        cgrp_result = next(item for item in result["conceptResults"] if item["id"] == "cgrp")
        self.assertTrue(cgrp_result["matched"])

    def test_drug_disease_query_uses_direct_paths_even_when_depth_two_requested(self):
        with patched_primekg_driver():
            result = retrieve_primekg_paths_for_question(
                "Which drugs are connected to migraine disorder?",
                top_k=5,
                max_depth=2,
                max_paths=5,
                checked_status={"enabled": True, "connected": True},
            )

        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["stats"]["maxDepth"], 1)

    def test_retrieve_paths_for_question_without_selected_disease(self):
        with patched_primekg_driver():
            result = retrieve_primekg_paths_for_question(
                "What drugs are connected to migraine?",
                top_k=5,
                max_depth=2,
                max_paths=5,
                checked_status={"enabled": True, "connected": True},
            )

        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["detectedEntities"][0]["name"], "Migraine")
        self.assertEqual(result["stats"]["pathCount"], 1)
        self.assertEqual(result["paths"][0]["pathText"], "Migraine --indication--> Erenumab")
        self.assertIn("treatment", result["paths"][0]["reason"])
        self.assertIn("coverage", result)
        self.assertIn("byConcept", result["stats"])

    def test_retrieve_paths_for_question_with_selected_disease(self):
        with patched_primekg_driver():
            result = retrieve_primekg_paths_for_question(
                "Show graph evidence for treatment",
                selected_disease="Migraine",
                top_k=5,
                max_depth=2,
                max_paths=5,
                checked_status={"enabled": True, "connected": True},
            )

        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["selectedDiseaseHint"], "Migraine")
        self.assertEqual(result["detectedEntities"][0]["matchType"], "hint")

    def test_retrieve_paths_for_question_no_paths_found(self):
        with patched_primekg_driver(rows_by_kind={"paths": []}):
            result = retrieve_primekg_paths_for_question(
                "What drugs are connected to migraine?",
                checked_status={"enabled": True, "connected": True},
            )

        self.assertEqual(result["status"], "empty")
        self.assertGreaterEqual(result["stats"]["detectedEntityCount"], 1)
        self.assertEqual(result["paths"], [])
        self.assertIn("no bounded evidence paths", result["message"].lower())

    def test_retrieve_paths_for_question_caps_results(self):
        path_rows = []
        for index in range(8):
            path_rows.append({
                "nodes": [
                    {"id": "DISEASE:1", "prime_id": "DISEASE:1", "name": "Migraine", "type": "disease"},
                    {"id": f"DRUG:{index}", "prime_id": f"DRUG:{index}", "name": f"Drug {index}", "type": "drug"},
                ],
                "relationships": [
                    {
                        "id": f"REL:{index}",
                        "source": "DISEASE:1",
                        "sourceName": "Migraine",
                        "target": f"DRUG:{index}",
                        "targetName": f"Drug {index}",
                        "relation": "indication",
                        "displayRelation": "indication",
                    }
                ],
                "score": 25,
                "length": 1,
            })
        with patched_primekg_driver(rows_by_kind={"paths": path_rows}):
            result = retrieve_primekg_paths_for_question(
                "What drugs are connected to migraine?",
                max_paths=3,
                checked_status={"enabled": True, "connected": True},
            )

        self.assertEqual(result["status"], "ok")
        self.assertEqual(len(result["paths"]), 3)
        self.assertEqual(result["stats"]["pathCount"], 3)


class FakeResult:
    def __init__(self, data):
        self._data = data

    def data(self):
        return self._data


class FakeSession:
    def __init__(self, rows_by_kind=None):
        rows_by_kind = rows_by_kind or {}
        self.detect_rows = rows_by_kind.get("detect", [
            {"id": "DISEASE:1", "name": "Migraine", "node_type": "disease", "source": "test"},
            {"id": "GENE:1", "name": "CGRP", "node_type": "gene/protein", "source": "test"},
        ])
        # Representative default: a real PrimeKG drug->disease indication edge so
        # therapeutic-intent retrieval has semantically valid evidence.
        self.path_rows = rows_by_kind.get("paths", [
            {
                "nodes": [
                    {"id": "DISEASE:1", "prime_id": "DISEASE:1", "name": "Migraine", "type": "disease"},
                    {"id": "DRUG:1", "prime_id": "DRUG:1", "name": "Erenumab", "type": "drug"},
                ],
                "relationships": [
                    {
                        "id": "REL:1",
                        "source": "DRUG:1",
                        "sourceName": "Erenumab",
                        "target": "DISEASE:1",
                        "targetName": "Migraine",
                        "relation": "indication",
                        "displayRelation": "indication",
                    },
                ],
                "score": 42,
                "length": 1,
            }
        ])
        self.run_count = 0

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def run(self, query, **params):
        self.run_count += 1
        if "MATCH path" in query:
            return FakeResult(self.path_rows)
        terms = [term.lower() for term in params.get("terms", [])]
        limit = params.get("limit", len(self.detect_rows))
        if not terms:
            return FakeResult(self.detect_rows[:limit])
        rows = []
        for row in self.detect_rows:
            name = (row.get("name") or "").lower()
            if any(
                name == term
                or (len(term) >= 4 and name.startswith(term))
                or (len(term) >= 4 and term in name)
                or (len(name) >= 5 and name in term)
                for term in terms
            ):
                rows.append(row)
        return FakeResult(rows[:limit])


class FakeDriver:
    def __init__(self, session):
        self._session = session

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def session(self, database=None):
        return self._session


class patched_primekg_driver:
    def __init__(self, rows_by_kind=None):
        self.session = FakeSession(rows_by_kind)
        self.patch = patch("backend.graph_rag.get_driver", return_value=FakeDriver(self.session))

    def __enter__(self):
        self.patch.__enter__()
        return self.session

    def __exit__(self, exc_type, exc, tb):
        self.patch.__exit__(exc_type, exc, tb)
        return False


if __name__ == "__main__":
    unittest.main()
