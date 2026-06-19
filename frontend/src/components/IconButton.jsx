function IconButton({ icon: Icon, label, onClick, variant = "secondary" }) {
  return (
    <button className={variant} type="button" onClick={onClick}>
      <Icon size={16} />
      {label}
    </button>
  );
}

export default IconButton;