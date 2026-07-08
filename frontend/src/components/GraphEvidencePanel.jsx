import { CheckCircle2, Clipboard, ExternalLink, Info, Route, ServerCrash } from "lucide-react";
import { useMemo, useState } from "react";

import { cleanEndpoint, PRIMEKG_NODE_TYPE_COLORS } from "../utils/primekgGraphAdapter.js";

export default function GraphEvidencePanel({
  items = [],
  selectedDisease = "",
  visualGraph = null,
  onOpenGraph,
  onLoadAnswerGraph,
  compact = false,
}) {
  const [expanded, setExpanded] = useState(() => new Set());
  const visualNodeIds = useMemo(() => new Set((visualGraph?.nodes || []).map((node) => cleanEndpoint(node.id || node.prime_id || node.name))), [visualGraph]);
  const visualRelationshipKeys = useMemo(() => new Set((visualGraph?.relationships || []).map((relationship) => relationshipKey(relationship))), [visualGraph]);
  const evidenceItems = useMemo(() => normalizeEvidenceItems(items), [items]);

  if (!evidenceItems.length) {
    return null;
  }

  const toggleExpanded = (pathKey) => {
    setExpanded((current) => {
      const next = new Set(current);
      if (next.has(pathKey)) next.delete(pathKey);
      else next.add(pathKey);
      return next;
    });
  };

  return (
    <section className={`graph-answer-panel ${compact ? "compact" : ""}`}>
      <div className="graph-answer-heading">
        <div>
          <span><Route size={14} /> Graph Evidence Routes</span>
          <h3>Routes Used For This Answer</h3>
        </div>
        <div className="graph-answer-status-row">
          {selectedDisease ? <em>Selected disease hint: {selectedDisease}</em> : <em>Auto-detecting entities from question</em>}
        </div>
      </div>

      {evidenceItems.map((item, itemIndex) => (
        <article key={`${item.nodeId || "graph"}-${itemIndex}`} className={`graph-answer-card ${statusClass(item.status)}`}>
          <div className="graph-answer-card-header">
            <div>
              <strong>{item.nodeName || item.nodeId || "Graph retriever"}</strong>
              <span>{item.mode || "graph"} - {item.collection || "PrimeKG"}</span>
            </div>
            <StatusBadge status={item.status} />
          </div>

          {item.message ? <GraphEvidenceState status={item.status} message={item.message} /> : null}

          {item.detectedEntities.length ? (
            <div className="graph-answer-badges" aria-label="Detected graph entities">
              {item.detectedEntities.slice(0, 8).map((entity, index) => (
                <span key={`${entity.id || entity.name}-${index}`} style={{ borderColor: typeColor(entity.node_type || entity.type) }}>
                  {entity.name || entity.id}
                  <small>{entity.node_type || entity.type || "entity"}</small>
                </span>
              ))}
            </div>
          ) : item.status === "empty" ? (
            <GraphEvidenceState status="empty" message="No imported PrimeKG entity matched this question. Try importing a relevant disease subgraph or selecting a disease." />
          ) : null}

          {item.stats ? (
            <div className="graph-answer-stats">
              <span>{item.stats.pathCount || item.paths.length || 0} paths</span>
              <span>{item.stats.entityCount || item.entities.length || 0} entities</span>
              <span>{item.stats.relationshipCount || item.relationships.length || 0} relationships</span>
            </div>
          ) : null}

          {item.paths.length ? (
            <div className="graph-answer-path-grid">
              {item.paths.slice(0, 8).map((path, pathIndex) => {
                const pathKey = path.pathId || `${item.nodeId || itemIndex}-${pathIndex}`;
                const isExpanded = expanded.has(pathKey);
                const visible = pathVisibleInGraph(path, visualNodeIds, visualRelationshipKeys);
                return (
                  <div key={pathKey} className={`graph-answer-path-card ${visible ? "visible" : "outside"}`}>
                    <div className="graph-answer-path-topline">
                      <span>Path {pathIndex + 1}</span>
                      {path.score !== undefined ? <em>score {Number(path.score || 0).toFixed(2)}</em> : null}
                    </div>
                    <PathRoute path={path} />
                    {path.reason ? <p className="graph-answer-reason">{path.reason}</p> : null}
                    {!visible ? (
                      <div className="graph-answer-outside">
                        Path is outside current visual focus.
                        {onLoadAnswerGraph ? (
                          <button type="button" onClick={() => onLoadAnswerGraph({ path, item })}>
                            <ExternalLink size={12} />
                            Load answer graph
                          </button>
                        ) : onOpenGraph ? (
                          <button type="button" onClick={onOpenGraph}>
                            <ExternalLink size={12} />
                            Open graph explorer
                          </button>
                        ) : null}
                      </div>
                    ) : null}
                    <div className="graph-answer-path-actions">
                      <button type="button" onClick={() => copyText(path.pathText)}>
                        <Clipboard size={13} />
                        Copy path
                      </button>
                      <button type="button" onClick={() => highlightPath(path)} disabled={!visible}>
                        <Route size={13} />
                        Highlight in graph
                      </button>
                      <button type="button" onClick={() => toggleExpanded(pathKey)}>
                        {isExpanded ? "Hide details" : "Expand details"}
                      </button>
                    </div>
                    {isExpanded ? <PathDetails path={path} /> : null}
                  </div>
                );
              })}
            </div>
          ) : item.status === "ok" || item.status === "available" ? (
            <GraphEvidenceState status="empty" message="Entities were detected, but no useful paths were found in the imported graph." />
          ) : null}
        </article>
      ))}
    </section>
  );
}

