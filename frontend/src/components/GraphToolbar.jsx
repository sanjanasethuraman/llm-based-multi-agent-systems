import { Box, Focus, LocateFixed, Pause, Play, RotateCcw, ScanLine, Search, X, Zap } from "lucide-react";

import IconButton from "./IconButton.jsx";

const TOP_N_OPTIONS = ["all", 50, 100, 200];

export default function GraphToolbar({
  searchText,
  searchResults = [],
  topN,
  frozen,
  graphMode,
  webglAvailable,
  activeFocusMode,
  evidencePathCount = 0,
  onSearchChange,
  onSearchSubmit,
  onClearSearch,
  onSelectSearchResult,
  onQuickFilter,
  onTopNChange,
  onGraphModeChange,
  onFitView,
  onReset,
  onCenterDisease,
  onToggleFreeze,
  disableGraphActions,
  hasDisease,
}) {
  return (
    <div className="primekg-toolbar">
      <div className="primekg-toolbar-row">
        <label className="primekg-search">
          <Search size={15} />
          <input
            value={searchText}
            onChange={(event) => onSearchChange(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === "Enter") {
                event.preventDefault();
                onSearchSubmit();
              }
            }}
            placeholder="Search node name, type, relation"
          />
          {searchText ? <button type="button" onClick={onClearSearch} aria-label="Clear graph search"><X size={14} /></button> : null}
          {searchResults.length ? (
            <div className="primekg-search-results">
              {searchResults.slice(0, 7).map((node) => (
                <button key={node.id} type="button" onClick={() => onSelectSearchResult(node)}>
                  <strong>{node.name}</strong>
                  <span>{node.type} - degree {node.degree}</span>
                </button>
              ))}
            </div>
          ) : null}
        </label>

        <div className="primekg-segmented" aria-label="Top N graph nodes">
          {TOP_N_OPTIONS.map((option) => (
            <button
              key={option}
              type="button"
              className={String(topN) === String(option) ? "active" : ""}
              onClick={() => onTopNChange(option)}
            >
              {option === "all" ? "All" : `Top ${option}`}
            </button>
          ))}
        </div>

        <div className="primekg-segmented mode" aria-label="Graph view mode">
          <button
            type="button"
            className={graphMode === "2d" ? "active" : ""}
            onClick={() => onGraphModeChange("2d")}
          >
            <ScanLine size={13} />
            2D Focus
          </button>
          <button
            type="button"
            className={graphMode === "3d" ? "active" : ""}
            onClick={() => onGraphModeChange("3d")}
            disabled={!webglAvailable}
            title={webglAvailable ? "Explore in WebGL 3D" : "WebGL is not available in this browser"}
          >
            <Box size={13} />
            3D Explore
          </button>
        </div>
      </div>

      <div className="primekg-toolbar-row lower">
        <div className="primekg-quick-filters">
          <button type="button" className={activeFocusMode === "disease" ? "active" : ""} onClick={() => onQuickFilter("disease")}>
            <Zap size={13} />
            Disease Neighborhood
          </button>
          <button type="button" className={activeFocusMode === "treatments" ? "active" : ""} onClick={() => onQuickFilter("treatments")}>Treatments</button>
          <button type="button" className={activeFocusMode === "mechanisms" ? "active" : ""} onClick={() => onQuickFilter("mechanisms")}>Mechanisms</button>
          <button type="button" className={activeFocusMode === "phenotypes" ? "active" : ""} onClick={() => onQuickFilter("phenotypes")}>Phenotypes</button>
          <button
            type="button"
            className={activeFocusMode === "evidence" ? "active" : ""}
            onClick={() => onQuickFilter("evidence")}
            disabled={evidencePathCount === 0}
            title={evidencePathCount === 0 ? "Run graph or hybrid retrieval to populate evidence paths." : "Highlight Graph RAG evidence paths."}
          >
            Evidence Paths
          </button>
          <button type="button" className={activeFocusMode === "overview" ? "active" : ""} onClick={() => onQuickFilter("overview")}>Overview</button>
        </div>

        <div className="primekg-explorer-actions">
          <IconButton icon={Focus} label="Fit View" onClick={onFitView} disabled={disableGraphActions} />
          <IconButton icon={RotateCcw} label="Reset" onClick={onReset} disabled={disableGraphActions} />
          <IconButton icon={frozen ? Play : Pause} label={frozen ? "Unfreeze" : "Freeze"} onClick={onToggleFreeze} disabled={disableGraphActions} />
          <IconButton icon={LocateFixed} label="Center Disease" onClick={onCenterDisease} disabled={!hasDisease} />
        </div>
      </div>
    </div>
  );
}
