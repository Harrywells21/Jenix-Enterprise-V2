import { useEffect, useState, useCallback } from "react";
import { Check, X, ArrowRightLeft, Terminal, Server, Wifi, WifiOff, ShieldCheck, Plus } from "lucide-react";
import { LoadingState, ErrorState, EmptyState } from "../components/States";
import { useToast } from "../components/Toast";
import {
  getAggregate, approveMachine, rejectMachine, reassignMachine,
  dispatchCommand, dispatchFleetCommand, generateAuditReport, createFloor,
} from "../api";

// Real allowed command types, shared with Automation's presets — no
// fabricated fleet-command types beyond what the backend accepts.
const COMMAND_TYPES = ["scan", "boost", "clean", "fix", "rollback", "exec"];

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
        padding: "6px 10px", borderRadius: "var(--radius-sm)",
        background: "transparent", border: "1px solid var(--border-default)",
        color: disabled ? "var(--text-muted)" : accent, fontSize: 12, fontWeight: 500,
        opacity: disabled ? 0.5 : 1, cursor: disabled ? "not-allowed" : "pointer",
      }}
    >
      {Icon && <Icon size={12} />} {children}
    </button>
  );
}

function timeAgo(iso) {
  if (!iso) return "never";
  const mins = Math.round((Date.now() - new Date(iso).getTime()) / 60000);
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.round(mins / 60);
  if (hrs < 24) return `${hrs}h ago`;
  return `${Math.round(hrs / 24)}d ago`;
}

