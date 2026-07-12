"""Invariant + unit tests for the hardened KG pipeline (semantics, resolution,
evidence gate). Deterministic; no Neo4j required."""

import unittest

from backend import kg_semantics as sem
from backend.kg_entity_resolution import (
    resolve_from_candidates, normalize_mention, extract_mentions,
    TIER_EXACT, TIER_ALIAS, TIER_TOKEN, TIER_UNRESOLVED, TIER_AMBIGUOUS,
)
from backend.kg_aliases import default_registry
from backend.kg_evidence import (
    select_evidence, assess_evidence, score_path, semantic_signature,
    STATUS_SUPPORTED, STATUS_INSUFFICIENT, STATUS_UNSUPPORTED_INTENT, STATUS_AMBIGUOUS,
)


def _path(nodes, rels):
    ns = [{"id": n, "prime_id": n, "name": n, "type": t} for n, t in nodes]
    rs = [{"source": s, "target": tg, "relation": rel, "displayRelation": rel} for s, tg, rel in rels]
    return {"nodes": ns, "relationships": rs, "pathText": "x", "length": len(rs)}


class SemanticsTests(unittest.TestCase):
    def test_contraindication_is_not_indication(self):
        self.assertTrue(sem.supports_treatment_claim("indication"))
        self.assertFalse(sem.supports_treatment_claim("contraindication"))
        self.assertTrue(sem.supports_contraindication_claim("contraindication"))
        self.assertNotEqual(sem.relation_semantics("indication").category,
                            sem.relation_semantics("contraindication").category)

    def test_ontology_relations_flagged(self):
        for rel in ("disease_disease", "phenotype_phenotype", "bioprocess_bioprocess"):
            self.assertTrue(sem.is_ontology_only(rel))
        self.assertFalse(sem.is_ontology_only("indication"))

    def test_unknown_relation_supports_nothing(self):
        rs = sem.relation_semantics("totally_made_up")
        self.assertFalse(rs.supports_treatment)
        self.assertFalse(rs.supports_causal)
        self.assertEqual(rs.category, sem.CAT_UNKNOWN)

    def test_validate_relations_reports_unmapped(self):
        report = sem.validate_relations(["indication", "brand_new_rel", "contraindication"])
        self.assertIn("brand_new_rel", report["unmapped"])
        self.assertFalse(report["ok"])

    def test_intent_distinguishes_indication_and_contraindication(self):
        self.assertEqual(sem.classify_intent("what drugs treat asthma").primary, sem.INTENT_TREATMENT)
        self.assertEqual(sem.classify_intent("what is contraindicated in migraine").primary, sem.INTENT_CONTRAINDICATION)

    def test_prevalence_and_causal_are_unsupported(self):
        self.assertFalse(sem.classify_intent("how common is lupus").supported)
        self.assertFalse(sem.classify_intent("what causes autoimmune disease").supported)
        self.assertTrue(sem.classify_intent("what genes are associated with asthma").supported)


class EntityResolutionTests(unittest.TestCase):
    def test_short_stopword_cannot_substring_match(self):
        cands = [{"id": "1", "name": "thecoma", "node_type": "disease"},
                 {"id": "2", "name": "tularemia", "node_type": "disease"}]
        res = resolve_from_candidates("the", cands)
        self.assertFalse(res.resolved)
        self.assertEqual(res.method, TIER_UNRESOLVED)

    def test_exact_match_resolves(self):
        cands = [{"id": "7", "name": "Migraine disorder", "node_type": "disease"}]
        res = resolve_from_candidates("migraine disorder", cands)
        self.assertTrue(res.resolved)
        self.assertEqual(res.method, TIER_EXACT)
        self.assertEqual(res.resolved_id, "7")

    def test_alias_resolution_for_cgrp(self):
        hit = default_registry().resolve_alias("CGRP")
        self.assertIsNotNone(hit)
        self.assertIn("CALCA", hit.canonical)
        cands = [{"id": "g", "name": "CALCA", "node_type": "gene/protein"}]
        res = resolve_from_candidates("cgrp", cands, alias_names=list(hit.canonical))
        self.assertTrue(res.resolved)
        self.assertEqual(res.method, TIER_ALIAS)

    def test_ambiguous_entity_not_silently_selected(self):
        cands = [{"id": "a", "name": "lupus nephritis", "node_type": "disease"},
                 {"id": "b", "name": "lupus vulgaris", "node_type": "disease"}]
        res = resolve_from_candidates("lupus", cands)
        self.assertFalse(res.resolved)
        self.assertEqual(res.method, TIER_AMBIGUOUS)
        self.assertGreaterEqual(len(res.ambiguous_alternatives), 2)

    def test_token_boundary_match(self):
        cands = [{"id": "d", "name": "type 2 diabetes mellitus", "node_type": "disease"}]
        res = resolve_from_candidates("type 2 diabetes", cands)
        self.assertTrue(res.resolved)
        self.assertEqual(res.method, TIER_TOKEN)

    def test_extract_mentions_drops_stopwords_and_short_tokens(self):
        mentions = extract_mentions("what are the causes of asthma")
        self.assertIn("asthma", mentions)
        self.assertNotIn("the", mentions)
        self.assertNotIn("are", mentions)

    def test_normalization_handles_hyphen_and_greek(self):
        self.assertEqual(normalize_mention("TNF-alpha"), "tnf-a")
        self.assertEqual(normalize_mention("PD-1"), "pd-1")


