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

import { getJson, postJson, runWorkflowBatch, getVectorDatabaseProviders } from "./api.js";
import {
  calculateNextId,
  createNode,
  DEFAULT_WORKFLOW,
  edgeId,
  NODE_TYPES,
  normalizeWorkflow,
  validateWorkflow,
} from "./workflow.js";

import McpServersPanel from "./components/panels/McpServersPanel.jsx"
import WorkflowTabs from "./components/WorkflowTabs.jsx"
import ExecutionModeControl from "./components/ExecutionModeControl.jsx"
import ComparisonReport from "./components/ComparisonReport.jsx"
import IconButton from "./components/IconButton.jsx"
import { useWorkflowTabs } from "./hooks/useWorkflowTabs.js";

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
// Note: Dynamic options will be loaded from backend API in WorkflowApp component
const retrievalModeOptions = [
  { value: "vector", label: "Vector" },
  { value: "graph", label: "Graph" },
  { value: "hybrid", label: "Hybrid" },
];

export default function App() {
  return (
    <ReactFlowProvider>
      <WorkflowApp />
    </ReactFlowProvider>
  );
}

function WorkflowApp() {
  // Multi-tab workflow management
  const {
    tabs,
    activeTabId,
    activeTab,
    createTab,
    duplicateTab,
    updateTabWorkflow,
    updateTabExecutionMode,
    setTabExecutionResults,
    closeTab,
    renameTab,
    setActiveTabId,
  } = useWorkflowTabs(normalizeWorkflow(DEFAULT_WORKFLOW));

  // Current active workflow
  const workflow = activeTab?.workflow || normalizeWorkflow(DEFAULT_WORKFLOW);
  const executionMode = activeTab?.executionMode || 'independent';

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
  const [mcpServers, setMcpServers] = useState([]);
  const [examples, setExamples] = useState([]);
  const [selectedExample, setSelectedExample] = useState("");
  const [collections, setCollections] = useState([]);
  const [recentDocuments, setRecentDocuments] = useState([]);
  const [ollamaStatus, setOllamaStatus] = useState(null);
  const [huggingFaceStatus, setHuggingFaceStatus] = useState(null);
  const [graphStatus, setGraphStatus] = useState(null);
  const [ingestStatus, setIngestStatus] = useState("No document ingested yet.");
  const [comparisonReports, setComparisonReports] = useState([]);
  const [isRunningBatch, setIsRunningBatch] = useState(false);
  const [ragForm, setRagForm] = useState({
    collection: "course_docs",
    vectorBackend: "auto",
    graphEnabled: true,
    title: "Project Notes",
    embeddingModel: "nomic-embed-text",
    baseUrl: "http://127.0.0.1:11434",
    text: "A visual multi-agent system builder lets users create workflows by connecting components such as inputs, agents, tools, retrievers, vector databases, and outputs. RAG adds document ingestion, embeddings, vector search, and retrieved context so agents can answer using project-specific knowledge.",
    files: [],
  });
  const [dynamicVectorBackendOptions, setDynamicVectorBackendOptions] = useState(vectorBackendOptions);

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

  const retrievalByNode = useMemo(() => {
    const map = {};
    (retrievals || []).forEach((retrieval) => {
      if (!map[retrieval.nodeId]) {
        map[retrieval.nodeId] = {
          nodeId: retrieval.nodeId,
          nodeName: retrieval.nodeName,
          collection: retrieval.collection,
          vectorBackend: retrieval.vectorBackend,
          embeddingBackend: retrieval.embeddingBackend,
          matches: [],
        };
      }
      map[retrieval.nodeId].matches.push(...(retrieval.matches || []));
    });
    return map;
  }, [retrievals]);

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
          retrievalInfo: retrievalByNode[node.id],
        },
      })),
    [nodeResults, selected, workflow.nodes, retrievalByNode],
  );

  const flowEdges = useMemo(
    () =>
      workflow.edges.map((edge) => {
        const id = edgeId(edge);
        const sourceStatus = nodeResults[edge.source]?.status;
        const targetStatus = nodeResults[edge.target]?.status;
        const retrievalInfo = retrievalByNode[edge.source];
        const matchingChunks = retrievalInfo?.matches?.length || 0;
        return {
          id,
          source: edge.source,
          target: edge.target,
          selected: selected.kind === "edge" && selected.id === id,
          animated: sourceStatus === "completed" && targetStatus === "completed",
          markerEnd: { type: MarkerType.ArrowClosed },
          className: `flow-edge ${sourceStatus || ""} ${targetStatus || ""}`,
          label: matchingChunks > 0 ? `${matchingChunks} chunk${matchingChunks === 1 ? "" : "s"}` : undefined,
          labelBgPadding: [8, 6],
          labelBgStyle: matchingChunks > 0 ? { fill: "rgba(255,255,255,0.94)", color: "#1f2937", fillOpacity: 0.9, stroke: "#cbd5e1" } : undefined,
        };
      }),
    [nodeResults, selected, workflow.edges, retrievalByNode],
  );

  useEffect(() => {
    refreshExamples();
    refreshCollections();
    refreshMcpTools();
    refreshGraphStatus();
    loadVectorDatabaseProviders();
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
    const updated = normalizeWorkflow(typeof updater === "function" ? updater(workflow) : updater);
    updateTabWorkflow(activeTabId, updated);
  }, [workflow, activeTabId, updateTabWorkflow]);

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

  async function loadVectorDatabaseProviders() {
    try {
      const result = await getVectorDatabaseProviders();
      if (result.list && result.list.length > 0) {
        // Convert provider names to options format
        const options = result.list.map((provider) => ({
          value: provider,
          label: result.providers[provider]?.name || provider.charAt(0).toUpperCase() + provider.slice(1),
        }));
        setDynamicVectorBackendOptions(options);
      }
    } catch (error) {
      console.warn("Failed to load vector database providers:", error);
      // Fallback to default options
      setDynamicVectorBackendOptions(vectorBackendOptions);
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
      updateTabWorkflow(activeTabId, nextWorkflow);
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
      updateTabWorkflow(activeTabId, nextWorkflow);
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

  async function refreshGraphStatus() {
    try {
      const result = await getJson("/api/graph-rag/status");
      setGraphStatus(result);
    } catch (error) {
      setGraphStatus({ connected: false, message: error.message });
    }
  }

  async function seedBiomedicalGraph() {
    try {
      setStatusMessage("Seeding biomedical Neo4j graph...");
      const result = await postJson("/api/graph-rag/seed-demo", {});
      setIngestStatus(JSON.stringify(result, null, 2));
      setStatusMessage(`Seeded ${result.entities} entities and ${result.relationships} relationships into ${result.collection}.`);
      await refreshGraphStatus();
      await refreshCollections();
    } catch (error) {
      setIngestStatus(error.message);
      setStatusMessage(error.message);
    }
  }

  async function refreshMcpTools() {
    try {
      const [toolsResult, serversResult] = await Promise.all([
        getJson("/api/mcp/tools"),
        getJson("/api/mcp/servers"),
      ]);
      console.log("tools response:", toolsResult);
      console.log("servers response:", serversResult);
      setMcpTools(toolsResult.tools || []);
      setMcpServers(serversResult.servers || []);
    } catch (error) {
      console.error("refreshMcpTools error:", error);
      setStatusMessage(error.message);
    }
  }

  async function connectMcpServer(config) {
    try {
      setStatusMessage(`Connecting to ${config.label}...`);
      await postJson("/api/mcp/connect", config);
      await refreshMcpTools();
      setStatusMessage(`Connected: ${config.label}`);
    } catch (error) {
      setStatusMessage(error.message);
    }
  }

  async function disconnectMcpServer(id) {
    try {
      await postJson("/api/mcp/disconnect", { id });
      await refreshMcpTools();
      setStatusMessage(`Disconnected server: ${id}`);
    } catch (error) {
      setStatusMessage(error.message);
    }
  }

  async function arrayBufferToBase64(buffer) {
    const bytes = new Uint8Array(buffer);
    let binary = "";
    const chunkSize = 0x8000;
    for (let i = 0; i < bytes.length; i += chunkSize) {
      binary += String.fromCharCode(...bytes.subarray(i, i + chunkSize));
    }
    return btoa(binary);
  }

  function isBinaryDocument(file) {
    const extension = file.name.slice(file.name.lastIndexOf(".")).toLowerCase();
    return [".pdf", ".docx", ".pptx", ".ppt"].includes(extension) ||
      file.type === "application/pdf" ||
      file.type === "application/vnd.openxmlformats-officedocument.wordprocessingml.document" ||
      file.type === "application/vnd.openxmlformats-officedocument.presentationml.presentation" ||
      file.type === "application/vnd.ms-powerpoint";
  }

  async function readDocumentFile(file) {
    const document = {
      title: file.name,
      source: `file:${file.name}`,
      fileName: file.name,
      mimeType: file.type || "application/octet-stream",
    };

    if (isBinaryDocument(file)) {
      const fileData = await arrayBufferToBase64(await file.arrayBuffer());
      return { ...document, fileData };
    }

    return { ...document, text: await file.text() };
  }

  async function ingestDocuments() {
    try {
      setIngestStatus("Reading files...");
      const documents = ragForm.files.length
        ? await Promise.all(ragForm.files.map(readDocumentFile))
        : [];

      const payload = documents.length
        ? {
            collection: ragForm.collection,
            vectorBackend: ragForm.vectorBackend,
            graphEnabled: ragForm.graphEnabled,
            embeddingModel: ragForm.embeddingModel,
            baseUrl: ragForm.baseUrl,
            documents,
          }
        : {
            collection: ragForm.collection,
            vectorBackend: ragForm.vectorBackend,
            graphEnabled: ragForm.graphEnabled,
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
      setIngestStatus(error.message || JSON.stringify(error));
      setStatusMessage(error.message || JSON.stringify(error));
    }
  }

  async function runWorkflowSequential() {
    try {
      setIsRunningBatch(true);
      setStatusMessage("Running all workflows sequentially...");
      const result = await runWorkflowBatch(
        tabs.map((tab) => tab.workflow),
        'sequential'
      );
      setComparisonReports(result.batchResult.reports || []);
      setStatusMessage(`Sequential execution completed: ${result.summary.successCount}/${result.summary.totalWorkflows} succeeded`);
      
      // Update each tab with its results
      const reports = result.batchResult.reports || [];
      reports.forEach((report, idx) => {
        if (tabs[idx]) {
          setTabExecutionResults(tabs[idx].id, {
            status: report.status,
            durationMs: report.durationMs,
            timestamp: report.timestamp,
          });
        }
      });
    } catch (error) {
      setStatusMessage(`Batch execution failed: ${error.message}`);
      setComparisonReports([]);
    } finally {
      setIsRunningBatch(false);
    }
  }

  async function runWorkflowParallel() {
    try {
      setIsRunningBatch(true);
      setStatusMessage("Running all workflows in parallel...");
      const result = await runWorkflowBatch(
        tabs.map((tab) => tab.workflow),
        'parallel'
      );
      setComparisonReports(result.batchResult.reports || []);
      const speedup = result.summary.timeSpeedupFactor || 1;
      setStatusMessage(`Parallel execution completed: ${result.summary.successCount}/${result.summary.totalWorkflows} succeeded (${speedup.toFixed(2)}x speedup)`);
      
      // Update each tab with its results
      const reports = result.batchResult.reports || [];
      reports.forEach((report, idx) => {
        if (tabs[idx]) {
          setTabExecutionResults(tabs[idx].id, {
            status: report.status,
            durationMs: report.durationMs,
            timestamp: report.timestamp,
          });
        }
      });
    } catch (error) {
      setStatusMessage(`Batch execution failed: ${error.message}`);
      setComparisonReports([]);
    } finally {
      setIsRunningBatch(false);
    }
  }

  return (
    <div className="app-shell">
      <div className="workflow-tabs-section">
        <WorkflowTabs
          tabs={tabs}
          activeTabId={activeTabId}
          onSelectTab={setActiveTabId}
          onCreateTab={createTab}
          onDuplicateTab={duplicateTab}
          onCloseTab={closeTab}
          onRenameTab={renameTab}
        />
      </div>

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

      <ExecutionModeControl
        mode={executionMode}
        tabs={tabs}
        activeTabId={activeTabId}
        onModeChange={(mode) => updateTabExecutionMode(activeTabId, mode)}
        onRunSequential={runWorkflowSequential}
        onRunParallel={runWorkflowParallel}
        isRunning={isRunningBatch}
      />

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
          mcpServers={mcpServers}
          ollamaStatus={ollamaStatus}
          onNodeChange={updateNode}
        />
      </main>

      <RagPanel
        collections={collections}
        recentDocuments={recentDocuments}
        form={ragForm}
        graphStatus={graphStatus}
        ingestStatus={ingestStatus}
        ollamaStatus={ollamaStatus}
        onFormChange={setRagForm}
        onRefreshGraphStatus={refreshGraphStatus}
        onSeedBiomedicalGraph={seedBiomedicalGraph}
        onIngest={ingestDocuments}
        onRefreshCollections={refreshCollections}
        dynamicVectorBackendOptions={dynamicVectorBackendOptions}
      />

      <McpServersPanel
        servers={mcpServers}
        onConnect={connectMcpServer}
        onDisconnect={disconnectMcpServer}
        onRefresh={refreshMcpTools}
      />

      <ResultPanels output={output} logs={logs} stats={stats} nodeResults={nodeResults} retrievals={retrievals} />
      <RetrievalPanel retrievals={retrievals} />
      <McpCallsPanel calls={mcpCalls} />

      {comparisonReports.length > 0 && (
        <section className="comparison-panel">
          <div className="comparison-header">
            <h2>Workflow Comparison Report</h2>
            <p>{comparisonReports.length} workflows executed</p>
          </div>
          <ComparisonReport reports={comparisonReports} />
        </section>
      )}

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
  const { node, result, retrievalInfo } = data;
  const status = result?.status || "idle";
  const chunkCount = retrievalInfo?.matches?.length || 0;
  const details = retrievalInfo && chunkCount > 0;

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
        {node.type === "tool" && <span>{node.config?.toolName || "unselected"}</span>}
        {node.type === "sub_agent" && <span>{node.config?.name || "unknown"}</span>}
      </div>
      {details && (
        <div className="node-retrieval-summary">
          <span>{chunkCount} retrieved chunk{chunkCount === 1 ? "" : "s"}</span>
          <span>{retrievalInfo.collection}</span>
          <span>{retrievalInfo.vectorBackend}</span>
        </div>
      )}
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

function ConfigPanel({ node, validation, huggingFaceStatus, mcpTools, mcpServers, ollamaStatus, onNodeChange }) {
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
              Think
              <select value={node.config.think ?? false} onChange={(event) => updateConfig({ think: event.target.value })}>
                <option value={true}>true</option>
                <option value={false}>false</option>
              </select>
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
            {node.type === "retriever" && (
              <>
                <label>
                  Retrieval Mode
                  <select
                    value={node.config.retrievalMode || "vector"}
                    onChange={(event) => updateConfig({ retrievalMode: event.target.value })}
                  >
                    {retrievalModeOptions.map((mode) => (
                      <option key={mode.value} value={mode.value}>
                        {mode.label}
                      </option>
                    ))}
                  </select>
                </label>
                {["graph", "hybrid"].includes(node.config.retrievalMode || "vector") && (
                  <>
                    <label>
                      Graph Hops
                      <input
                        max="3"
                        min="1"
                        step="1"
                        type="number"
                        value={node.config.graphHops || 1}
                        onChange={(event) => updateConfig({ graphHops: Number(event.target.value) })}
                      />
                    </label>
                    <label>
                      Graph Top K
                      <input
                        max="20"
                        min="1"
                        step="1"
                        type="number"
                        value={node.config.graphTopK || 5}
                        onChange={(event) => updateConfig({ graphTopK: Number(event.target.value) })}
                      />
                    </label>
                  </>
                )}
              </>
            )}
            <label>
              Vector Backend
              <select
                value={node.config.vectorBackend || "auto"}
                onChange={(event) => updateConfig({ vectorBackend: event.target.value })}
              >
                {dynamicVectorBackendOptions.map((backend) => (
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
              Tool
              <select
                value={node.config.toolName ? `${node.config.serverId}::${node.config.toolName}` : ""}
                onChange={(event) => {
                  const [serverId, toolName] = event.target.value.split("::");
                  const tool = mcpTools.find(t => t.name === toolName && t.serverId === serverId);
                  updateConfig({
                    serverId,
                    toolName,
                    name: tool?.name || toolName,
                    description: tool?.description || "",
                  });
                }}
              >
                <option value="">Select a tool...</option>
                {mcpServers.length === 0 && (
                  <option disabled>No servers connected</option>
                )}
                {mcpServers.map(server => {
                  const serverTools = mcpTools.filter(t => t.serverId === server.id);
                  if (!serverTools.length) return null;
                  return (
                    <optgroup key={server.id} label={`${server.label} ${server.connected ? "✓" : "(offline)"}`}>
                      {serverTools.map(tool => (
                        <option key={`${server.id}::${tool.name}`} value={`${server.id}::${tool.name}`}>
                          {tool.name}
                        </option>
                      ))}
                    </optgroup>
                  );
                })}
              </select>
            </label>
            {node.config.description && (
              <div className="provider-note neutral">{node.config.description}</div>
            )}
            {node.config.toolName && (
              <div className="provider-note success">
                Server: <strong>{node.config.serverId}</strong> · Tool: <strong>{node.config.toolName}</strong>
              </div>
            )}
          </>
        )}

        {node.type === "sub_agent" && (
          <>
            <label>
              Sub Agent Name
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
              Think
              <select value={node.config.think ?? false} onChange={(event) => updateConfig({ think: event.target.value })}>
                <option value={true}>true</option>
                <option value={false}>false</option>
              </select>
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
  graphStatus,
  ingestStatus,
  ollamaStatus,
  onFormChange,
  onRefreshGraphStatus,
  onSeedBiomedicalGraph,
  onIngest,
  onRefreshCollections,
  dynamicVectorBackendOptions,
}) {
  const updateField = (field, value) => onFormChange((current) => ({ ...current, [field]: value }));
  return (
    <section className="rag-panel">
      <div className="section-header">
        <div>
          <h2>Documents / RAG Ingestion</h2>
          <p>Upload files into vector RAG and optionally index them into the Neo4j graph.</p>
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
            {dynamicVectorBackendOptions.map((backend) => (
              <option key={backend.value} value={backend.value}>
                {backend.label}
              </option>
            ))}
          </select>
        </label>
        <label>
          Graph Indexing
          <select value={String(form.graphEnabled)} onChange={(event) => updateField("graphEnabled", event.target.value === "true")}>
            <option value="true">Neo4j graph + vector</option>
            <option value="false">Vector only</option>
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

      <div className={`provider-note ${graphStatus?.connected ? "success" : "warning"}`}>
        <strong>Neo4j Graph RAG:</strong>{" "}
        {graphStatus
          ? `${graphStatus.connected ? "connected" : "not connected"} at ${graphStatus.uri || "bolt://127.0.0.1:7687"}. ${graphStatus.message || ""}`
          : "Checking graph backend..."}
        <div className="inline-actions">
          <IconButton icon={RefreshCcw} label="Graph Status" onClick={onRefreshGraphStatus} />
          <IconButton icon={Upload} label="Seed Biomedical KG" variant="primary" onClick={onSeedBiomedicalGraph} />
        </div>
      </div>

      <label className="file-upload">
        <Upload size={18} />
        <span>{form.files.length ? `${form.files.length} file(s) selected` : "Choose files for ingestion"}</span>
        <input
          multiple
          accept=".txt,.md,.json,.csv,.py,.js,.css,.html,.htm,.pdf,.docx,.pptx,text/*,application/json,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document,application/vnd.openxmlformats-officedocument.presentationml.presentation"
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

function ResultPanels({ output, logs, stats, nodeResults, retrievals }) {
  const [selectedLogFilter, setSelectedLogFilter] = useState("all");
  const [searchTerm, setSearchTerm] = useState("");
  const [showFullOutput, setShowFullOutput] = useState(false);
  const [copyStatus, setCopyStatus] = useState("");
  const [resultsTab, setResultsTab] = useState("final");

  const nodes = useMemo(
    () =>
      Object.entries(nodeResults || {}).map(([id, result]) => ({
        id,
        ...result,
      })),
    [nodeResults],
  );

  const nodesDisplayed = nodes.filter((node) => node.outputPreview || node.message || node.status);

  const logCounts = useMemo(() => {
    return logs.reduce(
      (acc, log) => {
        const status = log.status || "completed";
        acc[status] = (acc[status] || 0) + 1;
        acc.all += 1;
        return acc;
      },
      { all: 0, completed: 0, warning: 0, error: 0 },
    );
  }, [logs]);

  const filteredLogs = useMemo(() => {
    return logs.filter((log) => {
      if (selectedLogFilter !== "all" && (log.status || "completed") !== selectedLogFilter) {
        return false;
      }
      if (!searchTerm.trim()) {
        return true;
      }
      const needle = searchTerm.toLowerCase();
      return `${log.nodeId} ${log.message} ${log.type || ""}`.toLowerCase().includes(needle);
    });
  }, [logs, selectedLogFilter, searchTerm]);

  const handleCopyOutput = async () => {
    try {
      await navigator.clipboard.writeText(output || "");
      setCopyStatus("Copied!");
      window.setTimeout(() => setCopyStatus(""), 2000);
    } catch (error) {
      setCopyStatus("Copy failed");
      window.setTimeout(() => setCopyStatus(""), 2000);
    }
  };

  const outputPreview = showFullOutput ? output : output?.slice(0, 1200) || "";
  const canShowMore = output && output.length > 1200;

  return (
    <section className="bottom-panel">
      <section className="results-panel">
        <div className="section-header">
          <div>
            <h2>Results</h2>
            <p>Review workflow output quickly and inspect node-level results when available.</p>
          </div>
        </div>
        <div className="result-summary-grid">
          <div className="stat-card">
            <span>Final output</span>
            <strong>{output ? `${Math.min(output.length, 1200)} chars shown` : "No output"}</strong>
          </div>
          <div className="stat-card">
            <span>Node results</span>
            <strong>{nodesDisplayed.length}</strong>
          </div>
          <div className="stat-card">
            <span>Errors</span>
            <strong>{logCounts.error}</strong>
          </div>
          <div className="stat-card">
            <span>Warnings</span>
            <strong>{logCounts.warning}</strong>
          </div>
        </div>
        <div className="results-tabs">
          <button
            type="button"
            className={`results-tab ${resultsTab === "final" ? "active" : ""}`}
            onClick={() => setResultsTab("final")}
          >
            Final Output
          </button>
          <button
            type="button"
            className={`results-tab ${resultsTab === "nodes" ? "active" : ""}`}
            onClick={() => setResultsTab("nodes")}
          >
            Node Outputs
          </button>
        </div>
        <div className="result-output-card result-output-final">
          <div className="result-output-header">
            <div>
              <strong>{resultsTab === "final" ? "Final Output" : "Node-level Output"}</strong>
              <span>{resultsTab === "final" ? "The merged workflow output shown clearly." : "Inspect results returned by individual nodes."}</span>
            </div>
            <div className="result-output-actions">
              <button className="icon-button" type="button" onClick={handleCopyOutput}>
                Copy
              </button>
              {resultsTab === "final" && canShowMore && (
                <button
                  className="icon-button"
                  type="button"
                  onClick={() => setShowFullOutput((current) => !current)}
                >
                  {showFullOutput ? "Collapse" : "Expand"}
                </button>
              )}
            </div>
          </div>
          {resultsTab === "final" ? (
            <pre>{outputPreview || "No output yet."}</pre>
          ) : nodesDisplayed.length ? (
            <div className="node-results-list">
              {nodesDisplayed.map((node) => (
                <article key={node.id} className="node-result-item">
                  <div className="node-result-header">
                    <div>
                      <strong>{node.id}</strong>
                      <span>{node.type}</span>
                    </div>
                    <StatusBadge status={node.status || "idle"} />
                  </div>
                  <div className="node-result-meta">
                    <span>{node.durationMs?.toFixed(2) ?? "0"}ms</span>
                    {node.message ? <span>{node.message}</span> : null}
                  </div>
                  <pre>{node.outputPreview || "No preview available."}</pre>
                </article>
              ))}
            </div>
          ) : (
            <div className="node-results-empty">No node-level results available yet.</div>
          )}
          {copyStatus && <div className="copy-feedback">{copyStatus}</div>}
        </div>
      </section>

      <section className="logs-panel">
        <div className="section-header">
          <div>
            <h2>Logs</h2>
            <p>Filter and search execution logs for better insight.</p>
          </div>
        </div>
        <div className="log-toolbar">
          <div className="log-filters">
            {[
              { key: "all", label: `All (${logCounts.all})` },
              { key: "completed", label: `Done (${logCounts.completed})` },
              { key: "warning", label: `Warn (${logCounts.warning})` },
              { key: "error", label: `Error (${logCounts.error})` },
            ].map((filter) => (
              <button
                key={filter.key}
                type="button"
                className={`filter-button ${selectedLogFilter === filter.key ? "active" : ""}`}
                onClick={() => setSelectedLogFilter(filter.key)}
              >
                {filter.label}
              </button>
            ))}
          </div>
          <input
            className="log-search"
            placeholder="Search logs"
            value={searchTerm}
            onChange={(event) => setSearchTerm(event.target.value)}
          />
        </div>
        <div className="log-summary-grid">
          <div className="log-stat-card">
            <strong>{filteredLogs.length}</strong>
            <span>Shown</span>
          </div>
          <div className="log-stat-card">
            <strong>{logCounts.error}</strong>
            <span>Total errors</span>
          </div>
          <div className="log-stat-card">
            <strong>{logCounts.warning}</strong>
            <span>Total warnings</span>
          </div>
        </div>
        <div className="log-list">
          {filteredLogs.length ? (
            filteredLogs.map((item, index) => (
              <article key={`${item.nodeId}-${index}`} className={`log-entry ${item.status || "completed"}`}>
                <div className="log-entry-header">
                  <StatusBadge status={item.status || "completed"} />
                  <span className="log-entry-meta">{item.nodeId}</span>
                </div>
                <p>{item.message}</p>
              </article>
            ))
          ) : (
            <p className="log-empty">No logs match the current filter.</p>
          )}
        </div>
      </section>

      <WorkflowStatsPanel stats={stats} retrievals={retrievals} />
      <NodeStatsPanel nodeResults={nodeResults} stats={stats} />
    </section>
  );
}

function WorkflowStatsPanel({ stats, retrievals }) {
  const retrievedChunks = useMemo(
    () => retrievals?.reduce((acc, retrieval) => acc + (retrieval.matches?.length || 0), 0) || 0,
    [retrievals],
  );

  const retrieverNodes = useMemo(
    () => new Set((retrievals || []).map((retrieval) => retrieval.nodeId)).size,
    [retrievals],
  );

  const retrievalCollections = useMemo(
    () => new Set((retrievals || []).map((retrieval) => retrieval.collection)).size,
    [retrievals],
  );

  const retrievalsWithMatches = useMemo(
    () => (retrievals || []).filter((retrieval) => (retrieval.matches || []).length > 0).length,
    [retrievals],
  );

  const metricCards = [
    { label: "Workflow runtime", value: stats?.runtimeMs, unit: "ms", key: "runtimeMs" },
    { label: "Nodes executed", value: stats?.nodesExecuted, unit: "", key: "nodesExecuted" },
    { label: "Agent calls", value: stats?.agentCalls, unit: "", key: "agentCalls" },
    { label: "Sub-Agent calls", value: stats?.subAgentCalls, unit: "", key: "subAgentCalls" },
    { label: "Tool calls", value: stats?.toolCalls, unit: "", key: "toolCalls" },
    { label: "Retriever calls", value: stats?.retrieverCalls, unit: "", key: "retrieverCalls" },
    { label: "Retrieved chunks", value: retrievedChunks, unit: "", key: "retrievedChunks" },
    { label: "Retriever nodes", value: retrieverNodes, unit: "", key: "retrieverNodes" },
    { label: "Collections retrieved", value: retrievalCollections, unit: "", key: "retrievalCollections" },
    { label: "Hit retrievals", value: retrievalsWithMatches, unit: "", key: "retrievalsWithMatches" },
    { label: "Tokens est.", value: stats?.estimatedTokens, unit: "", key: "estimatedTokens" },
  ];

  const [selectedMetric, setSelectedMetric] = useState(metricCards[0].key);
  const selected = metricCards.find((card) => card.key === selectedMetric) || metricCards[0];

  return (
    <section className="workflow-stats-panel">
      <div className="section-header">
        <div>
          <h2>Workflow Stats</h2>
          <p>Interactive execution metrics for your workflow run.</p>
        </div>
      </div>
      <div className="workflow-stats-grid">
        {metricCards.map((card) => (
          <button
            key={card.key}
            type="button"
            className={`metric-card ${selectedMetric === card.key ? "active" : ""}`}
            onClick={() => setSelectedMetric(card.key)}
          >
            <span>{card.label}</span>
            <strong>{card.value ?? 0}{card.unit}</strong>
          </button>
        ))}
      </div>
      <div className="metric-detail-card">
        <div className="metric-detail-header">
          <h3>{selected.label}</h3>
          <span>{selected.value ?? 0}{selected.unit}</span>
        </div>
        <p>
          {selected.key === "runtimeMs" && "Total time required to execute the workflow."}
          {selected.key === "nodesExecuted" && "The number of nodes that ran in this workflow execution."}
          {selected.key === "agentCalls" && "How many agent nodes triggered language model calls."}
          {selected.key === "subAgentCalls" && "How many sub agent nodes were triggered."}
          {selected.key === "toolCalls" && "Count of tool nodes executed during the workflow."}
          {selected.key === "retrieverCalls" && "Retriever nodes that fetched context from the vector store."}
          {selected.key === "retrievedChunks" && "Total matched chunks returned by retriever nodes."}
          {selected.key === "retrieverNodes" && "Number of retriever nodes that participated in this run."}
          {selected.key === "retrievalCollections" && "Distinct vector collections queried during retrieval."}
          {selected.key === "retrievalsWithMatches" && "Retriever executions that returned at least one matched chunk."}
          {selected.key === "estimatedTokens" && "Rough total token usage estimated from generated and retrieved text."}
        </p>
      </div>
    </section>
  );
}

function NodeStatsPanel({ nodeResults, stats }) {
  const nodes = useMemo(
    () =>
      Object.entries(nodeResults || {}).map(([id, result]) => ({
        id,
        ...result,
      })),
    [nodeResults],
  );

  const [activeTab, setActiveTab] = useState("overview");
  const [selectedType, setSelectedType] = useState("all");
  const [focusedNode, setFocusedNode] = useState(null);

  if (!nodes.length) {
    return (
      <div>
        <h2>Node Statistics</h2>
        <p>No node execution stats available yet.</p>
      </div>
    );
  }

  const nodesSorted = [...nodes].sort((a, b) => (b.durationMs || 0) - (a.durationMs || 0));
  const durations = nodes.map((node) => node.durationMs || 0);
  const maxDuration = Math.max(...durations, 1);
  const totalDuration = durations.reduce((sum, value) => sum + value, 0);
  const averageDuration = (totalDuration / nodes.length).toFixed(2);

  const typeStats = Object.values(
    nodes.reduce((acc, node) => {
      const type = node.type || "unknown";
      const duration = node.durationMs || 0;
      if (!acc[type]) {
        acc[type] = { type, count: 0, totalDuration: 0 };
      }
      acc[type].count += 1;
      acc[type].totalDuration += duration;
      return acc;
    }, {}),
  ).map((entry) => ({
    ...entry,
    averageDuration: entry.count ? entry.totalDuration / entry.count : 0,
  })).sort((a, b) => b.totalDuration - a.totalDuration);

  const nodeTypes = ["all", ...new Set(nodes.map((node) => node.type || "unknown"))];
  const filteredNodes = selectedType === "all" ? nodes : nodes.filter((node) => node.type === selectedType);

  const renderTabContent = () => {
    switch (activeTab) {
      case "overview":
        return (
          <div className="node-stat-overview-grid">
            {filteredNodes.map((node, index) => (
              <article
                key={node.id}
                className={`node-stat-summary ${focusedNode === node.id ? "focused" : ""}`}
                onMouseEnter={() => setFocusedNode(node.id)}
                onMouseLeave={() => setFocusedNode(null)}
              >
                <div className="node-stat-summary-header">
                  <strong>{node.id}</strong>
                  <StatusBadge status={node.status || "idle"} />
                </div>
                <span>{node.type}</span>
                <div className="node-stat-summary-values">
                  <strong>{(node.durationMs || 0).toFixed(2)}ms</strong>
                  <span>{node.outputPreview ? "Output available" : "No output"}</span>
                </div>
              </article>
            ))}
          </div>
        );
      case "slowest":
        return (
          <div className="node-ranking-list">
            {nodesSorted.slice(0, 8).map((node, index) => (
              <div
                key={node.id}
                className={`node-ranking-item ${focusedNode === node.id ? "focused" : ""}`}
                onMouseEnter={() => setFocusedNode(node.id)}
                onMouseLeave={() => setFocusedNode(null)}
              >
                <span>{index + 1}</span>
                <div>
                  <strong>{node.id}</strong>
                  <div className="node-ranking-meta">
                    <span>{node.type}</span>
                    <span>{(node.durationMs || 0).toFixed(2)}ms</span>
                  </div>
                </div>
                <StatusBadge status={node.status || "idle"} />
              </div>
            ))}
          </div>
        );
      case "type":
        return (
          <div className="type-breakdown-list">
            {typeStats.map((typeStat) => (
              <article key={typeStat.type} className="type-breakdown-item">
                <strong>{typeStat.type}</strong>
                <span>{typeStat.count} node{typeStat.count === 1 ? "" : "s"}</span>
                <span>{typeStat.totalDuration.toFixed(2)}ms total</span>
                <span>{typeStat.averageDuration.toFixed(2)}ms avg</span>
              </article>
            ))}
          </div>
        );
      default:
        return (
          <div className="chart-grid">
            {nodesSorted.map((node) => (
              <div
                key={node.id}
                className={`chart-row ${focusedNode === node.id ? "focused" : ""}`}
                onMouseEnter={() => setFocusedNode(node.id)}
                onMouseLeave={() => setFocusedNode(null)}
              >
                <div className="chart-label">
                  <strong>{node.id}</strong>
                  <span>{node.type}</span>
                </div>
                <div className="chart-bar">
                  <div
                    className="chart-fill"
                    style={{ width: `${((node.durationMs || 0) / maxDuration) * 100}%` }}
                  />
                </div>
                <span className="chart-value">{(node.durationMs || 0).toFixed(2)}ms</span>
              </div>
            ))}
          </div>
        );
    }
  };

  return (
    <section className="node-stats-panel interactive">
      <div className="section-header">
        <div>
          <h2>Node Execution Insights</h2>
          <p>More detailed stats for workflow node performance.</p>
        </div>
      </div>
      <div className="node-stats-overview">
        <div className="stat-card">
          <strong>{stats?.nodesExecuted ?? nodes.length}</strong>
          <span>Nodes executed</span>
        </div>
        <div className="stat-card">
          <strong>{stats?.runtimeMs ?? totalDuration}ms</strong>
          <span>Total runtime</span>
        </div>
        <div className="stat-card">
          <strong>{averageDuration}ms</strong>
          <span>Avg node duration</span>
        </div>
        <div className="stat-card">
          <strong>{nodesSorted[0]?.id || "-"}</strong>
          <span>Slowest node</span>
        </div>
      </div>
      <div className="node-stats-control-bar">
        <div className="node-stats-tabs">
          {[
            { key: "overview", label: "Overview" },
            { key: "slowest", label: "Slowest" },
            { key: "type", label: "Type" },
            { key: "chart", label: "Chart" },
          ].map((tab) => (
            <button
              key={tab.key}
              type="button"
              className={`tab-button ${activeTab === tab.key ? "active" : ""}`}
              onClick={() => setActiveTab(tab.key)}
            >
              {tab.label}
            </button>
          ))}
        </div>
        <select
          className="node-type-filter"
          value={selectedType}
          onChange={(event) => setSelectedType(event.target.value)}
        >
          {nodeTypes.map((type) => (
            <option key={type} value={type}>
              {type === "all" ? "All node types" : type}
            </option>
          ))}
        </select>
      </div>
      {renderTabContent()}
    </section>
  );
}

function RetrievalPanel({ retrievals }) {
  const matches = retrievals.flatMap((retrieval) => {
    const hits = (retrieval.matches || []).map((match, index) => ({
      ...match,
      nodeId: retrieval.nodeId,
      nodeType: retrieval.nodeType,
      nodeName: retrieval.nodeName,
      stage: retrieval.stage,
      collection: retrieval.collection,
      vectorBackend: retrieval.vectorBackend,
      embeddingBackend: retrieval.embeddingBackend,
      retrievalContext: retrieval.context,
      index,
    }));

    if (hits.length) {
      return hits;
    }

    return [{
      nodeId: retrieval.nodeId,
      nodeType: retrieval.nodeType,
      nodeName: retrieval.nodeName,
      stage: retrieval.stage,
      collection: retrieval.collection,
      vectorBackend: retrieval.vectorBackend,
      embeddingBackend: retrieval.embeddingBackend,
      retrievalContext: retrieval.context,
      index: null,
      text: retrieval.context || "Retriever executed with no matches.",
      score: null,
      metadata: {},
      placeholder: true,
    }];
  });

  const retrievedChunkCount = matches.filter((match) => !match.placeholder).length;
  const hasRetrieverRun = retrievals.length > 0;
  const graphEvidence = retrievals
    .map((retrieval) => ({
      nodeId: retrieval.nodeId,
      nodeName: retrieval.nodeName,
      collection: retrieval.collection,
      retrievalMode: retrieval.retrievalMode,
      evidence: retrieval.graphEvidence,
    }))
    .filter((item) => item.evidence && (item.evidence.entities?.length || item.evidence.relationships?.length || item.evidence.message));

  return (
    <section className="retrieval-panel">
      <div className="section-header">
        <div>
          <h2>Retrieved Chunks</h2>
          <p>{hasRetrieverRun ? `${retrievedChunkCount} chunks returned by retriever nodes.` : "No retriever run yet."}</p>
        </div>
      </div>
      <div className="retrieved-chunks">
        {matches.map((match) => (
          <article key={`${match.nodeId}-${match.index}-${match.metadata?.chunkIndex}-${match.placeholder ? "none" : "match"}`}>
            <div>
              <strong>{match.metadata?.title || (match.placeholder ? "Retriever result" : "Untitled")}</strong>
              <span>{match.nodeName || match.nodeId}</span>
              <span>Stage: {match.stage}</span>
              <span>Collection: {match.collection}</span>
              <span>{match.placeholder ? "no chunks" : `Chunk ${match.metadata?.chunkIndex ?? match.index}`}</span>
              {match.placeholder ? null : <span>Score: {Number(match.score || 0).toFixed(4)}</span>}
              {!match.placeholder && match.vectorBackend ? <span>Vector: {match.vectorBackend}</span> : null}
            </div>
            <p>{match.text}</p>
            <div className="retrieval-meta">
              <small>{match.placeholder ? (match.retrievalContext || "No matches were found.") : `source: ${match.metadata?.source || "unknown"}`}</small>
            </div>
          </article>
        ))}
      </div>
      {graphEvidence.length > 0 && (
        <div className="graph-evidence">
          <h3>Graph Evidence</h3>
          {graphEvidence.map((item) => (
            <article key={`${item.nodeId}-${item.collection}-graph`}>
              <div>
                <strong>{item.nodeName || item.nodeId}</strong>
                <span>{item.retrievalMode || "graph"}</span>
                <span>{item.collection}</span>
                <span>{item.evidence.status || "available"}</span>
              </div>
              {item.evidence.message && <p>{item.evidence.message}</p>}
              {item.evidence.entities?.length ? (
                <p>
                  <strong>Entities:</strong>{" "}
                  {item.evidence.entities.slice(0, 12).map((entity) => `${entity.type || "Entity"}:${entity.name}`).join(", ")}
                </p>
              ) : null}
              {item.evidence.relationships?.length ? (
                <ul>
                  {item.evidence.relationships.slice(0, 10).map((relationship, index) => (
                    <li key={`${relationship.source}-${relationship.target}-${relationship.type}-${index}`}>
                      {relationship.sourceName} -[{relationship.type}]-&gt; {relationship.targetName}
                    </li>
                  ))}
                </ul>
              ) : null}
            </article>
          ))}
        </div>
      )}
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


function selectionLabel(node, edge) {
  if (node) {
    return `${node.label} (${NODE_TYPES[node.type] || node.type})`;
  }
  if (edge) {
    return `${edge.source} -> ${edge.target}`;
  }
  return "No selection";
}
