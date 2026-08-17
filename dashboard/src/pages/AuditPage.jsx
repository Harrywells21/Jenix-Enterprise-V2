import { useState, useEffect } from "react";
import { getAuditLogs, verifyLog, getToken } from "../api";

const MONO = "'JetBrains Mono', monospace";
const FONT = "'Cabinet Grotesk', sans-serif";
const DISP = "'Syne', sans-serif";

function ActionBadge({ action }) {
  const colors = {
    login:         { bg: "rgba(16,185,129,0.08)",  border: "rgba(16,185,129,0.2)",  text: "#10b981" },
    logout:        { bg: "rgba(122,143,166,0.06)", border: "rgba(122,143,166,0.15)", text: "#7a8fa6" },
    command:       { bg: "rgba(56,189,248,0.08)",  border: "rgba(56,189,248,0.2)",  text: "#38bdf8" },
    scan:          { bg: "rgba(139,92,246,0.08)",  border: "rgba(139,92,246,0.2)",  text: "#8b5cf6" },
    fleet_command: { bg: "rgba(245,158,11,0.08)",  border: "rgba(245,158,11,0.2)",  text: "#f59e0b" },
    alert:         { bg: "rgba(244,63,94,0.08)",   border: "rgba(244,63,94,0.2)",   text: "#f43f5e" },
  };
  const key = Object.keys(colors).find(k => action?.toLowerCase().includes(k)) || "command";
  const c = colors[key];
  return (
    <span style={{
      padding: "2px 8px", borderRadius: "5px",
      background: c.bg, border: `1px solid ${c.border}`,
      color: c.text, fontSize: "10px", fontWeight: 600,
      fontFamily: MONO, letterSpacing: "0.06em",
      textTransform: "uppercase",
    }}>{action}</span>
  );
}

