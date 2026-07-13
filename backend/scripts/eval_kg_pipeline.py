"""Full-graph evaluation harness for the PrimeKG KG pipeline.

Runs a fixed regression corpus (many diseases, intents, and adversarial inputs)
plus an optional randomized disease-sampling mode against the live Neo4j graph,
checks pipeline invariants, and saves a reproducible JSON report.

Usage:
    python -m backend.scripts.eval_kg_pipeline                 # fixed corpus
    python -m backend.scripts.eval_kg_pipeline --sample 25     # + random diseases
    python -m backend.scripts.eval_kg_pipeline --out report.json
"""

from __future__ import annotations

import argparse
import json
import random
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.graph_rag import (  # noqa: E402
    retrieve_primekg_paths_for_question, primekg_question_retrieval_result,
    get_driver, neo4j_settings,
)
from backend.kg_semantics import (  # noqa: E402
    INTENT_TREATMENT, INTENT_CONTRAINDICATION, relation_semantics, is_ontology_only,
    CAT_CONTRAINDICATION,
)

ALLOWED = ["disease", "drug", "gene/protein", "pathway", "biological_process",
           "molecular_function", "phenotype", "effect/phenotype"]

# Fixed regression corpus: (question, selected_disease). Covers dense/sparse
# diseases, ontology-heavy cases, unsupported intents, and adversarial inputs.
CORPUS = [
    ("What drugs treat migraine?", "migraine"),
    ("What drugs treat rheumatoid arthritis?", "rheumatoid arthritis"),
    ("What drugs are indicated for type 2 diabetes?", "type 2 diabetes mellitus"),
    ("What drugs treat asthma?", "asthma"),
    ("What genes are associated with breast cancer?", "breast cancer"),
    ("What is contraindicated in migraine?", "migraine"),
    ("How common is lupus?", "systemic lupus erythematosus"),          # unsupported intent
    ("What causes autoimmune disease?", "autoimmune disease"),          # unsupported intent
    ("Which drugs connect to migraine through CGRP mechanisms and common autoimmune diseases?", "migraine"),  # compound
    ("the and are of", None),                                           # no biomedical entity
    ("xyzzy nonexistent disease foobar", None),                         # nonexistent
    ("What phenotypes are seen in asthma?", "asthma"),
    ("What genes are associated with HER2 positive breast cancer?", "breast cancer"),  # alias
]

# Invariants checked per case.
def check_invariants(question, result, evidence):
    violations = []
    intent = (result.get("intent") or {}).get("primary", "")
    gate = (result.get("evidenceStatus") or {}).get("status", "")
    paths = result.get("paths") or []

    # 1. contraindication path must never appear in a treatment result.
    if intent == INTENT_TREATMENT:
        for p in paths:
            if any(relation_semantics(r.get("relation")).category == CAT_CONTRAINDICATION
                   for r in p.get("relationships") or []):
                violations.append("contraindication path in treatment result")
                break

    # 2. ontology-only paths cannot yield a 'supported' therapeutic answer.
    if intent in (INTENT_TREATMENT, INTENT_CONTRAINDICATION) and gate == "supported":
        if paths and all(p.get("relationships") and all(is_ontology_only(r.get("relation"))
                         for r in p["relationships"]) for p in paths):
            violations.append("ontology-only evidence marked supported for therapeutic intent")

    # 3. unsupported intents must be flagged, never 'supported'.
    if not (result.get("intent") or {}).get("supported", True) and gate == "supported":
        violations.append("unsupported intent marked supported")

    # 4. no single anchor may consume every slot when multiple anchors resolved.
    anchors = {p.get("anchorId") for p in paths if p.get("anchorId")}
    detected = {e.get("id") for e in result.get("detectedEntities") or []}
    if len(paths) >= 6 and len(detected) >= 2 and len(anchors) == 1:
        violations.append("single anchor consumed all evidence slots")

    # 5. duplicate suppression: selected path texts must be unique.
    texts = [p.get("pathText") for p in paths]
    if len(texts) != len(set(texts)):
        violations.append("duplicate paths in selected evidence")

    return violations


