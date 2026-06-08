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
  { value: "huggingface", label: "Hugging Face" },
  { value: "api", label: "API" },
];
const providerDefaults = {
  huggingface: {
    baseUrl: "https://router.huggingface.co/v1",
    model: "mistralai/Mistral-7B-Instruct-v0.3",
  },
  ollama: {
    baseUrl: "http://127.0.0.1:11434",
    model: "llama3.2:1b",
  },
};
const vectorBackendOptions = [
  { value: "auto", label: "Auto" },
  { value: "chroma", label: "Chroma" },
  { value: "local-json-fallback", label: "Local JSON" },
  { value: "faiss", label: "FAISS" },
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
  const [mcpCalls, setMcpCalls] = useState([]);
  const [mcpTools, setMcpTools] = useState([]);
  const [examples, setExamples] = useState([]);
  const [selectedExample, setSelectedExample] = useState("");
  const [collections, setCollections] = useState([]);
  const [recentDocuments, setRecentDocuments] = useState([]);
  const [ollamaStatus, setOllamaStatus] = useState(null);
  const [huggingFaceStatus, setHuggingFaceStatus] = useState(null);
  const [ingestStatus, setIngestStatus] = useState("No document ingested yet.");
  const [ragForm, setRagForm] = useState({
    collection: "course_docs",
    vectorBackend: "auto",
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
    refreshMcpTools();
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

  useEffect(() => {
    if (selectedNode?.type !== "agent" || selectedNode?.config?.provider !== "huggingface") {
      setHuggingFaceStatus(null);
      return undefined;
    }

    const controller = new AbortController();
    const timeout = window.setTimeout(async () => {
      try {
        const result = await postJson("/api/provider/huggingface-status", {
          model: selectedNode.config.model,
          token: selectedNode.config.huggingFaceToken,
          baseUrl: selectedNode.config.baseUrl,
        });
        if (!controller.signal.aborted) {
          setHuggingFaceStatus(result);
        }
      } catch (error) {
        if (!controller.signal.aborted) {
          setHuggingFaceStatus({
            available: false,
            model: selectedNode.config.model,
            tokenConfigured: Boolean(selectedNode.config.huggingFaceToken),
            message: error.message,
          });
        }
      }
    }, 500);

    return () => {
      controller.abort();
      window.clearTimeout(timeout);
    };
  }, [
    selectedNode?.config?.baseUrl,
    selectedNode?.config?.huggingFaceToken,
    selectedNode?.config?.model,
    selectedNode?.config?.provider,
    selectedNode?.type,
  ]);

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
      setMcpCalls([]);
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
      setMcpCalls([]);
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
      setMcpCalls([]);
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
      setMcpCalls(result.mcpCalls || []);
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

  async function refreshMcpTools() {
    try {
      const result = await getJson("/api/mcp/tools");
      setMcpTools(result.tools || []);
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
            vectorBackend: ragForm.vectorBackend,
            embeddingModel: ragForm.embeddingModel,
            baseUrl: ragForm.baseUrl,
            documents,
          }
        : {
            collection: ragForm.collection,
            vectorBackend: ragForm.vectorBackend,
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
          huggingFaceStatus={huggingFaceStatus}
          mcpTools={mcpTools}
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
      <McpCallsPanel calls={mcpCalls} />

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
        {node.type === "mcp_tool" && <span>{node.config?.toolId || "unselected"}</span>}
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

function ConfigPanel({ node, validation, huggingFaceStatus, mcpTools, ollamaStatus, onNodeChange }) {
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
                    onClick={() => updateConfig({ provider: provider.value, ...(providerDefaults[provider.value] || {}) })}
                  >
                    {provider.label}
                  </button>
                ))}
              </div>
            </div>
            <ProviderNote
              provider={node.config.provider}
              huggingFaceStatus={huggingFaceStatus}
              ollamaStatus={ollamaStatus}
            />
            <label>
              {node.config.provider === "huggingface" ? "Hugging Face Model ID" : "Model"}
              <input
                value={node.config.model || ""}
                placeholder={node.config.provider === "huggingface" ? "mistralai/Mistral-7B-Instruct-v0.3" : "llama3.2:1b"}
                onChange={(event) => updateConfig({ model: event.target.value })}
              />
            </label>
            {node.config.provider === "huggingface" && (
              <label>
                Hugging Face Token
                <input
                  autoComplete="off"
                  type="password"
                  value={node.config.huggingFaceToken || ""}
                  placeholder="Uses HF_TOKEN on the backend if left blank"
                  onChange={(event) => updateConfig({ huggingFaceToken: event.target.value })}
                />
              </label>
            )}
            <label>
              {node.config.provider === "huggingface" ? "Inference API URL" : "Local Provider URL"}
              <input
                value={node.config.baseUrl || ""}
                placeholder={
                  node.config.provider === "huggingface"
                    ? "https://router.huggingface.co/v1"
                    : "http://127.0.0.1:11434"
                }
                onChange={(event) => updateConfig({ baseUrl: event.target.value })}
              />
            </label>
            {node.config.provider === "huggingface" && (
              <label>
                Max New Tokens
                <input
                  max="4096"
                  min="1"
                  step="1"
                  type="number"
                  value={node.config.maxNewTokens ?? 512}
                  onChange={(event) => updateConfig({ maxNewTokens: Number(event.target.value) })}
                />
              </label>
            )}
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
              Vector Backend
              <select
                value={node.config.vectorBackend || "auto"}
                onChange={(event) => updateConfig({ vectorBackend: event.target.value })}
              >
                {vectorBackendOptions.map((backend) => (
                  <option key={backend.value} value={backend.value}>
                    {backend.label}
                  </option>
                ))}
              </select>
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

        {node.type === "mcp_tool" && (
          <>
            <label>
              MCP Server
              <input
                value={node.config.server || "demo"}
                onChange={(event) => updateConfig({ server: event.target.value })}
              />
            </label>
            <label>
              MCP Tool
              <select
                value={node.config.toolId || ""}
                onChange={(event) => {
                  const selectedTool = mcpTools.find((tool) => tool.id === event.target.value);
                  updateConfig({
                    toolId: event.target.value,
                    server: selectedTool?.server || node.config.server || "demo",
                    name: selectedTool ? `MCP ${selectedTool.name}` : node.config.name,
                  });
                }}
              >
                <option value="">Select a tool</option>
                {mcpTools.map((tool) => (
                  <option key={tool.id} value={tool.id}>
                    {tool.id}
                  </option>
                ))}
              </select>
            </label>
            {mcpTools.find((tool) => tool.id === node.config.toolId)?.description && (
              <div className="provider-note neutral">
                {mcpTools.find((tool) => tool.id === node.config.toolId).description}
              </div>
            )}
            <label>
              Arguments JSON
              <textarea
                rows={7}
                value={node.config.arguments || "{}"}
                onChange={(event) => updateConfig({ arguments: event.target.value })}
              />
            </label>
            <label className="checkbox-field">
              <input
                checked={node.config.includeInput !== false}
                type="checkbox"
                onChange={(event) => updateConfig({ includeInput: event.target.checked })}
              />
              Include incoming workflow text
            </label>
          </>
        )}
      </div>

      <ValidationPanel validation={validation} />
    </aside>
  );
}

function ProviderNote({ provider, huggingFaceStatus, ollamaStatus }) {
  if (provider === "mock") {
    return <div className="provider-note neutral">Mock mode is deterministic and works offline.</div>;
  }
  if (provider === "api") {
    return <div className="provider-note warning">The API provider is a placeholder in this prototype.</div>;
  }
  if (provider === "huggingface") {
    if (!huggingFaceStatus) {
      return <div className="provider-note neutral">Checking Hugging Face link...</div>;
    }
    if (huggingFaceStatus.available && huggingFaceStatus.modelAvailable) {
      return (
        <div className="provider-note success">
          Hugging Face linked as {huggingFaceStatus.account}. Model {huggingFaceStatus.model} is available.
        </div>
      );
    }
    if (huggingFaceStatus.available) {
      return (
        <div className="provider-note warning">
          Hugging Face account linked as {huggingFaceStatus.account}. {huggingFaceStatus.message}
        </div>
      );
    }
    return <div className="provider-note warning">{huggingFaceStatus.message}</div>;
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
          Vector Backend
          <select value={form.vectorBackend} onChange={(event) => updateField("vectorBackend", event.target.value)}>
            {vectorBackendOptions.map((backend) => (
              <option key={backend.value} value={backend.value}>
                {backend.label}
              </option>
            ))}
          </select>
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
                <span>{collection.vectorBackend || collection.backend || "no vectors"}</span>
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

function McpCallsPanel({ calls }) {
  return (
    <section className="mcp-panel">
      <div className="section-header">
        <div>
          <h2>MCP Calls</h2>
          <p>{calls.length ? `${calls.length} MCP tool call(s) executed.` : "No MCP tool run yet."}</p>
        </div>
      </div>
      <div className="mcp-call-grid">
        {calls.map((call, index) => (
          <article key={`${call.nodeId}-${call.toolId}-${call.timestamp || index}`}>
            <div>
              <strong>{call.toolId}</strong>
              <span>{call.server || "demo"}</span>
              <span>{call.nodeId}</span>
            </div>
            <pre>{JSON.stringify({ arguments: call.arguments, result: call.result }, null, 2)}</pre>
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