function GraphEvidenceState({ status, message }) {
  const Icon = status === "unavailable" || status === "error" ? ServerCrash : Info;
  const fallback = status === "unavailable"
    ? "Graph evidence unavailable. Vector retrieval can still answer if enabled."
    : message;
  return (
    <div className={`graph-answer-state ${statusClass(status)}`}>
      <Icon size={15} />
      <span>{fallback}</span>
    </div>
  );
}

function StatusBadge({ status }) {
  const normalized = normalizeStatus(status);
  const Icon = normalized === "ok" ? CheckCircle2 : Info;
  return (
    <span className={`graph-answer-status ${statusClass(status)}`}>
      <Icon size={13} />
      {normalized}
    </span>
  );
}

function PathRoute({ path }) {
  if (!path.nodes.length) {
    return <p className="graph-answer-path-text">{path.pathText || "No readable path text returned."}</p>;
  }
  return (
    <div className="graph-answer-route">
      {path.nodes.map((node, index) => {
        const relationship = path.relationships[index - 1];
        return (
          <span key={`${node.id || node.name}-${index}`} className="graph-answer-route-segment">
            {index > 0 ? (
              <span className="graph-answer-relation">
                <i />
                {relationship?.displayRelation || relationship?.relation || "related_to"}
                <i />
              </span>
            ) : null}
            <span className="graph-answer-node" style={{ borderColor: typeColor(node.type || node.node_type) }}>
              {node.name || node.id}
              <small>{node.type || node.node_type || "entity"}</small>
            </span>
          </span>
        );
      })}
    </div>
  );
}

function PathDetails({ path }) {
  return (
    <details className="graph-answer-details" open>
      <summary>Nodes and relationships</summary>
      <div>
        <strong>Nodes</strong>
        {(path.nodes || []).map((node, index) => (
          <span key={`${node.id || node.name}-${index}`}>{node.name || node.id} ({node.type || node.node_type || "entity"})</span>
        ))}
      </div>
      <div>
        <strong>Relationships</strong>
        {(path.relationships || []).map((relationship, index) => (
          <span key={`${relationship.id || relationship.source}-${relationship.target}-${index}`}>
            {relationship.sourceName || relationship.source} -[{relationship.displayRelation || relationship.relation || "related_to"}]-&gt; {relationship.targetName || relationship.target}
          </span>
        ))}
      </div>
    </details>
  );
}