def run_case(question, disease):
    started = time.perf_counter()
    result = retrieve_primekg_paths_for_question(
        question, selected_disease=disease, top_k=8, max_depth=2, max_paths=12,
        allowed_node_types=ALLOWED,
    )
    rendered = primekg_question_retrieval_result(result) if result.get("status") == "ok" else {"graphEvidence": {}}
    duration = round((time.perf_counter() - started) * 1000, 1)
    violations = check_invariants(question, result, rendered.get("graphEvidence", {}))
    return {
        "question": question,
        "selectedDisease": disease,
        "status": result.get("status"),
        "intent": (result.get("intent") or {}).get("primary"),
        "intentSupported": (result.get("intent") or {}).get("supported"),
        "evidenceStatus": (result.get("evidenceStatus") or {}).get("status"),
        "pathCount": len(result.get("paths") or []),
        "rejectedCount": (result.get("stats") or {}).get("rejectedPaths"),
        "resolved": [r.get("resolvedName") for r in (result.get("entityResolution") or {}).get("resolved", [])],
        "unresolved": [r.get("mention") for r in (result.get("entityResolution") or {}).get("unresolved", [])],
        "durationMs": duration,
        "violations": violations,
    }


def sample_diseases(n):
    s = neo4j_settings()
    with get_driver() as d:
        with d.session(database=s["database"]) as ses:
            rows = ses.run(
                "MATCH (n:PrimeNode {node_type:'disease'}) RETURN n.name AS name, "
                "count{ (n)-[:PRIME_REL]-() } AS deg ORDER BY rand() LIMIT $k", k=int(n) * 3
            ).data()
    rows.sort(key=lambda r: r["deg"])
    picks = rows[:1] + rows[len(rows) // 2: len(rows) // 2 + 1] + rows[-1:]  # sparse/mid/dense
    picks = rows[:n] if len(picks) < n else rows[::max(1, len(rows) // n)][:n]
    return [r["name"] for r in picks]


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--sample", type=int, default=0, help="Also test N randomly sampled diseases.")
    ap.add_argument("--seed", type=int, default=1234)
    ap.add_argument("--out", default=str(ROOT / "data" / "primekg" / "kg_eval_report.json"))
    args = ap.parse_args()
    random.seed(args.seed)

    cases = list(CORPUS)
    if args.sample:
        try:
            for name in sample_diseases(args.sample):
                cases.append((f"What drugs treat {name}?", name))
        except Exception as exc:
            print(f"[warn] sampling failed: {exc}", file=sys.stderr)

    results = []
    for question, disease in cases:
        try:
            results.append(run_case(question, disease))
        except Exception as exc:
            results.append({"question": question, "selectedDisease": disease, "error": str(exc), "violations": ["exception"]})

    total_violations = sum(len(r.get("violations") or []) for r in results)
    latencies = sorted(r["durationMs"] for r in results if "durationMs" in r)
    report = {
        "cases": len(results),
        "totalViolations": total_violations,
        "emptyRate": round(sum(1 for r in results if r.get("status") != "ok") / max(1, len(results)), 3),
        "unsupportedIntentCases": sum(1 for r in results if r.get("intentSupported") is False),
        "p50LatencyMs": latencies[len(latencies) // 2] if latencies else None,
        "p95LatencyMs": latencies[int(len(latencies) * 0.95)] if latencies else None,
        "results": results,
    }
    Path(args.out).write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")

    print(f"cases={report['cases']} violations={total_violations} "
          f"emptyRate={report['emptyRate']} p50={report['p50LatencyMs']}ms p95={report['p95LatencyMs']}ms")
    for r in results:
        flag = "  !! " + ", ".join(r["violations"]) if r.get("violations") else ""
        print(f"  [{r.get('evidenceStatus') or r.get('status'):<20}] "
              f"{(r.get('intent') or '-'):<24} paths={r.get('pathCount', '-'):<3} {r['question'][:52]}{flag}")
    print(f"\nreport -> {args.out}")
    return 1 if total_violations else 0


if __name__ == "__main__":
    raise SystemExit(main())
