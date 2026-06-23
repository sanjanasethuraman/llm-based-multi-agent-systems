export const NODE_TYPES = {
  input: "Input",
  agent: "Agent",
  sub_agent: "Sub-Agent",
  retriever: "Retriever",
  vector_db: "Vector DB",
  tool: "Tool",
  output: "Output",
};

const VALID_VECTOR_BACKENDS = new Set(["auto", "chroma", "local-json-fallback", "faiss"]);
const VALID_AGENT_PROVIDERS = new Set(["mock", "ollama", "huggingface", "api"]);
const VALID_RETRIEVAL_MODES = new Set(["vector", "graph", "hybrid"]);

export const DEFAULT_WORKFLOW = {
  nodes: [
    {
      id: "input-1",
      type: "input",
      label: "User Query",
      position: { x: 60, y: 205 },
      config: { text: "Explain how a visual multi-agent system builder should work." },
    },
    {
      id: "agent-1",
      type: "agent",
      label: "Planner Agent",
      position: { x: 290, y: 150 },
      config: {
        name: "Planner Agent",
        provider: "mock",
        model: "llama3.2:1b",
        baseUrl: "http://127.0.0.1:11434",
        huggingFaceToken: "",
        maxNewTokens: 512,
        temperature: 0.2,
        think: false,
        systemPrompt: "Break the user's request into a short implementation plan.",
      },
    },
    {
      id: "agent-2",
      type: "agent",
      label: "Writer Agent",
      position: { x: 520, y: 150 },
      config: {
        name: "Writer Agent",
        provider: "mock",
        model: "llama3.2:1b",
        baseUrl: "http://127.0.0.1:11434",
        huggingFaceToken: "",
        maxNewTokens: 512,
        temperature: 0.4,
        think: false,
        systemPrompt: "Write a concise final response based on the plan.",
      },
    },
    {
      id: "tool-1",
      type: "tool",
      label: "Word Count",
      position: { x: 520, y: 285 },
      config: { name: "Word Count", toolType: "word_count" },
    },
    {
      id: "output-1",
      type: "output",
      label: "Final Output",
      position: { x: 760, y: 205 },
      config: {},
    },
  ],
  edges: [
    { source: "input-1", target: "agent-1" },
    { source: "agent-1", target: "agent-2" },
    { source: "agent-2", target: "tool-1" },
    { source: "agent-2", target: "output-1" },
    { source: "tool-1", target: "output-1" },
  ],
};

const DEFAULT_CONFIGS = {
  input: { text: "New user query" },
  agent: {
    name: "Agent",
    provider: "mock",
    model: "llama3.2:1b",
    baseUrl: "http://127.0.0.1:11434",
    huggingFaceToken: "",
    maxNewTokens: 512,
    temperature: 0.2,
    think: false,
    systemPrompt: "You are a helpful assistant.",
  },
  retriever: {
    collection: "course_docs",
    retrievalMode: "vector",
    vectorBackend: "auto",
    embeddingModel: "nomic-embed-text",
    baseUrl: "http://127.0.0.1:11434",
    topK: 3,
    graphHops: 1,
    graphTopK: 5,
  },
  vector_db: {
    collection: "course_docs",
    vectorBackend: "auto",
    embeddingModel: "nomic-embed-text",
    baseUrl: "http://127.0.0.1:11434",
  },
  tool: { name: "Tool", toolType: "echo" },
  sub_agent: {
    name: "Sub-Agent",
    provider: "mock",
    model: "llama3.2:1b",
    baseUrl: "http://127.0.0.1:11434",
    huggingFaceToken: "",
    maxNewTokens: 512,
    temperature: 0.2,
    think: false,
    systemPrompt: "You are a helpful assistant.",
  },
  output: {},
};

export function createNode(type, index) {
  return {
    id: `${type}-${index}`,
    type,
    label: NODE_TYPES[type] || type,
    position: { x: 120 + index * 30, y: 90 + index * 24 },
    config: { ...(DEFAULT_CONFIGS[type] || {}) },
  };
}

export function normalizeWorkflow(rawWorkflow) {
  const nodes = Array.isArray(rawWorkflow?.nodes) ? rawWorkflow.nodes : [];
  const edges = Array.isArray(rawWorkflow?.edges) ? rawWorkflow.edges : [];

  return {
    nodes: nodes.map((node, index) => ({
      id: String(node.id || `node-${index + 1}`),
      type: node.type || "agent",
      label: node.label || NODE_TYPES[node.type] || node.id || `Node ${index + 1}`,
      position: node.position || { x: 80 + index * 190, y: 180 },
      config: { ...(DEFAULT_CONFIGS[node.type] || {}), ...(node.config || {}) },
    })),
    edges: edges
      .filter((edge) => edge?.source && edge?.target)
      .map((edge) => ({ source: String(edge.source), target: String(edge.target) })),
  };
}

export function calculateNextId(workflow) {
  const numbers = workflow.nodes
    .map((node) => Number(String(node.id).split("-").pop()))
    .filter((value) => Number.isFinite(value));
  return Math.max(3, ...numbers) + 1;
}

