import { useEffect, useState, useCallback } from "react";
import { Plus, Trash2, Play, Pause, PenLine, X, Zap } from "lucide-react";
import { LoadingState, ErrorState, EmptyState } from "../components/States";
import { useToast } from "../components/Toast";
import {
  getFleetOverview, getSchedules, createSchedule, deleteSchedule, toggleSchedule,
  getPresets, createPreset, updatePreset, deletePreset, runPreset,
} from "../api";

// Real allowed values only — nothing here is invented.
const SCAN_TYPES = ["security", "health", "full"];
const FREQUENCIES = ["daily", "weekly"];
const PRESET_TYPES = ["scan", "boost", "clean", "fix", "rollback", "exec"];

function SectionCard({ title, action, children }) {
  return (
    <div className="card" style={{ padding: 18, marginBottom: 18 }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 14 }}>
        <h2 style={{ fontFamily: "var(--font-display)", fontSize: 15, fontWeight: 700 }}>{title}</h2>
        {action}
      </div>
      {children}
    </div>
  );
}

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

const inputStyle = {
  background: "var(--bg-input)", border: "1px solid var(--border-default)",
  borderRadius: "var(--radius-sm)", color: "var(--text-primary)",
  fontSize: 12.5, padding: "7px 10px", outline: "none",
};

// Machine picker — sourced only from real machine_scores returned by the
// existing /api/analytics/fleet aggregate. No separate machine-list route
// exists, and none is fabricated here.
function MachineSelect({ machines, value, onChange }) {
  return (
    <select value={value} onChange={(e) => onChange(e.target.value)} style={{ ...inputStyle, minWidth: 220 }}>
      <option value="">Select a machine…</option>
      {machines.map((m) => (
        <option key={`${m.floor_idx}:${m.id}`} value={`${m.floor_idx}:${m.id}`}>
          {m.hostname} — {m.floor_name} ({m.status})
        </option>
      ))}
    </select>
  );
}

