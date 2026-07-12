import { Crosshair } from "lucide-react";
import { lazy, Suspense, useCallback, useEffect, useMemo, useRef, useState } from "react";
import ForceGraph2D from "react-force-graph-2d";

import { adaptPrimeKGGraph, cleanEndpoint, filterPrimeKGGraph } from "../utils/primekgGraphAdapter.js";
import EvidencePathPanel from "./EvidencePathPanel.jsx";
import GraphFocusModes from "./GraphFocusModes.jsx";
import GraphInspector from "./GraphInspector.jsx";
import GraphLegend from "./GraphLegend.jsx";
import GraphStatsBar from "./GraphStatsBar.jsx";
import GraphToolbar from "./GraphToolbar.jsx";

const GRAPH_HEIGHT = 680;
const EMPTY_GRAPH = { nodes: [], links: [] };
const ForceGraph3D = lazy(() => import("react-force-graph-3d"));
const DARK_GRAPH_PALETTE = {
  nodeTypes: {
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
  },
  nodeStroke: "rgba(226, 232, 240, 0.75)",
  nodeSelectedStroke: "#f8fafc",
  nodeSelectedHalo: "rgba(248, 250, 252, 0.86)",
  nodeNeighborHalo: "rgba(125, 211, 252, 0.64)",
  nodeFadedAlpha: 0.22,
  nodeSelected3d: "#ffffff",
  nodeFaded3d: "rgba(100, 116, 139, 0.38)",
  labelBg: "rgba(5, 12, 28, 0.74)",
  labelBgStrong: "rgba(5, 12, 28, 0.92)",
  labelBorder: "rgba(148, 163, 184, 0.18)",
  labelBorderStrong: "rgba(248, 250, 252, 0.46)",
  labelText: "#e5f0ff",
  labelTextStrong: "#ffffff",
  labelFadedAlpha: 0.28,
  linkDefault: "rgba(148, 163, 184, 0.32)",
  linkFaded: "rgba(100, 116, 139, 0.18)",
  linkFocus: "rgba(125, 211, 252, 0.82)",
  linkSelected: "rgba(255, 255, 255, 0.88)",
  linkLabelBg: "rgba(3, 7, 18, 0.72)",
  linkLabelBgStrong: "rgba(3, 7, 18, 0.9)",
  linkLabelBorder: "rgba(148, 163, 184, 0.18)",
  linkLabelBorderStrong: "rgba(248, 250, 252, 0.36)",
  linkLabelText: "#b8c7dc",
  linkLabelTextStrong: "#ffffff",
  threeBackground: "rgba(0,0,0,0)",
  threeLinkOpacity: 1,
};
const LIGHT_GRAPH_PALETTE = {
  nodeTypes: {
    disease: "#d92d20",
    drug: "#176a3a",
    "gene/protein": "#155e63",
    pathway: "#6f5f3f",
    phenotype: "#8a5a00",
    biological_process: "#3f6f63",
    molecular_function: "#1f4f66",
    anatomy: "#5f6368",
    exposure: "#7a4f2b",
    other: "#4f5458",
  },
  nodeStroke: "rgba(255, 255, 255, 0.92)",
  nodeSelectedStroke: "#0a0a0a",
  nodeSelectedHalo: "rgba(10, 10, 10, 0.66)",
  nodeNeighborHalo: "rgba(10, 10, 10, 0.34)",
  nodeFadedAlpha: 0.38,
  nodeSelected3d: "#0a0a0a",
  nodeFaded3d: "rgba(95, 99, 104, 0.46)",
  labelBg: "rgba(255, 255, 255, 0.94)",
  labelBgStrong: "rgba(10, 10, 10, 0.92)",
  labelBorder: "rgba(10, 10, 10, 0.14)",
  labelBorderStrong: "rgba(10, 10, 10, 0.45)",
  labelText: "#0a0a0a",
  labelTextStrong: "#ffffff",
  labelFadedAlpha: 0.44,
  linkDefault: "rgba(10, 10, 10, 0.32)",
  linkFaded: "rgba(95, 99, 104, 0.24)",
  linkFocus: "rgba(10, 10, 10, 0.76)",
  linkSelected: "rgba(10, 10, 10, 0.9)",
  linkLabelBg: "rgba(255, 255, 255, 0.92)",
  linkLabelBgStrong: "rgba(10, 10, 10, 0.92)",
  linkLabelBorder: "rgba(10, 10, 10, 0.14)",
  linkLabelBorderStrong: "rgba(10, 10, 10, 0.5)",
  linkLabelText: "#3a352e",
  linkLabelTextStrong: "#ffffff",
  threeBackground: "rgba(0,0,0,0)",
  threeLinkOpacity: 1,
};

