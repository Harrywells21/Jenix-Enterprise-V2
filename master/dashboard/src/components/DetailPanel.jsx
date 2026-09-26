import { useState } from "react";
import { X, Check, Clock, UserPlus, Search, Wrench, ShieldCheck } from "lucide-react";
import { SeverityBadge, StatusBadge } from "./Badges";
import { useToast } from "./Toast";
import { setAlertStatus, assignAlertToMe, dispatchCommand } from "../api";

const RECOMMENDATIONS = {
  CRITICAL: "Immediate investigation recommended. Confirm the metric mentioned in the message before applying an automated fix.",
  WARNING: "Monitor and confirm this trend continues. Acknowledge once reviewed; escalate if it worsens.",
};

// Real fleet commands only — "offline" and "port" alert types have no
// obviously-correct automated fix yet, so Run Fix is disabled for those
// rather than guessing a command that might not apply.
const FIX_COMMAND_BY_TYPE = { disk: "clean", cpu: "boost", ram: "boost" };

function ActionButton({ icon: Icon, label, onClick, accent = "var(--cyan)", disabled = false }) {
  return (
    <button
      onClick={onClick}
      disabled={disabled}
      style={{
        display: "flex", alignItems: "center", gap: 7,
        padding: "8px 12px", borderRadius: "var(--radius-sm)",
        background: "transparent", border: `1px solid var(--border-default)`,
        color: disabled ? "var(--text-muted)" : "var(--text-secondary)", fontSize: 12, fontWeight: 500,
        opacity: disabled ? 0.5 : 1,
        cursor: disabled ? "not-allowed" : "pointer",
        transition: "all 0.15s",
      }}
      onMouseEnter={(e) => { if (!disabled) { e.currentTarget.style.borderColor = accent; e.currentTarget.style.color = accent; } }}
      onMouseLeave={(e) => { if (!disabled) { e.currentTarget.style.borderColor = "var(--border-default)"; e.currentTarget.style.color = "var(--text-secondary)"; } }}
    >
      <Icon size={13} /> {label}
    </button>
  );
}

