import unittest
from unittest.mock import patch

from backend.graph_rag import graph_unavailable_result, primekg_question_retrieval_result
from backend.nodes.retriever import RetrieverNodeExecutor
from backend.rag import retrieve_context


class RagPipelineTests(unittest.TestCase):
    def test_vector_mode_unchanged(self):
        vector_result = {
            "context": "Retrieved context from collection 'docs' using local-json-fallback:\n\n[1] Doc\nVector text",
            "matches": [{"text": "Vector text", "metadata": {"id": "v1"}}],
            "vectorBackend": "local-json-fallback",
            "embeddingBackend": "hash",
        }
        with patch("backend.rag.require_backend_available") as require_backend, \
             patch("backend.rag.retrieve_vector_context", return_value=vector_result) as vector_context, \
             patch("backend.rag.retrieve_graph_context") as graph_context:
            result = retrieve_context(
                {"retrievalMode": "vector", "collection": "docs", "vectorBackend": "local-json-fallback"},
                "What drugs are connected to migraine?",
            )

        require_backend.assert_called_once()
        vector_context.assert_called_once()
        graph_context.assert_not_called()
        self.assertEqual(result["retrievalMode"], "vector")
        self.assertNotIn("graphEvidence", result)
        self.assertEqual(result["matches"][0]["text"], "Vector text")

    def test_graph_mode_uses_graph_retrieval_without_selected_disease(self):
        graph_result = {
            "context": "Graph evidence paths:\n[PrimeKG Path 1] Migraine --indication--> Erenumab",
            "matches": [{"text": "Migraine --indication--> Erenumab", "metadata": {"stage": "graph"}}],
            "graphEvidence": {
                "status": "available",
                "detectedEntities": [{"id": "D:1", "name": "Migraine", "node_type": "disease"}],
                "paths": [{"pathText": "Migraine --indication--> Erenumab"}],
                "entities": [{"id": "D:1"}, {"id": "DRUG:1"}],
                "relationships": [{"id": "R:1"}],
            },
            "graphBackend": "neo4j-primekg",
        }
        with patch("backend.rag.retrieve_graph_context", return_value=graph_result) as graph_context, \
             patch("backend.rag.retrieve_vector_context") as vector_context:
            result = retrieve_context(
                {"retrievalMode": "graph", "collection": "docs", "graphTopK": 5, "graphHops": 2},
                "What drugs are connected to migraine?",
            )

        graph_context.assert_called_once()
        _, query, top_k, hops, config = graph_context.call_args.args
        self.assertEqual(query, "What drugs are connected to migraine?")
        self.assertEqual(top_k, 5)
        self.assertEqual(hops, 2)
        self.assertNotIn("disease", config)
        vector_context.assert_not_called()
        self.assertEqual(result["retrievalMode"], "graph")
        self.assertEqual(result["graphEvidence"]["detectedEntities"][0]["name"], "Migraine")

    def test_graph_mode_passes_selected_disease_hint_in_config(self):
        graph_result = {
            "context": "Graph evidence paths:\n[PrimeKG Path 1] Migraine --indication--> Erenumab",
            "matches": [],
            "graphEvidence": {"status": "available", "paths": [], "entities": [], "relationships": []},
            "graphBackend": "neo4j-primekg",
        }
        with patch("backend.rag.retrieve_graph_context", return_value=graph_result) as graph_context:
            result = retrieve_context(
                {"retrievalMode": "graph", "collection": "docs", "graphDisease": "Migraine"},
                "Show graph evidence for treatment",
            )

        self.assertEqual(graph_context.call_args.args[4]["graphDisease"], "Migraine")
        self.assertEqual(result["retrievalMode"], "graph")
        self.assertEqual(result["graphAnswerMode"], "grounded")

    def test_graph_mode_passes_answer_mode_in_config(self):
        graph_result = {
            "context": "ANSWER MODE: hybrid.\nGraph evidence paths:\n[PrimeKG Path 1] Migraine --indication--> Erenumab",
            "matches": [],
            "graphEvidence": {
                "status": "available",
                "paths": [],
                "entities": [],
                "relationships": [],
                "answerMode": "hybrid",
                "fallbackAllowed": True,
                "fallbackUsed": False,
            },
            "graphBackend": "neo4j-primekg",
            "graphAnswerMode": "hybrid",
        }
        with patch("backend.rag.retrieve_graph_context", return_value=graph_result) as graph_context:
            result = retrieve_context(
                {"retrievalMode": "graph", "collection": "docs", "graphAnswerMode": "hybrid"},
                "Show graph evidence for treatment",
            )

        self.assertEqual(graph_context.call_args.args[4]["graphAnswerMode"], "hybrid")
        self.assertEqual(result["graphAnswerMode"], "hybrid")
        self.assertTrue(result["graphEvidence"]["fallbackAllowed"])

    def test_hybrid_mode_combines_vector_and_primekg_graph(self):
        vector_result = {
            "context": "Retrieved context from collection 'docs' using local-json-fallback:\n\n[1] Doc\nVector text",
            "matches": [{"text": "Vector text", "metadata": {"id": "v1", "source": "local"}}],
            "vectorBackend": "local-json-fallback",
            "embeddingBackend": "hash",
        }
        graph_result = {
            "context": "Graph evidence paths:\n[PrimeKG Path 1] Migraine --indication--> Erenumab",
            "matches": [{"text": "Migraine --indication--> Erenumab", "metadata": {"id": "g1", "source": "neo4j-primekg"}}],
            "graphEvidence": {
                "status": "available",
                "paths": [{"pathText": "Migraine --indication--> Erenumab"}],
                "detectedEntities": [{"id": "D:1", "name": "Migraine"}],
                "entities": [{"id": "D:1"}],
                "relationships": [{"id": "R:1"}],
            },
            "graphBackend": "neo4j-primekg",
        }
        with patch("backend.rag.require_backend_available"), \
             patch("backend.rag.retrieve_vector_context", return_value=vector_result), \
             patch("backend.rag.retrieve_graph_context", return_value=graph_result):
            result = retrieve_context(
                {"retrievalMode": "hybrid", "collection": "docs", "vectorBackend": "local-json-fallback"},
                "What drugs are connected to migraine?",
            )

        self.assertEqual(result["retrievalMode"], "hybrid")
        self.assertIn("Vector text", result["context"])
        self.assertIn("Graph evidence paths:", result["context"])
        self.assertEqual([match["metadata"]["stage"] for match in result["matches"]], ["vector", "graph"])
        self.assertEqual(result["graphEvidence"]["status"], "available")

    def test_hybrid_mode_keeps_vector_when_graph_unavailable(self):
        vector_result = {
            "context": "Retrieved context from collection 'docs' using local-json-fallback:\n\n[1] Doc\nVector text",
            "matches": [{"text": "Vector text", "metadata": {"id": "v1", "source": "local"}}],
            "vectorBackend": "local-json-fallback",
            "embeddingBackend": "hash",
        }
        graph_result = graph_unavailable_result(
            {"message": "Neo4j is offline", "setupHint": "Start Neo4j."},
            "unavailable",
        )
        with patch("backend.rag.require_backend_available"), \
             patch("backend.rag.retrieve_vector_context", return_value=vector_result), \
             patch("backend.rag.retrieve_graph_context", return_value=graph_result):
            result = retrieve_context(
                {"retrievalMode": "hybrid", "collection": "docs", "vectorBackend": "local-json-fallback"},
                "What drugs are connected to migraine?",
            )

        self.assertEqual(result["retrievalMode"], "hybrid")
        self.assertIn("Vector text", result["context"])
        self.assertEqual(result["graphEvidence"]["status"], "unavailable")
        self.assertEqual(result["matches"][0]["metadata"]["stage"], "vector")

    def test_retriever_output_contains_graph_evidence_and_path_stats(self):
        retrieval = {
            "context": "Graph evidence paths:\n[PrimeKG Path 1] Migraine --indication--> Erenumab",
            "matches": [{"text": "Migraine --indication--> Erenumab", "metadata": {"id": "g1"}}],
            "retrievalMode": "graph",
            "graphBackend": "neo4j-primekg",
            "graphEvidence": {
                "status": "available",
                "paths": [{"pathText": "Migraine --indication--> Erenumab"}],
                "entities": [{"id": "D:1"}, {"id": "DRUG:1"}],
                "relationships": [{"id": "R:1"}],
            },
        }
        context = {
            "edges": [],
            "values": {},
            "nodes": [],
            "stats": {"retrieverCalls": 0},
            "retrievals": [],
        }
        node = {"id": "retriever-1", "type": "retriever", "config": {"name": "Graph Retriever"}}
        with patch("backend.nodes.retriever.retrieve_context", return_value=retrieval):
            result, metadata = RetrieverNodeExecutor().execute(node, context)

        self.assertIn("Graph evidence paths:", result)
        self.assertEqual(metadata["status"], "completed")
        self.assertEqual(context["stats"]["graphEntities"], 2)
        self.assertEqual(context["stats"]["graphRelationships"], 1)
        self.assertEqual(context["stats"]["graphPaths"], 1)
        self.assertEqual(context["retrievals"][0]["graphEvidence"]["paths"][0]["pathText"], "Migraine --indication--> Erenumab")

    def test_primekg_question_context_is_bounded_readable_path_text(self):
        long_path = "Migraine --related_to--> " + ("VeryLongNode " * 200)
        question_result = {
            "query": "What drugs are connected to migraine?",
            "selectedDiseaseHint": "",
            "detectedEntities": [{"id": "D:1", "name": "Migraine"}],
            "entities": [{"id": "D:1"}],
            "relationships": [{"id": "R:1"}],
            "paths": [
                {"pathText": long_path, "path_text": long_path, "score": 0.9, "nodes": [], "relationships": [], "length": 1}
            ],
            "pathText": [long_path],
            "stats": {"pathCount": 1, "entityCount": 1, "relationshipCount": 1},
        }

        result = primekg_question_retrieval_result(question_result)

        self.assertIn("Graph evidence paths:", result["context"])
        # Bound proves the 2600-char path was truncated (untruncated + grounding
        # preamble would exceed ~3400); grounding rules add fixed overhead.
        self.assertLess(len(result["context"]), 2800)
        self.assertNotIn('"nodes"', result["context"])
        self.assertEqual(result["graphEvidence"]["paths"][0]["pathText"], long_path)

    def test_primekg_question_context_explicitly_separates_evidence_gaps(self):
        question_result = {
            "query": "Which drugs are connected to migraine and autoimmune disease?",
            "selectedDiseaseHint": "",
            "detectedEntities": [{"id": "D:1", "name": "Migraine"}],
            "entities": [{"id": "D:1", "name": "Migraine"}],
            "relationships": [{"id": "R:1"}],
            "paths": [
                {
                    "pathText": "Migraine --indication--> Erenumab",
                    "path_text": "Migraine --indication--> Erenumab",
                    "score": 0.9,
                    "nodes": [{"id": "D:1", "name": "Migraine"}],
                    "relationships": [{"displayRelation": "indication"}],
                    "length": 1,
                }
            ],
            "pathText": ["Migraine --indication--> Erenumab"],
            "stats": {"pathCount": 1, "entityCount": 1, "relationshipCount": 1},
            "coverage": {
                "detectedConcepts": ["migraine", "autoimmune disease"],
                "matchedConcepts": ["migraine"],
                "unmatchedConcepts": ["autoimmune disease"],
                "fullyGrounded": False,
                "partiallyGrounded": True,
            },
            "evidenceStatus": {"status": "partially_supported", "reason": "Only migraine evidence was found."},
            "intent": {"primary": "drug_disease_association", "supported": True},
        }

        result = primekg_question_retrieval_result(question_result)

        self.assertIn("Graph evidence paths:", result["context"])
        self.assertIn("Question coverage:", result["context"])
        self.assertIn("Supported by retrieved graph evidence: migraine", result["context"])
        self.assertIn("Unsupported or unmatched concepts: autoimmune disease", result["context"])
        self.assertIn("do not answer those parts from model knowledge", result["context"])
        self.assertEqual(result["graphEvidence"]["coverage"]["unsupportedConcepts"], ["autoimmune disease"])
        self.assertEqual(result["graphEvidence"]["unsupportedConcepts"], ["autoimmune disease"])
        self.assertEqual(result["graphEvidence"]["answerMode"], "grounded")
        self.assertFalse(result["graphEvidence"]["fallbackAllowed"])

    def test_primekg_question_context_hybrid_answer_mode_allows_labeled_fallback(self):
        question_result = {
            "query": "Which drugs are connected to migraine and what causes autoimmune disease?",
            "selectedDiseaseHint": "",
            "detectedEntities": [{"id": "D:1", "name": "Migraine"}],
            "entities": [{"id": "D:1", "name": "Migraine"}],
            "relationships": [{"id": "R:1"}],
            "paths": [
                {
                    "pathText": "Migraine --indication--> Erenumab",
                    "path_text": "Migraine --indication--> Erenumab",
                    "score": 0.9,
                    "nodes": [{"id": "D:1", "name": "Migraine"}],
                    "relationships": [{"displayRelation": "indication"}],
                    "length": 1,
                }
            ],
            "pathText": ["Migraine --indication--> Erenumab"],
            "stats": {"pathCount": 1, "entityCount": 1, "relationshipCount": 1},
            "coverage": {
                "detectedConcepts": ["migraine", "autoimmune disease"],
                "matchedConcepts": ["migraine"],
                "unmatchedConcepts": ["autoimmune disease"],
                "fullyGrounded": False,
                "partiallyGrounded": True,
            },
            "evidenceStatus": {"status": "partially_supported", "reason": "Only migraine evidence was found."},
            "intent": {"primary": "drug_disease_association", "supported": True},
        }

        result = primekg_question_retrieval_result(question_result, answer_mode="hybrid")

        self.assertIn("ANSWER MODE: hybrid.", result["context"])
        self.assertIn("Additional model knowledge (not PrimeKG evidence)", result["context"])
        self.assertIn("Fallback used: yes", result["context"])
        self.assertEqual(result["graphEvidence"]["answerMode"], "hybrid")
        self.assertTrue(result["graphEvidence"]["fallbackAllowed"])
        self.assertFalse(result["graphEvidence"]["fallbackUsed"])


if __name__ == "__main__":
    unittest.main()
