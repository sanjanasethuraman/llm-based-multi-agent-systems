import { Copy, X, Plus } from 'lucide-react';
import './WorkflowTabs.css';

export default function WorkflowTabs({
  tabs,
  activeTabId,
  onSelectTab,
  onCreateTab,
  onDuplicateTab,
  onCloseTab,
  onRenameTab,
}) {
  const handleRename = (tabId, currentName) => {
    const newName = prompt('Rename workflow:', currentName);
    if (newName && newName.trim()) {
      onRenameTab(tabId, newName.trim());
    }
  };

  return (
    <div className="workflow-tabs-container">
      <div className="workflow-tabs">
        {tabs.map((tab) => (
          <div
            key={tab.id}
            className={`workflow-tab ${activeTabId === tab.id ? 'active' : ''}`}
            onClick={() => onSelectTab(tab.id)}
          >
            <span
              className="tab-name"
              onDoubleClick={() => handleRename(tab.id, tab.name)}
              title="Double-click to rename"
            >
              {tab.name}
            </span>
            {tab.executionResults && (
              <div
                className={`tab-status ${
                  tab.executionResults.status === 'completed'
                    ? 'success'
                    : tab.executionResults.status === 'failed'
                    ? 'error'
                    : 'running'
                }`}
                title={`Status: ${tab.executionResults.status}`}
              />
            )}
            <div className="tab-actions">
              <button
                className="tab-action-btn"
                onClick={(e) => {
                  e.stopPropagation();
                  onDuplicateTab(tab.id);
                }}
                title="Duplicate workflow"
              >
                <Copy size={14} />
              </button>
              <button
                className="tab-action-btn"
                onClick={(e) => {
                  e.stopPropagation();
                  onCloseTab(tab.id);
                }}
                title="Close workflow"
                disabled={tabs.length === 1}
              >
                <X size={14} />
              </button>
            </div>
          </div>
        ))}
      </div>
      <button className="add-tab-btn" onClick={onCreateTab} title="Create new workflow">
        <Plus size={16} />
      </button>
    </div>
  );
}
