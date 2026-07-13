import { BrainCircuit, Database, Eye, GitBranch, Network, Play, Search, Wrench } from "lucide-react";
import { useState } from "react";
import ActionButton from "./ui/ActionButton.jsx";
import StatusPill from "./ui/StatusPill.jsx";

const journeySteps = [
  { label: "Load demo workflow", action: "load" },
  { label: "Inspect agents/tools", action: "inspect" },
  { label: "Run workflow", action: "run" },
  { label: "Explore retrieved context", action: "evidence" },
  { label: "Open graph evidence", action: "graph" },
];

const quickStarts = [
  {
    key: "review_pipeline_workflow",
    fallbackTitle: "Review Pipeline",
    fallbackDescription: "Drafts live release notes with a local LLM agent.",
    icon: GitBranch,
    accent: "blue",
  },
  {
    key: "rag_qa_workflow",
    fallbackTitle: "RAG Q&A",
    fallbackDescription: "Retrieves context from the course_docs collection before answering.",
    icon: Database,
    accent: "green",
  },
  {
    key: "primekg_migraine_graph_rag_workflow",
    fallbackTitle: "PrimeKG Migraine Graph RAG",
    fallbackDescription: "Demo workflow for querying a filtered PrimeKG migraine subgraph imported into Neo4j.",
    icon: BrainCircuit,
    accent: "violet",
  },
  {
    key: "mcp_tool_workflow",
    fallbackTitle: "MCP Tool Demo",
    fallbackDescription: "Uses a live local LLM agent to write a demo note.",
    icon: Wrench,
    accent: "amber",
  },
];

export default function GuidedDemoPanel({
  checklist,
  examples = [],
  onLoadExample,
  onOpenEvidence,
  onOpenGraph,
  onRunWorkflow,
  workflowLoaded,
}) {
  const examplesByName = new Map(examples.map((example) => [example.name, example]));
  const [open, setOpen] = useState(false);
  const defaultDemoKey = quickStarts.find((card) => examplesByName.has(card.key))?.key || examples[0]?.name || "";
  const readyByAction = {
    load: Boolean(defaultDemoKey),
    inspect: workflowLoaded,
    run: workflowLoaded,
    evidence: workflowLoaded,
    graph: workflowLoaded,
  };

  function handleJourneyStep(action) {
    if (action === "load" && defaultDemoKey) {
      onLoadExample(defaultDemoKey);
    } else if (action === "inspect") {
      document.querySelector(".workspace")?.scrollIntoView({ behavior: "smooth", block: "start" });
    } else if (action === "run") {
      onRunWorkflow();
    } else if (action === "evidence") {
      onOpenEvidence();
    } else if (action === "graph") {
      onOpenGraph();
    }
  }

  return (
    <section className={`guided-demo-panel ${open ? "open" : ""}`}>
      
      <div className="guided-demo-main">
        <div className="guided-demo-heading">
          <span><Search size={14} aria-hidden="true" /> Guided demo</span>
          <h2>Build an explainable AI workflow in 5 steps</h2>
          <p>Start with a curated workflow, run it, then inspect retrieved context and graph evidence without guessing where to click.</p>
        </div>

        <div className="guided-journey" aria-label="Demo journey steps">
          {journeySteps.map((step, index) => (
            <button
              key={step.label}
              type="button"
              className={readyByAction[step.action] ? "active" : ""}
              onClick={() => handleJourneyStep(step.action)}
              disabled={step.action === "load" && !defaultDemoKey}
            >
              <span>{index + 1}</span>
              <strong>{step.label}</strong>
            </button>
          ))}
        </div>
      </div>
      <button
        className="action-button guided-demo-header"
        onClick={() => setOpen(!open)}
        aria-expanded={open}
      >
        <span>
        {open ? "Hide guided demo" : "Continue guided demo"}
        </span>
      </button>
      
      <section className={`guided-demo-content ${open ? "expanded" : ""}`}>
        <div className="quick-start-grid">
          {quickStarts.map((card) => {
            const Icon = card.icon;
            const example = examplesByName.get(card.key);
            const available = Boolean(example);
            const title = example?.label || card.fallbackTitle;
            const description = example?.description || card.fallbackDescription;
            return (
              <article className={`quick-start-card ${card.accent}`} key={card.key}>
                <div className="quick-start-icon"><Icon size={18} aria-hidden="true" /></div>
                <div>
                  <h3>{title}</h3>
                  <p>{description}</p>
                </div>
                  <div className="quick-start-actions">
                  <ActionButton variant="secondary" disabled={!available} onClick={() => onLoadExample(card.key)}>
                    Load this demo
                  </ActionButton>
                  <ActionButton icon={Play} variant="primary" onClick={onRunWorkflow}>
                    Run now
                  </ActionButton>
                  {card.key.includes("primekg") ? (
                    <ActionButton icon={Network} variant="ghost" onClick={onOpenGraph}>
                      Open graph
                    </ActionButton>
                  ) : (
                    <ActionButton icon={Eye} variant="ghost" onClick={onOpenEvidence}>
                      View evidence
                    </ActionButton>
                  )}
                </div>
              </article>
            );
          })}
        </div>

        <div className="demo-ready-checklist" aria-label="Demo ready checklist">
          {checklist.map((item) => (
            <StatusPill key={item.label} status={item.ready ? "success" : item.warning ? "warning" : "neutral"}>
              <span>{item.label}</span>
              <strong>{item.ready ? "ready" : item.warning ? "check" : "pending"}</strong>
            </StatusPill>
          ))}
        </div>
      </section>
    </section>
  );
}