export default function AuditPage() {
  const [logs,     setLogs]     = useState([]);
  const [search,   setSearch]   = useState("");
  const [verified, setVerified] = useState({});
  const [toast,    setToast]    = useState(null);
  const [filter,   setFilter]   = useState("all");
  const [loading,  setLoading]  = useState(true);
  const [view,     setView]     = useState("timeline");

  useEffect(() => {
    getAuditLogs()
      .then(r => { setLogs(r.data || []); setLoading(false); })
      .catch(() => setLoading(false));
  }, []);

  const showToast = (msg, type = "success") => {
    setToast({ msg, type });
    setTimeout(() => setToast(null), 3500);
  };

  const handleVerify = async (id) => {
    try {
      const r = await verifyLog(id);
      setVerified(p => ({ ...p, [id]: { valid: true, data: r.data } }));
      showToast(`Log #${id} verified — integrity confirmed`, "success");
    } catch {
      setVerified(p => ({ ...p, [id]: { valid: false } }));
      showToast(`Verification failed for log #${id}`, "error");
    }
  };

  const handleExportCSV = () => {
    const token = getToken();
    const a = document.createElement("a");
    a.href = `http://localhost:8000/api/audit/export?token=${token}`;
    a.download = `jenix_audit_${new Date().toISOString().slice(0, 10)}.csv`;
    document.body.appendChild(a); a.click(); document.body.removeChild(a);
  };

  const filtered = logs.filter(l => {
    const s = search.toLowerCase();
    const matchSearch = !s ||
      l.action?.toLowerCase().includes(s) ||
      l.detail?.toLowerCase().includes(s) ||
      l.hostname?.toLowerCase().includes(s) ||
      l.username?.toLowerCase().includes(s);
    const matchFilter = filter === "all" ? true :
      filter === "critical" ? l.status === "critical" :
      filter === "warning"  ? l.status === "warning"  : true;
    return matchSearch && matchFilter;
  });

  // Group by date for timeline view
  const grouped = filtered.reduce((acc, log) => {
    const date = log.timestamp?.slice(0, 10) || "Unknown";
    if (!acc[date]) acc[date] = [];
    acc[date].push(log);
    return acc;
  }, {});

  const stats = {
    total:    logs.length,
    today:    logs.filter(l => l.timestamp?.startsWith(new Date().toISOString().slice(0, 10))).length,
    verified: Object.values(verified).filter(v => v.valid).length,
    critical: logs.filter(l => l.status === "critical").length,
  };

  return (
    <div style={{ fontFamily: FONT, color: "#e8f0fe" }}>
      {toast && (
        <div style={{
          position: "fixed", top: "24px", right: "24px", zIndex: 9999,
          padding: "12px 18px",
          background: toast.type === "error" ? "rgba(244,63,94,0.12)" : "rgba(16,185,129,0.12)",
          border: `1px solid ${toast.type === "error" ? "rgba(244,63,94,0.3)" : "rgba(16,185,129,0.3)"}`,
          borderRadius: "10px", color: toast.type === "error" ? "#f43f5e" : "#10b981",
          fontSize: "12px", fontFamily: MONO,
        }}>{toast.type === "error" ? "✗" : "✓"} {toast.msg}</div>
      )}

      {/* Header */}
      <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", marginBottom: "24px" }}>
        <div>
          <div style={{ fontSize: "10px", color: "rgba(56,189,248,0.6)", fontFamily: MONO, letterSpacing: "0.2em", textTransform: "uppercase", marginBottom: "6px" }}>Security</div>
          <h1 style={{ fontFamily: DISP, fontSize: "26px", fontWeight: 800, letterSpacing: "-0.02em" }}>Audit Log</h1>
          <p style={{ color: "rgba(122,143,166,0.6)", fontSize: "13px", marginTop: "5px" }}>
            Tamper-evident SHA-256 verified records
          </p>
        </div>
        <button onClick={handleExportCSV} style={{
          padding: "9px 18px",
          background: "rgba(56,189,248,0.08)",
          border: "1px solid rgba(56,189,248,0.2)",
          borderRadius: "8px", color: "#38bdf8",
          fontSize: "12px", fontWeight: 600,
          cursor: "pointer", fontFamily: FONT,
          display: "flex", alignItems: "center", gap: "6px",
          transition: "all 0.2s",
        }}
          onMouseOver={e => e.currentTarget.style.background = "rgba(56,189,248,0.14)"}
          onMouseOut={e => e.currentTarget.style.background = "rgba(56,189,248,0.08)"}
        >⬇ Export CSV</button>
      </div>

      {/* Stats row */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: "12px", marginBottom: "20px" }}>
        {[
          { label: "Total Entries", value: stats.total,    accent: "#38bdf8" },
          { label: "Today",         value: stats.today,    accent: "#10b981" },
          { label: "Verified",      value: stats.verified, accent: "#8b5cf6" },
          { label: "Critical",      value: stats.critical, accent: stats.critical > 0 ? "#f43f5e" : "#10b981" },
        ].map(({ label, value, accent }) => (
          <div key={label} style={{
            background: "#0c1220", border: "1px solid rgba(255,255,255,0.06)",
            borderRadius: "12px", padding: "16px",
          }}>
            <div style={{ fontSize: "9px", color: "rgba(122,143,166,0.5)", fontFamily: MONO, letterSpacing: "0.18em", textTransform: "uppercase", marginBottom: "6px" }}>{label}</div>
            <div style={{ fontFamily: DISP, fontSize: "30px", fontWeight: 800, color: accent, lineHeight: 1 }}>{value}</div>
          </div>
        ))}
      </div>

      {/* SHA-256 info banner */}
      <div style={{
        display: "flex", alignItems: "center", gap: "12px",
        padding: "12px 16px", marginBottom: "20px",
        background: "rgba(56,189,248,0.04)",
        border: "1px solid rgba(56,189,248,0.1)",
        borderRadius: "10px",
      }}>
        <span style={{ fontSize: "16px" }}>🔐</span>
        <span style={{ fontSize: "12px", color: "rgba(122,143,166,0.7)", fontFamily: MONO }}>
          Each entry is SHA-256 hashed at creation. Click Verify on any entry to confirm it has not been tampered with. Export as CSV for compliance auditors.
        </span>
      </div>

      {/* Controls */}
      <div style={{ display: "flex", gap: "8px", marginBottom: "16px", flexWrap: "wrap", alignItems: "center" }}>
        <div style={{ position: "relative", flex: 1, maxWidth: "340px" }}>
          <span style={{ position: "absolute", left: "12px", top: "50%", transform: "translateY(-50%)", color: "rgba(122,143,166,0.4)", fontSize: "13px", pointerEvents: "none" }}>⌕</span>
          <input
            placeholder="Search action, detail, user..."
            value={search} onChange={e => setSearch(e.target.value)}
            style={{
              width: "100%", padding: "9px 14px 9px 32px",
              background: "#0c1220", border: "1px solid rgba(255,255,255,0.06)",
              borderRadius: "9px", color: "#e8f0fe",
              fontSize: "13px", outline: "none", fontFamily: FONT,
              transition: "border-color 0.2s",
            }}
            onFocus={e => e.target.style.borderColor = "rgba(56,189,248,0.3)"}
            onBlur={e => e.target.style.borderColor = "rgba(255,255,255,0.06)"}
          />
        </div>

        {["all", "critical", "warning"].map(f => (
          <button key={f} onClick={() => setFilter(f)} style={{
            padding: "8px 14px",
            background: filter === f ? "rgba(56,189,248,0.1)" : "rgba(255,255,255,0.02)",
            border: `1px solid ${filter === f ? "rgba(56,189,248,0.3)" : "rgba(255,255,255,0.06)"}`,
            borderRadius: "8px",
            color: filter === f ? "#38bdf8" : "rgba(122,143,166,0.5)",
            fontSize: "12px", cursor: "pointer", fontFamily: FONT,
            textTransform: "capitalize", fontWeight: filter === f ? 600 : 400,
          }}>{f}</button>
        ))}

        <div style={{ marginLeft: "auto", display: "flex", gap: "4px" }}>
          {["timeline", "table"].map(v => (
            <button key={v} onClick={() => setView(v)} style={{
              padding: "7px 12px",
              background: view === v ? "#0c1220" : "transparent",
              border: `1px solid ${view === v ? "rgba(56,189,248,0.2)" : "rgba(255,255,255,0.05)"}`,
              borderRadius: "7px", color: view === v ? "#38bdf8" : "rgba(122,143,166,0.4)",
              fontSize: "11px", cursor: "pointer", fontFamily: MONO,
              textTransform: "capitalize",
            }}>{v}</button>
          ))}
        </div>
      </div>

      {loading ? (
        <div style={{ textAlign: "center", padding: "60px 0", color: "rgba(122,143,166,0.4)", fontFamily: MONO, fontSize: "12px" }}>
          Loading audit records...
        </div>
      ) : filtered.length === 0 ? (
        <div style={{ textAlign: "center", padding: "60px 0", color: "rgba(122,143,166,0.3)" }}>
          <div style={{ fontSize: "28px", marginBottom: "10px" }}>◱</div>
          <div style={{ fontSize: "14px" }}>No audit entries found</div>
        </div>
      ) : view === "timeline" ? (
        /* Timeline view */
        <div>
          {Object.entries(grouped).sort((a, b) => b[0].localeCompare(a[0])).map(([date, entries]) => (
            <div key={date} style={{ marginBottom: "28px" }}>
              <div style={{
                fontSize: "11px", fontFamily: MONO, color: "rgba(122,143,166,0.4)",
                letterSpacing: "0.14em", textTransform: "uppercase",
                marginBottom: "10px", display: "flex", alignItems: "center", gap: "10px",
              }}>
                <div style={{ height: "1px", flex: 1, background: "rgba(255,255,255,0.04)" }}/>
                {date}
                <div style={{ height: "1px", flex: 1, background: "rgba(255,255,255,0.04)" }}/>
              </div>
              <div style={{ display: "flex", flexDirection: "column", gap: "6px" }}>
                {entries.map((l, i) => {
                  const v = verified[l.id];
                  return (
                    <div key={l.id || i} style={{
                      display: "flex", gap: "12px", alignItems: "flex-start",
                      padding: "14px 16px",
                      background: "#0c1220",
                      border: "1px solid rgba(255,255,255,0.05)",
                      borderRadius: "10px",
                      transition: "border-color 0.15s, background 0.15s",
                    }}
                      onMouseOver={e => { e.currentTarget.style.borderColor = "rgba(56,189,248,0.15)"; e.currentTarget.style.background = "#0e1628"; }}
                      onMouseOut={e => { e.currentTarget.style.borderColor = "rgba(255,255,255,0.05)"; e.currentTarget.style.background = "#0c1220"; }}
                    >
                      {/* Time */}
                      <div style={{ fontSize: "10px", fontFamily: MONO, color: "rgba(122,143,166,0.35)", whiteSpace: "nowrap", marginTop: "2px", minWidth: "54px" }}>
                        {l.timestamp?.slice(11, 19) || "—"}
                      </div>

                      {/* Dot */}
                      <div style={{
                        width: "7px", height: "7px", borderRadius: "50%", flexShrink: 0, marginTop: "4px",
                        background: l.status === "critical" ? "#f43f5e" : l.status === "warning" ? "#f59e0b" : "#38bdf8",
                        boxShadow: l.status === "critical" ? "0 0 6px #f43f5e" : "none",
                      }}/>

                      {/* Content */}
                      <div style={{ flex: 1, minWidth: 0 }}>
                        <div style={{ display: "flex", alignItems: "center", gap: "8px", marginBottom: "3px", flexWrap: "wrap" }}>
                          <ActionBadge action={l.action} />
                          {l.username && (
                            <span style={{ fontSize: "11px", color: "#38bdf8", fontFamily: MONO }}>{l.username}</span>
                          )}
                          {l.hostname && l.hostname !== "System" && (
                            <span style={{ fontSize: "10px", color: "rgba(122,143,166,0.5)", fontFamily: MONO }}>· {l.hostname}</span>
                          )}
                        </div>
                        <div style={{ fontSize: "12px", color: "rgba(122,143,166,0.6)" }}>{l.detail || "—"}</div>
                        {l.hash && (
                          <div style={{ fontSize: "10px", fontFamily: MONO, color: "rgba(61,80,104,0.6)", marginTop: "4px" }}>
                            SHA-256: {l.hash}
                          </div>
                        )}
                      </div>

                      {/* Verify */}
                      <div style={{ flexShrink: 0 }}>
                        {v ? (
                          <span style={{
                            fontSize: "10px", fontFamily: MONO, padding: "3px 8px",
                            background: v.valid ? "rgba(16,185,129,0.08)" : "rgba(244,63,94,0.08)",
                            border: `1px solid ${v.valid ? "rgba(16,185,129,0.2)" : "rgba(244,63,94,0.2)"}`,
                            borderRadius: "5px", color: v.valid ? "#10b981" : "#f43f5e",
                          }}>
                            {v.valid ? "✓ VALID" : "✗ INVALID"}
                          </span>
                        ) : (
                          <button onClick={() => handleVerify(l.id)} style={{
                            padding: "4px 10px",
                            background: "rgba(56,189,248,0.06)",
                            border: "1px solid rgba(56,189,248,0.15)",
                            borderRadius: "5px", color: "rgba(56,189,248,0.6)",
                            fontSize: "10px", cursor: "pointer", fontFamily: MONO,
                            transition: "all 0.15s",
                          }}
                            onMouseOver={e => { e.currentTarget.style.color = "#38bdf8"; e.currentTarget.style.borderColor = "rgba(56,189,248,0.35)"; }}
                            onMouseOut={e => { e.currentTarget.style.color = "rgba(56,189,248,0.6)"; e.currentTarget.style.borderColor = "rgba(56,189,248,0.15)"; }}
                          >Verify</button>
                        )}
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
          ))}
        </div>
      ) : (
        /* Table view */
        <div style={{ background: "#0c1220", border: "1px solid rgba(255,255,255,0.06)", borderRadius: "12px", overflow: "hidden" }}>
          <table style={{ width: "100%", borderCollapse: "collapse", fontSize: "12px" }}>
            <thead>
              <tr style={{ borderBottom: "1px solid rgba(255,255,255,0.05)" }}>
                {["#", "Time", "User", "Machine", "Action", "Detail", "Hash", "Verify"].map(h => (
                  <th key={h} style={{
                    textAlign: "left", padding: "12px 14px",
                    fontSize: "9px", color: "rgba(122,143,166,0.4)",
                    fontFamily: MONO, letterSpacing: "0.16em",
                    textTransform: "uppercase", fontWeight: 600,
                  }}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {filtered.map((l, i) => {
                const v = verified[l.id];
                return (
                  <tr key={l.id || i} style={{ borderBottom: "1px solid rgba(255,255,255,0.03)" }}
                    onMouseOver={e => e.currentTarget.style.background = "rgba(255,255,255,0.01)"}
                    onMouseOut={e => e.currentTarget.style.background = "transparent"}
                  >
                    <td style={{ padding: "10px 14px", color: "rgba(61,80,104,0.6)", fontFamily: MONO, fontSize: "10px" }}>{l.id}</td>
                    <td style={{ padding: "10px 14px", color: "rgba(122,143,166,0.5)", fontFamily: MONO, fontSize: "10px", whiteSpace: "nowrap" }}>{l.timestamp?.slice(0, 16).replace("T", " ")}</td>
                    <td style={{ padding: "10px 14px", color: "#38bdf8", fontFamily: MONO, fontSize: "11px" }}>{l.username || "system"}</td>
                    <td style={{ padding: "10px 14px", color: "rgba(122,143,166,0.5)", fontFamily: MONO, fontSize: "11px" }}>{l.hostname || "—"}</td>
                    <td style={{ padding: "10px 14px" }}><ActionBadge action={l.action} /></td>
                    <td style={{ padding: "10px 14px", color: "rgba(122,143,166,0.6)", maxWidth: "200px", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{l.detail}</td>
                    <td style={{ padding: "10px 14px", fontFamily: MONO, fontSize: "10px", color: "rgba(61,80,104,0.5)" }}>{l.hash}</td>
                    <td style={{ padding: "10px 14px" }}>
                      {v ? (
                        <span style={{ fontSize: "10px", fontFamily: MONO, color: v.valid ? "#10b981" : "#f43f5e" }}>
                          {v.valid ? "✓ Valid" : "✗ Invalid"}
                        </span>
                      ) : (
                        <button onClick={() => handleVerify(l.id)} style={{
                          padding: "3px 8px", background: "rgba(56,189,248,0.06)",
                          border: "1px solid rgba(56,189,248,0.15)",
                          borderRadius: "4px", color: "rgba(56,189,248,0.6)",
                          fontSize: "10px", cursor: "pointer", fontFamily: MONO,
                        }}>Verify</button>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}

      <style>{`
        @import url('https://fonts.googleapis.com/css2?family=Syne:wght@700;800&family=JetBrains+Mono:wght@400;500&family=Cabinet+Grotesk:wght@400;500;600;700&display=swap');
      `}</style>
    </div>
  );
}
