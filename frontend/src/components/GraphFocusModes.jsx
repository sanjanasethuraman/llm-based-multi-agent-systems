import { Activity, Beaker, ClipboardList, Crosshair, Dna, Pill, Route } from "lucide-react";

const FOCUS_MODES = [
  {
    id: "overview",
    label: "Overview",
    icon: Activity,
    description: "Shows the full bounded imported subgraph so the audience can see the overall biomedical landscape.",
  },
  {
    id: "disease",
    label: "Disease Neighborhood",
    icon: Crosshair,
    description: "Emphasizes the selected disease node and its direct neighbors without hiding the rest of the graph.",
  },
  {
    id: "treatments",
    label: "Treatments",
    icon: Pill,
    description: "Highlights drug nodes and treatment-like relationships that connect back to the selected disease.",
  },
  {
    id: "mechanisms",
    label: "Mechanisms",
    icon: Dna,
    description: "Highlights genes, proteins, pathways, and biological process nodes that explain possible mechanisms.",
  },
  {
    id: "phenotypes",
    label: "Phenotypes",
    icon: Beaker,
    description: "Highlights phenotype and symptom-like nodes linked to the disease-centered subgraph.",
  },
  {
    id: "evidence",
    label: "Evidence Paths",
    icon: Route,
    description: "Highlights readable Graph RAG evidence paths when retrieval results include graph paths.",
  },
];

const DEMO_STEPS = [
  { mode: "disease", label: "1 Disease" },
  { mode: "mechanisms", label: "2 Mechanisms" },
  { mode: "phenotypes", label: "3 Phenotypes" },
  { mode: "treatments", label: "4 Treatments" },
  { mode: "evidence", label: "5 Evidence" },
];

export default function GraphFocusModes({
  activeMode,
  modeSummary,
  activeFilterCount = 0,
  evidencePathCount = 0,
  onChangeMode,
}) {
  const active = FOCUS_MODES.find((mode) => mode.id === activeMode) || FOCUS_MODES[0];
  return (
    <section className="primekg-focus-panel">
      <div className="primekg-focus-heading">
        <div>
          <span>Story Focus</span>
          <strong>{active.label}</strong>
        </div>
        {activeFilterCount ? <em>{activeFilterCount} manual filters active</em> : <em>soft highlight mode</em>}
      </div>

      <div className="primekg-focus-modes" role="tablist" aria-label="PrimeKG focus presets">
        {FOCUS_MODES.map((mode) => {
          const Icon = mode.icon;
          const disabled = mode.id === "evidence" && evidencePathCount === 0;
          return (
            <button
              key={mode.id}
              type="button"
              className={activeMode === mode.id ? "active" : ""}
              onClick={() => onChangeMode(mode.id)}
              disabled={disabled}
              title={disabled ? "Run graph or hybrid retrieval to populate evidence paths." : mode.description}
            >
              <Icon size={14} />
              {mode.label}
            </button>
          );
        })}
      </div>

      <div className="primekg-focus-story">
        <ClipboardList size={15} />
        <p>{modeSummary?.description || active.description}</p>
        <strong>{modeSummary?.countText || "Full bounded graph remains visible."}</strong>
      </div>

      <div className="primekg-demo-script" aria-label="Demo script">
        <span>Demo script</span>
        {DEMO_STEPS.map((step) => (
          <button
            key={step.mode}
            type="button"
            className={activeMode === step.mode ? "active" : ""}
            onClick={() => onChangeMode(step.mode)}
            disabled={step.mode === "evidence" && evidencePathCount === 0}
          >
            {step.label}
          </button>
        ))}
      </div>
    </section>
  );
}
