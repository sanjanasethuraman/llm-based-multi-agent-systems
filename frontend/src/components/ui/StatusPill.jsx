const LABELS = {
  error: "Error",
  neutral: "Neutral",
  success: "Success",
  warning: "Warning",
};

export default function StatusPill({ children, className = "", dot = true, status = "neutral" }) {
  return (
    <span
      className={["status-pill", `status-pill--${status}`, className].filter(Boolean).join(" ")}
      aria-label={typeof children === "string" ? undefined : LABELS[status] || status}
    >
      {dot ? <span className="status-pill__dot" aria-hidden="true" /> : null}
      {children}
    </span>
  );
}