export default function Floors() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [reassignState, setReassignState] = useState({}); // `${floorIdx}:${machineId}` -> targetFloorIdx
  const [cmdState, setCmdState] = useState({});
  const [fleetCmdType, setFleetCmdType] = useState("scan");
  const [busy, setBusy] = useState(null);
  const [showAddFloor, setShowAddFloor] = useState(false);
  const [newFloor, setNewFloor] = useState({ name: "", url: "", username: "", password: "" });
  const [addFloorNote, setAddFloorNote] = useState(null);
  const showToast = useToast();

  const load = useCallback(async () => {
    try {
      const res = await getAggregate();
      setData(res.data);
      setError(null);
    } catch (e) {
      setError(e.response?.data?.detail || "Failed to load floors");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  if (loading) return <div style={{ padding: "22px 26px" }}><LoadingState rows={6} /></div>;
  if (error) return <div style={{ padding: "22px 26px" }}><ErrorState message={error} /></div>;

  const floors = data.floors || [];

  const onApprove = async (floorIdx, machineId) => {
    setBusy(`approve-${floorIdx}-${machineId}`);
    try {
      await approveMachine(floorIdx, machineId);
      showToast("Machine approved", "success");
      await load();
    } catch (e) {
      showToast(e.response?.data?.detail || "Failed to approve", "error");
    } finally { setBusy(null); }
  };

  const onReject = async (floorIdx, machineId) => {
    setBusy(`reject-${floorIdx}-${machineId}`);
    try {
      await rejectMachine(floorIdx, machineId);
      showToast("Machine rejected", "success");
      await load();
    } catch (e) {
      showToast(e.response?.data?.detail || "Failed to reject", "error");
    } finally { setBusy(null); }
  };

  const onReassign = async (floorIdx, machineId) => {
    const key = `${floorIdx}:${machineId}`;
    const targetFloorIdx = reassignState[key];
    if (targetFloorIdx === undefined || targetFloorIdx === "") { showToast("Select a target floor first", "error"); return; }
    setBusy(`reassign-${key}`);
    try {
      await reassignMachine(floorIdx, machineId, targetFloorIdx);
      showToast("Reassignment signed and dispatched", "success");
      await load();
    } catch (e) {
      showToast(e.response?.data?.detail || "Failed to reassign (machine must be online)", "error");
    } finally { setBusy(null); }
  };

  const onCommand = async (floorIdx, machineId) => {
    const key = `${floorIdx}:${machineId}`;
    const type = cmdState[key] || "scan";
    setBusy(`cmd-${key}`);
    try {
      await dispatchCommand(floorIdx, machineId, type);
      showToast(`"${type}" dispatched`, "success");
    } catch (e) {
      showToast(e.response?.data?.detail || "Failed to dispatch command", "error");
    } finally { setBusy(null); }
  };

  const onAudit = async (floorIdx, machineId) => {
    const key = `${floorIdx}:${machineId}`;
    setBusy(`audit-${key}`);
    try {
      const res = await generateAuditReport(floorIdx, [machineId]);
      showToast(`Audit report generated (${res.data.total_entries} events) - see Reports page`, "success");
    } catch (e) {
      showToast(e.response?.data?.detail || "Failed to generate audit report", "error");
    } finally { setBusy(null); }
  };

  const onFleetCommand = async () => {
    setBusy("fleet-command");
    try {
      const res = await dispatchFleetCommand(fleetCmdType);
      showToast(`Fleet "${fleetCmdType}" — sent ${res.data.sent}, failed ${res.data.failed} of ${res.data.total} online`, res.data.failed > 0 ? "info" : "success");
    } catch (e) {
      showToast(e.response?.data?.detail || "Failed to dispatch fleet command", "error");
    } finally { setBusy(null); }
  };

  const onCreateFloor = async () => {
    const { name, url, username, password } = newFloor;
    if (!name || !url || !username || !password) {
      showToast("All fields are required", "error");
      return;
    }
    setBusy("create-floor");
    try {
      const res = await createFloor(newFloor);
      showToast(`Floor "${res.data.name}" created`, "success");
      setAddFloorNote(res.data.note || null);
      setNewFloor({ name: "", url: "", username: "", password: "" });
      setShowAddFloor(false);
      await load();
    } catch (e) {
      showToast(e.response?.data?.detail || "Failed to create floor", "error");
    } finally { setBusy(null); }
  };

  return (
    <div style={{ padding: "22px 26px", overflowY: "auto", height: "100%" }}>
      <div style={{ marginBottom: 20 }}>
        <h1 style={{ fontFamily: "var(--font-display)", fontSize: 22, fontWeight: 800, marginBottom: 4 }}>Floors</h1>
        <p style={{ fontSize: 13, color: "var(--text-secondary)" }}>
          {data.grand_total} machines across {data.floors_total} floors ({data.floors_reachable} reachable) —
          {" "}{data.grand_online} online, {data.grand_offline} offline, {data.grand_pending} pending approval.
        </p>
      </div>

      {addFloorNote && (
        <div className="card" style={{ padding: 14, marginBottom: 18, border: "1px solid var(--amber)44", background: "var(--amber-dim)" }}>
          <div style={{ fontSize: 12.5, color: "var(--text-primary)" }}>{addFloorNote}</div>
        </div>
      )}

      <div className="card" style={{ padding: 18, marginBottom: 18 }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: showAddFloor ? 14 : 0 }}>
          <h2 style={{ fontFamily: "var(--font-display)", fontSize: 15, fontWeight: 700 }}>Add Floor</h2>
          <GhostButton icon={Plus} onClick={() => setShowAddFloor((s) => !s)}>
            {showAddFloor ? "Cancel" : "New Floor"}
          </GhostButton>
        </div>
        {showAddFloor && (
          <div style={{ display: "flex", gap: 8, flexWrap: "wrap", alignItems: "center" }}>
            <input placeholder="Name" value={newFloor.name} onChange={(e) => setNewFloor((p) => ({ ...p, name: e.target.value }))} style={{ ...inputStyle, width: 140 }} />
            <input placeholder="URL (http://host:port)" value={newFloor.url} onChange={(e) => setNewFloor((p) => ({ ...p, url: e.target.value }))} style={{ ...inputStyle, width: 220 }} />
            <input placeholder="Admin username" value={newFloor.username} onChange={(e) => setNewFloor((p) => ({ ...p, username: e.target.value }))} style={{ ...inputStyle, width: 160 }} />
            <input type="password" placeholder="Admin password" value={newFloor.password} onChange={(e) => setNewFloor((p) => ({ ...p, password: e.target.value }))} style={{ ...inputStyle, width: 160 }} />
            <GhostButton icon={Check} accent="var(--emerald)" disabled={busy === "create-floor"} onClick={onCreateFloor}>
              {busy === "create-floor" ? "Creating…" : "Create"}
            </GhostButton>
          </div>
        )}
      </div>

      <div className="card" style={{ padding: 18, marginBottom: 18 }}>
        <h2 style={{ fontFamily: "var(--font-display)", fontSize: 15, fontWeight: 700, marginBottom: 12 }}>Fleet-wide Command</h2>
        <div style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap" }}>
          <select value={fleetCmdType} onChange={(e) => setFleetCmdType(e.target.value)} style={inputStyle}>
            {COMMAND_TYPES.map((t) => <option key={t} value={t}>{t}</option>)}
          </select>
          <GhostButton icon={Terminal} accent="var(--rose)" disabled={busy === "fleet-command"} onClick={onFleetCommand}>
            {busy === "fleet-command" ? "Dispatching…" : "Send to all online machines"}
          </GhostButton>
          <span style={{ fontSize: 11.5, color: "var(--text-muted)" }}>
            Dispatches to every currently-online machine on every reachable floor.
          </span>
        </div>
      </div>

      {floors.map((f) => (
        <div key={f.idx} className="card" style={{ padding: 18, marginBottom: 18 }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 4, flexWrap: "wrap", gap: 8 }}>
            <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
              <Server size={16} color="var(--violet)" />
              <h2 style={{ fontFamily: "var(--font-display)", fontSize: 15, fontWeight: 700 }}>{f.name}</h2>
              <span style={{
                display: "inline-flex", alignItems: "center", gap: 5, fontSize: 11, fontFamily: "var(--font-mono)",
                color: f.reachable ? "var(--emerald)" : "var(--rose)",
                background: f.reachable ? "var(--emerald-dim)" : "var(--rose-dim)",
                border: `1px solid ${f.reachable ? "var(--emerald)" : "var(--rose)"}44`, padding: "2px 8px", borderRadius: 999,
              }}>
                {f.reachable ? <Wifi size={11} /> : <WifiOff size={11} />} {f.reachable ? "Reachable" : "Unreachable"}
              </span>
            </div>
            <span style={{ fontSize: 12, color: "var(--text-muted)", fontFamily: "var(--font-mono)" }}>
              {f.online}/{f.total} online · {f.pending_count} pending
            </span>
          </div>
          <div style={{ fontSize: 11.5, color: "var(--text-muted)", fontFamily: "var(--font-mono)", marginBottom: 14 }}>{f.url}</div>

          {f.pending_count > 0 && (
            <div style={{ marginBottom: 16 }}>
              <div style={{ fontSize: 11, color: "var(--amber)", fontFamily: "var(--font-mono)", textTransform: "uppercase", marginBottom: 8 }}>Pending Approval</div>
              <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                {f.pending.map((m) => (
                  <div key={m.id} style={{ display: "flex", justifyContent: "space-between", alignItems: "center", padding: 10, background: "var(--amber-dim)", border: "1px solid var(--amber)33", borderRadius: "var(--radius-sm)" }}>
                    <div style={{ fontSize: 12.5 }}>
                      <span style={{ fontWeight: 600 }}>{m.hostname}</span>
                      <span style={{ color: "var(--text-muted)", fontFamily: "var(--font-mono)", marginLeft: 8 }}>{m.ip}</span>
                    </div>
                    <div style={{ display: "flex", gap: 6 }}>
                      <GhostButton icon={Check} accent="var(--emerald)" disabled={busy === `approve-${f.idx}-${m.id}`} onClick={() => onApprove(f.idx, m.id)}>Approve</GhostButton>
                      <GhostButton icon={X} accent="var(--rose)" disabled={busy === `reject-${f.idx}-${m.id}`} onClick={() => onReject(f.idx, m.id)}>Reject</GhostButton>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {f.machines.length === 0 ? (
            <EmptyState icon="🖥" title="No machines on this floor" />
          ) : (
            <div style={{ overflowX: "auto" }}>
              <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13 }}>
                <thead>
                  <tr style={{ borderBottom: "1px solid var(--border-default)" }}>
                    {["Host", "IP", "OS", "Status", "Last Seen", "Command", "Reassign", "Audit"].map((h) => (
                      <th key={h} style={{ textAlign: "left", padding: "8px 10px", fontFamily: "var(--font-mono)", fontSize: 10, color: "var(--text-muted)", letterSpacing: "0.08em", textTransform: "uppercase", whiteSpace: "nowrap" }}>{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {f.machines.map((m) => {
                    const key = `${f.idx}:${m.id}`;
                    return (
                      <tr key={m.id} style={{ borderBottom: "1px solid var(--border-subtle)" }}>
                        <td style={{ padding: "8px 10px", fontWeight: 500, whiteSpace: "nowrap" }}>{m.hostname}</td>
                        <td style={{ padding: "8px 10px", fontFamily: "var(--font-mono)", fontSize: 12, color: "var(--text-secondary)", whiteSpace: "nowrap" }}>{m.ip}</td>
                        <td style={{ padding: "8px 10px", fontSize: 11.5, color: "var(--text-muted)", maxWidth: 200, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }} title={m.os_name}>{m.os_name}</td>
                        <td style={{ padding: "8px 10px", whiteSpace: "nowrap" }}>
                          <span style={{ display: "inline-flex", alignItems: "center", gap: 6, fontSize: 12, color: m.status === "online" ? "var(--emerald)" : "var(--text-muted)" }}>
                            <span style={{ width: 6, height: 6, borderRadius: "50%", background: m.status === "online" ? "var(--emerald)" : "var(--slate)" }} />
                            {m.status}
                          </span>
                        </td>
                        <td style={{ padding: "8px 10px", fontFamily: "var(--font-mono)", fontSize: 11, color: "var(--text-muted)", whiteSpace: "nowrap" }}>{timeAgo(m.last_seen)}</td>
                        <td style={{ padding: "8px 10px", whiteSpace: "nowrap" }}>
                          <div style={{ display: "flex", gap: 5 }}>
                            <select value={cmdState[key] || "scan"} onChange={(e) => setCmdState((p) => ({ ...p, [key]: e.target.value }))} style={{ ...inputStyle, padding: "5px 8px", fontSize: 11.5 }}>
                              {COMMAND_TYPES.map((t) => <option key={t} value={t}>{t}</option>)}
                            </select>
                            <GhostButton disabled={busy === `cmd-${key}`} onClick={() => onCommand(f.idx, m.id)}>Send</GhostButton>
                          </div>
                        </td>
                        <td style={{ padding: "8px 10px", whiteSpace: "nowrap" }}>
                          <div style={{ display: "flex", gap: 5 }}>
                            <select value={reassignState[key] ?? ""} onChange={(e) => setReassignState((p) => ({ ...p, [key]: e.target.value }))} style={{ ...inputStyle, padding: "5px 8px", fontSize: 11.5 }}>
                              <option value="">To floor…</option>
                              {floors.filter((ff) => ff.idx !== f.idx).map((ff) => <option key={ff.idx} value={ff.idx}>{ff.name}</option>)}
                            </select>
                            <GhostButton icon={ArrowRightLeft} accent="var(--violet)" disabled={busy === `reassign-${key}`} onClick={() => onReassign(f.idx, m.id)}>Go</GhostButton>
                          </div>
                        </td>
                        <td style={{ padding: "8px 10px", whiteSpace: "nowrap" }}>
                          <GhostButton icon={ShieldCheck} accent="var(--emerald)" disabled={busy === `audit-${key}`} onClick={() => onAudit(f.idx, m.id)}>
                            {busy === `audit-${key}` ? "..." : "Audit"}
                          </GhostButton>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </div>
      ))}
    </div>
  );
}