export default function DetailPanel({ signal, onClose, onStatusChange, onAssigned }) {
  const showToast = useToast();
  const [busy, setBusy] = useState(false);
  if (!signal) return null;

  const runStatusChange = async (label, newStatus) => {
    setBusy(true);
    try {
      await setAlertStatus(signal.floor_idx, signal.id, newStatus);
      onStatusChange(signal.id, newStatus);
      showToast(`${label} — ${signal.title}`, "success");
    } catch (e) {
      showToast(e.response?.data?.detail || `Failed to ${label.toLowerCase()}`, "error");
    } finally {
      setBusy(false);
    }
  };

  const runAssign = async () => {
    setBusy(true);
    try {
      const res = await assignAlertToMe(signal.floor_idx, signal.id);
      onAssigned(signal.id, res.data.assigned_to_user_id);
      showToast(`Assigned to you — ${signal.title}`, "success");
    } catch (e) {
      showToast(e.response?.data?.detail || "Failed to assign", "error");
    } finally {
      setBusy(false);
    }
  };

  const runFix = async () => {
    const cmdType = FIX_COMMAND_BY_TYPE[signal.type];
    if (!cmdType) {
      showToast(`No automated fix available for "${signal.type}" alerts yet`, "info");
      return;
    }
    setBusy(true);
    try {
      await dispatchCommand(signal.floor_idx, signal.machine_id, cmdType);
      showToast(`${cmdType} dispatched to ${signal.hostname}`, "success");
    } catch (e) {
      showToast(e.response?.data?.detail || "Failed to dispatch fix", "error");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div style={{
      width: 360, minWidth: 360, height: "100%",
      background: "var(--bg-surface)",
      borderLeft: "1px solid var(--border-default)",
      display: "flex", flexDirection: "column",
      animation: "slideIn 0.2s var(--ease-out) both",
    }}>
      <div style={{ padding: "16px 18px", borderBottom: "1px solid var(--border-subtle)" }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: 10 }}>
          <SeverityBadge severity={signal.severity} />
          <button onClick={onClose} style={{ background: "none", border: "none", color: "var(--text-muted)", padding: 2 }}>
            <X size={16} />
          </button>
        </div>
        <div style={{ fontFamily: "var(--font-display)", fontWeight: 700, fontSize: 15, lineHeight: 1.35 }}>
          {signal.title}
        </div>
        <div style={{ marginTop: 8 }}><StatusBadge status={signal.status} /></div>
      </div>

      <div style={{ flex: 1, overflowY: "auto", padding: "16px 18px", display: "flex", flexDirection: "column", gap: 18 }}>
        <div>
          <SectionLabel>Message</SectionLabel>
          <p style={{ fontSize: 13, color: "var(--text-secondary)", lineHeight: 1.55 }}>{signal.title}</p>
        </div>

        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
          <Field label="Detected" value={new Date(signal.timestamp).toLocaleString()} />
          <Field label="Type" value={signal.type} mono />
          <Field label="Host" value={signal.hostname} mono />
          <Field label="Floor" value={signal.floor_name} />
          <Field label="Assigned to" value={signal.assigned_to || "Unassigned"} />
          <Field label="Read" value={signal.is_read ? "Yes" : "No"} />
        </div>

        <div>
          <SectionLabel>Recommended Action</SectionLabel>
          <div style={{
            display: "flex", gap: 8, padding: 12,
            background: "var(--cyan-dim)", border: "1px solid var(--border-accent)",
            borderRadius: "var(--radius-md)", fontSize: 12.5, color: "var(--text-secondary)", lineHeight: 1.5,
          }}>
            <ShieldCheck size={15} style={{ flexShrink: 0, marginTop: 1, color: "var(--cyan)" }} />
            {RECOMMENDATIONS[signal.severity] || RECOMMENDATIONS.WARNING}
          </div>
        </div>

        {/* Only real known events — no fabricated history entries */}
        <div>
          <SectionLabel>History</SectionLabel>
          <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
            <div style={{ fontSize: 12, color: "var(--text-muted)", display: "flex", justifyContent: "space-between" }}>
              <span>Alert created</span>
              <span style={{ fontFamily: "var(--font-mono)", fontSize: 10.5 }}>{new Date(signal.timestamp).toLocaleString()}</span>
            </div>
            {signal.updated_at && (
              <div style={{ fontSize: 12, color: "var(--text-muted)", display: "flex", justifyContent: "space-between" }}>
                <span>Last updated</span>
                <span style={{ fontFamily: "var(--font-mono)", fontSize: 10.5 }}>{new Date(signal.updated_at).toLocaleString()}</span>
              </div>
            )}
          </div>
        </div>
      </div>

      <div style={{ padding: 14, borderTop: "1px solid var(--border-subtle)", display: "flex", flexWrap: "wrap", gap: 8 }}>
        <ActionButton icon={Check} label="Acknowledge" accent="var(--cyan)" disabled={busy} onClick={() => runStatusChange("Acknowledged", "acknowledged")} />
        <ActionButton icon={ShieldCheck} label="Resolve" accent="var(--emerald)" disabled={busy} onClick={() => runStatusChange("Resolved", "resolved")} />
        <ActionButton icon={Clock} label="Snooze" accent="var(--amber)" disabled={busy} onClick={() => runStatusChange("Snoozed", "snoozed")} />
        <ActionButton icon={Search} label="Investigate" accent="var(--cyan)" disabled={busy} onClick={() => runStatusChange("Investigating", "investigating")} />
        <ActionButton icon={UserPlus} label="Assign to Me" accent="var(--violet)" disabled={busy} onClick={runAssign} />
        <ActionButton
          icon={Wrench} label="Run Fix" accent="var(--rose)"
          disabled={busy || !FIX_COMMAND_BY_TYPE[signal.type]}
          onClick={runFix}
        />
      </div>
    </div>
  );
}

function SectionLabel({ children }) {
  return (
    <div style={{
      fontFamily: "var(--font-mono)", fontSize: 10, color: "var(--text-muted)",
      letterSpacing: "0.1em", textTransform: "uppercase", marginBottom: 8,
    }}>{children}</div>
  );
}

function Field({ label, value, mono }) {
  return (
    <div>
      <div style={{ fontSize: 10.5, color: "var(--text-muted)", marginBottom: 2 }}>{label}</div>
      <div style={{ fontSize: 12.5, color: "var(--text-primary)", fontFamily: mono ? "var(--font-mono)" : "inherit" }}>{value}</div>
    </div>
  );
}
