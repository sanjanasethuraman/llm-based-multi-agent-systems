import {
  addEdge,
  Background,
  Controls,
  Handle,
  MarkerType,
  MiniMap,
  Position,
  ReactFlow,
  ReactFlowProvider,
} from "@xyflow/react";
import {
  CheckCircle2,
  CircleDot,
  Download,
  FileInput,
  FolderOpen,
  Play,
  Plus,
  RefreshCcw,
  Save,
  Trash2,
  Upload,
  XCircle,
} from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";

import { getJson, postJson } from "./api.js";
import {
  calculateNextId,
  createNode,
  DEFAULT_WORKFLOW,
  edgeId,
  NODE_TYPES,
  normalizeWorkflow,
  validateWorkflow,
} from "./workflow.js";

const nodeTypes = { workflow: WorkflowNode };
const providerOptions = [
  { value: "mock", label: "Mock" },
  { value: "ollama", label: "Ollama" },
  { value: "api", label: "API" },
];

export default function App() {
  return (
    <ReactFlowProvider>
      <WorkflowApp />
    </ReactFlowProvider>
  );
}

function WorkflowApp() {
  const [workflow, setWorkflow] = useState(() => normalizeWorkflow(DEFAULT_WORKFLOW));
  const [selected, setSelected] = useState({ kind: "node", id: "agent-1" });
  const [statusMessage, setStatusMessage] = useState("Ready");
  const [output, setOutput] = useState("Run the workflow to see the final output.");
  const [logs, setLogs] = useState([]);
  const [stats, setStats] = useState(null);
  const [generatedCode, setGeneratedCode] = useState("Click Generate Python.");
  const [nodeResults, setNodeResults] = useState({});
  const [retrievals, setRetrievals] = useState([]);
  const [examples, setExamples] = useState([]);
  const [selectedExample, setSelectedExample] = useState("");
  const [collections, setCollections] = useState([]);
  const [recentDocuments, setRecentDocuments] = useState([]);
  const [ollamaStatus, setOllamaStatus] = useState(null);
  const [ingestStatus, setIngestStatus] = useState("No document ingested yet.");
  const [ragForm, setRagForm] = useState({
    collection: "course_docs",
    title: "Project Notes",
    embeddingModel: "nomic-embed-text",
    baseUrl: "http://127.0.0.1:11434",
    text: "A visual multi-agent system builder lets users create workflows by connecting components such as inputs, agents, tools, retrievers, vector databases, and outputs. RAG adds document ingestion, embeddings, vector search, and retrieved context so agents can answer using project-specific knowledge.",
    files: [],
  });

  const validation = useMemo(() => validateWorkflow(workflow), [workflow]);
  const selectedNode = useMemo(
    () => workflow.nodes.find((node) => selected.kind === "node" && node.id === selected.id),
    [selected, workflow.nodes],
  );
  const selectedEdge = useMemo(
    () => workflow.edges.find((edge) => selected.kind === "edge" && edgeId(edge) === selected.id),
    [selected, workflow.edges],
  );
  const nextId = useMemo(() => calculateNextId(workflow), [workflow]);

  const flowNodes = useMemo(
    () =>
      workflow.nodes.map((node) => ({
        id: node.id,
        type: "workflow",
        position: node.position,
        selected: selected.kind === "node" && selected.id === node.id,
        data: {
          node,
          result: nodeResults[node.id],
        },
      })),
    [nodeResults, selected, workflow.nodes],
  );

  const flowEdges = useMemo(
    () =>
      workflow.edges.map((edge) => {
        const id = edgeId(edge);
        const sourceStatus = nodeResults[edge.source]?.status;
        const targetStatus = nodeResults[edge.target]?.status;
        return {
          id,
          source: edge.source,
          target: edge.target,
          selected: selected.kind === "edge" && selected.id === id,
          animated: sourceStatus === "completed" && targetStatus === "completed",
          markerEnd: { type: MarkerType.ArrowClosed },
          className: `flow-edge ${sourceStatus || ""} ${targetStatus || ""}`,
        };
      }),
    [nodeResults, selected, workflow.edges],
  );

  useEffect(() => {
    refreshExamples();
    refreshCollections();
  }, []);

  useEffect(() => {
    const baseUrl = selectedNode?.config?.baseUrl || ragForm.baseUrl;
    const controller = new AbortController();
    const timeout = window.setTimeout(async () => {
      try {
        const params = new URLSearchParams({ baseUrl });
        const result = await getJson(`/api/provider/ollama-status?${params.toString()}`);
        if (!controller.signal.aborted) {
          setOllamaStatus(result);
        }
      } catch (error) {
        if (!controller.signal.aborted) {
          setOllamaStatus({ available: false, baseUrl, message: error.message });
        }
      }
    }, 300);

    return () => {
      controller.abort();
      window.clearTimeout(timeout);
    };
  }, [ragForm.baseUrl, selectedNode?.config?.baseUrl]);

  const updateWorkflow = useCallback((updater) => {
    setWorkflow((current) => normalizeWorkflow(typeof updater === "function" ? updater(current) : updater));
  }, []);

  const updateNode = useCallback(
    (nodeId, patch) => {
      updateWorkflow((current) => ({
        ...current,
        nodes: current.nodes.map((node) => (
          node.id === nodeId
            ? {
                ...node,
                ...patch,
                config: { ...node.config, ...(patch.config || {}) },
              }
            : node
        )),
      }));
    },
    [updateWorkflow],
  );

  const handleConnect = useCallback(
    (connection) => {
      if (!connection.source || !connection.target || connection.source === connection.target) {
        setStatusMessage("Choose two different nodes to connect.");
        return;
      }
      updateWorkflow((current) => {
        const exists = current.edges.some(
          (edge) => edge.source === connection.source && edge.target === connection.target,
        );
        if (exists) {
          return current;
        }
        return {
          ...current,
          edges: addEdge(connection, current.edges).map(({ source, target }) => ({ source, target })),
        };
      });
      setStatusMessage(`Connected ${connection.source} to ${connection.target}.`);
    },
    [updateWorkflow],
  );

  const handleNodeDragStop = useCallback(
    (_, draggedNode) => {
      updateNode(draggedNode.id, { position: draggedNode.position });
    },
    [updateNode],
  );

  const handleNodesChange = useCallback(
    (changes) => {
      const positionChanges = changes.filter((change) => change.type === "position" && change.position);
      if (!positionChanges.length) {
        return;
      }
      updateWorkflow((current) => ({
        ...current,
        nodes: current.nodes.map((node) => {
          const change = positionChanges.find((item) => item.id === node.id);
          return change ? { ...node, position: change.position } : node;
        }),
      }));
    },
    [updateWorkflow],
  );

  const handleNodesDelete = useCallback(
    (deletedNodes) => {
      const deletedIds = new Set(deletedNodes.map((node) => node.id));
      updateWorkflow((current) => ({
        nodes: current.nodes.filter((node) => !deletedIds.has(node.id)),
        edges: current.edges.filter((edge) => !deletedIds.has(edge.source) && !deletedIds.has(edge.target)),
      }));
      setSelected({ kind: "none", id: "" });
    },
    [updateWorkflow],
  );

  const handleEdgesDelete = useCallback(
    (deletedEdges) => {
      const deletedIds = new Set(deletedEdges.map((edge) => edge.id));
      updateWorkflow((current) => ({
        ...current,
        edges: current.edges.filter((edge) => !deletedIds.has(edgeId(edge))),
      }));
      setSelected({ kind: "none", id: "" });
    },
    [updateWorkflow],
  );

  function addWorkflowNode(type) {
    const node = createNode(type, nextId);
    updateWorkflow((current) => ({ ...current, nodes: [...current.nodes, node] }));
    setSelected({ kind: "node", id: node.id });
    setStatusMessage(`Added ${NODE_TYPES[type] || type}.`);
  }

  function deleteSelection() {
    if (selected.kind === "node" && selectedNode) {
      const deletedId = selectedNode.id;
      updateWorkflow((current) => ({
        nodes: current.nodes.filter((node) => node.id !== deletedId),
        edges: current.edges.filter((edge) => edge.source !== deletedId && edge.target !== deletedId),
      }));
      setSelected({ kind: "none", id: "" });
      setStatusMessage(`Deleted ${selectedNode.label}.`);
      return;
    }

    if (selected.kind === "edge" && selectedEdge) {
      updateWorkflow((current) => ({
        ...current,
        edges: current.edges.filter((edge) => edgeId(edge) !== selected.id),
      }));
      setSelected({ kind: "none", id: "" });
      setStatusMessage("Deleted edge.");
    }
  }

  async function refreshExamples() {
    try {
      const result = await getJson("/api/examples");
      setExamples(result.examples || []);
      setSelectedExample((current) => current || result.examples?.[0]?.name || "");
    } catch (error) {
      setStatusMessage(error.message);
    }
  }

  async function loadExample(name = selectedExample) {
    if (!name) {
      setStatusMessage("No example selected.");
      return;
    }
    try {
      const result = await getJson(`/api/example?name=${encodeURIComponent(name)}`);
      const nextWorkflow = normalizeWorkflow(result.workflow);
      setWorkflow(nextWorkflow);
      setNodeResults({});
      setRetrievals([]);
      setSelected({ kind: "node", id: nextWorkflow.nodes[0]?.id || "" });
      setStatusMessage(`Loaded example: ${result.label}.`);
    } catch (error) {
      setStatusMessage(error.message);
    }
  }

  async function loadSavedWorkflow() {
    try {
      setStatusMessage("Loading workflow...");
      const result = await getJson("/api/load-workflow");
      if (!result.workflow) {
        setStatusMessage("No saved workflow found.");
        return;
      }
      const nextWorkflow = normalizeWorkflow(result.workflow);
      setWorkflow(nextWorkflow);
      setNodeResults({});
      setRetrievals([]);
      setSelected({ kind: "node", id: nextWorkflow.nodes[0]?.id || "" });
      setStatusMessage(`Loaded workflow from ${result.path}.`);
    } catch (error) {
      setStatusMessage(error.message);
    }
  }

  async function saveWorkflow() {
    try {
      setStatusMessage("Saving workflow...");
      const result = await postJson("/api/save-workflow", workflow);
      setStatusMessage(`Saved workflow to ${result.path}.`);
    } catch (error) {
      setStatusMessage(error.message);
    }
  }

  async function runWorkflow() {
    const localValidation = validateWorkflow(workflow);
    if (localValidation.errors.length) {
      setOutput(localValidation.errors.join("\n"));
      setStatusMessage("Fix validation errors before running.");
      return;
    }

    try {
      setStatusMessage("Validating workflow...");
      const serverValidation = await postJson("/api/validate", workflow);
      if (serverValidation.errors?.length) {
        setOutput(serverValidation.errors.join("\n"));
        setStatusMessage("Backend validation failed.");
        return;
      }

      setStatusMessage("Running workflow...");
      setOutput("Running...");
      setLogs([]);
      setStats(null);
      setRetrievals([]);
      setNodeResults(
        Object.fromEntries(
          workflow.nodes.map((node) => [
            node.id,
            { status: "running", message: "Queued for execution.", type: node.type },
          ]),
        ),
      );

      const result = await postJson("/api/run", workflow);
      setOutput(result.output || "(No output)");
      setLogs(result.logs || []);
      setStats(result.stats || null);
      setRetrievals(result.retrievals || []);
      setNodeResults(result.nodeResults || {});
      setStatusMessage("Workflow run completed.");
    } catch (error) {
      setOutput(error.payload?.validation?.errors?.join("\n") || error.message);
      setStatusMessage(error.message);
      setNodeResults({});
    }
  }

  async function generatePython() {
    try {
      setGeneratedCode("Generating...");
      const result = await postJson("/api/generate-python", workflow);
      setGeneratedCode(result.code || "No code generated.");
      setStatusMessage("Generated Python preview.");
    } catch (error) {
      setGeneratedCode(error.message);
      setStatusMessage(error.message);
    }
  }

  async function exportPythonFile() {
    try {
      setGeneratedCode("Exporting...");
      const result = await postJson("/api/export-python-file", workflow);
      setGeneratedCode(result.code || "No code exported.");
      setStatusMessage(`Exported executable Python to ${result.path}.`);
    } catch (error) {
      setGeneratedCode(error.message);
      setStatusMessage(error.message);
    }
  }

  async function refreshCollections() {
    try {
      const result = await getJson("/api/documents/collections");
      setCollections(result.collections || []);
      setRecentDocuments(result.recentDocuments || []);
    } catch (error) {
      setStatusMessage(error.message);
    }
  }

  async function ingestDocuments() {
    try {
      setIngestStatus("Reading files...");
      const documents = ragForm.files.length
        ? await Promise.all(
            ragForm.files.map(async (file) => ({
              title: file.name,
              source: `file:${file.name}`,
              text: await file.text(),
            })),
          )
        : [];

      const payload = documents.length
        ? {
            collection: ragForm.collection,
            embeddingModel: ragForm.embeddingModel,
            baseUrl: ragForm.baseUrl,
            documents,
          }
        : {
            collection: ragForm.collection,
            title: ragForm.title,
            source: "manual-ui",
            text: ragForm.text,
            embeddingModel: ragForm.embeddingModel,
            baseUrl: ragForm.baseUrl,
          };

      setIngestStatus("Ingesting documents...");
      setStatusMessage("Ingesting RAG documents...");
      const result = await postJson("/api/ingest-document", payload);
      setIngestStatus(JSON.stringify(result, null, 2));
      setStatusMessage(`Ingested ${result.chunks} chunks into ${result.collection}.`);
      await refreshCollections();
    } catch (error) {
      setIngestStatus(error.message);
      setStatusMessage(error.message);
    }
  }

  return (
    <div className="app-shell">
      <header className="topbar">
        <div>
          <h1>Visual MAS Tool</h1>
          <p>Build, run, and inspect LLM-based multi-agent workflows.</p>
        </div>
        <div className="actions">
          <select
            aria-label="Example workflow"
            value={selectedExample}
            onChange={(event) => setSelectedExample(event.target.value)}
          >
            {examples.map((example) => (
              <option key={example.name} value={example.name}>
                {example.label}
              </option>
            ))}
          </select>
          <IconButton icon={FolderOpen} label="Load Example" onClick={() => loadExample()} />
          <IconButton icon={Play} label="Run" variant="primary" onClick={runWorkflow} />
          <IconButton icon={Save} label="Save" onClick={saveWorkflow} />
          <IconButton icon={Download} label="Load Saved" onClick={loadSavedWorkflow} />
          <IconButton icon={FileInput} label="Generate Python" onClick={generatePython} />
          <IconButton icon={Download} label="Export .py" onClick={exportPythonFile} />
        </div>
      </header>

      <div className="status-message">{statusMessage}</div>

      <main className="workspace">
        <Palette onAddNode={addWorkflowNode} />

        <section className="canvas-panel">
          <div className="canvas-header">
            <strong>Workflow Graph</strong>
            <div className="canvas-tools">
              <span>{selectionLabel(selectedNode, selectedEdge)}</span>
              <button type="button" disabled={!selectedNode && !selectedEdge} onClick={deleteSelection}>
                <Trash2 size={15} />
                Delete
              </button>
            </div>
          </div>
          <div className="canvas">
            <ReactFlow
              fitView
              deleteKeyCode={["Backspace", "Delete"]}
              edges={flowEdges}
              nodes={flowNodes}
              nodeTypes={nodeTypes}
              onConnect={handleConnect}
              onEdgeClick={(_, edge) => setSelected({ kind: "edge", id: edge.id })}
              onEdgesDelete={handleEdgesDelete}
              onNodeClick={(_, node) => setSelected({ kind: "node", id: node.id })}
              onNodeDragStop={handleNodeDragStop}
              onNodesChange={handleNodesChange}
              onNodesDelete={handleNodesDelete}
              onPaneClick={() => setSelected({ kind: "none", id: "" })}
            >
              <Background gap={22} size={1} />
              <MiniMap pannable zoomable nodeStrokeWidth={3} />
              <Controls />
            </ReactFlow>
          </div>
        </section>

        <ConfigPanel
          node={selectedNode}
          validation={validation}
          ollamaStatus={ollamaStatus}
          onNodeChange={updateNode}
        />
      </main>

      <RagPanel
        collections={collections}
        recentDocuments={recentDocuments}
        form={ragForm}
        ingestStatus={ingestStatus}
        ollamaStatus={ollamaStatus}
        onFormChange={setRagForm}
        onIngest={ingestDocuments}
        onRefreshCollections={refreshCollections}
      />

      <ResultPanels output={output} logs={logs} stats={stats} />
      <RetrievalPanel retrievals={retrievals} />

      <section className="code-panel">
        <div className="code-header">
          <h2>Generated Python</h2>
          <span>Executable export for the current workflow</span>
        </div>
        <pre id="generated-code">{generatedCode}</pre>
      </section>
    </div>
  );
}

