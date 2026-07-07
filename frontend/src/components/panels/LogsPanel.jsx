import React, { useState, useMemo } from "react";
import StatusBadge from "../StatusBadge.jsx";


function LogsPanel({ logs, logCounts }) {
  const [selectedLogFilter, setSelectedLogFilter] = useState("all");
  const [searchTerm, setSearchTerm] = useState("");

  const filteredLogs = useMemo(() => {
    return Object.values(logs || {})
      .flat()
      .filter((log) => {
        if (
          selectedLogFilter !== "all" &&
          (log.status || "completed") !== selectedLogFilter
        ) {
          return false;
        }

        if (!searchTerm.trim()) {
          return true;
        }

        const needle = searchTerm.toLowerCase();
        return `${log.nodeId} ${log.message} ${log.type || ""}`
          .toLowerCase()
          .includes(needle);
      });
  }, [logs, selectedLogFilter, searchTerm]);

  return (
    <section className="logs-panel">
      <div className="section-header">
        <div>
          <h2>Logs</h2>
          <p>Filter and search execution logs for better insight.</p>
        </div>
      </div>
      <div className="log-toolbar">
        <div className="log-filters">
          {[
            { key: "all", label: `All (${logCounts.all})` },
            { key: "completed", label: `Done (${logCounts.completed})` },
            { key: "info", label: `Info (${logCounts.info})` },
            { key: "warning", label: `Warn (${logCounts.warning})` },
            { key: "error", label: `Error (${logCounts.error})` },
          ].map((filter) => (
            <button
              key={filter.key}
              type="button"
              className={`filter-button ${selectedLogFilter === filter.key ? "active" : ""}`}
              onClick={() => setSelectedLogFilter(filter.key)}
            >
              {filter.label}
            </button>
          ))}
        </div>
        <input
          className="log-search"
          placeholder="Search logs"
          value={searchTerm}
          onChange={(event) => setSearchTerm(event.target.value)}
        />
      </div>
      <div className="log-summary-grid">
        <div className="log-stat-card">
          <strong>{filteredLogs.length}</strong>
          <span>Shown</span>
        </div>
        <div className="log-stat-card">
          <strong>{logCounts.error}</strong>
          <span>Total errors</span>
        </div>
        <div className="log-stat-card">
          <strong>{logCounts.warning}</strong>
          <span>Total warnings</span>
        </div>
      </div>
      <div className="log-list">
        {filteredLogs.length ? (
          filteredLogs.map((item, index) => (
            <article key={`${item.nodeId}-${index}`} className={`log-entry ${item.status || "completed"}`}>
              <div className="log-entry-header">
                <StatusBadge status={item.status || "completed"} />
                <span className="log-entry-meta">{item.nodeId}</span>
              </div>
              <p>{item.message}</p>
            </article>
          ))
        ) : (
          <p className="log-empty">No logs match the current filter.</p>
        )}
      </div>
    </section>
  );
}

export default LogsPanel;