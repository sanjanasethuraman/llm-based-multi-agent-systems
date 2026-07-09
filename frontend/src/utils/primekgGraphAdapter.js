export const PRIMEKG_NODE_TYPE_COLORS = {
  disease: "#fb7185",
  drug: "#60a5fa",
  "gene/protein": "#a78bfa",
  pathway: "#34d399",
  phenotype: "#fbbf24",
  biological_process: "#2dd4bf",
  molecular_function: "#22d3ee",
  anatomy: "#94a3b8",
  exposure: "#c084fc",
  other: "#64748b",
};

const NODE_TYPE_ALIASES = {
  gene: "gene/protein",
  protein: "gene/protein",
  gene_protein: "gene/protein",
  "gene protein": "gene/protein",
  symptom: "phenotype",
  symptoms: "phenotype",
  mechanism: "biological_process",
  "biological process": "biological_process",
  molecular_function: "molecular_function",
  "molecular function": "molecular_function",
};

export function adaptPrimeKGGraph(response = {}) {
  const rawNodes = Array.isArray(response?.nodes) ? response.nodes : [];
  const rawRelationships = Array.isArray(response?.relationships)
    ? response.relationships
    : Array.isArray(response?.links)
      ? response.links
      : [];

  const nodesById = new Map();
  rawNodes.forEach((node, index) => {
    if (!node || typeof node !== "object") {
      return;
    }
    const id = cleanText(node?.id || node?.prime_id || node?.primeId || node?.name || `node-${index}`);
    if (!id || nodesById.has(id)) {
      return;
    }
    const name = cleanText(node?.name || node?.label || id);
    const type = normalizeNodeType(node?.node_type || node?.nodeType || node?.type || node?.category);
    nodesById.set(id, {
      id,
      name,
      label: cleanText(node?.label || name),
      node_type: type,
      type,
      degree: 0,
      colorKey: type,
      color: PRIMEKG_NODE_TYPE_COLORS[type] || PRIMEKG_NODE_TYPE_COLORS.other,
      searchText: "",
      raw: node || {},
    });
  });

  const linksByKey = new Map();
  rawRelationships.forEach((relationship, index) => {
    const source = cleanEndpoint(relationship?.source || relationship?.source_id || relationship?.sourceId);
    const target = cleanEndpoint(relationship?.target || relationship?.target_id || relationship?.targetId);
    if (!source || !target || source === target) {
      return;
    }

    ensureEndpointNode(nodesById, source, relationship?.sourceName || relationship?.source_name);
    ensureEndpointNode(nodesById, target, relationship?.targetName || relationship?.target_name);

    const relation = cleanText(
      relationship?.relation ||
      relationship?.type ||
      relationship?.displayRelation ||
      relationship?.display_relation ||
      "related_to",
    );
    const displayRelation = cleanText(
      relationship?.displayRelation ||
      relationship?.display_relation ||
      relationship?.label ||
      humanizeRelation(relation),
    );
    const explicitId = cleanText(relationship?.id || relationship?.prime_key || relationship?.key);
    const naturalKey = `${source}|${relation}|${target}`;
    const id = explicitId || naturalKey || `relationship-${index}`;
    const dedupeKey = explicitId ? `id:${explicitId}` : `natural:${naturalKey}`;
    if (linksByKey.has(dedupeKey)) {
      return;
    }

    linksByKey.set(dedupeKey, {
      id,
      source,
      target,
      relation,
      display_relation: displayRelation,
      label: displayRelation,
      searchText: [source, target, relation, displayRelation, relationship?.sourceName, relationship?.targetName]
        .filter(Boolean)
        .join(" ")
        .toLowerCase(),
      raw: relationship || {},
    });
  });

  const adjacency = {};
  const links = Array.from(linksByKey.values());
  links.forEach((link) => {
    const sourceId = cleanEndpoint(link.source);
    const targetId = cleanEndpoint(link.target);
    const sourceNode = nodesById.get(sourceId);
    const targetNode = nodesById.get(targetId);
    if (!sourceNode || !targetNode) {
      return;
    }

    sourceNode.degree += 1;
    targetNode.degree += 1;
    adjacency[sourceId] = adjacency[sourceId] || [];
    adjacency[targetId] = adjacency[targetId] || [];
    adjacency[sourceId].push({ nodeId: targetId, direction: "out", relation: link.display_relation, link });
    adjacency[targetId].push({ nodeId: sourceId, direction: "in", relation: link.display_relation, link });
  });

  const nodes = Array.from(nodesById.values()).map((node) => ({
    ...node,
    val: nodeValue(node),
    searchText: [
      node.id,
      node.name,
      node.label,
      node.type,
      node.raw?.source,
      node.raw?.diseaseContext,
      node.raw?.disease_context,
    ].filter(Boolean).join(" ").toLowerCase(),
  }));

  const nodeTypes = countBy(nodes, "type");
  const relationTypes = countBy(links, "display_relation");
  return {
    nodes,
    links,
    nodeTypes,
    relationTypes,
    adjacency,
    counts: {
      nodes: nodes.length,
      links: links.length,
      nodeTypes: Object.keys(nodeTypes).length,
      relationTypes: Object.keys(relationTypes).length,
      sourceNodes: rawNodes.length,
      sourceRelationships: rawRelationships.length,
    },
    metadata: {
      status: response?.status || "",
      message: response?.message || "",
      disease: response?.disease || "",
      depth: response?.depth || null,
      source: response?.source || "",
      warnings: Array.isArray(response?.warnings) ? response.warnings : [],
      stats: response?.stats || {},
      seeds: Array.isArray(response?.seeds) ? response.seeds : [],
      neo4j: response?.neo4j || {},
    },
  };
}