function WorkflowNode({ data, selected }) {
  const { node, result } = data;
  const status = result?.status || "idle";
  return (
    <div className={`workflow-node ${node.type} ${status} ${selected ? "selected" : ""}`}>
      <Handle className="node-handle target" type="target" position={Position.Left} />
      <div className="node-title">
        <strong>{node.label || node.id}</strong>
        <StatusBadge status={status} />
      </div>
      <div className="node-meta">
        <span>{NODE_TYPES[node.type] || node.type}</span>
        {node.type === "agent" && <span>{node.config?.provider || "mock"}</span>}
      </div>
      {result?.message && <p>{result.message}</p>}
      <Handle className="node-handle source" type="source" position={Position.Right} />
    </div>
  );
}

function Palette({ onAddNode }) {
  return (
    <aside className="palette">
      <h2>Components</h2>
      {Object.entries(NODE_TYPES).map(([type, label]) => (
        <button key={type} type="button" onClick={() => onAddNode(type)}>
          <Plus size={15} />
          {label}
        </button>
      ))}
      <p className="hint">Drag nodes on the canvas. Connect side ports to build the execution graph.</p>
    </aside>
  );
}

function ConfigPanel({ node, validation, ollamaStatus, onNodeChange }) {
  if (!node) {
    return (
      <aside className="config">
        <h2>Configuration</h2>
        <p className="empty-state">Select a node or edge to edit it.</p>
        <ValidationPanel validation={validation} />
      </aside>
    );
  }

  const updateConfig = (patch) => onNodeChange(node.id, { config: patch });
  const updateLabel = (label) => onNodeChange(node.id, { label });

  return (
    <aside className="config">
      <h2>Configuration</h2>
      <div className="form-grid">
        <label>
          Label
          <input value={node.label || ""} onChange={(event) => updateLabel(event.target.value)} />
        </label>

        {node.type === "input" && (
          <label>
            Input Text
            <textarea
              rows={6}
              value={node.config.text || ""}
              onChange={(event) => updateConfig({ text: event.target.value })}
            />
          </label>
        )}

        {node.type === "agent" && (
          <>
            <label>
              Agent Name
              <input
                value={node.config.name || ""}
                onChange={(event) => updateConfig({ name: event.target.value })}
              />
            </label>
            <div className="field-group">
              <span>Provider</span>
              <div className="segmented">
                {providerOptions.map((provider) => (
                  <button
                    className={node.config.provider === provider.value ? "active" : ""}
                    key={provider.value}
                    type="button"
                    onClick={() => updateConfig({ provider: provider.value })}
                  >
                    {provider.label}
                  </button>
                ))}
              </div>
            </div>
            <ProviderNote provider={node.config.provider} ollamaStatus={ollamaStatus} />
            <label>
              Model
              <input
                value={node.config.model || ""}
                placeholder="llama3.2:1b"
                onChange={(event) => updateConfig({ model: event.target.value })}
              />
            </label>
            <label>
              Local Provider URL
              <input
                value={node.config.baseUrl || ""}
                placeholder="http://127.0.0.1:11434"
                onChange={(event) => updateConfig({ baseUrl: event.target.value })}
              />
            </label>
            <label>
              Temperature
              <input
                max="2"
                min="0"
                step="0.1"
                type="number"
                value={node.config.temperature ?? 0.2}
                onChange={(event) => updateConfig({ temperature: Number(event.target.value) })}
              />
            </label>
            <label>
              System Prompt
              <textarea
                rows={6}
                value={node.config.systemPrompt || ""}
                onChange={(event) => updateConfig({ systemPrompt: event.target.value })}
              />
            </label>
          </>
        )}

        {(node.type === "retriever" || node.type === "vector_db") && (
          <>
            <label>
              Collection
              <input
                value={node.config.collection || ""}
                placeholder="course_docs"
                onChange={(event) => updateConfig({ collection: event.target.value })}
              />
            </label>
            <label>
              Embedding Model
              <input
                value={node.config.embeddingModel || ""}
                placeholder="nomic-embed-text"
                onChange={(event) => updateConfig({ embeddingModel: event.target.value })}
              />
            </label>
            <label>
              Ollama URL
              <input
                value={node.config.baseUrl || ""}
                placeholder="http://127.0.0.1:11434"
                onChange={(event) => updateConfig({ baseUrl: event.target.value })}
              />
            </label>
            {node.type === "retriever" && (
              <label>
                Top K
                <input
                  max="10"
                  min="1"
                  step="1"
                  type="number"
                  value={node.config.topK || 3}
                  onChange={(event) => updateConfig({ topK: Number(event.target.value) })}
                />
              </label>
            )}
          </>
        )}

        {node.type === "tool" && (
          <>
            <label>
              Tool Name
              <input
                value={node.config.name || ""}
                onChange={(event) => updateConfig({ name: event.target.value })}
              />
            </label>
            <label>
              Tool Type
              <select
                value={node.config.toolType || "echo"}
                onChange={(event) => updateConfig({ toolType: event.target.value })}
              >
                <option value="echo">Echo</option>
                <option value="word_count">Word Count</option>
                <option value="uppercase">Uppercase</option>
              </select>
            </label>
          </>
        )}
      </div>

      <ValidationPanel validation={validation} />
    </aside>
  );
}

