export default function ActionButton({
  as: Component = "button",
  children,
  className = "",
  disabled = false,
  icon: Icon,
  loading = false,
  type = "button",
  variant = "secondary",
  ...props
}) {
  const classes = ["action-button", `action-button--${variant}`, className].filter(Boolean).join(" ");

  return (
    <Component
      className={classes}
      disabled={Component === "button" ? disabled || loading : undefined}
      type={Component === "button" ? type : undefined}
      aria-busy={loading || undefined}
      {...props}
    >
      {loading ? <span className="loading-dot" aria-hidden="true" /> : Icon ? <Icon size={16} aria-hidden="true" /> : null}
      <span>{children}</span>
    </Component>
  );
}
