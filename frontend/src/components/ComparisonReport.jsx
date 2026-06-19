import { ChevronDown, ChevronUp, Copy, Download } from 'lucide-react';
import { useState } from 'react';
import './ComparisonReport.css';

export default function ComparisonReport({ reports = [] }) {
  const [expandedMetrics, setExpandedMetrics] = useState({});

  if (!reports || reports.length === 0) {
    return (
      <div className="comparison-report">
        <p className="no-data">Run workflows to generate comparison data</p>
      </div>
    );
  }

  const toggleMetric = (metricKey) => {
    setExpandedMetrics((prev) => ({
      ...prev,
      [metricKey]: !prev[metricKey],
    }));
  };

  const downloadJSON = () => {
    const json = JSON.stringify(reports, null, 2);
    const blob = new Blob([json], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `workflow-comparison-${Date.now()}.json`;
    a.click();
    URL.revokeObjectURL(url);
  };

  const copyToClipboard = () => {
    const json = JSON.stringify(reports, null, 2);
    navigator.clipboard.writeText(json);
  };

  return (
    <div className="comparison-report">
      <div className="report-header">
        <h3>Workflow Comparison Report</h3>
        <div className="report-actions">
          <button onClick={copyToClipboard} title="Copy to clipboard">
            <Copy size={14} />
          </button>
          <button onClick={downloadJSON} title="Download as JSON">
            <Download size={14} />
          </button>
        </div>
      </div>

      <div className="comparison-grid">
        {/* Summary */}
        <div className="comparison-section">
          <h4>Summary</h4>
          <table className="comparison-table">
            <thead>
              <tr>
                <th>Workflow</th>
                <th>Status</th>
                <th>Duration</th>
                <th>Timestamp</th>
              </tr>
            </thead>
            <tbody>
              {reports.map((report, idx) => (
                <tr key={idx}>
                  <td className="workflow-name">{report.workflowName}</td>
                  <td>
                    <span className={`status-badge ${report.status}`}>
                      {report.status.toUpperCase()}
                    </span>
                  </td>
                  <td>{formatDuration(report.durationMs)}</td>
                  <td className="timestamp">
                    {new Date(report.timestamp).toLocaleString()}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        {/* Execution Time Comparison */}
        <div className="comparison-section">
          <div
            className="section-header"
            onClick={() => toggleMetric('executionTime')}
          >
            <h4>Execution Time</h4>
            {expandedMetrics['executionTime'] ? <ChevronUp size={16} /> : <ChevronDown size={16} />}
          </div>
          {expandedMetrics['executionTime'] && (
            <div className="metric-content">
              <table className="comparison-table">
                <thead>
                  <tr>
                    <th>Workflow</th>
                    <th>Duration (ms)</th>
                    <th>Relative</th>
                  </tr>
                </thead>
                <tbody>
                  {(() => {
                    const times = reports.map((r) => r.durationMs || 0);
                    const minTime = Math.min(...times);
                    const maxTime = Math.max(...times);
                    return reports.map((report, idx) => (
                      <tr key={idx}>
                        <td>{report.workflowName}</td>
                        <td>{report.durationMs || 'N/A'}ms</td>
                        <td>
                          <div className="progress-bar">
                            <div
                              className="progress-fill"
                              style={{
                                width: `${
                                  ((report.durationMs || 0) / (maxTime || 1)) * 100
                                }%`,
                              }}
                            />
                          </div>
                        </td>
                      </tr>
                    ));
                  })()}
                </tbody>
              </table>
            </div>
          )}
        </div>

        {/* Output Comparison */}
        <div className="comparison-section">
          <div
            className="section-header"
            onClick={() => toggleMetric('output')}
          >
            <h4>Output</h4>
            {expandedMetrics['output'] ? <ChevronUp size={16} /> : <ChevronDown size={16} />}
          </div>
          {expandedMetrics['output'] && (
            <div className="metric-content">
              <table className="comparison-table output-table">
                <tbody>
                  {reports.map((report, idx) => (
                    <tr key={idx}>
                      <td className="workflow-col">{report.workflowName}:</td>
                      <td>
                        <div className="output-cell">
                          {report.output ? (
                            <pre>{truncate(report.output, 200)}</pre>
                          ) : (
                            <em>No output</em>
                          )}
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>

        {/* Performance Metrics */}
        <div className="comparison-section">
          <div
            className="section-header"
            onClick={() => toggleMetric('performance')}
          >
            <h4>Performance Metrics</h4>
            {expandedMetrics['performance'] ? <ChevronUp size={16} /> : <ChevronDown size={16} />}
          </div>
          {expandedMetrics['performance'] && (
            <div className="metric-content">
              <table className="comparison-table">
                <thead>
                  <tr>
                    <th>Workflow</th>
                    <th>Nodes Executed</th>
                    <th>Log Entries</th>
                    <th>Retrievals</th>
                  </tr>
                </thead>
                <tbody>
                  {reports.map((report, idx) => (
                    <tr key={idx}>
                      <td>{report.workflowName}</td>
                      <td>{report.stats?.executedNodes || 0}</td>
                      <td>{(report.logs || []).length}</td>
                      <td>{(report.retrievals || []).length}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>

        {/* Logs & Events */}
        <div className="comparison-section">
          <div
            className="section-header"
            onClick={() => toggleMetric('logs')}
          >
            <h4>Logs & Events</h4>
            {expandedMetrics['logs'] ? <ChevronUp size={16} /> : <ChevronDown size={16} />}
          </div>
          {expandedMetrics['logs'] && (
            <div className="metric-content">
              {reports.map((report, idx) => (
                <div key={idx} className="log-section">
                  <h5>{report.workflowName}</h5>
                  <div className="log-list">
                    {(report.logs || []).length > 0 ? (
                      (report.logs || []).slice(0, 5).map((log, logIdx) => (
                        <div key={logIdx} className="log-entry">
                          <span className={`log-level ${log.level || 'info'}`}>
                            {(log.level || 'INFO').toUpperCase()}
                          </span>
                          <span className="log-text">{truncate(log.message || '', 100)}</span>
                        </div>
                      ))
                    ) : (
                      <em>No logs</em>
                    )}
                    {(report.logs || []).length > 5 && (
                      <div className="log-more">
                        +{(report.logs || []).length - 5} more logs
                      </div>
                    )}
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Success/Failure States */}
        <div className="comparison-section">
          <div
            className="section-header"
            onClick={() => toggleMetric('status')}
          >
            <h4>Execution Status</h4>
            {expandedMetrics['status'] ? <ChevronUp size={16} /> : <ChevronDown size={16} />}
          </div>
          {expandedMetrics['status'] && (
            <div className="metric-content">
              <table className="comparison-table">
                <thead>
                  <tr>
                    <th>Workflow</th>
                    <th>Status</th>
                    <th>Message</th>
                  </tr>
                </thead>
                <tbody>
                  {reports.map((report, idx) => (
                    <tr key={idx}>
                      <td>{report.workflowName}</td>
                      <td>
                        <span className={`status-badge ${report.status}`}>
                          {report.status.toUpperCase()}
                        </span>
                      </td>
                      <td className="status-message">
                        {report.statusMessage || '-'}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

function formatDuration(ms) {
  if (!ms) return '-';
  if (ms < 1000) return `${ms}ms`;
  return `${(ms / 1000).toFixed(2)}s`;
}

function truncate(text, length) {
  if (!text) return '';
  return text.length > length ? text.substring(0, length) + '...' : text;
}