function ProviderNote({ provider, ollamaStatus }) {
  if (provider === "mock") {
    return <div className="provider-note neutral">Mock mode is deterministic and works offline.</div>;
  }
  if (provider === "api") {
    return <div className="provider-note warning">The API provider is a placeholder in this prototype.</div>;
  }
  if (!ollamaStatus) {
    return <div className="provider-note neutral">Checking Ollama...</div>;
  }
  if (ollamaStatus.available) {
    return (
      <div className="provider-note success">
        Ollama is reachable at {ollamaStatus.baseUrl}. {ollamaStatus.models?.length || 0} models found.
      </div>
    );
  }
  return (
    <div className="provider-note warning">
      Ollama is not reachable at {ollamaStatus.baseUrl}. Use mock mode or start Ollama.
    </div>
  );
}

function ValidationPanel({ validation }) {
  const issues = [
    ...validation.errors.map((message) => ({ message, type: "error" })),
    ...validation.warnings.map((message) => ({ message, type: "warning" })),
  ];

  return (
    <section className="validation-panel">
      <h2>Validation</h2>
      {issues.length ? (
        <ul>
          {issues.map((issue) => (
            <li className={issue.type} key={`${issue.type}-${issue.message}`}>
              {issue.type === "error" ? <XCircle size={14} /> : <CircleDot size={14} />}
              {issue.message}
            </li>
          ))}
        </ul>
      ) : (
        <div className="validation-ok">
          <CheckCircle2 size={15} />
          Workflow is ready to run.
        </div>
      )}
    </section>
  );
}

