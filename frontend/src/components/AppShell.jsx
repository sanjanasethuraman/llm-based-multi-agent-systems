export default function AppShell({ children, presentationMode = false, theme = "dark" }) {
  return (
    <div className={`app-shell theme-${theme} ${presentationMode ? "presentation-mode" : ""}`} data-theme={theme}>
      <div className="app-shell__container">{children}</div>
    </div>
  );
}
