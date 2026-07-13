"""Centralized PrimeKG relation semantics and question-intent classification.

Single source of truth for what each PrimeKG relationship *means* and which
question intents it can legitimately support. String matching on relation names
is confined to this module; the rest of the pipeline asks typed questions like
``supports_treatment_claim(rel)`` instead of doing substring checks.

Keyed on the PrimeKG ``relation`` property (not ``display_relation``), because
display labels such as "parent-child" and "interacts with" are reused across
many distinct relations.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field


# Semantic categories used by ranking / gating.
CAT_INDICATION = "indication"
CAT_CONTRAINDICATION = "contraindication"
CAT_OFF_LABEL = "off_label"
CAT_ADVERSE = "adverse_effect"
CAT_DRUG_TARGET = "drug_target"
CAT_DRUG_INTERACTION = "drug_interaction"
CAT_ASSOCIATION = "association"
CAT_PHENOTYPE = "phenotype"
CAT_MOLECULAR = "molecular_interaction"
CAT_EXPRESSION = "expression"
CAT_EXPOSURE = "exposure"
CAT_ONTOLOGY = "ontology"
CAT_UNKNOWN = "unknown"

POS = "positive"
NEG = "negative"
NEU = "neutral"


@dataclass(frozen=True)
class RelationSemantics:
    relation: str                 # canonical PrimeKG relation name (the registry key)
    display: str                  # human label
    category: str
    polarity: str = NEU
    source_types: tuple = ()      # allowed source node types (empty = any)
    target_types: tuple = ()
    symmetric: bool = False
    ontology_only: bool = False
    supports_treatment: bool = False
    supports_contraindication: bool = False
    supports_causal: bool = False   # PrimeKG models NO causal relations
    priority: int = 1              # 1 (weak) .. 10 (strong direct evidence)


def _r(relation, display, category, **kw):
    return RelationSemantics(relation=relation, display=display, category=category, **kw)


# Ground-truth registry (relations verified present in the imported PrimeKG graph).
RELATION_REGISTRY: dict[str, RelationSemantics] = {rs.relation: rs for rs in [
    _r("indication", "indication", CAT_INDICATION, polarity=POS,
       source_types=("drug",), target_types=("disease",),
       supports_treatment=True, priority=10),
    _r("off-label use", "off-label use", CAT_OFF_LABEL, polarity=POS,
       source_types=("drug",), target_types=("disease",),
       supports_treatment=True, priority=7),
    _r("contraindication", "contraindication", CAT_CONTRAINDICATION, polarity=NEG,
       source_types=("drug",), target_types=("disease",),
       supports_contraindication=True, priority=9),
    _r("drug_effect", "side effect", CAT_ADVERSE, polarity=NEG,
       source_types=("drug",), target_types=("effect/phenotype",), priority=8),
    _r("drug_protein", "target", CAT_DRUG_TARGET, polarity=NEU,
       source_types=("drug",), target_types=("gene/protein",), priority=6),
    _r("drug_drug", "synergistic interaction", CAT_DRUG_INTERACTION, polarity=NEU,
       source_types=("drug",), target_types=("drug",), symmetric=True, priority=4),
    _r("disease_protein", "associated with", CAT_ASSOCIATION, polarity=NEU,
       source_types=("disease",), target_types=("gene/protein",), priority=7),
    _r("phenotype_protein", "associated with", CAT_ASSOCIATION, polarity=NEU,
       source_types=("effect/phenotype",), target_types=("gene/protein",), priority=5),
    _r("disease_phenotype_positive", "phenotype present", CAT_PHENOTYPE, polarity=POS,
       source_types=("disease",), target_types=("effect/phenotype",), priority=7),
    _r("disease_phenotype_negative", "phenotype absent", CAT_PHENOTYPE, polarity=NEG,
       source_types=("disease",), target_types=("effect/phenotype",), priority=4),
    _r("protein_protein", "ppi", CAT_MOLECULAR, polarity=NEU,
       source_types=("gene/protein",), target_types=("gene/protein",), symmetric=True, priority=4),
    _r("bioprocess_protein", "interacts with", CAT_MOLECULAR, polarity=NEU, priority=4),
    _r("molfunc_protein", "interacts with", CAT_MOLECULAR, polarity=NEU, priority=4),
    _r("cellcomp_protein", "interacts with", CAT_MOLECULAR, polarity=NEU, priority=3),
    _r("pathway_protein", "interacts with", CAT_MOLECULAR, polarity=NEU, priority=5),
    _r("anatomy_protein_present", "expression present", CAT_EXPRESSION, polarity=POS, priority=3),
    _r("anatomy_protein_absent", "expression absent", CAT_EXPRESSION, polarity=NEG, priority=2),
    _r("exposure_disease", "linked to", CAT_EXPOSURE, polarity=NEU, priority=3),
    _r("exposure_protein", "interacts with", CAT_EXPOSURE, polarity=NEU, priority=2),
    _r("exposure_bioprocess", "interacts with", CAT_EXPOSURE, polarity=NEU, priority=2),
    _r("exposure_molfunc", "interacts with", CAT_EXPOSURE, polarity=NEU, priority=2),
    _r("exposure_cellcomp", "interacts with", CAT_EXPOSURE, polarity=NEU, priority=2),
    # Ontology parent-child relations (structural only; never therapeutic evidence).
    *[_r(rel, "parent-child", CAT_ONTOLOGY, ontology_only=True, symmetric=False, priority=2)
      for rel in ("disease_disease", "bioprocess_bioprocess", "phenotype_phenotype",
                  "anatomy_anatomy", "molfunc_molfunc", "cellcomp_cellcomp",
                  "pathway_pathway", "exposure_exposure")],
]}

# An unknown relation resolves to this: neutral, low priority, no claims supported.
UNKNOWN_RELATION = _r("__unknown__", "unknown", CAT_UNKNOWN, polarity=NEU, priority=1)


def relation_semantics(relation: str) -> RelationSemantics:
    return RELATION_REGISTRY.get((relation or "").strip(), UNKNOWN_RELATION)


def is_known_relation(relation: str) -> bool:
    return (relation or "").strip() in RELATION_REGISTRY


def is_ontology_only(relation: str) -> bool:
    return relation_semantics(relation).ontology_only


def supports_treatment_claim(relation: str) -> bool:
    return relation_semantics(relation).supports_treatment


def supports_contraindication_claim(relation: str) -> bool:
    return relation_semantics(relation).supports_contraindication


def validate_relations(db_relations) -> dict:
    """Report relations present in the DB but not modeled in the registry."""
    unmapped = sorted({(r or "").strip() for r in db_relations if (r or "").strip()
                       and (r or "").strip() not in RELATION_REGISTRY})
    return {"unmapped": unmapped, "known": sorted(RELATION_REGISTRY), "ok": not unmapped}


# ---------------------------------------------------------------------------
# Intent classification (Phase 4). Deterministic, rule-based.
# ---------------------------------------------------------------------------

INTENT_TREATMENT = "treatment_indication"
INTENT_CONTRAINDICATION = "contraindication"
INTENT_DRUG_DISEASE = "drug_disease_association"
INTENT_GENE_DISEASE = "gene_disease_association"
INTENT_PHENOTYPE = "phenotype_association"
INTENT_PATHWAY = "pathway_association"
INTENT_ANATOMY = "anatomy_association"
INTENT_MOLECULAR = "molecular_interaction"
INTENT_DRUG_TARGET = "drug_target"
INTENT_ONTOLOGY = "ontology_relation"
INTENT_ADVERSE = "adverse_effect"
INTENT_EVIDENCE = "evidence_lookup"
# Unsupported: PrimeKG has no relation modeling these claim types.
INTENT_CAUSAL = "causal"
INTENT_PREVALENCE = "prevalence"
INTENT_DIAGNOSIS = "diagnosis"
INTENT_PROGNOSIS = "prognosis"
INTENT_RISK = "risk"

UNSUPPORTED_INTENTS = {INTENT_CAUSAL, INTENT_PREVALENCE, INTENT_DIAGNOSIS,
                       INTENT_PROGNOSIS, INTENT_RISK}

# Intent -> semantic categories that can answer it.
INTENT_RELATION_CATEGORIES = {
    INTENT_TREATMENT: {CAT_INDICATION, CAT_OFF_LABEL},
    INTENT_CONTRAINDICATION: {CAT_CONTRAINDICATION},
    INTENT_DRUG_DISEASE: {CAT_INDICATION, CAT_OFF_LABEL, CAT_CONTRAINDICATION},
    INTENT_GENE_DISEASE: {CAT_ASSOCIATION},
    INTENT_PHENOTYPE: {CAT_PHENOTYPE},
    INTENT_PATHWAY: {CAT_MOLECULAR},
    INTENT_ANATOMY: {CAT_EXPRESSION},
    INTENT_MOLECULAR: {CAT_MOLECULAR, CAT_DRUG_TARGET},
    INTENT_DRUG_TARGET: {CAT_DRUG_TARGET},
    INTENT_ADVERSE: {CAT_ADVERSE},
    INTENT_ONTOLOGY: {CAT_ONTOLOGY},
    INTENT_EVIDENCE: set(RELATION_REGISTRY and {rs.category for rs in RELATION_REGISTRY.values()}),
}

# Ordered (phrase, intent). First hit wins for the primary intent; all hits are
# recorded. Phrases are matched on word boundaries against the normalized query.
_INTENT_PATTERNS = [
    (r"\bcontraindicat", INTENT_CONTRAINDICATION),
    (r"\bside effect", INTENT_ADVERSE),
    (r"\badverse", INTENT_ADVERSE),
    (r"\b(prevalence|how common|most common|commonness|frequency|how many people)\b", INTENT_PREVALENCE),
    (r"\b(cause|causes|caused by|etiology|why do|why does)\b", INTENT_CAUSAL),
    (r"\b(risk factor|risk of)\b", INTENT_RISK),
    (r"\b(diagnos)\b", INTENT_DIAGNOSIS),
    (r"\b(prognos|survival rate|life expectancy)\b", INTENT_PROGNOSIS),
    (r"\b(treat|treats|treatment|therapy|drug for|drugs for|medication|indicated for|indication)\b", INTENT_TREATMENT),
    (r"\b(target|targets|inhibit|inhibits|binds)\b", INTENT_DRUG_TARGET),
    (r"\b(symptom|symptoms|phenotype|phenotypes|manifestation)\b", INTENT_PHENOTYPE),
    (r"\b(pathway|pathways|signaling)\b", INTENT_PATHWAY),
    (r"\b(express|expression|tissue|anatomy)\b", INTENT_ANATOMY),
    (r"\b(gene|genes|protein|proteins|mutation|associated gene)\b", INTENT_GENE_DISEASE),
    (r"\b(drug|drugs|compound)\b", INTENT_DRUG_DISEASE),
    (r"\b(subtype|parent|child|type of|kind of|classification)\b", INTENT_ONTOLOGY),
]


@dataclass
class Intent:
    primary: str
    all_intents: list = field(default_factory=list)
    supported: bool = True
    reason: str = ""


def classify_intent(question: str) -> Intent:
    text = " " + re.sub(r"\s+", " ", (question or "").strip().lower()) + " "
    hits = []
    for pattern, intent in _INTENT_PATTERNS:
        if re.search(pattern, text) and intent not in hits:
            hits.append(intent)
    if not hits:
        return Intent(primary=INTENT_EVIDENCE, all_intents=[INTENT_EVIDENCE], supported=True,
                      reason="No specific intent detected; defaulting to evidence lookup.")
    primary = hits[0]
    if primary in UNSUPPORTED_INTENTS:
        return Intent(primary=primary, all_intents=hits, supported=False,
                      reason=f"PrimeKG does not model '{primary}' claims (no supporting relation type).")
    return Intent(primary=primary, all_intents=hits, supported=True)


def intent_relation_compatible(intent: str, relation: str) -> bool:
    """Whether a relation can legitimately answer an intent."""
    categories = INTENT_RELATION_CATEGORIES.get(intent)
    if categories is None:
        return True  # evidence lookup / unknown intent: don't over-filter
    return relation_semantics(relation).category in categories
