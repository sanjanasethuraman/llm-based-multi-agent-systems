import { CheckCircle2, CircleDashed, Database, FileText, HelpCircle, Network, RefreshCcw, Search, ServerCrash, Sparkles } from "lucide-react";
import { useState } from "react";

import DiseaseCombobox from "./DiseaseCombobox.jsx";
import IconButton from "./IconButton.jsx";
import PrimeKGGraphExplorer from "./PrimeKGGraphExplorer.jsx";

export default function PrimeKGPanel({
  form,
  status,
  loading,
  graph,
  retrievals = [],
  error,
  onFormChange,
  onRefreshStatus,
  onLoadGraph,
  presentationMode = false,
}) {
  const [graphViewMode, setGraphViewMode] = useState("2d");
  const updateField = (field, value) => onFormChange((current) => ({ ...current, [field]: value }));
  const neo4jConnected = Boolean(status?.neo4jConnected || status?.neo4j?.connected);
  const fileFound = Boolean(status?.fileExists);
  const graphDisabled = !neo4jConnected || loading === "graph";
  const statusClass = neo4jConnected && fileFound ? "success" : fileFound ? "warning" : "neutral";
  const datasetComplete = Boolean(status?.datasetComplete);
  const graphLoaded = Boolean(graph?.status === "available" && (graph?.nodes?.length || graph?.stats?.nodeCount));
  const answerGraphLoaded = graphLoaded && graph?.mode === "answer";
  const selectedDisease = form.disease?.trim();
  const graphModeLabel = graphViewMode === "3d" ? "3D Explore" : "2D Focus";
  const graphNodeCount = graph?.stats?.nodeCount || graph?.nodes?.length || 0;
  const graphRelationshipCount = graph?.stats?.relationshipCount || graph?.relationships?.length || graph?.links?.length || 0;
  const workflowSteps = [
    { label: "Select disease", detail: selectedDisease || "Choose a disease", done: Boolean(selectedDisease) },
    { label: "Find disease", detail: neo4jConnected ? "Neo4j lookup" : "waiting for Neo4j", done: neo4jConnected },
    { label: "Load graph", detail: graphLoaded ? graphModeLabel : "bounded viewer", done: graphLoaded },
    { label: "Ask question", detail: retrievals.length ? "evidence available" : "Graph RAG ready", done: Boolean(retrievals.length) },
  ];

  return (
    <section className={`primekg-panel ${presentationMode ? "primekg-panel--presentation" : ""}`}>
      <div className="primekg-hero">
        <div className="primekg-hero-copy">
          <span><Sparkles size={14} /> Flagship biomedical graph workflow</span>
          <h2>Biomedical Knowledge Graph</h2>
          <p>Explore bounded disease-centered views from the complete PrimeKG graph and use graph evidence in RAG answers.</p>
          <p className="primekg-mode-helper">
            Select a disease to explore its graph. Asking a question can also auto-detect relevant entities from the imported Neo4j graph.
          </p>
        </div>
        <div className="primekg-hero-actions">
          <IconButton icon={RefreshCcw} label={loading === "status" ? "Checking" : "Check Status"} onClick={onRefreshStatus} disabled={loading === "status"} />
          <IconButton icon={Network} label={loading === "graph" ? "Loading Graph" : "Load Graph"} variant="primary" onClick={onLoadGraph} disabled={graphDisabled} />
        </div>
      </div>

      <div className="primekg-status-grid" aria-label="PrimeKG demo readiness">
        <StatusCard icon={FileText} title="PrimeKG CSV" detail={fileFound ? `Found at ${status?.defaultCsvPath || "data/primekg/kg.csv"}` : "Missing from data/primekg/kg.csv"} ready={fileFound} />
        <StatusCard icon={neo4jConnected ? Database : ServerCrash} title="Neo4j" detail={neo4jConnected ? "Connected to PrimeKG" : status?.neo4j?.message || "Offline"} ready={neo4jConnected} />
        <StatusCard icon={Database} title="Dataset" detail={datasetComplete ? "Complete PrimeKG loaded" : "PrimeKG import not confirmed"} ready={datasetComplete} />
        <StatusCard icon={Search} title="Selected Disease" detail={selectedDisease || "No disease selected yet"} ready={Boolean(selectedDisease)} />
        <StatusCard icon={Network} title="Graph Loaded" detail={graphLoaded ? `${graphNodeCount} nodes, ${graphRelationshipCount} relationships` : "Not loaded yet"} ready={graphLoaded} />
      </div>

      <div className={`provider-note primekg-status-note ${statusClass}`}>
        <div>
          <strong>PrimeKG:</strong>{" "}
          {fileFound ? `kg.csv found at ${status.defaultCsvPath || "data/primekg/kg.csv"}` : status?.message || "kg.csv has not been checked yet."}
        </div>
        <div>Neo4j: {neo4jConnected ? "connected" : status?.neo4j?.message || "offline"}</div>
        {!fileFound ? <div>Place the dataset at data/primekg/kg.csv, then check status again.</div> : null}
        {!neo4jConnected ? <div>{status?.neo4j?.setupHint || "Start Neo4j before loading the graph view."}</div> : null}
      </div>

      <div className="primekg-workflow-steps" aria-label="PrimeKG workflow steps">
        {workflowSteps.map((step, index) => (
          <div key={step.label} className={step.done ? "done" : ""}>
            <span>{index + 1}</span>
            <strong>{step.label}</strong>
            <small>{step.detail}</small>
          </div>
        ))}
      </div>
      <p className="context-helper">
        Explore Mode uses the selected disease to focus the 2D/3D viewer. Ask Mode can answer graph or hybrid questions without a required disease selection.
      </p>

      <div className="primekg-control-surface">
        <div className="primekg-control-heading">
          <span>Step 1</span>
          <strong>Explore a bounded read-only disease graph</strong>
        </div>

        <div className="primekg-grid">
          <div className="primekg-disease-field">
            <DiseaseCombobox label="Explore disease" value={form.disease} onChange={(value) => updateField("disease", value)} />
            <p>This controls graph exploration only. Graph RAG questions can still auto-detect entities when this is blank.</p>
            <div className={`primekg-ask-hint ${form.disease?.trim() ? "hinted" : "auto"}`}>
              {form.disease?.trim() ? "Using selected disease as graph hint" : "Auto-detecting graph entities from question"}
            </div>
          </div>
          <div className="primekg-depth-control">
            <span>Depth</span>
            <div className="primekg-depth-segments">
              {[1, 2, 3].map((depth) => (
                <button
                  key={depth}
                  type="button"
                  className={Number(form.depth) === depth ? "active" : ""}
                  onClick={() => updateField("depth", depth)}
                >
                  <strong>{depth}</strong>
                  <small>{depth === 1 ? "direct" : depth === 2 ? "paths" : "broad"}</small>
                </button>
              ))}
            </div>
          </div>
          <label className="primekg-compact-input">
            Max Nodes
            <input type="number" min="1" max="5000" value={form.maxNodes} onChange={(event) => updateField("maxNodes", Number(event.target.value))} />
          </label>
          <label className="primekg-compact-input">
            Max Relationships
            <input type="number" min="1" max="15000" value={form.maxRelationships} onChange={(event) => updateField("maxRelationships", Number(event.target.value))} />
          </label>
        </div>

        {Number(form.depth) === 3 ? (
          <div className="provider-note warning compact">Depth 3 can grow quickly. The backend enforces bounded graph caps.</div>
        ) : null}

        <div className="inline-actions primekg-actions">
          <IconButton icon={Network} label={loading === "graph" ? "Loading Graph" : "Load In-App Graph"} variant="primary" onClick={onLoadGraph} disabled={graphDisabled} />
        </div>
      </div>

      {error ? <div className="provider-note warning">{error}</div> : null}
      {!fileFound ? <PrimeKGEmptyState icon={FileText} title="PrimeKG kg.csv missing" message="Download PrimeKG and place kg.csv in data/primekg/kg.csv to enable disease search." /> : null}
      {fileFound && !neo4jConnected ? <PrimeKGEmptyState icon={ServerCrash} title="Neo4j offline" message="Graph loading requires Neo4j to be running with PrimeKG imported." /> : null}

      <div className="primekg-graph-stage">
        <div className="primekg-graph-heading">
          <div>
            <span>Step 4</span>
            <h3>{answerGraphLoaded ? "Answer Graph" : "Explore the imported graph"}</h3>
            <p>Use the in-app graph explorer for biomedical paths, selected-node details, relationships, and Graph RAG evidence. The visual focus can differ from the evidence routes used by an answer.</p>
            {answerGraphLoaded ? (
              <p className="primekg-answer-graph-label">
                Showing a bounded graph around answer evidence.
                {graph?.answerGraph?.questionSnippet ? ` Question: ${graph.answerGraph.questionSnippet}` : ""}
              </p>
            ) : null}
          </div>
          {answerGraphLoaded ? (
            <IconButton icon={Network} label="Return to selected disease graph" onClick={onLoadGraph} disabled={loading === "graph"} />
          ) : !graphLoaded ? <small>No graph loaded yet. Select a disease, then load the graph viewer.</small> : null}
        </div>
        <PrimeKGGraphExplorer graph={graph} retrievals={retrievals} loading={loading === "graph"} error={error} onGraphModeChange={setGraphViewMode} />
      </div>
    </section>
  );
}

function StatusCard({ icon: Icon, title, detail, ready }) {
  const StateIcon = ready ? CheckCircle2 : CircleDashed;
  return (
    <div className={`primekg-status-card ${ready ? "ready" : "pending"}`}>
      <div className="primekg-status-card-icon"><Icon size={17} /></div>
      <div>
        <strong>{title}</strong>
        <span>{detail}</span>
      </div>
      <StateIcon size={15} />
    </div>
  );
}

function PrimeKGEmptyState({ icon: Icon = HelpCircle, title, message }) {
  return (
    <div className="primekg-empty-state">
      <Icon size={18} />
      <div>
        <strong>{title}</strong>
        <span>{message}</span>
      </div>
    </div>
  );
}

