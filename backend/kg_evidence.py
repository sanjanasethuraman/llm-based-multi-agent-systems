"""Evidence ranking (explicit score components) and the evidence-quality gate.

Ranking uses named, inspectable score components rather than overloaded numeric
constants, and semantic-category rules from kg_semantics — so one relation class
can never collide with another (e.g. contraindication cannot score as indication).

The gate maps selected evidence to a structured support status the LLM must obey.
All functions here are pure and unit-testable without a database.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from backend.kg_semantics import (
    CAT_ONTOLOGY, CAT_MOLECULAR, CAT_EXPRESSION, CAT_DRUG_INTERACTION,
    CAT_INDICATION, CAT_CONTRAINDICATION,
    intent_relation_compatible, relation_semantics, is_ontology_only,
)

# Evidence-quality outcomes (Phase 8).
STATUS_SUPPORTED = "supported"
STATUS_PARTIAL = "partially_supported"
STATUS_INSUFFICIENT = "insufficient_evidence"
STATUS_AMBIGUOUS = "ambiguous_entity"
STATUS_UNSUPPORTED_INTENT = "unsupported_intent"
STATUS_CONFLICTING = "conflicting_evidence"
STATUS_RETRIEVAL_FAILURE = "retrieval_failure"

_GENERIC_CATEGORIES = {CAT_MOLECULAR, CAT_EXPRESSION, CAT_DRUG_INTERACTION}


def _rel_of(relationship):
    return (relationship or {}).get("relation") or ""


def path_relations(path):
    return [_rel_of(r) for r in (path.get("relationships") or [])]


def semantic_signature(path):
    """Dedup key: ordered (relation-category, target-name) pairs + endpoints.

    Collapses 'eight variations of essentially the same path' that differ only by
    a trailing hub target while keeping genuinely distinct evidence separate.
    """
    nodes = path.get("nodes") or []
    rels = path.get("relationships") or []
    start = (nodes[0].get("name") if nodes else "") or ""
    cats = tuple(relation_semantics(_rel_of(r)).category for r in rels)
    end = (nodes[-1].get("name") if nodes else "") or ""
    return (start.lower(), cats, end.lower())


@dataclass
class ScoreComponents:
    intent_match: float = 0.0
    relation_priority: float = 0.0
    directness: float = 0.0
    anchor_confidence: float = 0.0
    ontology_penalty: float = 0.0
    generic_penalty: float = 0.0
    hub_penalty: float = 0.0
    total: float = 0.0

    def as_dict(self):
        return {k: round(v, 4) for k, v in self.__dict__.items()}


def score_path(path, intent, anchor_confidence=1.0, node_degrees=None):
    rels = path.get("relationships") or []
    nodes = path.get("nodes") or []
    length = max(1, len(rels))
    sems = [relation_semantics(_rel_of(r)) for r in rels]

    intent_match = 1.0 if any(intent_relation_compatible(intent, s.relation) for s in sems) else 0.0
    relation_priority = (max((s.priority for s in sems), default=1)) / 10.0
    directness = 1.0 / length
    ontology_penalty = sum(1 for s in sems if s.ontology_only) / length
    generic_penalty = sum(1 for s in sems if s.category in _GENERIC_CATEGORIES) / length

    hub_penalty = 0.0
    if node_degrees:
        degs = [node_degrees.get(n.get("id") or n.get("prime_id"), 0) for n in nodes]
        if degs:
            worst = max(degs)
            hub_penalty = min(0.5, worst / 200000.0)  # dampen ultra-high-degree hubs

    total = (
        0.40 * intent_match
        + 0.20 * relation_priority
        + 0.15 * directness
        + 0.15 * max(0.0, anchor_confidence)
        - 0.25 * ontology_penalty
        - 0.10 * generic_penalty
        - hub_penalty
    )
    return ScoreComponents(
        intent_match=intent_match, relation_priority=relation_priority, directness=directness,
        anchor_confidence=max(0.0, anchor_confidence), ontology_penalty=ontology_penalty,
        generic_penalty=generic_penalty, hub_penalty=hub_penalty, total=round(total, 4),
    )


def select_evidence(paths, intent, anchor_ids, anchor_confidence=None, max_paths=12,
                    per_anchor=4, per_relation=6, per_target=3, node_degrees=None,
                    drop_ontology_for_therapeutic=True):
    """Diversify + cap + dedup evidence. Returns (selected, rejected)."""
    from backend.kg_semantics import INTENT_TREATMENT, INTENT_CONTRAINDICATION
    anchor_confidence = anchor_confidence or {}
    therapeutic = intent in (INTENT_TREATMENT, INTENT_CONTRAINDICATION)
    # For a therapeutic intent, the opposing therapeutic category must never
    # appear anywhere in a selected path (e.g. a treatment answer cannot ride on
    # a path that contains a contraindication edge).
    opposing = set()
    if intent == INTENT_TREATMENT:
        opposing = {CAT_CONTRAINDICATION}
    elif intent == INTENT_CONTRAINDICATION:
        opposing = {CAT_INDICATION}

    scored = []
    for path in paths or []:
        nodes = path.get("nodes") or []
        anchor = next((n.get("id") or n.get("prime_id") for n in nodes
                       if (n.get("id") or n.get("prime_id")) in set(anchor_ids)), "_other")
        conf = anchor_confidence.get(anchor, 1.0)
        comp = score_path(path, intent, conf, node_degrees)
        rels = path_relations(path)
        all_ontology = bool(rels) and all(is_ontology_only(r) for r in rels)
        path_categories = {relation_semantics(r).category for r in rels}
        rejected_reason = ""
        if opposing & path_categories:
            rejected_reason = "path contains an opposing therapeutic relation"
        elif therapeutic and drop_ontology_for_therapeutic and all_ontology:
            rejected_reason = "ontology-only path cannot support a therapeutic claim"
        elif comp.intent_match == 0.0 and therapeutic:
            rejected_reason = "no intent-compatible relation for therapeutic question"
        scored.append({"path": path, "anchor": anchor, "score": comp.total,
                       "components": comp.as_dict(), "signature": semantic_signature(path),
                       "rejected": rejected_reason})

    scored.sort(key=lambda item: -item["score"])

    selected, rejected = [], []
    seen_sig = set()
    per_anchor_count, per_rel_count, per_target_count = {}, {}, {}
    for item in scored:
        if item["rejected"]:
            rejected.append(item)
            continue
        sig = item["signature"]
        if sig in seen_sig:
            item["rejected"] = "duplicate path (semantic signature)"
            rejected.append(item)
            continue
        anchor = item["anchor"]
        rels = path_relations(item["path"])
        primary_rel = rels[0] if rels else ""
        nodes = item["path"].get("nodes") or []
        target = (nodes[-1].get("id") if nodes else "") or ""
        if per_anchor_count.get(anchor, 0) >= per_anchor:
            item["rejected"] = "per-anchor cap"
            rejected.append(item); continue
        if per_rel_count.get(primary_rel, 0) >= per_relation:
            item["rejected"] = "per-relation cap"
            rejected.append(item); continue
        if per_target_count.get(target, 0) >= per_target:
            item["rejected"] = "per-target cap"
            rejected.append(item); continue
        seen_sig.add(sig)
        per_anchor_count[anchor] = per_anchor_count.get(anchor, 0) + 1
        per_rel_count[primary_rel] = per_rel_count.get(primary_rel, 0) + 1
        per_target_count[target] = per_target_count.get(target, 0) + 1
        selected.append(item)
        if len(selected) >= max_paths:
            break
    return selected, rejected


def _has_conflict(selected):
    cats_by_target = {}
    for item in selected:
        for rel in item["path"].get("relationships") or []:
            cat = relation_semantics(_rel_of(rel)).category
            key = (rel.get("source"), rel.get("target"))
            cats_by_target.setdefault(key, set()).add(cat)
    return any({CAT_INDICATION, CAT_CONTRAINDICATION}.issubset(cats) for cats in cats_by_target.values())


def assess_evidence(intent_supported, resolved_anchors, ambiguous, selected, rejected, intent):
    """Map evidence to a structured support status the LLM must obey."""
    if not intent_supported:
        return {"status": STATUS_UNSUPPORTED_INTENT,
                "reason": "PrimeKG does not model this fact type (e.g. prevalence/causal)."}
    if not resolved_anchors and ambiguous:
        return {"status": STATUS_AMBIGUOUS,
                "reason": "The main entity is ambiguous; multiple candidates are equally plausible."}
    if not resolved_anchors:
        return {"status": STATUS_INSUFFICIENT, "reason": "No question entity resolved in PrimeKG."}
    if not selected:
        reason = "No relevant relations found for this intent."
        if rejected and all(r["rejected"].startswith("ontology") for r in rejected):
            reason = "Only ontology (parent-child) evidence exists; not a therapeutic answer."
        return {"status": STATUS_INSUFFICIENT, "reason": reason}
    if _has_conflict(selected):
        return {"status": STATUS_CONFLICTING,
                "reason": "Both indication and contraindication evidence exist for a pair."}
    direct = sum(1 for s in selected if s["components"]["directness"] >= 0.99)
    intent_matched = sum(1 for s in selected if s["components"]["intent_match"] >= 1.0)
    if intent_matched and direct:
        return {"status": STATUS_SUPPORTED, "reason": "Direct, intent-compatible graph evidence found."}
    return {"status": STATUS_PARTIAL,
            "reason": "Only indirect or partially relevant evidence found."}
