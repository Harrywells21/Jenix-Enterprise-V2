import { useState, useEffect } from "react";
import { getAuditLogs, exportAuditCSV, verifyLog } from "../api";

export default function AuditPage() {
  const [logs,     setLogs]     = useState([]);
  const [search,   setSearch]   = useState("");
  const [verified, setVerified] = useState({});
  const [toast,    setToast]    = useState("");

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

  const filtered = logs.filter(l =>
    l.action.includes(search.toLowerCase()) ||
    l.hostname?.toLowerCase().includes(search.toLowerCase()) ||
    l.detail?.toLowerCase().includes(search.toLowerCase())
  );

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
            Every action is cryptographically hashed with SHA-256
          </div>
        </div>
        <a href={exportAuditCSV()} target="_blank" rel="noreferrer"
          style={{
            padding:"8px 20px", background:"#00bcd4",
            color:"#000", borderRadius:"8px",
            fontWeight:700, fontSize:"13px",
            textDecoration:"none", display:"inline-block"
          }}>
          ⬇ Export CSV
        </a>
      </div>

      {/* Search */}
      <input placeholder="Search by action, machine, or detail..."
        value={search} onChange={e => setSearch(e.target.value)}
        style={{
          width:"360px", padding:"8px 14px", marginBottom:"16px",
          background:"#13131f", border:"1px solid #2a2a3e",
          borderRadius:"8px", color:"#e0e0e0",
          fontSize:"13px", outline:"none"
        }}
      />

      {/* Info banner */}
      <div style={{
        background:"#0a1628", border:"1px solid #1a2a3a",
        borderRadius:"8px", padding:"12px 16px",
        marginBottom:"16px", display:"flex",
        alignItems:"center", gap:"10px"
      }}>
        <span style={{ fontSize:"16px" }}>🔐</span>
        <span style={{ color:"#aaa", fontSize:"12px" }}>
          Each log entry is hashed using SHA-256. Click "Verify" on any entry
          to confirm it has not been tampered with since creation.
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
            <tr style={{
              background:"#0d0d1a",
              borderBottom:"1px solid #2a2a3e"
            }}>
              {["#","Timestamp","Machine","Action",
                "Detail","Status","Hash","Verify"].map(h => (
                <th key={h} style={{
                  textAlign:"left", padding:"10px 12px",
                  color:"#666", fontWeight:600,
                  fontSize:"11px", textTransform:"uppercase"
                }}>
                  {h}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {filtered.map((l, i) => (
              <tr key={l.id} style={{
                borderBottom:"1px solid #1a1a2e",
                background: i%2===0 ? "transparent" : "#0d0d1a"
              }}>
                <td style={{ padding:"10px 12px",
                             color:"#444" }}>{l.id}</td>
                <td style={{ padding:"10px 12px", color:"#666",
                             whiteSpace:"nowrap" }}>
                  {l.timestamp?.slice(0,16).replace("T"," ")}
                </td>
                <td style={{ padding:"10px 12px", color:"#00bcd4",
                             fontWeight:600 }}>
                  {l.hostname || "System"}
                </td>
                <td style={{ padding:"10px 12px" }}>
                  <span style={{
                    padding:"2px 8px", borderRadius:"4px",
                    fontSize:"11px", fontWeight:600,
                    background:"#1a1a2e", color:"#e0e0e0",
                    textTransform:"capitalize"
                  }}>
                    {l.action}
                  </span>
                </td>
                <td style={{ padding:"10px 12px", color:"#aaa",
                             maxWidth:"200px", overflow:"hidden",
                             textOverflow:"ellipsis",
                             whiteSpace:"nowrap" }}>
                  {l.detail}
                </td>
                <td style={{ padding:"10px 12px",
                  color: l.status==="ok" ? "#4caf50" : "#f44336" }}>
                  {l.status}
                </td>
                <td style={{ padding:"10px 12px" }}>
                  <span style={{
                    fontFamily:"monospace", fontSize:"10px",
                    color: verified[l.id] ? "#4caf50" : "#444"
                  }}>
                    {l.hash}
                  </span>
                </td>
                <td style={{ padding:"10px 12px" }}>
                  {verified[l.id] ? (
                    <span style={{ color:"#4caf50", fontSize:"11px" }}>
                      ✅ Valid
                    </span>
                  ) : (
                    <button onClick={() => handleVerify(l.id)} style={{
                      padding:"3px 10px", background:"#1a1a2e",
                      color:"#00bcd4", border:"1px solid #00bcd4",
                      borderRadius:"4px", fontSize:"11px",
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
