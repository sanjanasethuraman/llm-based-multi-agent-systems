import { Play, Copy, Clock, Zap } from 'lucide-react';
import './ExecutionModeControl.css';

export default function ExecutionModeControl({
  mode = 'independent',
  tabs,
  activeTabId,
  onModeChange,
  onRunSequential,
  onRunParallel,
  isRunning = false,
}) {
  const multipleTabsExist = tabs.length > 1;

  const handleModeChange = (newMode) => {
    if (newMode !== mode) {
      onModeChange(newMode);
    }
  };

  const modeDescriptions = {
    independent: 'Run current workflow only',
    sequential: 'Run all workflows one after another',
    parallel: 'Run all workflows simultaneously',
  };

  return (
    <div className="execution-mode-control">
      <div className="mode-selector">
        <label>Execution Mode:</label>
        <div className="mode-buttons">
          <button
            className={`mode-btn ${mode === 'independent' ? 'active' : ''}`}
            onClick={() => handleModeChange('independent')}
            title={modeDescriptions.independent}
            disabled={!multipleTabsExist}
          >
            <Play size={14} />
            <span>Independent</span>
          </button>
          <button
            className={`mode-btn ${mode === 'sequential' ? 'active' : ''}`}
            onClick={() => handleModeChange('sequential')}
            title={modeDescriptions.sequential}
            disabled={!multipleTabsExist}
          >
            <Clock size={14} />
            <span>Sequential</span>
          </button>
          <button
            className={`mode-btn ${mode === 'parallel' ? 'active' : ''}`}
            onClick={() => handleModeChange('parallel')}
            title={modeDescriptions.parallel}
            disabled={!multipleTabsExist}
          >
            <Zap size={14} />
            <span>Parallel</span>
          </button>
        </div>
      </div>

      {multipleTabsExist && mode !== 'independent' && (
        <div className="multi-run-buttons">
          <button
            className="run-all-btn sequential"
            onClick={onRunSequential}
            disabled={isRunning}
            title="Run all workflows sequentially"
          >
            <Clock size={14} />
            Run All Sequential ({tabs.length} workflows)
          </button>
          <button
            className="run-all-btn parallel"
            onClick={onRunParallel}
            disabled={isRunning}
            title="Run all workflows in parallel"
          >
            <Zap size={14} />
            Run All Parallel ({tabs.length} workflows)
          </button>
        </div>
      )}

      {!multipleTabsExist && (
        <div className="mode-hint">Create multiple workflows to enable multi-run modes</div>
      )}
    </div>
  );
}