export function edgeId(edge) {
  return `${edge.source}->${edge.target}`;
}

export function validateWorkflow(workflow) {
  const errors = [];
  const warnings = [];
  const nodes = workflow.nodes || [];
  const edges = workflow.edges || [];
  const nodeMap = new Map(nodes.map((node) => [node.id, node]));

  if (!nodes.length) {
    errors.push("Workflow must contain at least one node.");
  }
  if (!nodes.some((node) => node.type === "output")) {
    errors.push("Workflow must contain at least one output node.");
  }
  if (!nodes.some((node) => node.type === "input")) {
    warnings.push("Workflow has no input node.");
  }

  const seenEdges = new Set();
  edges.forEach((edge) => {
    if (!nodeMap.has(edge.source)) {
      errors.push(`Edge references missing source node: ${edge.source}.`);
    }
    if (!nodeMap.has(edge.target)) {
      errors.push(`Edge references missing target node: ${edge.target}.`);
    }
    if (edge.source === edge.target) {
      errors.push(`Node ${edge.source} cannot connect to itself.`);
    }
    const id = edgeId(edge);
    if (seenEdges.has(id)) {
      warnings.push(`Duplicate edge: ${edge.source} -> ${edge.target}.`);
    }
    seenEdges.add(id);
  });

  nodes.forEach((node) => {
    const incoming = edges.filter((edge) => edge.target === node.id);
    const outgoing = edges.filter((edge) => edge.source === node.id);
    if (node.type === "output" && incoming.length === 0) {
      warnings.push(`Output node ${node.label || node.id} has no incoming edge.`);
    }
    if (!["input", "output"].includes(node.type) && incoming.length === 0 && outgoing.length === 0) {
      warnings.push(`Node ${node.label || node.id} is disconnected.`);
    }
    if (node.type === "retriever") {
      const retrievalMode = node.config?.retrievalMode || "vector";
      if (!VALID_RETRIEVAL_MODES.has(retrievalMode)) {
        errors.push(`Retriever ${node.label || node.id} has unsupported retrieval mode: ${retrievalMode}.`);
      }
      if (["graph", "hybrid"].includes(retrievalMode)) {
        warnings.push(`Retriever ${node.label || node.id} uses Neo4j Graph RAG; make sure Neo4j is running and seeded.`);
      }
      const queryEdges = incoming.filter((edge) => nodeMap.get(edge.source)?.type !== "vector_db");
      if (!queryEdges.length) {
        warnings.push(`Retriever ${node.label || node.id} has no query input.`);
      }
    }
    if (["retriever", "vector_db"].includes(node.type)) {
      const vectorBackend = node.config?.vectorBackend || "auto";
      if (!VALID_VECTOR_BACKENDS.has(vectorBackend)) {
        errors.push(`Node ${node.label || node.id} has unsupported vector backend: ${vectorBackend}.`);
      }
      if (vectorBackend === "faiss") {
        warnings.push(`Node ${node.label || node.id} selects FAISS, which is scaffolded but not implemented.`);
      }
    }
    if (node.type === "agent" || node.type === "sub_agent") {
      const provider = node.config?.provider || "mock";
      if (!VALID_AGENT_PROVIDERS.has(provider)) {
        errors.push(`Agent ${node.label || node.id} has unsupported provider: ${provider}.`);
      }
      if (provider === "api") {
        warnings.push(`Agent ${node.label || node.id} uses the placeholder api provider.`);
      }
      if (provider === "huggingface") {
        if (!node.config?.model) {
          warnings.push(`Agent ${node.label || node.id} uses Hugging Face without a model id.`);
        }
        if (!node.config?.huggingFaceToken) {
          warnings.push(
            `Agent ${node.label || node.id} uses Hugging Face without a saved token; the backend will look for HF_TOKEN or HUGGING_FACE_API_TOKEN.`,
          );
        }
      }
    }
  });

  if (!errors.length && hasCycle(nodes, edges)) {
    errors.push("Workflow contains a cycle.");
  }

  return { valid: errors.length === 0, errors, warnings };
}

function hasCycle(nodes, edges) {
  const indegree = new Map(nodes.map((node) => [node.id, 0]));
  const outgoing = new Map(nodes.map((node) => [node.id, []]));

  edges.forEach((edge) => {
    if (!indegree.has(edge.source) || !indegree.has(edge.target)) {
      return;
    }
    outgoing.get(edge.source).push(edge.target);
    indegree.set(edge.target, indegree.get(edge.target) + 1);
  });

  const queue = [...indegree.entries()]
    .filter(([, degree]) => degree === 0)
    .map(([nodeId]) => nodeId);
  let visited = 0;

  while (queue.length) {
    const nodeId = queue.shift();
    visited += 1;
    outgoing.get(nodeId).forEach((target) => {
      const nextDegree = indegree.get(target) - 1;
      indegree.set(target, nextDegree);
      if (nextDegree === 0) {
        queue.push(target);
      }
    });
  }

  return visited !== nodes.length;
}
