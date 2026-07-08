import { Database, FolderOpen, Gauge, GitBranch, Maximize2, Minimize2, Moon, Network, Play, Sparkles, Sun, Wrench } from "lucide-react";

import ActionButton from "./ui/ActionButton.jsx";

const chips = [
  { icon: GitBranch, label: "Agent Workflows" },
  { icon: Database, label: "Vector RAG" },
  { icon: Network, label: "PrimeKG Graph RAG" },
  { icon: Wrench, label: "MCP Tools" },
];

export default function HeroHeader({
  examples = [],
  onCheckStatus,
  onExportPython,
  onGeneratePython,
  onLoadDemo,
  onLoadSaved,
  onOpenKnowledgeGraph,
  onTogglePresentationMode,
  onToggleTheme,
  onRunWorkflow,
  onSaveWorkflow,
  onSelectExample,
  presentationMode = false,
  selectedExample,
  statusMessage,
  theme = "dark",
}) {
  const PresentationIcon = presentationMode ? Minimize2 : Maximize2;
  const ThemeIcon = theme === "dark" ? Sun : Moon;

  return (
    <header className="hero-header">
      <nav className="product-nav" aria-label="Product navigation">
        <div className="product-brand">
          <div className="product-brand__mark" aria-hidden="true">
            <Sparkles size={18} />
          </div>
          <div>
            <strong>FlowScope</strong>
            <span>Visual MAS Tool</span>
          </div>
        </div>
        <div className="product-nav__actions">
          <select
            className="hero-example-select"
            aria-label="Example workflow"
            value={selectedExample}
            onChange={(event) => onSelectExample(event.target.value)}
          >
            {examples.map((example) => (
              <option key={example.name} value={example.name}>
                {example.label}
              </option>
            ))}
          </select>
          <ActionButton icon={Gauge} variant="ghost" onClick={onCheckStatus}>
            Check System Status
          </ActionButton>
          <button
            type="button"
            className="theme-toggle"
            onClick={onToggleTheme}
            aria-label={`Switch to ${theme === "dark" ? "light" : "dark"} theme`}
            title={`Switch to ${theme === "dark" ? "light" : "dark"} theme`}
          >
            <span className="theme-toggle__track" aria-hidden="true">
              <span className="theme-toggle__thumb">
                <ThemeIcon size={13} />
              </span>
            </span>
            <span>{theme === "dark" ? "Light" : "Dark"}</span>
          </button>
          <ActionButton
            icon={PresentationIcon}
            variant={presentationMode ? "success" : "secondary"}
            onClick={onTogglePresentationMode}
          >
            {presentationMode ? "Exit Presentation" : "Presentation Mode"}
          </ActionButton>
          <ActionButton icon={Play} variant="primary" onClick={onRunWorkflow}>
            Run Workflow
          </ActionButton>
        </div>
      </nav>

      <section className="hero-dashboard" aria-label="Product overview">
        <div className="hero-dashboard__content">
          <span className="hero-kicker">AI workflow builder</span>
          <h1>FlowScope</h1>
          <p>Visual AI workflows with agents, tools, RAG, and biomedical knowledge graphs.</p>
          <div className="hero-chip-row" aria-label="Core capabilities">
            {chips.map((chip) => {
              const Icon = chip.icon;
              return (
                <span className="hero-chip" key={chip.label}>
                  <Icon size={14} aria-hidden="true" />
                  {chip.label}
                </span>
              );
            })}
          </div>
        </div>

        <div className="hero-dashboard__actions" aria-label="Demo actions">
          <ActionButton icon={FolderOpen} variant="secondary" onClick={onLoadDemo}>
            Load Demo Workflow
          </ActionButton>
          <ActionButton icon={Play} variant="primary" onClick={onRunWorkflow}>
            Run Workflow
          </ActionButton>
          <ActionButton icon={Network} variant="secondary" onClick={onOpenKnowledgeGraph}>
            Open Knowledge Graph
          </ActionButton>
          <div className="hero-secondary-actions" aria-label="Workflow file actions">
            <ActionButton variant="ghost" onClick={onSaveWorkflow}>
              Save
            </ActionButton>
            <ActionButton variant="ghost" onClick={onLoadSaved}>
              Load Saved
            </ActionButton>
            <ActionButton variant="ghost" onClick={onGeneratePython}>
              Generate Python
            </ActionButton>
            <ActionButton variant="ghost" onClick={onExportPython}>
              Export .py
            </ActionButton>
          </div>
          <div className="hero-status-line" title={statusMessage}>
            <span>Status</span>
            <strong>{statusMessage || "Ready"}</strong>
          </div>
        </div>
      </section>
    </header>
  );
}
