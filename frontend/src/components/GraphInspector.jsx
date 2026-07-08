import { BadgeInfo, ChevronRight, ExternalLink, Network } from "lucide-react";

import { cleanEndpoint, PRIMEKG_NODE_TYPE_COLORS } from "../utils/primekgGraphAdapter.js";

export default function GraphInspector({
  node,
  link,
  adjacency,
  nodesById,
  selected,
  onFocusNode,
  onHoverLink,
}) {
  const resolvedLink = link ? normalizeLinkForDisplay(link, nodesById) : null;
  const grouped = node ? groupRelationships(adjacency[node.id] || [], nodesById) : null;
  const connectedCount = grouped ? grouped.incoming.length + grouped.outgoing.length : 0;

  return (
    <aside className="primekg-inspector">
      <div className="primekg-inspector-heading">
        <span>{selected ? "Selected" : "Hover or select"}</span>
        <strong>{resolvedLink ? "Relationship Details" : node ? node.name : "Graph Inspector"}</strong>
        <p>This view shows the filtered PrimeKG subgraph imported into Neo4j.</p>
      </div>

      {resolvedLink ? (
        <RelationshipDetails relationship={resolvedLink} />
      ) : node ? (
        <NodeDetails
          node={node}
          grouped={grouped}
          connectedCount={connectedCount}
          onFocusNode={onFocusNode}
          onHoverLink={onHoverLink}
        />
      ) : (
        <div className="primekg-inspector-empty">
          <BadgeInfo size={18} />
          <p>Select a node or relationship to inspect biomedical entity details, neighbors, and evidence context.</p>
        </div>
      )}
    </aside>
  );
}

function NodeDetails({ node, grouped, connectedCount, onFocusNode, onHoverLink }) {
  const relationGroups = groupByRelation([...(grouped?.incoming || []), ...(grouped?.outgoing || [])]);
  return (
    <div className="primekg-inspector-content">
      <div className="primekg-node-hero">
        <span className="primekg-type-badge" style={{ borderColor: typeColor(node.type), color: typeColor(node.type) }}>
          <i style={{ background: typeColor(node.type) }} />
          {node.type || "other"}
        </span>
        <h4>{node.name}</h4>
      </div>

      <dl className="primekg-detail-grid">
        <div><dt>Degree</dt><dd>{node.degree || 0}</dd></div>
        <div><dt>Connected Relationships</dt><dd>{connectedCount}</dd></div>
        <div><dt>PrimeKG ID</dt><dd>{node.raw?.prime_id || node.id}</dd></div>
        {node.raw?.source ? <div><dt>Source</dt><dd>{node.raw.source}</dd></div> : null}
      </dl>

      <button type="button" className="primekg-focus-neighborhood" onClick={() => onFocusNode(node)}>
        <Network size={14} />
        Focus neighborhood
      </button>

      <RelationshipGroup title="Outgoing" items={grouped?.outgoing || []} onFocusNode={onFocusNode} onHoverLink={onHoverLink} />
      <RelationshipGroup title="Incoming" items={grouped?.incoming || []} onFocusNode={onFocusNode} onHoverLink={onHoverLink} />

      <section className="primekg-relation-summary">
        <h4>By relation type</h4>
        {Object.entries(relationGroups).map(([relation, count]) => (
          <div key={relation}>
            <span>{relation}</span>
            <strong>{count}</strong>
          </div>
        ))}
      </section>

      <details className="primekg-raw-details">
        <summary>Raw details</summary>
        <pre>{JSON.stringify(node.raw || node, null, 2)}</pre>
      </details>
    </div>
  );
}

function RelationshipDetails({ relationship }) {
  return (
    <div className="primekg-inspector-content">
      <div className="primekg-node-hero">
        <span className="primekg-type-badge relation">
          <ChevronRight size={13} />
          {relationship.label}
        </span>
        <h4>{relationship.sourceName} to {relationship.targetName}</h4>
      </div>

      <dl className="primekg-detail-grid">
        <div><dt>Source Node</dt><dd>{relationship.sourceName || relationship.source}</dd></div>
        <div><dt>Target Node</dt><dd>{relationship.targetName || relationship.target}</dd></div>
        <div><dt>Relation</dt><dd>{relationship.relation || relationship.label}</dd></div>
        {relationship.raw?.prime_source ? <div><dt>Prime Source</dt><dd>{relationship.raw.prime_source}</dd></div> : null}
        {relationship.raw?.depth !== undefined ? <div><dt>Depth</dt><dd>{relationship.raw.depth}</dd></div> : null}
        {relationship.raw?.imported_at ? <div><dt>Imported</dt><dd>{relationship.raw.imported_at}</dd></div> : null}
      </dl>

      <details className="primekg-raw-details">
        <summary>Raw details</summary>
        <pre>{JSON.stringify(relationship.raw || relationship, null, 2)}</pre>
      </details>
    </div>
  );
}

function RelationshipGroup({ title, items, onFocusNode, onHoverLink }) {
  return (
    <section className="primekg-relationship-group">
      <h4>{title}</h4>
      <div className="primekg-neighbor-list">
        {items.slice(0, 16).map((item, index) => (
          <button
            key={`${item.node?.id || item.nodeId}-${item.link?.id || index}`}
            type="button"
            onMouseEnter={() => onHoverLink(item.link)}
            onMouseLeave={() => onHoverLink(null)}
            onClick={() => onFocusNode(item.node)}
          >
            <span>{item.relation}</span>
            <strong>{item.node?.name || item.nodeId}</strong>
            <em>{item.node?.type || "other"}</em>
            <ExternalLink size={12} />
          </button>
        ))}
        {items.length ? null : <p className="hint">None visible.</p>}
      </div>
    </section>
  );
}

function groupRelationships(items, nodesById) {
  const grouped = { incoming: [], outgoing: [] };
  items.forEach((item) => {
    const node = nodesById.get(item.nodeId);
    const entry = { ...item, node };
    if (item.direction === "out") {
      grouped.outgoing.push(entry);
    } else {
      grouped.incoming.push(entry);
    }
  });
  return grouped;
}

function groupByRelation(items) {
  return items.reduce((acc, item) => {
    const key = item.relation || "related to";
    acc[key] = (acc[key] || 0) + 1;
    return acc;
  }, {});
}

function normalizeLinkForDisplay(link, nodesById) {
  const source = cleanEndpoint(link.source);
  const target = cleanEndpoint(link.target);
  const sourceNode = nodesById.get(source);
  const targetNode = nodesById.get(target);
  return {
    ...link,
    source,
    target,
    sourceName: link.raw?.sourceName || link.raw?.source_name || sourceNode?.name || source,
    targetName: link.raw?.targetName || link.raw?.target_name || targetNode?.name || target,
  };
}

function typeColor(type) {
  return PRIMEKG_NODE_TYPE_COLORS[type] || PRIMEKG_NODE_TYPE_COLORS.other;
}
