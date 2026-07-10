import { BrainCircuit, Database, Eye, GitBranch, Network, Play, Search, Wrench } from "lucide-react";
import { useState } from "react";
import ActionButton from "./ui/ActionButton.jsx";
import StatusPill from "./ui/StatusPill.jsx";

const journeySteps = [
  "Load demo workflow",
  "Inspect agents/tools",
  "Run workflow",
  "Explore retrieved context",
  "Open graph evidence",
];

const quickStarts = [
  {
    key: "review_pipeline_workflow",
    title: "Job Search Workflow",
    description: "A compact agent/tool pipeline for reviewing and transforming a brief.",
    icon: GitBranch,
    accent: "blue",
  },
  {
    key: "rag_qa_workflow",
    title: "RAG Pipeline",
    description: "Load a retriever workflow and inspect vector context after running.",
    icon: Database,
    accent: "green",
  },
  {
    key: "primekg_migraine_graph_rag_workflow",
    title: "PrimeKG Migraine Graph RAG",
    description: "Show hybrid retrieval with biomedical graph evidence paths.",
    icon: BrainCircuit,
    accent: "violet",
  },
  {
    key: "mcp_tool_workflow",
    title: "MCP Tool Demo",
    description: "Demonstrate tool calls, arguments, and results inside the workflow.",
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
  const exampleNames = new Set(examples.map((example) => example.name));
  const activeStep = workflowLoaded ? 2 : 1;
  const [open, setOpen] = useState(false);

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
            <div key={step} className={index + 1 <= activeStep ? "active" : ""}>
              <span>{index + 1}</span>
              <strong>{step}</strong>
            </div>
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
            const available = exampleNames.has(card.key);
            return (
              <article className={`quick-start-card ${card.accent}`} key={card.key}>
                <div className="quick-start-icon"><Icon size={18} aria-hidden="true" /></div>
                <div>
                  <h3>{card.title}</h3>
                  <p>{card.description}</p>
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
