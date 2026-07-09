function IconButton({ icon: Icon, label, onClick, variant = "secondary", disabled = false, loading = false }) {
  return (
    <button
      className={`action-button action-button--${variant} icon-button`}
      disabled={disabled || loading}
      type="button"
      onClick={onClick}
      aria-label={label}
      aria-busy={loading}
    >
      {loading ? <span className="loading-dot" aria-hidden="true" /> : Icon ? <Icon size={16} /> : null}
      {label}
    </button>
  );
}

export default IconButton;
