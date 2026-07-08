import { Activity, BrainCircuit, Database, FileText, Network, Server, Wrench } from "lucide-react";

import StatusPill from "./ui/StatusPill.jsx";

function classify(value) {
  if (value === true) return "success";
  if (value === false) return "warning";
  return "neutral";
}

function labelFor(value, readyLabel, missingLabel) {
  if (value === true) return readyLabel;
  if (value === false) return missingLabel;
  return "unknown";
}

export default function DemoStatusBar({
  backendKnown,
  collections = [],
  graphLoaded,
  graphStatus,
  mcpServers = [],
  primekgStatus,
}) {
  const neo4jConnected = primekgStatus?.neo4jConnected ?? primekgStatus?.neo4j?.connected ?? graphStatus?.connected;
  const csvFound = primekgStatus?.fileExists;
  const connectedMcpServers = mcpServers.filter((server) => server.connected).length;
  const vectorReady = collections.length > 0 ? true : undefined;

  const items = [
    {
      icon: Server,
      label: "Backend",
      status: classify(backendKnown),
      value: labelFor(backendKnown, "online", "offline"),
    },
    {
      icon: Database,
      label: "Vector Store",
      status: classify(vectorReady),
      value: collections.length ? `${collections.length} collection${collections.length === 1 ? "" : "s"}` : "unknown",
    },
    {
      icon: Network,
      label: "Neo4j",
      status: classify(neo4jConnected),
      value: labelFor(neo4jConnected, "connected", "offline"),
    },
    {
      icon: FileText,
      label: "PrimeKG CSV",
      status: classify(csvFound),
      value: labelFor(csvFound, "found", "missing"),
    },
    {
      icon: BrainCircuit,
      label: "Graph",
      status: classify(graphLoaded),
      value: labelFor(graphLoaded, "loaded", "not loaded"),
    },
    {
      icon: Wrench,
      label: "MCP",
      status: connectedMcpServers ? "success" : mcpServers.length ? "warning" : "neutral",
      value: connectedMcpServers ? `${connectedMcpServers} connected` : mcpServers.length ? "configured" : "unknown",
    },
  ];

  return (
    <section className="demo-status-bar" aria-label="Demo readiness status">
      <div className="demo-status-bar__title">
        <Activity size={16} aria-hidden="true" />
        <span>Demo readiness</span>
      </div>
      <div className="demo-status-bar__items">
        {items.map((item) => {
          const Icon = item.icon;
          return (
            <StatusPill key={item.label} status={item.status}>
              <Icon size={14} aria-hidden="true" />
              <span>{item.label}</span>
              <strong>{item.value}</strong>
            </StatusPill>
          );
        })}
      </div>
    </section>
  );
}
