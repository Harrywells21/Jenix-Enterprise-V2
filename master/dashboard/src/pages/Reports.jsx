import { useEffect, useState, useCallback, useMemo } from "react";
import { FileText, Download, Trash2, FileBarChart2, ShieldCheck } from "lucide-react";
import { LoadingState, ErrorState, EmptyState } from "../components/States";
import { useToast } from "../components/Toast";
import {
  getFleetOverview, getReports, generateMachineReport, generateFleetReport,
  generateAuditReport, reportDownloadUrl, deleteReport,
} from "../api";

const inputStyle = {
  background: "var(--bg-input)", border: "1px solid var(--border-default)",
  borderRadius: "var(--radius-sm)", color: "var(--text-primary)",
  fontSize: 12.5, padding: "7px 10px", outline: "none",
};

function GhostButton({ icon: Icon, children, onClick, accent = "var(--cyan)", disabled }) {
  return (
    <button
      onClick={onClick}
      disabled={disabled}
      style={{
        display: "flex", alignItems: "center", gap: 6,
        padding: "7px 12px", borderRadius: "var(--radius-sm)",
        background: "transparent", border: "1px solid var(--border-default)",
        color: disabled ? "var(--text-muted)" : accent, fontSize: 12.5, fontWeight: 500,
        opacity: disabled ? 0.5 : 1, cursor: disabled ? "not-allowed" : "pointer",
      }}
    >
      {Icon && <Icon size={13} />} {children}
    </button>
  );
}