function RagPanel({
  collections,
  recentDocuments,
  form,
  ingestStatus,
  ollamaStatus,
  onFormChange,
  onIngest,
  onRefreshCollections,
}) {
  const updateField = (field, value) => onFormChange((current) => ({ ...current, [field]: value }));
  return (
    <section className="rag-panel">
      <div className="section-header">
        <div>
          <h2>Documents / RAG Ingestion</h2>
          <p>Upload text-like files into a collection, then connect a retriever node to use them.</p>
        </div>
        <IconButton icon={RefreshCcw} label="Refresh" onClick={onRefreshCollections} />
      </div>

      <div className="ingest-grid">
        <label>
          Collection
          <input value={form.collection} onChange={(event) => updateField("collection", event.target.value)} />
        </label>
        <label>
          Fallback Title
          <input value={form.title} onChange={(event) => updateField("title", event.target.value)} />
        </label>
        <label>
          Embedding Model
          <input
            value={form.embeddingModel}
            onChange={(event) => updateField("embeddingModel", event.target.value)}
          />
        </label>
        <label>
          Ollama URL
          <input value={form.baseUrl} onChange={(event) => updateField("baseUrl", event.target.value)} />
        </label>
      </div>

      <div className="rag-provider-row">
        <ProviderNote provider="ollama" ollamaStatus={ollamaStatus} />
      </div>

      <label className="file-upload">
        <Upload size={18} />
        <span>{form.files.length ? `${form.files.length} file(s) selected` : "Choose files for ingestion"}</span>
        <input
          multiple
          accept=".txt,.md,.json,.csv,.py,.js,.css,text/*,application/json"
          type="file"
          onChange={(event) => updateField("files", Array.from(event.target.files || []))}
        />
      </label>

      <label>
        Manual Text Fallback
        <textarea
          rows={5}
          value={form.text}
          onChange={(event) => updateField("text", event.target.value)}
        />
      </label>

      <div className="inline-actions">
        <IconButton icon={Upload} label="Ingest" variant="primary" onClick={onIngest} />
      </div>
      <pre>{ingestStatus}</pre>

      <div className="collections-list">
        <h3>Collections</h3>
        {collections.length ? (
          <div className="collection-grid">
            {collections.map((collection) => (
              <div className="collection-item" key={collection.name}>
                <strong>{collection.name}</strong>
                <span>{collection.documents} docs</span>
                <span>{collection.chunks} chunks</span>
                <span>{collection.vectorCount ?? 0} vectors</span>
              </div>
            ))}
          </div>
        ) : (
          <p>No collections yet.</p>
        )}

        {recentDocuments.length > 0 && (
          <div className="recent-docs">
            <h3>Recent Documents</h3>
            {recentDocuments.slice(0, 5).map((document) => (
              <span key={`${document.createdAt}-${document.title}`}>
                {document.title} ({document.collection}, {document.chunks} chunks)
              </span>
            ))}
          </div>
        )}
      </div>
    </section>
  );
}

