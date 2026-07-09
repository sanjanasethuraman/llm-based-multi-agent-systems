"""Filter a small disease-centered PrimeKG subgraph without importing Neo4j.

The script streams PrimeKG kg.csv in repeated passes: one pass to find matching
disease nodes, then one pass per traversal depth. This keeps memory bounded by
the requested output size rather than the full dataset size.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import Counter, OrderedDict
from datetime import datetime, timezone
from difflib import SequenceMatcher
from pathlib import Path


DEFAULT_INPUT = Path("data/primekg/kg.csv")
DEFAULT_NODE_TYPES = {
    "disease",
    "drug",
    "gene/protein",
    "pathway",
    "phenotype",
    "biological_process",
    "molecular_function",
    "anatomy",
    "exposure",
    "other",
}
NODE_TYPE_ALIASES = {
    "gene": "gene/protein",
    "protein": "gene/protein",
    "gene_protein": "gene/protein",
    "gene/protein": "gene/protein",
    "biological process": "biological_process",
    "biological_process": "biological_process",
    "molecular function": "molecular_function",
    "molecular_function": "molecular_function",
}
COLUMN_CANDIDATES = {
    "relation": ["relation", "rel", "predicate", "edge_type"],
    "display_relation": ["display_relation", "relation_name", "display_rel"],
    "x_id": ["x_id", "source_id", "subject_id", "start_id", "node_1_id", "src_id"],
    "x_name": ["x_name", "source_name", "subject_name", "start_name", "node_1_name", "src_name"],
    "x_type": ["x_type", "source_type", "subject_type", "start_type", "node_1_type", "src_type"],
    "x_source": ["x_source", "source_source", "subject_source", "start_source", "node_1_source", "src_source"],
    "y_id": ["y_id", "target_id", "object_id", "end_id", "node_2_id", "dst_id"],
    "y_name": ["y_name", "target_name", "object_name", "end_name", "node_2_name", "dst_name"],
    "y_type": ["y_type", "target_type", "object_type", "end_type", "node_2_type", "dst_type"],
    "y_source": ["y_source", "target_source", "object_source", "end_source", "node_2_source", "dst_source"],
}
REQUIRED_FIELDS = ["relation", "x_id", "x_name", "x_type", "y_id", "y_name", "y_type"]


class PrimeKGFilterError(Exception):
    """Raised for user-fixable PrimeKG filtering errors."""


def normalize_text(value: str | None) -> str:
    return " ".join((value or "").strip().casefold().replace("_", " ").split())


def normalize_node_type(value: str | None) -> str:
    normalized = normalize_text(value)
    normalized = NODE_TYPE_ALIASES.get(normalized, normalized.replace(" ", "_"))
    return normalized if normalized in DEFAULT_NODE_TYPES else "other"


def normalize_allowed_node_type(value: str) -> str:
    normalized = normalize_text(value)
    normalized = NODE_TYPE_ALIASES.get(normalized, normalized.replace(" ", "_"))
    if normalized not in DEFAULT_NODE_TYPES:
        raise PrimeKGFilterError(
            f"Unknown node type '{value}'. Allowed values: {', '.join(sorted(DEFAULT_NODE_TYPES))}"
        )
    return normalized


def parse_csv_list(values: list[str] | None) -> set[str] | None:
    if not values:
        return None
    parsed: set[str] = set()
    for value in values:
        for item in value.split(","):
            item = item.strip()
            if item:
                parsed.add(item)
    return parsed or None


def detect_columns(fieldnames: list[str] | None) -> dict[str, str]:
    if not fieldnames:
        raise PrimeKGFilterError("Input CSV has no header row.")

    by_normalized = {normalize_text(name): name for name in fieldnames}
    detected: dict[str, str] = {}
    for logical_name, candidates in COLUMN_CANDIDATES.items():
        for candidate in candidates:
            actual = by_normalized.get(normalize_text(candidate))
            if actual:
                detected[logical_name] = actual
                break

    missing = [field for field in REQUIRED_FIELDS if field not in detected]
    if missing:
        raise PrimeKGFilterError(
            "Could not detect required PrimeKG columns: "
            f"{', '.join(missing)}. Found columns: {', '.join(fieldnames)}"
        )
    return detected


def row_node(row: dict, columns: dict[str, str], side: str) -> dict:
    raw_type = row.get(columns[f"{side}_type"], "")
    return {
        "id": row.get(columns[f"{side}_id"], "").strip(),
        "name": row.get(columns[f"{side}_name"], "").strip(),
        "type": normalize_node_type(raw_type),
        "originalType": raw_type.strip(),
        "source": row.get(columns.get(f"{side}_source", ""), "").strip() if columns.get(f"{side}_source") else "",
    }


def row_relation(row: dict, columns: dict[str, str], source_id: str, target_id: str) -> dict:
    relation = row.get(columns["relation"], "").strip()
    display_relation = row.get(columns.get("display_relation", ""), "").strip() if columns.get("display_relation") else ""
    return {
        "id": f"{source_id}|{relation}|{target_id}",
        "source": source_id,
        "target": target_id,
        "relation": relation,
        "displayRelation": display_relation or relation,
    }


def node_allowed(node: dict, allowed_types: set[str]) -> bool:
    return node["type"] in allowed_types


def relation_allowed(relation: dict, allowed_relations: set[str] | None) -> bool:
    if not allowed_relations:
        return True
    normalized_allowed = {normalize_text(item) for item in allowed_relations}
    return (
        normalize_text(relation["relation"]) in normalized_allowed
        or normalize_text(relation["displayRelation"]) in normalized_allowed
    )


def find_matching_diseases(path: Path, disease_query: str, allowed_types: set[str]) -> tuple[list[dict], list[dict], dict[str, str]]:
    if "disease" not in allowed_types:
        raise PrimeKGFilterError("Allowed node types must include 'disease' to find a disease-centered subgraph.")

    query = normalize_text(disease_query)
    exact: OrderedDict[str, dict] = OrderedDict()
    contains: OrderedDict[str, dict] = OrderedDict()
    suggestions: dict[str, dict] = {}
    columns: dict[str, str] = {}

    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        columns = detect_columns(reader.fieldnames)
        for row in reader:
            for side in ("x", "y"):
                node = row_node(row, columns, side)
                if node["type"] != "disease" or not node["id"]:
                    continue
                name = normalize_text(node["name"])
                if name == query or normalize_text(node["id"]) == query:
                    exact.setdefault(node["id"], node)
                elif query and query in name:
                    contains.setdefault(node["id"], node)
                else:
                    name_tokens = name.split()
                    token_scores = [SequenceMatcher(None, query, token).ratio() for token in name_tokens]
                    score = max([SequenceMatcher(None, query, name).ratio(), *token_scores])
                    if score >= 0.58:
                        existing = suggestions.get(node["id"])
                        if not existing or score > existing["score"]:
                            suggestions[node["id"]] = {"score": score, "node": node}

    matches = list(exact.values()) or list(contains.values())
    ranked_suggestions = [
        item["node"]
        for item in sorted(suggestions.values(), key=lambda item: item["score"], reverse=True)[:10]
        if item["node"]["id"] not in exact and item["node"]["id"] not in contains
    ]
    return matches, ranked_suggestions, columns


def add_node(nodes: OrderedDict[str, dict], node: dict, max_nodes: int) -> bool:
    if not node["id"]:
        return False
    if node["id"] in nodes:
        return True
    if len(nodes) >= max_nodes:
        return False
    nodes[node["id"]] = node
    return True


def filter_subgraph(
    input_path: Path,
    disease_query: str,
    depth: int,
    max_nodes: int,
    max_relationships: int,
    allowed_types: set[str],
    allowed_relations: set[str] | None,
) -> dict:
    if not input_path.exists():
        return {
            "ok": False,
            "error": "PrimeKG kg.csv is not present.",
            "setupHint": "Download PrimeKG manually and pass --input data/primekg/kg.csv.",
            "input": str(input_path.resolve()),
        }
    if not input_path.is_file():
        return {
            "ok": False,
            "error": "PrimeKG input path is not a file.",
            "setupHint": "Pass --input pointing to the real PrimeKG kg.csv file.",
            "input": str(input_path.resolve()),
        }
    if depth < 1 or depth > 3:
        raise PrimeKGFilterError("--depth must be 1, 2, or 3.")
    if max_nodes < 1 or max_relationships < 1:
        raise PrimeKGFilterError("--max-nodes and --max-relationships must be positive.")

    matched_diseases, suggestions, columns = find_matching_diseases(input_path, disease_query, allowed_types)
    if not matched_diseases:
        return {
            "ok": False,
            "error": f"No disease node matched '{disease_query}'.",
            "suggestions": suggestions,
            "input": str(input_path.resolve()),
            "detectedColumns": columns,
        }

    nodes: OrderedDict[str, dict] = OrderedDict()
    relationships: OrderedDict[str, dict] = OrderedDict()
    for node in matched_diseases:
        add_node(nodes, node, max_nodes)

    visited = set(nodes)
    frontier = set(nodes)
    caps_reached = {"nodes": False, "relationships": False}

    for current_depth in range(1, depth + 1):
        next_frontier: set[str] = set()
        with input_path.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            detect_columns(reader.fieldnames)
            for row in reader:
                if len(relationships) >= max_relationships:
                    caps_reached["relationships"] = True
                    break
                x_node = row_node(row, columns, "x")
                y_node = row_node(row, columns, "y")
                if x_node["id"] not in frontier and y_node["id"] not in frontier:
                    continue
                if not node_allowed(x_node, allowed_types) or not node_allowed(y_node, allowed_types):
                    continue
                relation = row_relation(row, columns, x_node["id"], y_node["id"])
                if not relation_allowed(relation, allowed_relations):
                    continue

                x_ok = add_node(nodes, x_node, max_nodes)
                y_ok = add_node(nodes, y_node, max_nodes)
                if not x_ok or not y_ok:
                    caps_reached["nodes"] = True
                    continue

                relationships.setdefault(relation["id"], {**relation, "depth": current_depth})
                for node_id in (x_node["id"], y_node["id"]):
                    if node_id not in visited:
                        next_frontier.add(node_id)
        if not next_frontier or caps_reached["relationships"]:
            break
        visited.update(next_frontier)
        frontier = next_frontier

    node_type_counts = Counter(node["type"] for node in nodes.values())
    relation_type_counts = Counter(rel["displayRelation"] or rel["relation"] for rel in relationships.values())
    return {
        "ok": True,
        "metadata": {
            "createdAt": datetime.now(timezone.utc).isoformat(),
            "input": str(input_path.resolve()),
            "depth": depth,
            "maxNodes": max_nodes,
            "maxRelationships": max_relationships,
            "allowedNodeTypes": sorted(allowed_types),
            "allowedRelationTypes": sorted(allowed_relations) if allowed_relations else "all",
            "detectedColumns": columns,
            "capsReached": caps_reached,
            "note": "Filtered PrimeKG subgraph only. Not imported into Neo4j.",
        },
        "diseaseQuery": disease_query,
        "matchedDiseaseNodes": matched_diseases,
        "nodes": list(nodes.values()),
        "relationships": list(relationships.values()),
        "statsByNodeType": dict(sorted(node_type_counts.items())),
        "statsByRelationType": dict(sorted(relation_type_counts.items())),
    }


def write_json(result: dict, output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as handle:
        json.dump(result, handle, indent=2)
        handle.write("\n")


def write_csv_outputs(result: dict, output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    nodes_path = output_dir / "filtered_nodes.csv"
    relationships_path = output_dir / "filtered_relationships.csv"

    with nodes_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["id", "name", "type", "originalType", "source"])
        writer.writeheader()
        writer.writerows(result.get("nodes", []))

    with relationships_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["id", "source", "target", "relation", "displayRelation", "depth"],
        )
        writer.writeheader()
        writer.writerows(result.get("relationships", []))


def parse_allowed_types(values: list[str] | None) -> set[str]:
    raw_types = parse_csv_list(values)
    if not raw_types:
        return set(DEFAULT_NODE_TYPES)
    return {normalize_allowed_node_type(value) for value in raw_types}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", default=str(DEFAULT_INPUT), help="PrimeKG kg.csv path.")
    parser.add_argument("--disease", required=True, help="Disease name or ID to center the subgraph on.")
    parser.add_argument("--depth", type=int, default=2, help="Traversal depth: 1, 2, or 3.")
    parser.add_argument("--max-nodes", type=int, default=1000, help="Maximum output nodes.")
    parser.add_argument("--max-relationships", type=int, default=3000, help="Maximum output relationships.")
    parser.add_argument("--output", required=True, help="Output JSON path.")
    parser.add_argument(
        "--allowed-node-types",
        action="append",
        help="Comma-separated allowed node types. Defaults to broad biomedical demo types.",
    )
    parser.add_argument(
        "--allowed-relations",
        action="append",
        help="Comma-separated relation names to keep. Defaults to all relations.",
    )
    parser.add_argument(
        "--csv-output-dir",
        help="Optional directory for filtered_nodes.csv and filtered_relationships.csv.",
    )
    args = parser.parse_args()

    try:
        allowed_types = parse_allowed_types(args.allowed_node_types)
        allowed_relations = parse_csv_list(args.allowed_relations)
        if args.depth == 3:
            print("Warning: depth 3 PrimeKG traversals can be large; caps will be enforced.", file=sys.stderr)
        result = filter_subgraph(
            input_path=Path(args.input),
            disease_query=args.disease,
            depth=args.depth,
            max_nodes=args.max_nodes,
            max_relationships=args.max_relationships,
            allowed_types=allowed_types,
            allowed_relations=allowed_relations,
        )
        write_json(result, Path(args.output))
        if args.csv_output_dir and result.get("ok"):
            write_csv_outputs(result, Path(args.csv_output_dir))
    except (PrimeKGFilterError, OSError, csv.Error) as exc:
        print(f"PrimeKG filter error: {exc}", file=sys.stderr)
        return 1

    if result.get("ok"):
        print(
            "Filtered PrimeKG subgraph: "
            f"{len(result['nodes'])} nodes, {len(result['relationships'])} relationships -> {args.output}"
        )
        if args.csv_output_dir:
            print(f"CSV outputs -> {args.csv_output_dir}")
        return 0

    print(json.dumps(result, indent=2))
    print(f"Wrote status JSON -> {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