export function filterPrimeKGGraph(adaptedGraph, filters = {}) {
  const graph = adaptedGraph || adaptPrimeKGGraph();
  const query = cleanText(filters.search || filters.query).toLowerCase();
  const allowedNodeTypes = normalizeAllowedSet(filters.nodeTypes);
  const allowedRelationTypes = normalizeAllowedSet(filters.relationTypes);

  const baseNodeIds = new Set();
  graph.nodes.forEach((node) => {
    if (!allowedNodeTypes || allowedNodeTypes.has(node.type)) {
      baseNodeIds.add(node.id);
    }
  });

  const searchedNodeIds = new Set();
  if (query) {
    graph.nodes.forEach((node) => {
      if (baseNodeIds.has(node.id) && node.searchText.includes(query)) {
        searchedNodeIds.add(node.id);
      }
    });
    graph.links.forEach((link) => {
      const source = cleanEndpoint(link.source);
      const target = cleanEndpoint(link.target);
      if (baseNodeIds.has(source) && baseNodeIds.has(target) && link.searchText.includes(query)) {
        searchedNodeIds.add(source);
        searchedNodeIds.add(target);
      }
    });
    graph.links.forEach((link) => {
      const source = cleanEndpoint(link.source);
      const target = cleanEndpoint(link.target);
      if (searchedNodeIds.has(source) || searchedNodeIds.has(target)) {
        if (baseNodeIds.has(source)) searchedNodeIds.add(source);
        if (baseNodeIds.has(target)) searchedNodeIds.add(target);
      }
    });
  }

  const nodesById = new Map();
  graph.nodes.forEach((node) => {
    const visible = baseNodeIds.has(node.id) && (!query || searchedNodeIds.has(node.id));
    if (visible) {
      nodesById.set(node.id, { ...node, degree: 0 });
    }
  });

  const links = graph.links.filter((link) => {
    const relationAllowed = !allowedRelationTypes || allowedRelationTypes.has(link.display_relation);
    const queryAllowed = !query || link.searchText.includes(query);
    const endpointAllowed = nodesById.has(cleanEndpoint(link.source)) && nodesById.has(cleanEndpoint(link.target));
    return relationAllowed && endpointAllowed && (!query || queryAllowed || searchedNodeIds.has(cleanEndpoint(link.source)) || searchedNodeIds.has(cleanEndpoint(link.target)));
  });

  links.forEach((link) => {
    const source = nodesById.get(cleanEndpoint(link.source));
    const target = nodesById.get(cleanEndpoint(link.target));
    if (source) source.degree += 1;
    if (target) target.degree += 1;
  });

  const nodes = Array.from(nodesById.values()).map((node) => ({ ...node, val: nodeValue(node) }));
  return {
    ...graph,
    nodes,
    links,
    counts: {
      ...graph.counts,
      visibleNodes: nodes.length,
      visibleLinks: links.length,
    },
  };
}

export function normalizeNodeType(value) {
  const raw = cleanText(value || "other").toLowerCase();
  const normalized = raw.replace(/[-\s]+/g, "_");
  return NODE_TYPE_ALIASES[raw] || NODE_TYPE_ALIASES[normalized] || normalized || "other";
}

export function cleanEndpoint(value) {
  if (value && typeof value === "object") {
    return cleanText(value.id || value.prime_id || value.name);
  }
  return cleanText(value);
}

function ensureEndpointNode(nodesById, id, label) {
  if (!id || nodesById.has(id)) {
    return;
  }
  const name = cleanText(label || id);
  nodesById.set(id, {
    id,
    name,
    label: name,
    node_type: "other",
    type: "other",
    degree: 0,
    colorKey: "other",
    color: PRIMEKG_NODE_TYPE_COLORS.other,
    searchText: "",
    raw: { id, name, inferred: true },
  });
}

function normalizeAllowedSet(values) {
  if (!values || values === "all") {
    return null;
  }
  const items = Array.isArray(values) ? values : [values];
  const cleaned = items.map((item) => cleanText(item)).filter(Boolean);
  return new Set(cleaned);
}

function nodeValue(node) {
  const base = node.type === "disease" ? 8 : node.type === "drug" ? 6 : 4;
  return Math.min(base + Math.sqrt(Math.max(0, Number(node.degree) || 0)) * 2, 18);
}

function countBy(items, field) {
  const counts = {};
  items.forEach((item) => {
    const key = cleanText(item?.[field] || "unknown");
    counts[key] = (counts[key] || 0) + 1;
  });
  return Object.fromEntries(Object.entries(counts).sort((left, right) => right[1] - left[1] || left[0].localeCompare(right[0])));
}

function humanizeRelation(value) {
  return cleanText(value || "related_to").replace(/[_-]+/g, " ");
}

function cleanText(value) {
  if (value === null || value === undefined) {
    return "";
  }
  return String(value).trim();
}
