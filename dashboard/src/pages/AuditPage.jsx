import { useState, useEffect } from "react";
import { getAuditLogs, verifyLog } from "../api";
import { getToken } from "../api";

export default function AuditPage() {
  const [logs,     setLogs]     = useState([]);
  const [search,   setSearch]   = useState("");
  const [verified, setVerified] = useState({});
  const [toast,    setToast]    = useState("");
  const [filter,   setFilter]   = useState("all");

  const showToast = (msg) => {
    setToast(msg); setTimeout(() => setToast(""), 3000);
  };

  useEffect(() => {
    getAuditLogs().then(r => setLogs(r.data)).catch(console.error);
  }, []);

  const handleVerify = async (id) => {
    try {
      const r = await verifyLog(id);
      setVerified(prev => ({ ...prev, [id]: r.data }));
      showToast(`✅ Log #${id} verified — hash matches`);
    } catch {
      showToast(`❌ Verification failed for log #${id}`);
    }
  };

  // ✅ Fixed: download with auth token as query param
  const handleExportCSV = () => {
    const token = getToken();
    const url   = `http://localhost:8000/audit/logs/export?token=${token}`;
    const a     = document.createElement("a");
    a.href      = url;
    a.download  = `jenix_audit_${new Date().toISOString().slice(0,10)}.csv`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
  };

  const filtered = logs.filter(l => {
    const matchSearch =
      l.action?.toLowerCase().includes(search.toLowerCase()) ||
      l.hostname?.toLowerCase().includes(search.toLowerCase()) ||
      l.detail?.toLowerCase().includes(search.toLowerCase());
    const matchFilter =
      filter === "all"      ? true :
      filter === "critical" ? l.status === "critical" :
      filter === "warning"  ? l.status === "warning"  :
      filter === "ok"       ? l.status === "ok"        : true;
    return matchSearch && matchFilter;
  });

  const statusColor = (s) =>
    s === "ok"       ? "#4caf50" :
    s === "warning"  ? "#ffb300" :
    s === "critical" ? "#f44336" : "#666";

  return (
    <div>
      {toast && (
        <div style={{
          position:"fixed", top:"20px", right:"20px",
          background:"#1a1a2e", border:"1px solid #2a2a3e",
          borderRadius:"8px", padding:"12px 20px",
          color:"#e0e0e0", fontSize:"13px", zIndex:1000
        }}>{toast}</div>
      )}

      {/* Header */}
      <div style={{ display:"flex", justifyContent:"space-between",
                    alignItems:"flex-start", marginBottom:"24px" }}>
        <div>
          <h1 style={{ color:"#e0e0e0", fontSize:"22px",
                       fontWeight:700, marginBottom:"4px" }}>
            Tamper-Proof Audit Log
          </h1>
          <div style={{ color:"#666", fontSize:"13px" }}>
            {logs.length} entries · SHA-256 verified
          </div>
        </div>
        <button onClick={handleExportCSV} style={{
          padding:"8px 20px", background:"#00bcd4",
          color:"#000", border:"none", borderRadius:"8px",
          fontWeight:700, fontSize:"13px", cursor:"pointer"
        }}>
          ⬇ Export CSV
        </button>
      </div>

      {/* Filters */}
      <div style={{ display:"flex", gap:"10px",
                    marginBottom:"16px", flexWrap:"wrap" }}>
        <input placeholder="Search action, machine, detail..."
          value={search} onChange={e => setSearch(e.target.value)}
          style={{
            flex:1, minWidth:"200px", padding:"8px 14px",
            background:"#13131f", border:"1px solid #2a2a3e",
            borderRadius:"8px", color:"#e0e0e0",
            fontSize:"13px", outline:"none"
          }}
        />
        {["all","ok","warning","critical"].map(f => (
          <button key={f} onClick={() => setFilter(f)} style={{
            padding:"8px 14px",
            background: filter===f ? "#1a1a2e" : "transparent",
            color:  filter===f ? "#00bcd4" : "#666",
            border:`1px solid ${filter===f ? "#00bcd4" : "#2a2a3e"}`,
            borderRadius:"8px", cursor:"pointer",
            fontSize:"12px", fontWeight:600,
            textTransform:"capitalize"
          }}>
            {f}
          </button>
        ))}
      </div>

      {/* Info banner */}
      <div style={{
        background:"#0a1628", border:"1px solid #1a2a3a",
        borderRadius:"8px", padding:"10px 16px",
        marginBottom:"16px", display:"flex",
        alignItems:"center", gap:"10px"
      }}>
        <span>🔐</span>
        <span style={{ color:"#aaa", fontSize:"12px" }}>
          Each entry is hashed with SHA-256 at creation time.
          Click Verify to confirm it has not been modified.
          Export as CSV with full hashes for auditor submission.
        </span>
      </div>

      {/* Table */}
      <div style={{
        background:"#13131f", border:"1px solid #2a2a3e",
        borderRadius:"12px", overflow:"hidden"
      }}>
        <table style={{ width:"100%", borderCollapse:"collapse",
                        fontSize:"12px" }}>
          <thead>
            <tr style={{ background:"#0d0d1a",
                         borderBottom:"1px solid #2a2a3e" }}>
              {["#","Time","Machine","Action",
                "Detail","Status","Hash","Verify"].map(h => (
                <th key={h} style={{
                  textAlign:"left", padding:"10px 12px",
                  color:"#555", fontWeight:600,
                  fontSize:"11px", textTransform:"uppercase"
                }}>{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {filtered.map((l, i) => (
              <tr key={l.id} style={{
                borderBottom:"1px solid #1a1a2e",
                background: i%2===0 ? "transparent" : "#0a0a14"
              }}>
                <td style={{ padding:"8px 12px",
                             color:"#333" }}>{l.id}</td>
                <td style={{ padding:"8px 12px", color:"#555",
                             whiteSpace:"nowrap", fontSize:"11px" }}>
                  {l.timestamp?.slice(0,16).replace("T"," ")}
                </td>
                <td style={{ padding:"8px 12px", color:"#00bcd4",
                             fontWeight:600 }}>
                  {l.hostname || "System"}
                </td>
                <td style={{ padding:"8px 12px" }}>
                  <span style={{
                    padding:"2px 8px", borderRadius:"4px",
                    fontSize:"10px", fontWeight:600,
                    background:"#1a1a2e", color:"#e0e0e0",
                    textTransform:"capitalize"
                  }}>
                    {l.action}
                  </span>
                </td>
                <td style={{ padding:"8px 12px", color:"#666",
                             maxWidth:"180px", overflow:"hidden",
                             textOverflow:"ellipsis",
                             whiteSpace:"nowrap" }}>
                  {l.detail}
                </td>
                <td style={{ padding:"8px 12px",
                  color: statusColor(l.status) }}>
                  {l.status}
                </td>
                <td style={{ padding:"8px 12px" }}>
                  <span style={{
                    fontFamily:"monospace", fontSize:"10px",
                    color: verified[l.id] ? "#4caf50" : "#333"
                  }}>
                    {l.hash}
                  </span>
                </td>
                <td style={{ padding:"8px 12px" }}>
                  {verified[l.id] ? (
                    <span style={{ color:"#4caf50",
                                   fontSize:"11px" }}>
                      ✅ Valid
                    </span>
                  ) : (
                    <button onClick={() => handleVerify(l.id)}
                      style={{
                        padding:"3px 10px", background:"#1a1a2e",
                        color:"#00bcd4", border:"1px solid #00bcd4",
                        borderRadius:"4px", fontSize:"10px",
                        cursor:"pointer"
                      }}>
                      Verify
                    </button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {filtered.length === 0 && (
          <div style={{ color:"#666", textAlign:"center",
                        padding:"40px", fontSize:"13px" }}>
            No audit logs found.
          </div>
        )}
      </div>
    </div>
  );
}