function normalizeEvidenceItems(items) {
  return (items || [])
    .map((item) => {
      const evidence = item.evidence || item.graphEvidence || item;
      if (!evidence) return null;
      return {
        nodeId: item.nodeId,
        nodeName: item.nodeName,
        collection: item.collection,
        mode: item.retrievalMode,
        status: normalizeStatus(evidence.status),
        message: evidence.message || "",
        query: evidence.query || "",
        selectedDiseaseHint: evidence.selectedDiseaseHint || "",
        detectedEntities: evidence.detectedEntities || evidence.seedEntities || [],
        entities: evidence.entities || [],
        relationships: evidence.relationships || [],
        paths: normalizePaths(evidence.paths, evidence.pathText || evidence.path_text),
        stats: evidence.stats,
      };
    })
    .filter((item) => item && (item.message || item.detectedEntities.length || item.entities.length || item.relationships.length || item.paths.length));
}

function normalizePaths(paths = [], pathText = []) {
  const normalized = (paths || []).map((path, index) => ({
    pathId: path.pathId || path.id || `path-${index}`,
    score: path.score,
    reason: path.reason || "",
    pathText: path.pathText || path.path_text || "",
    nodes: normalizeNodes(path.nodes || []),
    relationships: normalizeRelationships(path.relationships || []),
  }));
  if (normalized.length) return normalized;
  return (pathText || []).map((text, index) => ({
    pathId: `path-text-${index}`,
    pathText: text,
    nodes: [],
    relationships: [],
  }));
}

function normalizeNodes(nodes) {
  return (nodes || []).map((node) => ({
    ...node,
    id: cleanEndpoint(node.id || node.prime_id || node.name),
    name: node.name || node.id || node.prime_id,
    type: node.type || node.node_type || "other",
  }));
}

function normalizeRelationships(relationships) {
  return (relationships || []).map((relationship) => ({
    ...relationship,
    id: relationship.id || "",
    source: cleanEndpoint(relationship.source || relationship.source_id),
    target: cleanEndpoint(relationship.target || relationship.target_id),
    displayRelation: relationship.displayRelation || relationship.display_relation || relationship.relation,
  }));
}

function pathVisibleInGraph(path, visualNodeIds, visualRelationshipKeys) {
  if (!visualNodeIds.size) return false;
  const nodeIds = (path.nodes || []).map((node) => cleanEndpoint(node.id || node.prime_id || node.name)).filter(Boolean);
  if (nodeIds.length && nodeIds.some((id) => !visualNodeIds.has(id))) return false;
  const relationships = path.relationships || [];
  if (!relationships.length) return nodeIds.length > 0;
  return relationships.every((relationship) => visualRelationshipKeys.has(relationshipKey(relationship)));
}

function relationshipKey(relationship) {
  const source = cleanEndpoint(relationship.source || relationship.source_id);
  const target = cleanEndpoint(relationship.target || relationship.target_id);
  const relation = String(relationship.displayRelation || relationship.display_relation || relationship.label || relationship.relation || "").toLowerCase();
  return [source, target, relation].join("|");
}

function highlightPath(path) {
  if (typeof window === "undefined") return;
  window.dispatchEvent(new CustomEvent("primekg:highlight-path", { detail: { path } }));
  document.querySelector(".primekg-explorer")?.scrollIntoView({ behavior: "smooth", block: "start" });
}

function copyText(text) {
  if (!text || typeof navigator === "undefined" || !navigator.clipboard) return;
  navigator.clipboard.writeText(text).catch(() => {});
}

function normalizeStatus(status) {
  if (status === "available") return "ok";
  return status || "empty";
}

function statusClass(status) {
  const normalized = normalizeStatus(status);
  if (normalized === "ok") return "ok";
  if (normalized === "unavailable" || normalized === "error") return "unavailable";
  return "empty";
}

function typeColor(type) {
  return PRIMEKG_NODE_TYPE_COLORS[type] || PRIMEKG_NODE_TYPE_COLORS.other;
}
