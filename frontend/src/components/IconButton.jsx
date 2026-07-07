function IconButton({ icon: Icon, label, onClick, variant = "secondary", disabled = false }) {
  return (
    <button className={variant} disabled={disabled} type="button" onClick={onClick} aria-label={label}>
      <Icon size={16} />
      {label}
    </button>
  );
}

export default IconButton;
