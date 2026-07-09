import { Background, Controls, MiniMap, ReactFlow } from "@xyflow/react";
import { CheckCircle2, CircleAlert, Plus, Play, Trash2 } from "lucide-react";

import ActionButton from "./ui/ActionButton.jsx";
import StatusPill from "./ui/StatusPill.jsx";

export default function WorkflowWorkspace({
  canvasCallbacks,
  edges,
  inspector,
  nodeTypes,
  nodeTypesCatalog,
  nodes,
  onAddNode,
  onDeleteSelection,
  onRunWorkflow,
  presentationMode = false,
  selectedEdge,
  selectedLabel,
  selectedNode,
  validation,
}) {
  const hasSelection = Boolean(selectedNode || selectedEdge);
  const validationErrors = validation?.errors?.length || 0;
  const validationWarnings = validation?.warnings?.length || 0;
  const validationStatus = validationErrors ? "error" : validationWarnings ? "warning" : "success";
  const validationText = validationErrors
    ? `${validationErrors} issue${validationErrors === 1 ? "" : "s"}`
    : validationWarnings
      ? `${validationWarnings} warning${validationWarnings === 1 ? "" : "s"}`
      : "valid";

  return (
    <main className={`workspace ${presentationMode ? "workspace--presentation" : ""}`}>
      <aside className="palette workflow-panel">
        <div className="workspace-panel-heading">
          <span>Build</span>
          <strong>Components</strong>
        </div>
        <div className="palette-actions">
          {Object.entries(nodeTypesCatalog).map(([type, label]) => (
            <button key={type} type="button" onClick={() => onAddNode(type)}>
              <Plus size={15} aria-hidden="true" />
              {label}
            </button>
          ))}
        </div>
        <p className="hint">Add nodes, connect side ports, then run the workflow from the canvas toolbar.</p>
      </aside>

      <section className="canvas-panel workflow-panel">
        <div className="canvas-header">
          <div className="canvas-title-group">
            <span>Workflow Canvas</span>
            <strong>Visual execution graph</strong>
          </div>
          <div className="canvas-tools">
            <StatusPill status={validationStatus}>
              {validationStatus === "success" ? <CheckCircle2 size={14} aria-hidden="true" /> : <CircleAlert size={14} aria-hidden="true" />}
              <span>{validationText}</span>
            </StatusPill>
            <span className="selection-chip">{selectedLabel}</span>
            <ActionButton icon={Play} variant="primary" onClick={onRunWorkflow}>
              Run
            </ActionButton>
            <ActionButton icon={Trash2} variant="danger" disabled={!hasSelection} onClick={onDeleteSelection}>
              Delete
            </ActionButton>
          </div>
        </div>
        <div className="canvas">
          {!nodes.length ? (
            <div className="canvas-empty-state">
              <strong>No workflow nodes yet</strong>
              <span>Add a component from the left panel or load a demo workflow.</span>
            </div>
          ) : null}
          <ReactFlow
            fitView
            deleteKeyCode={["Backspace", "Delete"]}
            edges={edges}
            nodes={nodes}
            nodeTypes={nodeTypes}
            {...canvasCallbacks}
          >
            <Background gap={22} size={1} />
            <MiniMap pannable zoomable nodeStrokeWidth={3} />
            <Controls />
          </ReactFlow>
        </div>
      </section>

      {inspector}
    </main>
  );
}