export default function PrimeKGGraphExplorer({ graph, retrievals = [], loading = false, error = "", onGraphModeChange }) {
  const graphRef = useRef(null);
  const shellRef = useRef(null);
  const [size, setSize] = useState({ width: 960, height: GRAPH_HEIGHT });
  const [searchText, setSearchText] = useState("");
  const [hiddenNodeTypes, setHiddenNodeTypes] = useState(() => new Set());
  const [hiddenRelationTypes, setHiddenRelationTypes] = useState(() => new Set());
  const [hoveredNode, setHoveredNode] = useState(null);
  const [selectedNode, setSelectedNode] = useState(null);
  const [selectedLink, setSelectedLink] = useState(null);
  const [hoveredLink, setHoveredLink] = useState(null);
  const [hoveredPath, setHoveredPath] = useState(null);
  const [selectedPath, setSelectedPath] = useState(null);
  const [zoomLevel, setZoomLevel] = useState(1);
  const [topN, setTopN] = useState("all");
  const [frozen, setFrozen] = useState(false);
  const [graphMode, setGraphMode] = useState("2d");
  const [webglAvailable, setWebglAvailable] = useState(true);
  const [focusMode, setFocusMode] = useState("overview");
  const [theme, setTheme] = useState(getDocumentTheme);

  const adapted = useMemo(() => adaptPrimeKGGraph(graph), [graph]);
  const graphPalette = useMemo(() => getGraphPalette(theme), [theme]);
  const visibleNodeTypes = useMemo(() => Object.keys(adapted.nodeTypes || {}).filter((type) => !hiddenNodeTypes.has(type)), [adapted.nodeTypes, hiddenNodeTypes]);
  const visibleRelationTypes = useMemo(() => Object.keys(adapted.relationTypes || {}).filter((type) => !hiddenRelationTypes.has(type)), [adapted.relationTypes, hiddenRelationTypes]);
  const filtered = useMemo(() => {
    return filterPrimeKGGraph(adapted, {
      search: searchText,
      nodeTypes: visibleNodeTypes.length ? visibleNodeTypes : [],
      relationTypes: visibleRelationTypes.length ? visibleRelationTypes : [],
    });
  }, [adapted, searchText, visibleNodeTypes, visibleRelationTypes]);

  const limited = useMemo(() => limitGraph(filtered, topN), [filtered, topN]);
  const graphData = useMemo(() => ({
    nodes: limited.nodes.map((node) => ({ ...node })),
    links: limited.links.map((link) => ({ ...link })),
  }), [limited]);

  const selectedNodeId = selectedNode?.id || "";
  const hoveredNodeId = hoveredNode?.id || "";
  const evidencePaths = useMemo(() => extractEvidencePaths(retrievals), [retrievals]);
  const activePath = hoveredPath || selectedPath;
  const pathFocus = useMemo(() => buildPathFocus(graphData, activePath), [activePath, graphData]);
  const diseaseNode = useMemo(() => (
    graphData.nodes.find((node) => node.type === "disease" && matchesDisease(node, adapted.metadata?.disease)) ||
    graphData.nodes.find((node) => node.type === "disease")
  ), [adapted.metadata?.disease, graphData.nodes]);
  const focusModeResult = useMemo(
    () => buildFocusModeFocus(graphData, focusMode, diseaseNode, evidencePaths),
    [diseaseNode, evidencePaths, focusMode, graphData],
  );
  const focus = useMemo(
    () => mergeFocusSets(
      focusModeResult.focus,
      buildFocusSets(graphData.links, selectedNodeId || hoveredNodeId),
      buildLinkFocus(graphData.links, hoveredLink),
      pathFocus,
    ),
    [focusModeResult.focus, graphData.links, hoveredLink, hoveredNodeId, pathFocus, selectedNodeId],
  );
  const inspectorNode = selectedNode || hoveredNode;
  const searchResults = useMemo(() => searchGraphNodes(graphData.nodes, searchText), [graphData.nodes, searchText]);
  const activeFilterCount = hiddenNodeTypes.size + hiddenRelationTypes.size + (searchText.trim() ? 1 : 0) + (topN !== "all" ? 1 : 0);
  const nodesById = useMemo(() => new Map(adapted.nodes.map((node) => [node.id, node])), [adapted.nodes]);

  useEffect(() => {
    const element = shellRef.current;
    if (!element || typeof ResizeObserver === "undefined") {
      return undefined;
    }
    const observer = new ResizeObserver(([entry]) => {
      const width = Math.max(520, Math.floor(entry.contentRect.width));
      const height = Math.max(520, Math.floor(entry.contentRect.height || GRAPH_HEIGHT));
      setSize((current) => (
        current.width === width && current.height === height
          ? current
          : { width, height }
      ));
    });
    observer.observe(element);
    return () => observer.disconnect();
  }, []);

  useEffect(() => {
    setWebglAvailable(canUseWebGL());
  }, []);

  useEffect(() => {
    if (typeof document === "undefined" || typeof MutationObserver === "undefined") {
      return undefined;
    }
    const root = document.documentElement;
    const observer = new MutationObserver(() => setTheme(getDocumentTheme()));
    observer.observe(root, { attributes: true, attributeFilter: ["data-theme"] });
    return () => observer.disconnect();
  }, []);

  useEffect(() => {
    if (graphMode === "3d" && !webglAvailable) {
      setGraphMode("2d");
    }
  }, [graphMode, webglAvailable]);

  useEffect(() => {
    onGraphModeChange?.(graphMode);
  }, [graphMode, onGraphModeChange]);

  useEffect(() => {
    setSelectedNode((current) => current && graphData.nodes.find((node) => node.id === current.id) ? current : null);
    setSelectedLink((current) => current && graphData.links.find((link) => link.id === current.id) ? current : null);
  }, [graphData.links, graphData.nodes]);

  useEffect(() => {
    if (graphData.nodes.length && graphRef.current) {
      const timeout = window.setTimeout(() => graphRef.current?.zoomToFit?.(500, 64), 120);
      return () => window.clearTimeout(timeout);
    }
    return undefined;
  }, [graphData.nodes.length, graphMode]);

  useEffect(() => {
    if (!graphRef.current) return;
    if (frozen) {
      graphRef.current.pauseAnimation?.();
    } else {
      graphRef.current.resumeAnimation?.();
      graphRef.current.d3ReheatSimulation?.();
    }
  }, [frozen]);

  useEffect(() => {
    graphRef.current?.d3ReheatSimulation?.();
  }, [theme]);

  useEffect(() => () => {
    graphRef.current?.pauseAnimation?.();
  }, []);

  const selectAndFocusNode = useCallback((node) => {
    const graphNode = graphData.nodes.find((item) => item.id === node?.id) || node;
    setSelectedNode(graphNode || null);
    setSelectedLink(null);
    if (graphNode) {
      centerNode(graphRef.current, graphNode, graphMode, 2.05);
    }
  }, [graphData.nodes, graphMode]);

  const handleSearchSubmit = useCallback(() => {
    if (searchResults[0]) {
      selectAndFocusNode(searchResults[0]);
    }
  }, [searchResults, selectAndFocusNode]);

  const handleGraphModeChange = useCallback((mode) => {
    if (mode === "3d" && !webglAvailable) return;
    setGraphMode(mode);
  }, [webglAvailable]);

  const handleFitView = useCallback(() => {
    graphRef.current?.zoomToFit?.(500, 72);
  }, []);

  const handleReset = useCallback(() => {
    resetCamera(graphRef.current, graphMode);
  }, [graphMode]);

  const handleCenterDisease = useCallback(() => {
    if (diseaseNode) {
      selectAndFocusNode(diseaseNode);
    }
  }, [diseaseNode, selectAndFocusNode]);

  const handleToggleFreeze = useCallback(() => {
    setFrozen((current) => !current);
  }, []);

  const handleToggleNodeType = useCallback((type) => toggleSet(setHiddenNodeTypes, type), []);
  const handleToggleRelationType = useCallback((type) => toggleSet(setHiddenRelationTypes, type), []);
  const handleHoverLink = useCallback((link) => setHoveredLink(link), []);
  const handleSelectEvidencePath = useCallback((path) => {
    setSelectedPath(path);
    const firstNode = path?.nodes?.[0];
    if (firstNode?.id) {
      selectAndFocusNode(firstNode);
    }
  }, [selectAndFocusNode]);

  useEffect(() => {
    const handleExternalHighlight = (event) => {
      const path = normalizeEvidencePath(event.detail?.path || {}, event.detail?.path?.pathId || event.detail?.path?.id || "external-answer-path");
      if (!path.pathText && !path.nodes.length) return;
      setSelectedPath(path);
      setFocusMode("evidence");
      const firstVisibleNode = path.nodes.find((node) => graphData.nodes.some((graphNode) => graphNode.id === node.id));
      if (firstVisibleNode) {
        selectAndFocusNode(firstVisibleNode);
      }
    };
    window.addEventListener("primekg:highlight-path", handleExternalHighlight);
    return () => window.removeEventListener("primekg:highlight-path", handleExternalHighlight);
  }, [graphData.nodes, selectAndFocusNode]);

  if (loading) {
    return <GraphState title="Loading PrimeKG graph" message="Preparing the bounded biomedical subgraph view." />;
  }

  if (error && !graph) {
    return <GraphState title="Graph unavailable" message={error} tone="warning" />;
  }

  if (!graph) {
    return <GraphState title="No graph loaded" message="Select a disease, then load a bounded read-only graph view." />;
  }

  if (!adapted.nodes.length) {
    return <GraphState title={graph.message || "No PrimeKG graph available"} message={graph.neo4j?.setupHint || "No imported PrimeKG nodes were returned for the current request."} />;
  }

  const visibleCounts = filtered.counts || {};
  const noVisibleResults = graphData.nodes.length === 0;

  return (
    <section className="primekg-explorer">
      <div className="primekg-explorer-topbar">
        <div>
          <h3>PrimeKG Graph Explorer</h3>
          <p>
            {visibleCounts.visibleNodes ?? graphData.nodes.length} of {adapted.counts.nodes} nodes,{" "}
            {visibleCounts.visibleLinks ?? graphData.links.length} of {adapted.counts.links} relationships
            {adapted.metadata?.disease ? ` around ${adapted.metadata.disease}` : ""}
          </p>
        </div>
      </div>

      {adapted.metadata?.warnings?.length ? (
        <div className="primekg-explorer-warning">{adapted.metadata.warnings.join(" ")}</div>
      ) : null}

      <GraphStatsBar
        totalNodes={adapted.counts.nodes}
        totalLinks={adapted.counts.links}
        visibleNodes={graphData.nodes.length}
        visibleLinks={graphData.links.length}
        selectedNode={selectedNode}
        activeFilterCount={activeFilterCount}
      />

      <GraphToolbar
        searchText={searchText}
        searchResults={searchResults}
        topN={topN}
        frozen={frozen}
        graphMode={graphMode}
        webglAvailable={webglAvailable}
        onSearchChange={setSearchText}
        onSearchSubmit={handleSearchSubmit}
        onClearSearch={() => setSearchText("")}
        onSelectSearchResult={selectAndFocusNode}
        activeFocusMode={focusMode}
        evidencePathCount={evidencePaths.length}
        onQuickFilter={setFocusMode}
        onTopNChange={setTopN}
        onGraphModeChange={handleGraphModeChange}
        onFitView={handleFitView}
        onReset={handleReset}
        onCenterDisease={handleCenterDisease}
        onToggleFreeze={handleToggleFreeze}
        disableGraphActions={noVisibleResults}
        hasDisease={Boolean(diseaseNode)}
      />

      <GraphFocusModes
        activeMode={focusMode}
        modeSummary={focusModeResult.summary}
        activeFilterCount={activeFilterCount}
        evidencePathCount={evidencePaths.length}
        onChangeMode={setFocusMode}
      />

      <GraphLegend
        nodeTypes={adapted.nodeTypes}
        relationTypes={adapted.relationTypes}
        hiddenNodeTypes={hiddenNodeTypes}
        hiddenRelationTypes={hiddenRelationTypes}
        nodeTypeColors={graphPalette.nodeTypes}
        onToggleNodeType={handleToggleNodeType}
        onToggleRelationType={handleToggleRelationType}
      />

      <div className="primekg-explorer-grid">
        <div ref={shellRef} className="primekg-force-shell">
          {noVisibleResults ? (
            <div className="primekg-force-empty">
              <strong>No visible graph results</strong>
              <span>Clear search or re-enable filters to bring nodes back.</span>
            </div>
          ) : null}
          {graphMode === "3d" && !webglAvailable ? (
            <div className="primekg-force-empty">
              <strong>3D mode unavailable</strong>
              <span>This browser does not expose WebGL. Use 2D Focus Mode instead.</span>
            </div>
          ) : graphMode === "3d" ? (
            <Suspense fallback={<div className="primekg-force-empty"><strong>Loading 3D graph</strong><span>Preparing the WebGL explorer.</span></div>}>
              <ForceGraph3D
                ref={graphRef}
                width={size.width}
                height={size.height}
                graphData={noVisibleResults ? EMPTY_GRAPH : graphData}
                nodeId="id"
                nodeVal={(node) => node3dValue(node)}
                nodeLabel={(node) => `${node.name}\n${node.type}\nDegree ${node.degree}`}
                nodeColor={(node) => node3dColor(node, focus, selectedNodeId, hoveredNodeId, graphPalette)}
                nodeOpacity={0.96}
                linkSource="source"
                linkTarget="target"
                linkLabel={(link) => link.label}
                linkColor={(link) => linkColor(link, focus, selectedLink, graphPalette)}
                linkOpacity={graphPalette.threeLinkOpacity}
                linkWidth={(link) => isFocusedLink(link, focus, selectedLink) ? 2 : 0.7}
                linkDirectionalParticles={(link) => isFocusedLink(link, focus, selectedLink) ? 3 : graphData.links.length <= 80 ? 1 : 0}
                linkDirectionalParticleColor={(link) => linkColor(link, focus, selectedLink, graphPalette)}
                linkDirectionalParticleWidth={(link) => isFocusedLink(link, focus, selectedLink) ? 2.5 : 0.7}
                cooldownTicks={120}
                d3AlphaDecay={0.028}
                d3VelocityDecay={0.28}
                backgroundColor={graphPalette.threeBackground}
                onNodeHover={(node) => setHoveredNode(node || null)}
                onNodeClick={(node) => {
                  setSelectedNode(node);
                  setSelectedLink(null);
                  setSelectedPath(null);
                  centerNode(graphRef.current, node, "3d", 2.1);
                }}
                onLinkClick={(link) => {
                  setSelectedLink(link);
                  setSelectedNode(null);
                  setSelectedPath(null);
                }}
              />
            </Suspense>
          ) : (
            <ForceGraph2D
              ref={graphRef}
              width={size.width}
              height={size.height}
              graphData={noVisibleResults ? EMPTY_GRAPH : graphData}
              nodeId="id"
              nodeVal={(node) => node.val}
              nodeLabel={(node) => `${node.name}\n${node.type}\nDegree ${node.degree}`}
              linkSource="source"
              linkTarget="target"
              linkLabel={(link) => link.label}
              linkCurvature={0.18}
              linkDirectionalArrowLength={4}
              linkDirectionalArrowRelPos={0.92}
              linkDirectionalParticles={(link) => isFocusedLink(link, focus, selectedLink) ? 2 : graphData.links.length <= 80 ? 1 : 0}
              linkDirectionalParticleWidth={(link) => isFocusedLink(link, focus, selectedLink) ? 1.8 : 0.75}
              cooldownTicks={90}
              d3AlphaDecay={0.035}
              d3VelocityDecay={0.34}
              enableNodeDrag
              enablePanInteraction
              enableZoomInteraction
              onZoom={({ k }) => setZoomLevel(k)}
              onNodeHover={(node) => setHoveredNode(node || null)}
              onNodeClick={(node) => {
                setSelectedNode(node);
                setSelectedLink(null);
                setSelectedPath(null);
                centerNode(graphRef.current, node, "2d", 1.7);
              }}
              onLinkClick={(link) => {
                setSelectedLink(link);
                setSelectedNode(null);
                setSelectedPath(null);
              }}
              nodeCanvasObjectMode={() => "replace"}
              nodeCanvasObject={(node, ctx, globalScale) => paintNode(node, ctx, globalScale, {
                selectedNodeId,
                hoveredNodeId,
                focus,
                zoomLevel,
                graphSize: graphData.nodes.length,
                palette: graphPalette,
              })}
              linkCanvasObjectMode={() => "after"}
              linkCanvasObject={(link, ctx, globalScale) => paintLinkLabel(link, ctx, globalScale, {
                selectedLink,
                focus,
                zoomLevel,
                graphSize: graphData.links.length,
                palette: graphPalette,
              })}
              linkColor={(link) => linkColor(link, focus, selectedLink, graphPalette)}
              linkWidth={(link) => isFocusedLink(link, focus, selectedLink) ? 2.2 : 0.8}
              linkDirectionalParticleColor={(link) => linkColor(link, focus, selectedLink, graphPalette)}
            />
          )}
          <div className="primekg-zoom-readout">
            <Crosshair size={14} />
            {graphMode === "3d" ? "3D orbit" : `${zoomLevel.toFixed(2)}x`}
          </div>
        </div>

        <GraphInspector
          node={inspectorNode}
          link={selectedLink}
          adjacency={adapted.adjacency}
          nodesById={nodesById}
          selected={Boolean(selectedNode || selectedLink)}
          nodeTypeColors={graphPalette.nodeTypes}
          onFocusNode={selectAndFocusNode}
          onHoverLink={handleHoverLink}
        />
      </div>

      <EvidencePathPanel
        paths={evidencePaths}
        activePathId={activePath?.id || ""}
        onHoverPath={setHoveredPath}
        onSelectPath={handleSelectEvidencePath}
      />
    </section>
  );
}