export default function Automation() {
  const [machines, setMachines] = useState([]);
  const [schedules, setSchedules] = useState([]);
  const [presets, setPresets] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const showToast = useToast();

  const load = useCallback(async () => {
    try {
      const [fleetRes, schedulesRes, presetsRes] = await Promise.all([
        getFleetOverview(), getSchedules(), getPresets(),
      ]);
      setMachines(fleetRes.data.machine_scores || []);
      setSchedules(schedulesRes.data || []);
      setPresets(presetsRes.data || []);
      setError(null);
    } catch (e) {
      setError(e.response?.data?.detail || "Failed to load automation data");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  if (loading) return <div style={{ padding: "22px 26px" }}><LoadingState rows={5} /></div>;
  if (error) return <div style={{ padding: "22px 26px" }}><ErrorState message={error} /></div>;

  return (
    <div style={{ padding: "22px 26px", overflowY: "auto", height: "100%" }}>
      <div style={{ marginBottom: 20 }}>
        <h1 style={{ fontFamily: "var(--font-display)", fontSize: 22, fontWeight: 800, marginBottom: 4 }}>Automation</h1>
        <p style={{ fontSize: 13, color: "var(--text-secondary)" }}>
          Recurring scans and one-click command presets, run against real fleet machines.
        </p>
      </div>

      <SchedulesSection
        machines={machines} schedules={schedules} setSchedules={setSchedules}
        showToast={showToast} reload={load}
      />
      <PresetsSection
        machines={machines} presets={presets} setPresets={setPresets}
        showToast={showToast} reload={load}
      />
    </div>
  );
}

function SchedulesSection({ machines, schedules, setSchedules, showToast, reload }) {
  const [showForm, setShowForm] = useState(false);
  const [machineKey, setMachineKey] = useState("");
  const [scanType, setScanType] = useState("security");
  const [frequency, setFrequency] = useState("daily");
  const [hour, setHour] = useState(2);
  const [busy, setBusy] = useState(false);

  const submit = async (e) => {
    e.preventDefault();
    if (!machineKey) { showToast("Select a machine first", "error"); return; }
    const [floorIdx, machineId] = machineKey.split(":").map(Number);
    setBusy(true);
    try {
      await createSchedule(floorIdx, { machine_id: machineId, scan_type: scanType, frequency, hour: Number(hour) });
      showToast("Schedule created", "success");
      setShowForm(false);
      setMachineKey("");
      reload();
    } catch (e) {
      showToast(e.response?.data?.detail || "Failed to create schedule", "error");
    } finally {
      setBusy(false);
    }
  };

  const onToggle = async (s) => {
    try {
      await toggleSchedule(s.floor_idx, s.id);
      setSchedules((prev) => prev.map((x) => (x.id === s.id ? { ...x, is_active: !x.is_active } : x)));
      showToast(s.is_active ? "Schedule paused" : "Schedule activated", "success");
    } catch (e) {
      showToast(e.response?.data?.detail || "Failed to toggle schedule", "error");
    }
  };

  const onDelete = async (s) => {
    try {
      await deleteSchedule(s.floor_idx, s.id);
      setSchedules((prev) => prev.filter((x) => x.id !== s.id));
      showToast("Schedule deleted", "success");
    } catch (e) {
      showToast(e.response?.data?.detail || "Failed to delete schedule", "error");
    }
  };

  return (
    <SectionCard
      title="Schedules"
      action={<GhostButton icon={showForm ? X : Plus} onClick={() => setShowForm((v) => !v)}>{showForm ? "Cancel" : "New Schedule"}</GhostButton>}
    >
      {showForm && (
        <form onSubmit={submit} style={{ display: "flex", flexWrap: "wrap", gap: 10, alignItems: "center", marginBottom: 16, padding: 12, background: "var(--bg-elevated)", borderRadius: "var(--radius-md)" }}>
          <MachineSelect machines={machines} value={machineKey} onChange={setMachineKey} />
          <select value={scanType} onChange={(e) => setScanType(e.target.value)} style={inputStyle}>
            {SCAN_TYPES.map((t) => <option key={t} value={t}>{t}</option>)}
          </select>
          <select value={frequency} onChange={(e) => setFrequency(e.target.value)} style={inputStyle}>
            {FREQUENCIES.map((f) => <option key={f} value={f}>{f}</option>)}
          </select>
          <input type="number" min={0} max={23} value={hour} onChange={(e) => setHour(e.target.value)} style={{ ...inputStyle, width: 70 }} title="Hour of day (0-23)" />
          <GhostButton icon={Plus} accent="var(--emerald)" disabled={busy}>{busy ? "Creating…" : "Create"}</GhostButton>
        </form>
      )}

      {schedules.length === 0 ? (
        <EmptyState icon="⏱" title="No schedules yet" subtitle="Create one above to run recurring scans automatically" />
      ) : (
        <div style={{ overflowX: "auto" }}>
          <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13 }}>
            <thead>
              <tr style={{ borderBottom: "1px solid var(--border-default)" }}>
                {["Machine", "Floor", "Scan Type", "Frequency", "Hour", "Status", ""].map((h) => (
                  <th key={h} style={{ textAlign: "left", padding: "8px 12px", fontFamily: "var(--font-mono)", fontSize: 10, color: "var(--text-muted)", letterSpacing: "0.08em", textTransform: "uppercase" }}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {schedules.map((s) => {
                const machine = machines.find((m) => m.id === s.machine_id && m.floor_idx === s.floor_idx);
                return (
                  <tr key={`${s.floor_idx}-${s.id}`} style={{ borderBottom: "1px solid var(--border-subtle)" }}>
                    <td style={{ padding: "10px 12px", fontFamily: "var(--font-mono)", fontSize: 12 }}>{machine?.hostname ?? `Machine #${s.machine_id}`}</td>
                    <td style={{ padding: "10px 12px", color: "var(--text-muted)", fontSize: 12 }}>{s.floor_name}</td>
                    <td style={{ padding: "10px 12px" }}>{s.scan_type}</td>
                    <td style={{ padding: "10px 12px" }}>{s.frequency}</td>
                    <td style={{ padding: "10px 12px", fontFamily: "var(--font-mono)" }}>{String(s.hour).padStart(2, "0")}:00</td>
                    <td style={{ padding: "10px 12px" }}>
                      <span style={{ display: "inline-flex", alignItems: "center", gap: 6, fontSize: 12, color: s.is_active ? "var(--emerald)" : "var(--text-muted)" }}>
                        <span style={{ width: 6, height: 6, borderRadius: "50%", background: s.is_active ? "var(--emerald)" : "var(--slate)" }} />
                        {s.is_active ? "Active" : "Paused"}
                      </span>
                    </td>
                    <td style={{ padding: "10px 12px", display: "flex", gap: 6, justifyContent: "flex-end" }}>
                      <GhostButton icon={s.is_active ? Pause : Play} onClick={() => onToggle(s)}>{s.is_active ? "Pause" : "Resume"}</GhostButton>
                      <GhostButton icon={Trash2} accent="var(--rose)" onClick={() => onDelete(s)}>Delete</GhostButton>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </SectionCard>
  );
}

const emptyPresetForm = { name: "", description: "", command_type: "scan", paramsText: "{}", script: "", signature: "" };

function PresetsSection({ machines, presets, setPresets, showToast, reload }) {
  const [showForm, setShowForm] = useState(false);
  const [editingId, setEditingId] = useState(null);
  const [form, setForm] = useState(emptyPresetForm);
  const [busy, setBusy] = useState(false);
  const [runState, setRunState] = useState({}); // presetId -> { machineKey, passphrase }

  const startEdit = (p) => {
    setEditingId(p.id);
    setForm({
      name: p.name, description: p.description || "", command_type: p.command_type,
      paramsText: JSON.stringify(p.params || {}, null, 2),
      script: p.script || "", signature: p.signature || "",
    });
    setShowForm(true);
  };

  const startNew = () => { setEditingId(null); setForm(emptyPresetForm); setShowForm(true); };

  const submit = async (e) => {
    e.preventDefault();
    let params;
    try { params = JSON.parse(form.paramsText || "{}"); }
    catch { showToast("Params must be valid JSON", "error"); return; }
    if (form.command_type === "exec" && (!form.script || !form.signature)) {
      showToast("'exec' presets require both a script and a signature", "error");
      return;
    }
    const body = {
      name: form.name, description: form.description, command_type: form.command_type,
      params, script: form.script || null, signature: form.signature || null,
    };
    setBusy(true);
    try {
      if (editingId) {
        const res = await updatePreset(editingId, body);
        setPresets((prev) => prev.map((p) => (p.id === editingId ? res.data : p)));
        showToast("Preset updated", "success");
      } else {
        const res = await createPreset(body);
        setPresets((prev) => [...prev, res.data]);
        showToast("Preset created", "success");
      }
      setShowForm(false);
      setForm(emptyPresetForm);
      setEditingId(null);
    } catch (e) {
      showToast(e.response?.data?.detail || "Failed to save preset", "error");
    } finally {
      setBusy(false);
    }
  };

  const onDelete = async (p) => {
    try {
      await deletePreset(p.id);
      setPresets((prev) => prev.filter((x) => x.id !== p.id));
      showToast("Preset deleted", "success");
    } catch (e) {
      showToast(e.response?.data?.detail || "Failed to delete preset", "error");
    }
  };

  const onRun = async (p) => {
    const state = runState[p.id] || {};
    if (!state.machineKey) { showToast("Select a machine to run this preset on", "error"); return; }
    const [floor_idx, machine_id] = state.machineKey.split(":").map(Number);
    try {
      await runPreset(p.id, { floor_idx, machine_id, passphrase: state.passphrase || undefined });
      showToast(`"${p.name}" dispatched`, "success");
      reload();
    } catch (e) {
      showToast(e.response?.data?.detail || "Failed to run preset", "error");
    }
  };

  return (
    <SectionCard
      title="Command Presets"
      action={<GhostButton icon={showForm ? X : Plus} onClick={() => (showForm ? setShowForm(false) : startNew())}>{showForm ? "Cancel" : "New Preset"}</GhostButton>}
    >
      {showForm && (
        <form onSubmit={submit} style={{ display: "flex", flexDirection: "column", gap: 10, marginBottom: 16, padding: 12, background: "var(--bg-elevated)", borderRadius: "var(--radius-md)" }}>
          <div style={{ display: "flex", gap: 10, flexWrap: "wrap" }}>
            <input placeholder="Name" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} style={{ ...inputStyle, flex: "1 1 200px" }} required />
            <select value={form.command_type} onChange={(e) => setForm({ ...form, command_type: e.target.value })} style={inputStyle}>
              {PRESET_TYPES.map((t) => <option key={t} value={t}>{t}</option>)}
            </select>
          </div>
          <input placeholder="Description" value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} style={inputStyle} />
          <textarea placeholder="Params (JSON)" value={form.paramsText} onChange={(e) => setForm({ ...form, paramsText: e.target.value })} rows={3} style={{ ...inputStyle, fontFamily: "var(--font-mono)", resize: "vertical" }} />
          {form.command_type === "exec" && (
            <>
              <textarea placeholder="Script (required for exec presets)" value={form.script} onChange={(e) => setForm({ ...form, script: e.target.value })} rows={4} style={{ ...inputStyle, fontFamily: "var(--font-mono)", resize: "vertical" }} />
              <input placeholder="Signature (sign offline via tools/sign_script.py — this server never signs scripts itself)" value={form.signature} onChange={(e) => setForm({ ...form, signature: e.target.value })} style={{ ...inputStyle, fontFamily: "var(--font-mono)" }} />
            </>
          )}
          <div>
            <GhostButton icon={PenLine} accent="var(--emerald)" disabled={busy}>{busy ? "Saving…" : editingId ? "Save Changes" : "Create Preset"}</GhostButton>
          </div>
        </form>
      )}

      {presets.length === 0 ? (
        <EmptyState icon="⚡" title="No presets yet" subtitle="Create a reusable command preset above" />
      ) : (
        <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
          {presets.map((p) => (
            <div key={p.id} style={{ padding: 14, background: "var(--bg-elevated)", borderRadius: "var(--radius-md)", border: "1px solid var(--border-subtle)" }}>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: 12, flexWrap: "wrap" }}>
                <div>
                  <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 4 }}>
                    <Zap size={13} color="var(--amber)" />
                    <span style={{ fontWeight: 600, fontSize: 13.5 }}>{p.name}</span>
                    <span style={{ fontFamily: "var(--font-mono)", fontSize: 10, color: "var(--text-muted)", textTransform: "uppercase", background: "var(--bg-card)", padding: "2px 8px", borderRadius: 999 }}>{p.command_type}</span>
                  </div>
                  {p.description && <div style={{ fontSize: 12.5, color: "var(--text-secondary)" }}>{p.description}</div>}
                </div>
                <div style={{ display: "flex", gap: 6 }}>
                  <GhostButton icon={PenLine} onClick={() => startEdit(p)}>Edit</GhostButton>
                  <GhostButton icon={Trash2} accent="var(--rose)" onClick={() => onDelete(p)}>Delete</GhostButton>
                </div>
              </div>
              <div style={{ display: "flex", gap: 8, alignItems: "center", marginTop: 10, flexWrap: "wrap" }}>
                <MachineSelect
                  machines={machines}
                  value={runState[p.id]?.machineKey || ""}
                  onChange={(v) => setRunState((prev) => ({ ...prev, [p.id]: { ...prev[p.id], machineKey: v } }))}
                />
                <input
                  type="password" placeholder="Passphrase (if required)"
                  value={runState[p.id]?.passphrase || ""}
                  onChange={(e) => setRunState((prev) => ({ ...prev, [p.id]: { ...prev[p.id], passphrase: e.target.value } }))}
                  style={{ ...inputStyle, width: 180 }}
                />
                <GhostButton icon={Play} accent="var(--emerald)" onClick={() => onRun(p)}>Run</GhostButton>
              </div>
            </div>
          ))}
        </div>
      )}
    </SectionCard>
  );
}
