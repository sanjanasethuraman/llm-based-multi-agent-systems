function StatusBadge({ status }) {
  const labels = {
    idle: "Idle",
    running: "Running",
    completed: "Done",
    warning: "Warn",
    error: "Error",
  };
  return <span className={`status-badge ${status}`}>{labels[status] || status}</span>;
}

export default StatusBadge;