function GraphState({ title, message, tone = "neutral" }) {
  return (
    <section className={`primekg-explorer-state ${tone}`}>
      <strong>{title}</strong>
      <span>{message}</span>
    </section>
  );
}

function limitGraph(graph, topN) {
  if (topN === "all" || !Number(topN)) {
    return graph;
  }
  const limit = Number(topN);
  const ranked = [...graph.nodes].sort((left, right) => {
    const leftWeight = nodeRankWeight(left);
    const rightWeight = nodeRankWeight(right);
    return rightWeight - leftWeight || String(left.name).localeCompare(String(right.name));
  });
  const allowed = new Set(ranked.slice(0, limit).map((node) => node.id));
  const links = graph.links.filter((link) => allowed.has(cleanEndpoint(link.source)) && allowed.has(cleanEndpoint(link.target)));
  const degree = {};
  links.forEach((link) => {
    const source = cleanEndpoint(link.source);
    const target = cleanEndpoint(link.target);
    degree[source] = (degree[source] || 0) + 1;
    degree[target] = (degree[target] || 0) + 1;
  });
  const nodes = ranked
    .filter((node) => allowed.has(node.id))
    .map((node) => ({ ...node, degree: degree[node.id] || 0 }));
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

function searchGraphNodes(nodes, query, allowedTypes) {
  const term = String(query || "").trim().toLowerCase();
  if (!term) {
    return [];
  }
  return nodes
    .filter((node) => (!allowedTypes || allowedTypes.has(node.type)) && node.searchText.includes(term))
    .sort((left, right) => {
      const leftStarts = String(left.name).toLowerCase().startsWith(term) ? 1 : 0;
      const rightStarts = String(right.name).toLowerCase().startsWith(term) ? 1 : 0;
      return rightStarts - leftStarts || nodeRankWeight(right) - nodeRankWeight(left) || String(left.name).localeCompare(String(right.name));
    })
    .slice(0, 8);
}

function nodeRankWeight(node) {
  const typeBoost = {
    disease: 100,
    drug: 60,
    "gene/protein": 55,
    pathway: 50,
    biological_process: 48,
    molecular_function: 42,
    phenotype: 40,
  };
  return (node.degree || 0) * 12 + (typeBoost[node.type] || 10);
}

function paintNode(node, ctx, globalScale, state) {
  const palette = state.palette || DARK_GRAPH_PALETTE;
  const focused = state.selectedNodeId === node.id || state.hoveredNodeId === node.id;
  const neighbor = state.focus.nodes.has(node.id);
  const faded = state.focus.active && !focused && !neighbor;
  const radius = nodeRadius(node);

  ctx.save();
  ctx.globalAlpha = faded ? palette.nodeFadedAlpha : 1;
  const glow = focused ? 18 : neighbor ? 10 : 0;
  if (glow) {
    ctx.shadowColor = focused ? palette.nodeSelectedHalo : typeColor(node.type, palette);
    ctx.shadowBlur = glow;
  }
  if (focused || neighbor) {
    ctx.beginPath();
    ctx.arc(node.x, node.y, radius + (focused ? 5.5 : 3.5), 0, 2 * Math.PI, false);
    ctx.lineWidth = Math.max(2, (focused ? 5 : 3) / Math.max(1, globalScale * 0.7));
    ctx.strokeStyle = focused ? palette.nodeSelectedHalo : palette.nodeNeighborHalo;
    ctx.stroke();
  }
  ctx.beginPath();
  ctx.arc(node.x, node.y, radius, 0, 2 * Math.PI, false);
  ctx.fillStyle = typeColor(node.type, palette);
  ctx.fill();
  ctx.lineWidth = focused ? 2.8 : 1.2;
  ctx.strokeStyle = focused ? palette.nodeSelectedStroke : palette.nodeStroke;
  ctx.stroke();
  ctx.restore();

  if (shouldShowLabel(node, focused, neighbor, state)) {
    paintNodeLabel(node, ctx, globalScale, radius, { faded, focused, neighbor, palette });
  }
}

function paintNodeLabel(node, ctx, globalScale, radius, state) {
  const label = truncate(node.label || node.name || node.id, 34);
  const fontSize = Math.max(9, 13 / Math.max(1, globalScale * 0.58));
  const emphasized = state.focused || state.neighbor;
  ctx.save();
  ctx.globalAlpha = state.faded ? state.palette.labelFadedAlpha : 0.98;
  ctx.font = `${emphasized ? 760 : 620} ${fontSize}px Inter, system-ui, sans-serif`;
  ctx.textAlign = "center";
  ctx.textBaseline = "middle";
  const width = ctx.measureText(label).width + 14;
  const y = node.y + radius + fontSize * 0.9;
  roundRect(ctx, node.x - width / 2, y - fontSize / 2 - 5, width, fontSize + 10, 7);
  ctx.fillStyle = emphasized ? state.palette.labelBgStrong : state.palette.labelBg;
  ctx.fill();
  ctx.lineWidth = 1;
  ctx.strokeStyle = emphasized ? state.palette.labelBorderStrong : state.palette.labelBorder;
  ctx.stroke();
  ctx.fillStyle = emphasized ? state.palette.labelTextStrong : state.palette.labelText;
  ctx.fillText(label, node.x, y);
  ctx.restore();
}

function paintLinkLabel(link, ctx, globalScale, state) {
  if (!isFocusedLink(link, state.focus, state.selectedLink) && (state.zoomLevel < 1.55 || state.graphSize > 120)) {
    return;
  }
  const source = typeof link.source === "object" ? link.source : null;
  const target = typeof link.target === "object" ? link.target : null;
  if (!source || !target) {
    return;
  }
  const label = truncate(link.label || link.display_relation || link.relation, 28);
  const midX = (source.x + target.x) / 2;
  const midY = (source.y + target.y) / 2;
  const fontSize = Math.max(7, 10 / Math.max(1, globalScale * 0.55));
  const selected = isFocusedLink(link, state.focus, state.selectedLink);
  const palette = state.palette || DARK_GRAPH_PALETTE;
  ctx.save();
  ctx.font = `${selected ? 720 : 560} ${fontSize}px Inter, system-ui, sans-serif`;
  ctx.textAlign = "center";
  ctx.textBaseline = "middle";
  const width = ctx.measureText(label).width + 10;
  roundRect(ctx, midX - width / 2, midY - fontSize / 2 - 3, width, fontSize + 6, 6);
  ctx.fillStyle = selected ? palette.linkLabelBgStrong : palette.linkLabelBg;
  ctx.fill();
  ctx.lineWidth = 1;
  ctx.strokeStyle = selected ? palette.linkLabelBorderStrong : palette.linkLabelBorder;
  ctx.stroke();
  ctx.fillStyle = selected ? palette.linkLabelTextStrong : palette.linkLabelText;
  ctx.fillText(label, midX, midY);
  ctx.restore();
}

function buildFocusModeFocus(graphData, mode, diseaseNode, evidencePaths) {
  if (!mode || mode === "overview") {
    return {
      focus: emptyFocus(),
      summary: {
        description: "Overview mode keeps the full bounded subgraph visible for orientation before narrowing the story.",
        countText: `${graphData.nodes.length} visible nodes and ${graphData.links.length} visible relationships.`,
      },
    };
  }

  if (mode === "evidence") {
    const merged = mergeFocusSets(...(evidencePaths || []).map((path) => buildPathFocus(graphData, path)));
    return {
      focus: merged,
      summary: {
        description: merged.active
          ? "Evidence mode highlights readable Graph RAG paths returned by graph or hybrid retrieval."
          : "Evidence mode needs graph or hybrid retrieval results with readable paths before it can highlight the story.",
        countText: merged.active ? `${merged.nodes.size} path nodes and ${merged.links.size} path relationships highlighted.` : "No evidence paths available yet.",
      },
    };
  }

  if (mode === "disease") {
    const focus = buildFocusSets(graphData.links, diseaseNode?.id);
    return {
      focus,
      summary: {
        description: "Disease Neighborhood mode emphasizes the disease anchor and its direct biomedical neighbors.",
        countText: focus.active ? `${focus.nodes.size} direct-neighborhood nodes highlighted.` : "No disease anchor found in the visible graph.",
      },
    };
  }

  const modeConfig = {
    treatments: {
      nodeTypes: ["drug"],
      relationPatterns: [/treat/i, /therapy/i, /indication/i, /drug/i, /target/i, /off-label/i],
      description: "Treatment mode highlights drug nodes and relationships that connect them back to the selected disease.",
    },
    mechanisms: {
      nodeTypes: ["gene/protein", "pathway", "biological_process", "molecular_function"],
      relationPatterns: [/associated/i, /interacts/i, /ppi/i, /expression/i, /pathway/i, /process/i],
      description: "Mechanism mode highlights genes, proteins, pathways, and biological processes that may explain the disease.",
    },
    phenotypes: {
      nodeTypes: ["phenotype"],
      relationPatterns: [/phenotype/i, /symptom/i, /manifest/i, /present/i],
      matchRelations: true,
      description: "Phenotype mode highlights symptom and phenotype nodes connected to the disease-centered graph.",
    },
  }[mode];

  if (!modeConfig) {
    return { focus: emptyFocus(), summary: null };
  }

  const focus = buildBiomedicalModeFocus(graphData, diseaseNode, modeConfig);
  return {
    focus,
    summary: {
      description: modeConfig.description,
      countText: focus.active ? `${focus.nodes.size} nodes and ${focus.links.size} relationships highlighted.` : "No matching visible nodes for this focus mode.",
    },
  };
}

function buildBiomedicalModeFocus(graphData, diseaseNode, config) {
  const focus = emptyFocus();
  const nodeTypes = new Set(config.nodeTypes || []);
  const diseaseId = diseaseNode?.id || "";
  const diseaseNeighbors = new Set();
  const relationMatches = (link) => config.relationPatterns?.some((pattern) => pattern.test(link.display_relation || link.relation || link.label || "")) || false;

  if (diseaseId) {
    focus.active = true;
    focus.nodes.add(diseaseId);
    graphData.links.forEach((link) => {
      const source = cleanEndpoint(link.source);
      const target = cleanEndpoint(link.target);
      if (source === diseaseId || target === diseaseId) {
        diseaseNeighbors.add(source === diseaseId ? target : source);
        if (relationMatches(link)) {
          focus.links.add(link.id);
          focus.nodes.add(source);
          focus.nodes.add(target);
        }
      }
    });
  }

  const nodesById = new Map(graphData.nodes.map((node) => [node.id, node]));
  graphData.nodes.forEach((node) => {
    if (nodeTypes.has(node.type)) {
      focus.active = true;
      focus.nodes.add(node.id);
    }
  });

  graphData.links.forEach((link) => {
    const source = cleanEndpoint(link.source);
    const target = cleanEndpoint(link.target);
    const sourceNode = nodesById.get(source);
    const targetNode = nodesById.get(target);
    const endpointMatchesType = nodeTypes.has(sourceNode?.type) || nodeTypes.has(targetNode?.type);
    const touchesDiseaseStory = !diseaseId || source === diseaseId || target === diseaseId || diseaseNeighbors.has(source) || diseaseNeighbors.has(target);
    if ((endpointMatchesType && touchesDiseaseStory) || (relationMatches(link) && (config.matchRelations || endpointMatchesType || touchesDiseaseStory))) {
      focus.active = true;
      focus.links.add(link.id);
      focus.nodes.add(source);
      focus.nodes.add(target);
    }
  });

  return focus;
}

function emptyFocus() {
  return { active: false, nodes: new Set(), links: new Set() };
}

function buildFocusSets(links, nodeId) {
  const nodes = new Set();
  const linksSet = new Set();
  if (!nodeId) {
    return { active: false, nodes, links: linksSet };
  }
  nodes.add(nodeId);
  links.forEach((link) => {
    const source = cleanEndpoint(link.source);
    const target = cleanEndpoint(link.target);
    if (source === nodeId || target === nodeId) {
      nodes.add(source);
      nodes.add(target);
      linksSet.add(link.id);
    }
  });
  return { active: true, nodes, links: linksSet };
}

function buildLinkFocus(links, link) {
  const nodes = new Set();
  const linksSet = new Set();
  if (!link?.id) {
    return { active: false, nodes, links: linksSet };
  }
  const matched = links.find((item) => item.id === link.id) || link;
  const source = cleanEndpoint(matched.source);
  const target = cleanEndpoint(matched.target);
  if (source) nodes.add(source);
  if (target) nodes.add(target);
  linksSet.add(matched.id);
  return { active: true, nodes, links: linksSet };
}

function buildPathFocus(graphData, path) {
  const nodes = new Set();
  const linksSet = new Set();
  if (!path) {
    return { active: false, nodes, links: linksSet };
  }
  (path.nodes || []).forEach((node) => {
    const id = cleanEndpoint(node);
    if (id) nodes.add(id);
  });
  (path.relationships || []).forEach((relationship) => {
    const match = findMatchingGraphLink(graphData.links, relationship);
    if (match?.id) {
      linksSet.add(match.id);
      nodes.add(cleanEndpoint(match.source));
      nodes.add(cleanEndpoint(match.target));
    }
  });
  return { active: nodes.size > 0 || linksSet.size > 0, nodes, links: linksSet };
}

function mergeFocusSets(...sets) {
  const merged = { active: false, nodes: new Set(), links: new Set() };
  sets.forEach((set) => {
    if (!set?.active) return;
    merged.active = true;
    set.nodes.forEach((node) => merged.nodes.add(node));
    set.links.forEach((link) => merged.links.add(link));
  });
  return merged;
}

function findMatchingGraphLink(links, relationship) {
  const source = cleanEndpoint(relationship.source || relationship.source_id);
  const target = cleanEndpoint(relationship.target || relationship.target_id);
  const relation = String(relationship.displayRelation || relationship.display_relation || relationship.relation || "").toLowerCase();
  return links.find((link) => {
    const linkSource = cleanEndpoint(link.source);
    const linkTarget = cleanEndpoint(link.target);
    const linkRelation = String(link.label || link.display_relation || link.relation || "").toLowerCase();
    const sameDirection = linkSource === source && linkTarget === target;
    const reverseDirection = linkSource === target && linkTarget === source;
    return (sameDirection || reverseDirection) && (!relation || linkRelation === relation || linkRelation.includes(relation) || relation.includes(linkRelation));
  });
}

function isFocusedLink(link, focus, selectedLink) {
  return selectedLink?.id === link.id || focus.links.has(link.id);
}

function linkColor(link, focus, selectedLink, palette = DARK_GRAPH_PALETTE) {
  if (selectedLink?.id === link.id) return palette.linkSelected;
  if (focus.links.has(link.id)) return palette.linkFocus;
  if (focus.active) return palette.linkFaded;
  return palette.linkDefault;
}

function node3dValue(node) {
  const base = node.type === "disease" ? 10 : node.type === "drug" ? 7.8 : node.type === "gene/protein" ? 7.2 : 5.8;
  return Math.min(base + Math.sqrt(Math.max(0, node.degree || 0)) * 1.8, 20);
}

function node3dColor(node, focus, selectedNodeId, hoveredNodeId, palette = DARK_GRAPH_PALETTE) {
  const focused = selectedNodeId === node.id || hoveredNodeId === node.id;
  const neighbor = focus.nodes.has(node.id);
  if (focused) return palette.nodeSelected3d;
  if (focus.active && !neighbor) return palette.nodeFaded3d;
  return typeColor(node.type, palette);
}

function nodeRadius(node) {
  const base = node.type === "disease" ? 8.5 : node.type === "drug" ? 7 : node.type === "gene/protein" ? 6.8 : 5.5;
  return Math.min(base + Math.sqrt(Math.max(0, node.degree || 0)) * 1.7, 18);
}

function shouldShowLabel(node, focused, neighbor, state) {
  if (focused || neighbor) return true;
  if (state.graphSize <= 35) return true;
  if (state.zoomLevel > 1.65 && node.degree >= 2) return true;
  return node.type === "disease" && state.zoomLevel > 1.1;
}

function typeColor(type, palette = DARK_GRAPH_PALETTE) {
  return palette.nodeTypes[type] || palette.nodeTypes.other;
}

function getDocumentTheme() {
  if (typeof document === "undefined") {
    return "dark";
  }
  return document.documentElement.dataset.theme === "light" ? "light" : "dark";
}

function getGraphPalette(theme) {
  return theme === "light" ? LIGHT_GRAPH_PALETTE : DARK_GRAPH_PALETTE;
}

function toggleSet(setter, value) {
  setter((current) => {
    const next = new Set(current);
    if (next.has(value)) next.delete(value);
    else next.add(value);
    return next;
  });
}

function centerNode(graph, node, mode = "2d", zoom = 2.1) {
  if (!graph || !node) return;
  if (mode === "3d" && graph.cameraPosition) {
    const distance = Math.max(90, 210 / Math.max(0.7, zoom));
    const distRatio = 1 + distance / Math.hypot(node.x || 1, node.y || 1, node.z || 1);
    graph.cameraPosition(
      {
        x: (node.x || 0) * distRatio,
        y: (node.y || 0) * distRatio,
        z: (node.z || 0) * distRatio + distance,
      },
      { x: node.x || 0, y: node.y || 0, z: node.z || 0 },
      650,
    );
    return;
  }
  graph.centerAt?.(node.x || 0, node.y || 0, 550);
  graph.zoom?.(zoom, 550);
}

function resetCamera(graph, mode = "2d") {
  if (!graph) return;
  graph.d3ReheatSimulation?.();
  if (mode === "3d" && graph.cameraPosition) {
    graph.cameraPosition({ x: 0, y: 0, z: 520 }, { x: 0, y: 0, z: 0 }, 650);
    window.setTimeout(() => graph.zoomToFit?.(500, 72), 80);
    return;
  }
  graph.centerAt?.(0, 0, 500);
  graph.zoomToFit?.(650, 72);
}

function matchesDisease(node, disease) {
  if (!disease) return false;
  return `${node.name} ${node.id}`.toLowerCase().includes(String(disease).toLowerCase());
}

function truncate(value, length) {
  const text = String(value || "").trim();
  if (text.length <= length) return text;
  return `${text.slice(0, Math.max(0, length - 3))}...`;
}

function extractEvidencePaths(retrievals) {
  const paths = [];
  (retrievals || []).forEach((retrieval, retrievalIndex) => {
    const evidence = retrieval?.graphEvidence;
    if (!evidence) return;
    (evidence.paths || []).forEach((path, pathIndex) => {
      paths.push(normalizeEvidencePath(path, `${retrieval.nodeId || retrievalIndex}-${pathIndex}`));
    });
    if (!evidence.paths?.length && evidence.path_text?.length) {
      evidence.path_text.forEach((pathText, pathIndex) => {
        paths.push({
          id: `${retrieval.nodeId || retrievalIndex}-text-${pathIndex}`,
          pathText,
          nodes: [],
          relationships: [],
        });
      });
    }
  });
  return paths.filter((path) => path.pathText);
}

function normalizeEvidencePath(path, id) {
  const nodes = (path.nodes || []).map((node) => ({
    id: cleanEndpoint(node.id || node.prime_id || node.name),
    name: node.name || node.id || node.prime_id,
    type: node.type || node.node_type || "other",
  }));
  const relationships = (path.relationships || []).map((relationship) => ({
    source: cleanEndpoint(relationship.source),
    target: cleanEndpoint(relationship.target),
    relation: relationship.relation,
    displayRelation: relationship.displayRelation || relationship.display_relation || relationship.relation,
  }));
  return {
    id,
    pathText: path.path_text || path.pathText || "",
    nodes,
    relationships,
  };
}

function roundRect(ctx, x, y, width, height, radius) {
  ctx.beginPath();
  ctx.moveTo(x + radius, y);
  ctx.arcTo(x + width, y, x + width, y + height, radius);
  ctx.arcTo(x + width, y + height, x, y + height, radius);
  ctx.arcTo(x, y + height, x, y, radius);
  ctx.arcTo(x, y, x + width, y, radius);
  ctx.closePath();
}

function canUseWebGL() {
  if (typeof document === "undefined") {
    return false;
  }
  try {
    const canvas = document.createElement("canvas");
    return Boolean(canvas.getContext("webgl") || canvas.getContext("experimental-webgl"));
  } catch {
    return false;
  }
}
