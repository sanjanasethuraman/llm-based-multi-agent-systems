import { CheckCircle2, CircleDashed, Database, FileText, HelpCircle, Network, RefreshCcw, Search, ServerCrash, Sparkles } from "lucide-react";

import DiseaseCombobox from "./DiseaseCombobox.jsx";
import IconButton from "./IconButton.jsx";
import PrimeKGGraphExplorer from "./PrimeKGGraphExplorer.jsx";

export default function PrimeKGPanel({
  form,
  status,
  preview,
  importSummary,
  loading,
  graph,
  retrievals = [],
  error,
  onFormChange,
  onRefreshStatus,
  onPreview,
  onImport,
  onFilterAndImport,
  onLoadGraph,
  presentationMode = false,
}) {
  const updateField = (field, value) => onFormChange((current) => ({ ...current, [field]: value }));
  const neo4jConnected = Boolean(status?.neo4jConnected || status?.neo4j?.connected);
  const fileFound = Boolean(status?.fileExists);
  const previewReady = Boolean(preview?.ok && preview?.outputPath);
  const previewHasCapWarning = Boolean(preview?.warnings?.some((warning) => /cap reached|truncated/i.test(warning)));
  const importDisabled = !neo4jConnected || !previewReady || loading === "import";
  const filterImportDisabled = !neo4jConnected || !fileFound || !form.disease?.trim() || loading === "filterImport";
  const graphDisabled = !neo4jConnected || loading === "graph";
  const statusClass = neo4jConnected && fileFound ? "success" : fileFound ? "warning" : "neutral";
  const matchedDisease = preview?.matchedDiseaseNodes?.[0];
  const imported = Boolean(importSummary && (importSummary.status === "imported" || importSummary.status === "dry_run"));
  const graphLoaded = Boolean(graph?.status === "available" && (graph?.nodes?.length || graph?.stats?.nodeCount));
  const answerGraphLoaded = graphLoaded && graph?.mode === "answer";
  const workflowSteps = [
    { label: "Explore disease", detail: form.disease || "Choose a disease", done: Boolean(form.disease?.trim()) },
    { label: "Preview subgraph", detail: previewReady ? `${preview.nodeCount || 0} nodes` : "bounded filter", done: previewReady },
    { label: "Import to Neo4j", detail: imported ? "ready for retrieval" : "optional graph DB", done: imported },
    { label: "Load graph", detail: graphLoaded ? "viewer ready" : "in-app explorer", done: graphLoaded },
    { label: "Ask Graph RAG", detail: "auto-detects entities", done: false },
  ];

  return (
    <section className={`primekg-panel ${presentationMode ? "primekg-panel--presentation" : ""}`}>
      <div className="primekg-hero">
        <div className="primekg-hero-copy">
          <span><Sparkles size={14} /> Flagship biomedical graph workflow</span>
          <h2>Biomedical Knowledge Graph</h2>
          <p>Explore disease-centered PrimeKG subgraphs and use graph evidence in RAG answers.</p>
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
        <StatusCard icon={neo4jConnected ? Database : ServerCrash} title="Neo4j" detail={neo4jConnected ? "Connected and ready for imports" : status?.neo4j?.message || "Offline"} ready={neo4jConnected} />
        <StatusCard icon={Database} title="Filtered Subgraph" detail={previewReady ? "Preview file ready" : imported ? "Last import available" : "Preview required"} ready={previewReady || imported} />
        <StatusCard icon={Network} title="Graph Viewer" detail={graphLoaded ? "Loaded in-app" : "Not loaded yet"} ready={graphLoaded} />
      </div>

      <div className={`provider-note primekg-status-note ${statusClass}`}>
        <div>
          <strong>PrimeKG:</strong>{" "}
          {fileFound ? `kg.csv found at ${status.defaultCsvPath || "data/primekg/kg.csv"}` : status?.message || "kg.csv has not been checked yet."}
        </div>
        <div>Neo4j: {neo4jConnected ? "connected" : status?.neo4j?.message || "offline"}</div>
        {!fileFound ? <div>Place the dataset at data/primekg/kg.csv, then check status again.</div> : null}
        {!neo4jConnected ? <div>{status?.neo4j?.setupHint || "Start Neo4j before importing or loading the graph view."}</div> : null}
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
          <strong>Explore disease and preview a bounded graph</strong>
        </div>

        <div className="primekg-grid">
          <div className="primekg-disease-field">
            <DiseaseCombobox label="Explore disease" value={form.disease} onChange={(value) => updateField("disease", value)} />
            <p>This controls graph exploration and preview/import. Graph RAG questions can still auto-detect entities when this is blank.</p>
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
          <div className="provider-note warning compact">Depth 3 can grow quickly. The backend enforces caps before writing a preview.</div>
        ) : null}

        <div className="inline-actions primekg-actions">
          <IconButton icon={Search} label={loading === "preview" ? "Previewing" : "Preview Subgraph"} variant="primary" onClick={onPreview} disabled={loading === "preview" || !form.disease?.trim()} />
          <IconButton icon={Database} label={loading === "import" ? "Importing" : "Import Filtered Subgraph"} variant="secondary" onClick={onImport} disabled={importDisabled} />
          <IconButton icon={Database} label={loading === "filterImport" ? "Filtering + Importing" : "Filter + Import"} variant="success" onClick={onFilterAndImport} disabled={filterImportDisabled} />
          <IconButton icon={Network} label={loading === "graph" ? "Loading Graph" : "Load In-App Graph"} variant="secondary" onClick={onLoadGraph} disabled={graphDisabled} />
        </div>
      </div>

      {error ? <div className="provider-note warning">{error}</div> : null}
      {!fileFound ? <PrimeKGEmptyState icon={FileText} title="PrimeKG kg.csv missing" message="Download PrimeKG and place kg.csv in data/primekg/kg.csv to enable disease search and filtering." /> : null}
      {fileFound && !neo4jConnected ? <PrimeKGEmptyState icon={ServerCrash} title="Neo4j offline" message="You can preview CSV subgraphs, but import and graph loading require Neo4j to be running." /> : null}

      {preview ? (
        <div className="primekg-preview">
          <div className="primekg-preview-heading">
            <div>
              <span>Preview result</span>
              <h3>{matchedDisease?.name || form.disease || "Disease subgraph"}</h3>
            </div>
            <small>{preview.outputPath ? "Filtered JSON ready for import" : "Preview did not write an output file"}</small>
          </div>
          <div className="result-summary-grid compact">
            <div className="stat-card">
              <span>Matched disease</span>
              <strong>{matchedDisease?.name || preview.error || "None"}</strong>
            </div>
            <div className="stat-card">
              <span>Nodes</span>
              <strong>{preview.nodeCount ?? 0}</strong>
            </div>
            <div className="stat-card">
              <span>Relationships</span>
              <strong>{preview.relationshipCount ?? 0}</strong>
            </div>
            <div className="stat-card">
              <span>Preview file</span>
              <strong>{preview.outputPath || "not written"}</strong>
            </div>
          </div>

          {preview.warnings?.length ? (
            <div className="provider-note warning">
              {preview.warnings.join(" ")}
              {previewHasCapWarning ? (
                <span> Import will use this bounded preview only, not the full PrimeKG dataset.</span>
              ) : null}
            </div>
          ) : null}

          <div className="primekg-preview-grid">
            <TopStats title="Top Node Types" stats={preview.statsByNodeType} />
            <TopStats title="Top Relation Types" stats={preview.statsByRelationType} />
            <div className="primekg-samples">
              <h3>Sample Relationships</h3>
              {(preview.sampleRelationships || []).slice(0, 6).map((relationship, index) => (
                <div key={`${relationship.id || index}`} className="primekg-sample-card">
                  <strong>{relationship.source}</strong>
                  <span>{relationship.displayRelation || relationship.relation || "related_to"}</span>
                  <strong>{relationship.target}</strong>
                </div>
              ))}
              {preview.sampleRelationships?.length ? null : <p className="hint">No sample relationships yet.</p>}
            </div>
          </div>
        </div>
      ) : null}

      {importSummary ? (
        <div className={`provider-note ${importSummary.status === "imported" || importSummary.status === "dry_run" ? "success" : "warning"}`}>
          <strong>Last Import:</strong> {importSummary.status}.{" "}
          {importSummary.nodesImported || importSummary.nodeCount || 0} nodes, {importSummary.relationshipsImported || importSummary.relationshipCount || 0} relationships.
          {importSummary.errors?.length ? <div>{importSummary.errors[0]}</div> : null}
        </div>
      ) : null}

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
          ) : !graphLoaded ? <small>No graph loaded yet. Import a filtered subgraph, then load the graph viewer.</small> : null}
        </div>
        <PrimeKGGraphExplorer graph={graph} retrievals={retrievals} loading={loading === "graph"} error={error} />
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

function TopStats({ title, stats }) {
  const entries = Object.entries(stats || {}).sort((left, right) => Number(right[1]) - Number(left[1])).slice(0, 6);
  return (
    <div className="primekg-stat-list">
      <h3>{title}</h3>
      {entries.length ? entries.map(([label, value]) => (
        <div key={label}>
          <span>{label}</span>
          <strong>{value}</strong>
        </div>
      )) : <p className="hint">No stats yet.</p>}
    </div>
  );
}
