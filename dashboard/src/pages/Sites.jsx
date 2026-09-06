import { useState, useEffect } from "react";
import { getSites, createSite, deleteSite } from "../api";

export default function Sites() {
  const [sites, setSites]   = useState([]);
  const [name, setName]     = useState("");
  const [toast, setToast]   = useState(null);

  const load = () => getSites().then(r => setSites(r.data || [])).catch(() => {});
  useEffect(() => { load(); }, []);

  const showToast = (msg, type) => {
    setToast({ msg, type });
    setTimeout(() => setToast(null), 3000);
  };

  const handleCreate = async (e) => {
    e.preventDefault();
    if (!name.trim()) return;
    try {
      await createSite(name.trim());
      setName("");
      showToast("Site created", "success");
      load();
    } catch (err) {
      showToast(err.response?.data?.detail || err.message, "error");
    }
  };

  const handleDelete = async (id, siteName) => {
    try {
      await deleteSite(id);
      showToast(`${siteName} deleted`, "success");
      load();
    } catch (err) {
      showToast(err.response?.data?.detail || err.message, "error");
    }
  };

  return (
    <div style={{ fontFamily: "'Cabinet Grotesk', sans-serif", color: "#e8f0fe" }}>
      <div style={{
        fontSize: "22px", fontWeight: 800, fontFamily: "'Syne', sans-serif",
        marginBottom: "6px",
      }}>Sites</div>
      <div style={{
        fontSize: "13px", color: "rgba(122,143,166,0.7)", marginBottom: "24px",
      }}>Group machines by client site or physical location.</div>

      <form onSubmit={handleCreate} style={{ display: "flex", gap: "10px", marginBottom: "24px" }}>
        <input
          value={name}
          onChange={e => setName(e.target.value)}
          placeholder="New site name"
          style={{
            flex: 1, maxWidth: "320px", padding: "10px 14px",
            background: "#0c1220", border: "1px solid rgba(255,255,255,0.08)",
            borderRadius: "8px", color: "#e8f0fe", fontSize: "13px",
            fontFamily: "'Cabinet Grotesk', sans-serif",
          }}
        />
        <button
          type="submit"
          style={{
            padding: "10px 18px", background: "rgba(56,189,248,0.12)",
            border: "1px solid rgba(56,189,248,0.3)", borderRadius: "8px",
            color: "#38bdf8", fontSize: "13px", fontWeight: 600, cursor: "pointer",
            fontFamily: "'Cabinet Grotesk', sans-serif",
          }}
        >+ Create Site</button>
      </form>

      {toast && (
        <div style={{
          padding: "10px 14px", marginBottom: "18px", borderRadius: "8px",
          background: toast.type === "error" ? "rgba(244,63,94,0.1)" : "rgba(16,185,129,0.1)",
          border: `1px solid ${toast.type === "error" ? "rgba(244,63,94,0.3)" : "rgba(16,185,129,0.3)"}`,
          color: toast.type === "error" ? "#f43f5e" : "#10b981",
          fontSize: "12px",
        }}>{toast.msg}</div>
      )}

      <div style={{ display: "flex", flexDirection: "column", gap: "8px" }}>
        {sites.length === 0 && (
          <div style={{ fontSize: "13px", color: "rgba(122,143,166,0.5)" }}>No sites yet.</div>
        )}
        {sites.map(s => (
          <div key={s.id} style={{
            display: "flex", alignItems: "center", justifyContent: "space-between",
            padding: "12px 16px", background: "#0c1220",
            border: "1px solid rgba(255,255,255,0.06)", borderRadius: "10px",
          }}>
            <div>
              <span style={{ fontWeight: 600, fontSize: "14px" }}>{s.name}</span>
              <span style={{
                marginLeft: "12px", fontSize: "11px", color: "rgba(122,143,166,0.6)",
                fontFamily: "'JetBrains Mono', monospace",
              }}>{s.machine_count} machine{s.machine_count !== 1 ? "s" : ""}</span>
            </div>
            <button
              onClick={() => handleDelete(s.id, s.name)}
              style={{
                padding: "6px 14px", background: "rgba(244,63,94,0.1)",
                border: "1px solid rgba(244,63,94,0.3)", borderRadius: "6px",
                color: "#f43f5e", fontSize: "12px", fontWeight: 600, cursor: "pointer",
                fontFamily: "'Cabinet Grotesk', sans-serif",
              }}
            >Delete</button>
          </div>
        ))}
      </div>
    </div>
  );
}