export default function Reports() {
  const [machines, setMachines] = useState([]);
  const [reports, setReports] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [machineKey, setMachineKey] = useState("");
  const [genFloor, setGenFloor] = useState("");
  const [busy, setBusy] = useState(null); // which action is in flight
  const showToast = useToast();

  const load = useCallback(async () => {
    try {
      const [fleetRes, reportsRes] = await Promise.all([getFleetOverview(), getReports()]);
      setMachines(fleetRes.data.machine_scores || []);
      setReports(reportsRes.data || []);
      setError(null);
    } catch (e) {
      setError(e.response?.data?.detail || "Failed to load reports");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  // Real floors are only known from data already fetched (machines + reports)
  // — no separate floor-list route has been confirmed, so nothing here is guessed.
  const floors = useMemo(() => {
    const map = new Map();
    machines.forEach((m) => map.set(m.floor_idx, m.floor_name));
    reports.forEach((r) => map.set(r.floor_idx, r.floor_name));
    return Array.from(map, ([floor_idx, floor_name]) => ({ floor_idx, floor_name }));
  }, [machines, reports]);

  useEffect(() => {
    if (!genFloor && floors.length > 0) setGenFloor(String(floors[0].floor_idx));
  }, [floors, genFloor]);

  const machineHostname = (r) => {
    const m = machines.find((x) => x.id === r.machine_id && x.floor_idx === r.floor_idx);
    return m?.hostname ?? `Machine #${r.machine_id}`;
  };

  const runGen = async (label, fn) => {
    setBusy(label);
    try {
      await fn();
      showToast(`${label} generated`, "success");
      await load();
    } catch (e) {
      showToast(e.response?.data?.detail || `Failed to generate ${label.toLowerCase()}`, "error");
    } finally {
      setBusy(null);
    }
  };

  const onGenerateMachine = () => {
    if (!machineKey) { showToast("Select a machine first", "error"); return; }
    const [floorIdx, machineId] = machineKey.split(":").map(Number);
    runGen("Machine report", () => generateMachineReport(floorIdx, machineId));
  };
  const onGenerateFleet = () => {
    if (!genFloor) { showToast("No floor available", "error"); return; }
    runGen("Fleet report", () => generateFleetReport(genFloor));
  };
  const onGenerateAudit = () => {
    if (!genFloor) { showToast("No floor available", "error"); return; }
    runGen("Audit report", () => generateAuditReport(genFloor));
  };

  const onDownload = (r) => window.open(reportDownloadUrl(r.floor_idx, r.id), "_blank");
  const onDelete = async (r) => {
    try {
      await deleteReport(r.floor_idx, r.id);
      setReports((prev) => prev.filter((x) => x.id !== r.id || x.floor_idx !== r.floor_idx));
      showToast("Report deleted", "success");
    } catch (e) {
      showToast(e.response?.data?.detail || "Failed to delete report", "error");
    }
  };

  if (loading) return <div style={{ padding: "22px 26px" }}><LoadingState rows={6} /></div>;
  if (error) return <div style={{ padding: "22px 26px" }}><ErrorState message={error} /></div>;

  return (
    <div style={{ padding: "22px 26px", overflowY: "auto", height: "100%" }}>
      <div style={{ marginBottom: 20 }}>
        <h1 style={{ fontFamily: "var(--font-display)", fontSize: 22, fontWeight: 800, marginBottom: 4 }}>Reports</h1>
        <p style={{ fontSize: 13, color: "var(--text-secondary)" }}>
          Generate and download security & compliance PDFs, or audit-trail reports, per floor or per machine.
        </p>
      </div>

      <div className="card" style={{ padding: 18, marginBottom: 18 }}>
        <h2 style={{ fontFamily: "var(--font-display)", fontSize: 15, fontWeight: 700, marginBottom: 14 }}>Generate</h2>
        <div style={{ display: "flex", flexWrap: "wrap", gap: 20 }}>
          <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
            <label style={{ fontSize: 11, color: "var(--text-muted)", fontFamily: "var(--font-mono)", textTransform: "uppercase" }}>Single Machine</label>
            <div style={{ display: "flex", gap: 8 }}>
              <select value={machineKey} onChange={(e) => setMachineKey(e.target.value)} style={{ ...inputStyle, minWidth: 220 }}>
                <option value="">Select a machine…</option>
                {machines.map((m) => (
                  <option key={`${m.floor_idx}:${m.id}`} value={`${m.floor_idx}:${m.id}`}>
                    {m.hostname} — {m.floor_name} ({m.status})
                  </option>
                ))}
              </select>
              <GhostButton icon={FileText} accent="var(--emerald)" disabled={busy === "Machine report"} onClick={onGenerateMachine}>
                {busy === "Machine report" ? "Generating…" : "Generate"}
              </GhostButton>
            </div>
          </div>

          <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
            <label style={{ fontSize: 11, color: "var(--text-muted)", fontFamily: "var(--font-mono)", textTransform: "uppercase" }}>Fleet-wide</label>
            <div style={{ display: "flex", gap: 8 }}>
              <select value={genFloor} onChange={(e) => setGenFloor(e.target.value)} style={inputStyle}>
                {floors.map((f) => <option key={f.floor_idx} value={f.floor_idx}>{f.floor_name}</option>)}
              </select>
              <GhostButton icon={FileBarChart2} accent="var(--emerald)" disabled={busy === "Fleet report"} onClick={onGenerateFleet}>
                {busy === "Fleet report" ? "Generating…" : "Generate"}
              </GhostButton>
            </div>
          </div>

          <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
            <label style={{ fontSize: 11, color: "var(--text-muted)", fontFamily: "var(--font-mono)", textTransform: "uppercase" }}>Audit Trail</label>
            <div style={{ display: "flex", gap: 8 }}>
              <select value={genFloor} onChange={(e) => setGenFloor(e.target.value)} style={inputStyle}>
                {floors.map((f) => <option key={f.floor_idx} value={f.floor_idx}>{f.floor_name}</option>)}
              </select>
              <GhostButton icon={ShieldCheck} accent="var(--emerald)" disabled={busy === "Audit report"} onClick={onGenerateAudit}>
                {busy === "Audit report" ? "Generating…" : "Generate"}
              </GhostButton>
            </div>
          </div>
        </div>
      </div>

      <div className="card" style={{ padding: 18 }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 14 }}>
          <h2 style={{ fontFamily: "var(--font-display)", fontSize: 15, fontWeight: 700 }}>Generated Reports</h2>
          <span style={{ fontSize: 11, color: "var(--text-muted)", fontFamily: "var(--font-mono)" }}>{reports.length} total</span>
        </div>
        {reports.length === 0 ? (
          <EmptyState icon="📄" title="No reports generated yet" subtitle="Use the panel above to generate one" />
        ) : (
          <div style={{ overflowX: "auto" }}>
            <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13 }}>
              <thead>
                <tr style={{ borderBottom: "1px solid var(--border-default)" }}>
                  {["Filename", "Machine", "Floor", "Size", "Created", ""].map((h) => (
                    <th key={h} style={{ textAlign: "left", padding: "8px 12px", fontFamily: "var(--font-mono)", fontSize: 10, color: "var(--text-muted)", letterSpacing: "0.08em", textTransform: "uppercase", whiteSpace: "nowrap" }}>{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {[...reports].sort((a, b) => new Date(b.created_at) - new Date(a.created_at)).map((r) => (
                  <tr key={`${r.floor_idx}-${r.id}`} style={{ borderBottom: "1px solid var(--border-subtle)" }}>
                    <td style={{ padding: "10px 12px", fontFamily: "var(--font-mono)", fontSize: 12, maxWidth: 320, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }} title={r.filename}>
                      {r.filename}
                    </td>
                    <td style={{ padding: "10px 12px", fontSize: 12, whiteSpace: "nowrap" }}>{machineHostname(r)}</td>
                    <td style={{ padding: "10px 12px", color: "var(--text-muted)", fontSize: 12, whiteSpace: "nowrap" }}>{r.floor_name}</td>
                    <td style={{ padding: "10px 12px", fontFamily: "var(--font-mono)", fontSize: 12, whiteSpace: "nowrap" }}>{r.size_kb?.toFixed(1)} KB</td>
                    <td style={{ padding: "10px 12px", fontFamily: "var(--font-mono)", fontSize: 11, color: "var(--text-muted)", whiteSpace: "nowrap" }}>{new Date(r.created_at).toLocaleString()}</td>
                    <td style={{ padding: "10px 12px", display: "flex", gap: 6, justifyContent: "flex-end" }}>
                      <GhostButton icon={Download} onClick={() => onDownload(r)}>Download</GhostButton>
                      <GhostButton icon={Trash2} accent="var(--rose)" onClick={() => onDelete(r)}>Delete</GhostButton>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
