import { CheckCircle2, CircleDashed, Database, FileText, Network, RefreshCcw, Search, ServerCrash } from "lucide-react";

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
  onLoadGraph,
}) {
  const updateField = (field, value) => onFormChange((current) => ({ ...current, [field]: value }));
  const neo4jConnected = Boolean(status?.neo4jConnected || status?.neo4j?.connected);
  const fileFound = Boolean(status?.fileExists);
  const previewReady = Boolean(preview?.ok && preview?.outputPath);
  const previewHasCapWarning = Boolean(preview?.warnings?.some((warning) => /cap reached|truncated/i.test(warning)));
  const importDisabled = !neo4jConnected || !previewReady || loading === "import";
  const graphDisabled = !neo4jConnected || loading === "graph";
  const statusClass = neo4jConnected && fileFound ? "success" : fileFound ? "warning" : "neutral";
  const matchedDisease = preview?.matchedDiseaseNodes?.[0];
  const imported = Boolean(importSummary && (importSummary.status === "imported" || importSummary.status === "dry_run"));
  const graphLoaded = Boolean(graph?.status === "available" && (graph?.nodes?.length || graph?.stats?.nodeCount));

  return (
    <section className="primekg-panel">
      <div className="section-header">
        <div>
          <h2>PrimeKG Biomedical Subgraph</h2>
          <p>Filter a disease-centered biomedical graph, preview it, then import only that bounded subgraph into Neo4j.</p>
        </div>
        <IconButton icon={RefreshCcw} label={loading === "status" ? "Checking" : "Check PrimeKG Status"} onClick={onRefreshStatus} disabled={loading === "status"} />
      </div>

      <div className="primekg-demo-ready" aria-label="PrimeKG demo readiness">
        <ChecklistItem icon={FileText} label="kg.csv" detail={fileFound ? "found" : "missing"} ready={fileFound} />
        <ChecklistItem icon={neo4jConnected ? Database : ServerCrash} label="Neo4j" detail={neo4jConnected ? "connected" : "offline"} ready={neo4jConnected} />
        <ChecklistItem icon={Database} label="Subgraph" detail={imported ? "imported" : "not imported"} ready={imported} />
        <ChecklistItem icon={Network} label="Graph view" detail={graphLoaded ? "loaded" : "not loaded"} ready={graphLoaded} />
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

      <div className="primekg-control-surface">
        <div className="primekg-control-heading">
          <span>Filtered Import</span>
          <strong>{form.disease || "disease"} subgraph</strong>
        </div>

        <div className="primekg-grid">
        <DiseaseCombobox value={form.disease} onChange={(value) => updateField("disease", value)} />
        <label>
          Depth
          <select value={form.depth} onChange={(event) => updateField("depth", Number(event.target.value))}>
            <option value={1}>1 - direct neighbors</option>
            <option value={2}>2 - biomedical paths</option>
            <option value={3}>3 - broad search</option>
          </select>
        </label>
        <label>
          Max Nodes
          <input type="number" min="1" max="5000" value={form.maxNodes} onChange={(event) => updateField("maxNodes", Number(event.target.value))} />
        </label>
        <label>
          Max Relationships
          <input type="number" min="1" max="15000" value={form.maxRelationships} onChange={(event) => updateField("maxRelationships", Number(event.target.value))} />
        </label>
        </div>

        {Number(form.depth) === 3 ? (
          <div className="provider-note warning compact">Depth 3 can grow quickly. The backend will enforce caps before writing a preview.</div>
        ) : null}

        <div className="inline-actions primekg-actions">
          <IconButton icon={Search} label={loading === "preview" ? "Previewing" : "Preview Subgraph"} variant="primary" onClick={onPreview} disabled={loading === "preview" || !form.disease?.trim()} />
          <IconButton icon={Database} label={loading === "import" ? "Importing" : "Import Filtered Subgraph"} onClick={onImport} disabled={importDisabled} />
          <IconButton icon={Network} label={loading === "graph" ? "Loading Graph" : "Load In-App Graph"} onClick={onLoadGraph} disabled={graphDisabled} />
        </div>
      </div>

      {error ? <div className="provider-note warning">{error}</div> : null}

      {preview ? (
        <div className="primekg-preview">
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
                <div key={`${relationship.id || index}`} className="primekg-path-line">
                  {relationship.source} --{relationship.displayRelation || relationship.relation || "related_to"}--&gt; {relationship.target}
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

      <PrimeKGGraphExplorer graph={graph} retrievals={retrievals} loading={loading === "graph"} error={error} />
    </section>
  );
}

function ChecklistItem({ icon: Icon, label, detail, ready }) {
  const StateIcon = ready ? CheckCircle2 : CircleDashed;
  return (
    <div className={`primekg-check-item ${ready ? "ready" : "pending"}`}>
      <Icon size={15} />
      <div>
        <strong>{label}</strong>
        <span>{detail}</span>
      </div>
      <StateIcon size={15} />
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
