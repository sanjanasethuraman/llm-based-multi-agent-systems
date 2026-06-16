import {useState} from "react"
import IconButton from "../IconButton.jsx"
import {
  CheckCircle2,
  Plus,
  RefreshCcw,
  Trash2,
  XCircle,
} from "lucide-react";

function McpServersPanel({ servers, onConnect, onDisconnect, onRefresh }) {
  const [form, setForm] = useState({
    id: "", label: "", transport: "http", url: "", command: "", args: "", headers: "",
  });
  const [showForm, setShowForm] = useState(false);

  const updateField = (field, value) => setForm(current => ({ ...current, [field]: value }));

  function handleConnect() {
    if (!form.id || !form.label) return;
    const config = {
      id: form.id,
      label: form.label,
      transport: form.transport,
      ...(form.transport === "http"
        ? {
            url: form.url,
            headers: form.headers
              ? Object.fromEntries(form.headers.split(",").map(h => h.split("=").map(s => s.trim())))
              : {},
          }
        : {
            command: form.command.split(" ")[0],
            args: form.command.split(" ").slice(1).concat(form.args ? form.args.split(" ") : []),
          }),
    };
    onConnect(config);
    setShowForm(false);
    setForm({ id: "", label: "", transport: "http", url: "", command: "", args: "", headers: "" });
  }

  return (
    <section className="mcp-servers-panel">
      <div className="section-header">
        <div>
          <h2>MCP Servers</h2>
          <p>Connect internal and external tool servers.</p>
        </div>
        <div style={{ display: "flex", gap: 8 }}>
          <IconButton icon={RefreshCcw} label="Refresh" onClick={onRefresh} />
          <IconButton icon={Plus} label="Add Server" onClick={() => setShowForm(s => !s)} />
        </div>
      </div>

      {/* Server list */}
      <div className="mcp-server-list">
        {servers.length === 0 && <p>No servers connected.</p>}
        {servers.map(server => (
          <div key={server.id} className={`mcp-server-item ${server.connected ? "connected" : "offline"}`}>
            <div>
              <strong>{server.label}</strong>
              <span className={`status-badge ${server.connected ? "completed" : "error"}`}>
                {server.connected ? "Connected" : "Offline"}
              </span>
              <span style={{ opacity: 0.6, fontSize: 12 }}>{server.transport} · {server.id}</span>
            </div>
            {server.id !== "internal" && (
              <button type="button" onClick={() => onDisconnect(server.id)}>
                <Trash2 size={14} /> Disconnect
              </button>
            )}
          </div>
        ))}
      </div>

      {/* Add server form */}
      {showForm && (
        <div className="mcp-add-form">
          <h3>Add External Server</h3>
          <div className="form-grid">
            <label>
              ID (unique key)
              <input placeholder="acme-weather" value={form.id} onChange={e => updateField("id", e.target.value)} />
            </label>
            <label>
              Display Label
              <input placeholder="Acme Weather API" value={form.label} onChange={e => updateField("label", e.target.value)} />
            </label>
            <div className="field-group">
              <span>Transport</span>
              <div className="segmented">
                {["http", "stdio"].map(t => (
                  <button
                    key={t} type="button"
                    className={form.transport === t ? "active" : ""}
                    onClick={() => updateField("transport", t)}
                  >
                    {t}
                  </button>
                ))}
              </div>
            </div>

            {form.transport === "http" ? (
              <>
                <label>
                  Server URL
                  <input placeholder="https://api.acme.com/mcp" value={form.url} onChange={e => updateField("url", e.target.value)} />
                </label>
                <label>
                  Auth Headers <span style={{ opacity: 0.6 }}>(KEY=value, comma-separated)</span>
                  <input placeholder="Authorization=Bearer token123" value={form.headers} onChange={e => updateField("headers", e.target.value)} />
                </label>
              </>
            ) : (
              <label>
                Command
                <input placeholder="npx @acme/mcp-server" value={form.command} onChange={e => updateField("command", e.target.value)} />
              </label>
            )}

            <div className="inline-actions">
              <IconButton icon={CheckCircle2} label="Connect" variant="primary" onClick={handleConnect} />
              <IconButton icon={XCircle} label="Cancel" onClick={() => setShowForm(false)} />
            </div>
          </div>
        </div>
      )}
    </section>
  );
}
export default McpServersPanel;