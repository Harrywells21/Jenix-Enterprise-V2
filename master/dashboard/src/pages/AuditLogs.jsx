import { useEffect, useState, useCallback, useMemo } from "react";
import { ShieldCheck, ShieldAlert, ShieldQuestion, Download } from "lucide-react";
import { LoadingState, ErrorState, EmptyState } from "../components/States";
import { useToast } from "../components/Toast";
import { getAuditLogs, verifyAuditLog, auditLogExportUrl } from "../api";

const STATUS_COLOR = { ok: "var(--emerald)", warning: "var(--amber)", critical: "var(--rose)" };

const inputStyle = {
  background: "var(--bg-input)", border: "1px solid var(--border-default)",
  borderRadius: "var(--radius-sm)", color: "var(--text-primary)",
  fontSize: 12.5, padding: "7px 10px", outline: "none",
};

function StatusDot({ status }) {
  return (
    <span style={{ display: "inline-flex", alignItems: "center", gap: 6, fontSize: 12, color: "var(--text-secondary)" }}>
      <span style={{ width: 6, height: 6, borderRadius: "50%", background: STATUS_COLOR[status] || "var(--slate)" }} />
      {status}
    </span>
  );
}

export default function AuditLogs() {
  const [logs, setLogs] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [verifyResults, setVerifyResults] = useState({}); // log_id -> {verified, hash}
  const [exportFloor, setExportFloor] = useState("");
  const showToast = useToast();

  const load = useCallback(async () => {
    try {
      const res = await getAuditLogs();
      setLogs(res.data || []);
      setError(null);
    } catch (e) {
      setError(e.response?.data?.detail || "Failed to load audit logs");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  // Real floors are only known from the data itself — no separate floor-list
  // route has been confirmed, so this is derived rather than fabricated.
  const floors = useMemo(() => {
    const map = new Map();
    logs.forEach((l) => map.set(l.floor_idx, l.floor_name));
    return Array.from(map, ([floor_idx, floor_name]) => ({ floor_idx, floor_name }));
  }, [logs]);

  useEffect(() => {
    if (!exportFloor && floors.length > 0) setExportFloor(String(floors[0].floor_idx));
  }, [floors, exportFloor]);

  const onVerify = async (log) => {
    try {
      const res = await verifyAuditLog(log.floor_idx, log.id);
      setVerifyResults((prev) => ({ ...prev, [log.id]: res.data }));
      if (res.data.verified === true) showToast(`Log #${log.id} verified — hash matches`, "success");
      else if (res.data.verified === false) showToast(`Log #${log.id} FAILED verification — hash mismatch`, "error");
      else showToast(`Log #${log.id}: ${res.data.error || "no stored hash to compare"}`, "info");
    } catch (e) {
      showToast(e.response?.data?.detail || "Verification request failed", "error");
    }
  };

  const onExport = () => {
    if (!exportFloor) { showToast("No floor available to export", "error"); return; }
    window.open(auditLogExportUrl(exportFloor), "_blank");
  };

  if (loading) return <div style={{ padding: "22px 26px" }}><LoadingState rows={6} /></div>;
  if (error) return <div style={{ padding: "22px 26px" }}><ErrorState message={error} /></div>;

  return (
    <div style={{ padding: "22px 26px", overflowY: "auto", height: "100%" }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: 20, flexWrap: "wrap", gap: 12 }}>
        <div>
          <h1 style={{ fontFamily: "var(--font-display)", fontSize: 22, fontWeight: 800, marginBottom: 4 }}>Audit Logs</h1>
          <p style={{ fontSize: 13, color: "var(--text-secondary)" }}>
            Tamper-evident action log — every entry is SHA256-hashed at write time. {logs.length} entries loaded.
          </p>
        </div>
        <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
          <select value={exportFloor} onChange={(e) => setExportFloor(e.target.value)} style={inputStyle}>
            {floors.map((f) => <option key={f.floor_idx} value={f.floor_idx}>{f.floor_name}</option>)}
          </select>
          <button onClick={onExport} style={{
            display: "flex", alignItems: "center", gap: 6,
            padding: "7px 12px", borderRadius: "var(--radius-sm)",
            background: "transparent", border: "1px solid var(--border-default)",
            color: "var(--cyan)", fontSize: 12.5, fontWeight: 500,
          }}>
            <Download size={13} /> Export CSV
          </button>
        </div>
      </div>

      <div className="card" style={{ padding: 18 }}>
        {logs.length === 0 ? (
          <EmptyState icon="🛡" title="No audit log entries yet" />
        ) : (
          <div style={{ overflowX: "auto" }}>
            <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13 }}>
              <thead>
                <tr style={{ borderBottom: "1px solid var(--border-default)" }}>
                  {["Timestamp", "Action", "Detail", "Machine", "User", "Status", "Hash", "Floor", ""].map((h) => (
                    <th key={h} style={{ textAlign: "left", padding: "8px 12px", fontFamily: "var(--font-mono)", fontSize: 10, color: "var(--text-muted)", letterSpacing: "0.08em", textTransform: "uppercase", whiteSpace: "nowrap" }}>{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {logs.map((l) => {
                  const vr = verifyResults[l.id];
                  return (
                    <tr key={l.id} style={{ borderBottom: "1px solid var(--border-subtle)" }}>
                      <td style={{ padding: "10px 12px", fontFamily: "var(--font-mono)", fontSize: 11, color: "var(--text-muted)", whiteSpace: "nowrap" }}>
                        {new Date(l.timestamp).toLocaleString()}
                      </td>
                      <td style={{ padding: "10px 12px", fontWeight: 500, whiteSpace: "nowrap" }}>{l.action}</td>
                      <td style={{ padding: "10px 12px", color: "var(--text-secondary)", maxWidth: 320, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }} title={l.detail}>
                        {l.detail}
                      </td>
                      <td style={{ padding: "10px 12px", fontFamily: "var(--font-mono)", fontSize: 12, whiteSpace: "nowrap" }}>{l.hostname}</td>
                      <td style={{ padding: "10px 12px", fontSize: 12, whiteSpace: "nowrap" }}>{l.username}</td>
                      <td style={{ padding: "10px 12px", whiteSpace: "nowrap" }}><StatusDot status={l.status} /></td>
                      <td style={{ padding: "10px 12px", fontFamily: "var(--font-mono)", fontSize: 11, color: "var(--text-muted)", whiteSpace: "nowrap" }}>{l.hash}</td>
                      <td style={{ padding: "10px 12px", color: "var(--text-muted)", fontSize: 12, whiteSpace: "nowrap" }}>{l.floor_name}</td>
                      <td style={{ padding: "10px 12px", whiteSpace: "nowrap" }}>
                        <button onClick={() => onVerify(l)} style={{
                          display: "flex", alignItems: "center", gap: 5,
                          padding: "5px 10px", borderRadius: "var(--radius-sm)",
                          background: "transparent",
                          border: `1px solid ${vr?.verified === true ? "var(--emerald)" : vr?.verified === false ? "var(--rose)" : "var(--border-default)"}`,
                          color: vr?.verified === true ? "var(--emerald)" : vr?.verified === false ? "var(--rose)" : "var(--text-secondary)",
                          fontSize: 11.5,
                        }}>
                          {vr?.verified === true ? <ShieldCheck size={12} /> : vr?.verified === false ? <ShieldAlert size={12} /> : <ShieldQuestion size={12} />}
                          {vr?.verified === true ? "Verified" : vr?.verified === false ? "Mismatch" : "Verify"}
                        </button>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