function ResultPanels({ output, logs, stats }) {
  return (
    <section className="bottom-panel">
      <div>
        <h2>Results</h2>
        <pre>{output}</pre>
      </div>
      <div>
        <h2>Logs</h2>
        <pre>
          {logs.length
            ? logs.map((item) => `${item.nodeId}: [${item.status || "completed"}] ${item.message}`).join("\n")
            : "No logs yet."}
        </pre>
      </div>
      <div>
        <h2>Statistics</h2>
        <pre>{stats ? JSON.stringify(stats, null, 2) : "No statistics yet."}</pre>
      </div>
    </section>
  );
}

function RetrievalPanel({ retrievals }) {
  const matches = retrievals.flatMap((retrieval) => (
    (retrieval.matches || []).map((match, index) => ({
      ...match,
      nodeId: retrieval.nodeId,
      collection: retrieval.collection,
      index,
    }))
  ));

  return (
    <section className="retrieval-panel">
      <div className="section-header">
        <div>
          <h2>Retrieved Chunks</h2>
          <p>{matches.length ? `${matches.length} chunks returned by retriever nodes.` : "No retriever run yet."}</p>
        </div>
      </div>
      <div className="retrieved-chunks">
        {matches.map((match) => (
          <article key={`${match.nodeId}-${match.index}-${match.metadata?.chunkIndex}`}>
            <div>
              <strong>{match.metadata?.title || "Untitled"}</strong>
              <span>{match.collection}</span>
              <span>score {Number(match.score || 0).toFixed(4)}</span>
            </div>
            <p>{match.text}</p>
          </article>
        ))}
      </div>
    </section>
  );
}

function StatusBadge({ status }) {
  const labels = {
    idle: "Idle",
    running: "Running",
    completed: "Done",
    warning: "Warn",
    error: "Error",
  };
  return <span className={`status-badge ${status}`}>{labels[status] || status}</span>;
}

function IconButton({ icon: Icon, label, onClick, variant = "secondary" }) {
  return (
    <button className={variant} type="button" onClick={onClick}>
      <Icon size={16} />
      {label}
    </button>
  );
}

function selectionLabel(node, edge) {
  if (node) {
    return `${node.label} (${NODE_TYPES[node.type] || node.type})`;
  }
  if (edge) {
    return `${edge.source} -> ${edge.target}`;
  }
  return "No selection";
}
