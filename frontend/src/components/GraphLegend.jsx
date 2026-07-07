import { PRIMEKG_NODE_TYPE_COLORS } from "../utils/primekgGraphAdapter.js";

export default function GraphLegend({
  nodeTypes = {},
  relationTypes = {},
  hiddenNodeTypes,
  hiddenRelationTypes,
  onToggleNodeType,
  onToggleRelationType,
}) {
  return (
    <div className="primekg-legend-panel">
      <FilterGroup
        title="Node Types"
        counts={nodeTypes}
        hidden={hiddenNodeTypes}
        onToggle={onToggleNodeType}
        colorFor={typeColor}
      />
      <FilterGroup
        title="Relation Types"
        counts={relationTypes}
        hidden={hiddenRelationTypes}
        onToggle={onToggleRelationType}
        colorFor={() => "#7dd3fc"}
      />
    </div>
  );
}

function FilterGroup({ title, counts, hidden, onToggle, colorFor }) {
  const entries = Object.entries(counts || {}).slice(0, 16);
  if (!entries.length) {
    return null;
  }
  return (
    <div className="primekg-filter-group">
      <span>{title}</span>
      <div>
        {entries.map(([type, count]) => {
          const inactive = hidden.has(type);
          return (
            <button
              key={type}
              type="button"
              className={inactive ? "inactive" : ""}
              onClick={() => onToggle(type)}
              title={`${inactive ? "Show" : "Hide"} ${type}`}
            >
              <i style={{ background: colorFor(type) }} />
              {type} {count}
            </button>
          );
        })}
      </div>
    </div>
  );
}

function typeColor(type) {
  return PRIMEKG_NODE_TYPE_COLORS[type] || PRIMEKG_NODE_TYPE_COLORS.other;
}