class EvidenceGateTests(unittest.TestCase):
    def test_contraindication_never_in_treatment_result(self):
        paths = [_path([("Migraine", "disease"), ("Estradiol", "drug")],
                       [("Estradiol", "Migraine", "contraindication")])]
        selected, rejected = select_evidence(paths, sem.INTENT_TREATMENT, ["Migraine"])
        self.assertEqual(selected, [])
        self.assertTrue(rejected)

    def test_indication_supports_treatment(self):
        paths = [_path([("Migraine", "disease"), ("Rizatriptan", "drug")],
                       [("Rizatriptan", "Migraine", "indication")])]
        selected, rejected = select_evidence(paths, sem.INTENT_TREATMENT, ["Migraine"])
        self.assertEqual(len(selected), 1)
        gate = assess_evidence(True, True, False, selected, rejected, sem.INTENT_TREATMENT)
        self.assertEqual(gate["status"], STATUS_SUPPORTED)

    def test_ontology_only_cannot_support_treatment(self):
        paths = [_path([("migraine", "disease"), ("headache disorder", "disease")],
                       [("migraine", "headache disorder", "disease_disease")])]
        selected, rejected = select_evidence(paths, sem.INTENT_TREATMENT, ["migraine"])
        self.assertEqual(selected, [])
        gate = assess_evidence(True, True, False, selected, rejected, sem.INTENT_TREATMENT)
        self.assertEqual(gate["status"], STATUS_INSUFFICIENT)

    def test_unsupported_intent_gate(self):
        gate = assess_evidence(False, True, False, [], [], sem.INTENT_CAUSAL)
        self.assertEqual(gate["status"], STATUS_UNSUPPORTED_INTENT)

    def test_unresolved_entity_cannot_be_supported(self):
        gate = assess_evidence(True, False, False, [], [], sem.INTENT_TREATMENT)
        self.assertEqual(gate["status"], STATUS_INSUFFICIENT)

    def test_ambiguous_entity_gate(self):
        gate = assess_evidence(True, False, True, [], [], sem.INTENT_TREATMENT)
        self.assertEqual(gate["status"], STATUS_AMBIGUOUS)

    def test_duplicate_paths_suppressed(self):
        p = _path([("Migraine", "disease"), ("Rizatriptan", "drug")], [("Rizatriptan", "Migraine", "indication")])
        selected, _ = select_evidence([dict(p), dict(p), dict(p)], sem.INTENT_TREATMENT, ["Migraine"])
        self.assertEqual(len(selected), 1)

    def test_no_single_anchor_consumes_all_slots(self):
        paths = []
        for i in range(10):  # anchor A: many drugs
            paths.append(_path([("A", "disease"), (f"drugA{i}", "drug")], [(f"drugA{i}", "A", "indication")]))
        for i in range(3):   # anchor B: fewer drugs
            paths.append(_path([("B", "disease"), (f"drugB{i}", "drug")], [(f"drugB{i}", "B", "indication")]))
        selected, _ = select_evidence(paths, sem.INTENT_DRUG_DISEASE, ["A", "B"], per_anchor=4, max_paths=12)
        anchors = {s["anchor"] for s in selected}
        self.assertEqual(anchors, {"A", "B"})
        self.assertLessEqual(sum(1 for s in selected if s["anchor"] == "A"), 4)

    def test_direct_evidence_outranks_multi_hop(self):
        direct = _path([("A", "disease"), ("d1", "drug")], [("d1", "A", "indication")])
        indirect = _path([("A", "disease"), ("g", "gene/protein"), ("d2", "drug")],
                         [("A", "g", "disease_protein"), ("d2", "g", "drug_protein")])
        s_direct = score_path(direct, sem.INTENT_TREATMENT).total
        s_indirect = score_path(indirect, sem.INTENT_TREATMENT).total
        self.assertGreater(s_direct, s_indirect)

    def test_unknown_relation_low_score(self):
        p = _path([("A", "disease"), ("B", "drug")], [("B", "A", "mystery_relation")])
        comp = score_path(p, sem.INTENT_TREATMENT)
        self.assertEqual(comp.intent_match, 0.0)

    def test_semantic_signature_collapses_hub_variants(self):
        a = _path([("A", "disease"), ("Estradiol", "drug"), ("x", "disease")],
                  [("Estradiol", "A", "contraindication"), ("Estradiol", "x", "contraindication")])
        b = _path([("A", "disease"), ("Estradiol", "drug"), ("x", "disease")],
                  [("Estradiol", "A", "contraindication"), ("Estradiol", "x", "contraindication")])
        self.assertEqual(semantic_signature(a), semantic_signature(b))


if __name__ == "__main__":
    unittest.main()
