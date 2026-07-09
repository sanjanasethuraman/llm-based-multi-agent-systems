import { Clipboard, Route } from "lucide-react";

export default function EvidencePathPanel({
  paths = [],
  activePathId = "",
  onHoverPath,
  onSelectPath,
}) {
  if (!paths.length) {
    return (
      <section className="primekg-path-panel empty">
        <div>
          <Route size={15} />
          <strong>Evidence Paths</strong>
        </div>
        <p>No Graph RAG evidence paths are available yet. Run a graph or hybrid retrieval workflow to populate readable biomedical paths.</p>
      </section>
    );
  }

  return (
    <section className="primekg-path-panel">
      <div>
        <Route size={15} />
        <strong>Evidence Paths</strong>
      </div>
      <p>Hover or click a path to highlight matching nodes and relationships in the graph.</p>
      <div className="primekg-evidence-path-list">
        {paths.slice(0, 8).map((path, index) => (
          <button
            key={path.id || `${path.pathText}-${index}`}
            type="button"
            className={activePathId === path.id ? "active" : ""}
            onMouseEnter={() => onHoverPath(path)}
            onMouseLeave={() => onHoverPath(null)}
            onClick={() => onSelectPath(path)}
          >
            <span>Path {index + 1}</span>
            <strong>{path.pathText}</strong>
            <small>{path.nodes.length} nodes - {path.relationships.length} relationships</small>
          </button>
        ))}
      </div>
      <button
        type="button"
        className="primekg-copy-path"
        onClick={() => copyPathText(paths[0]?.pathText)}
        disabled={!paths[0]?.pathText}
      >
        <Clipboard size={13} />
        Copy first path text
      </button>
    </section>
  );
}

function copyPathText(text) {
  if (!text || typeof navigator === "undefined" || !navigator.clipboard) {
    return;
  }
  navigator.clipboard.writeText(text).catch(() => {});
}
