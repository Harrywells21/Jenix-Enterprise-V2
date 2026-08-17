import { useState, useEffect } from "react";
import { Link } from "react-router-dom";
import { getNotifyConfig, updateNotifyConfig, testNotification } from "../api";

const MONO = "'JetBrains Mono', monospace";
const FONT = "'Cabinet Grotesk', sans-serif";
const DISP = "'Syne', sans-serif";

function SettingRow({ label, desc, children }) {
  return (
    <div style={{
      display: "flex", alignItems: "center", justifyContent: "space-between",
      gap: "16px", padding: "16px 0",
      borderBottom: "1px solid rgba(255,255,255,0.04)",
    }}>
      <div style={{ flex: 1 }}>
        <div style={{ fontSize: "13px", fontWeight: 600, color: "#e8f0fe", marginBottom: "2px" }}>{label}</div>
        {desc && <div style={{ fontSize: "12px", color: "rgba(122,143,166,0.5)" }}>{desc}</div>}
      </div>
      <div style={{ flexShrink: 0 }}>{children}</div>
    </div>
  );
}

function Section({ title, children, footer }) {
  return (
    <div style={{ background: "#0c1220", border: "1px solid rgba(255,255,255,0.06)", borderRadius: "14px", padding: "20px 24px", marginBottom: "16px" }}>
      <div style={{ fontSize: "11px", color: "rgba(122,143,166,0.4)", fontFamily: MONO, letterSpacing: "0.16em", textTransform: "uppercase", marginBottom: "4px" }}>{title}</div>
      <div style={{ borderTop: "1px solid rgba(255,255,255,0.04)", marginTop: "12px" }}>
        {children}
      </div>
      {footer}
    </div>
  );
}

function TestButton({ onClick, disabled }) {
  return (
    <button onClick={onClick} disabled={disabled} style={{
      padding: "7px 14px",
      background: "rgba(56,189,248,0.06)",
      border: "1px solid rgba(56,189,248,0.15)",
      borderRadius: "8px", color: disabled ? "rgba(56,189,248,0.3)" : "#38bdf8",
      fontSize: "11px", cursor: disabled ? "not-allowed" : "pointer", fontFamily: MONO,
      transition: "all 0.15s",
    }}
      onMouseOver={e => { if (!disabled) e.currentTarget.style.background = "rgba(56,189,248,0.12)"; }}
      onMouseOut={e => { e.currentTarget.style.background = "rgba(56,189,248,0.06)"; }}
    >Send Test</button>
  );
}

export default function Settings() {
  const [toast, setToast]   = useState(null);
  const [saving, setSaving] = useState(false);
  const [testing, setTesting] = useState(null);
  const [loading, setLoading] = useState(true);
  const [form, setForm] = useState({
    slack_webhook: "", teams_webhook: "", alert_email: "",
    smtp_host: "", smtp_port: 587, smtp_user: "", smtp_pass: "",
  });
  const [status, setStatus] = useState({ smtp_configured: false, slack_configured: false, teams_configured: false });

  useEffect(() => {
    getNotifyConfig().then(r => {
      setForm(p => ({ ...p, ...r.data, smtp_pass: "" }));
      setStatus({
        smtp_configured: r.data.smtp_configured,
        slack_configured: r.data.slack_configured,
        teams_configured: r.data.teams_configured,
      });
    }).catch(() => {}).finally(() => setLoading(false));
  }, []);

  const showToast = (msg, type = "success") => {
    setToast({ msg, type });
    setTimeout(() => setToast(null), 3000);
  };

  const save = async () => {
    setSaving(true);
    try {
      await updateNotifyConfig(form);
      showToast("Notification settings saved");
    } catch (e) {
      showToast(e.response?.data?.detail || "Save failed", "error");
    } finally { setSaving(false); }
  };

  const runTest = async (type) => {
    setTesting(type);
    try {
      const r = await testNotification(type);
      showToast(r.data?.ok ? `Test ${type} notification sent` : (r.data?.message || "Test failed"), r.data?.ok ? "success" : "error");
    } catch (e) {
      showToast(e.response?.data?.detail || e.message, "error");
    } finally { setTesting(null); }
  };

  const inputStyle = {
    width: "100%", padding: "9px 13px",
    background: "#080d1a", border: "1px solid rgba(255,255,255,0.07)",
    borderRadius: "9px", color: "#e8f0fe",
    fontSize: "13px", outline: "none", fontFamily: FONT,
    transition: "border-color 0.2s",
  };

  return (
    <div style={{ fontFamily: FONT, color: "#e8f0fe", maxWidth: "800px" }}>
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
      <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", marginBottom: "20px" }}>
        <div>
          <div style={{ fontSize: "10px", color: "rgba(56,189,248,0.6)", fontFamily: MONO, letterSpacing: "0.2em", textTransform: "uppercase", marginBottom: "6px" }}>Configuration</div>
          <h1 style={{ fontFamily: DISP, fontSize: "26px", fontWeight: 800, letterSpacing: "-0.02em" }}>Settings</h1>
          <p style={{ color: "rgba(122,143,166,0.6)", fontSize: "13px", marginTop: "5px" }}>Notification and alerting configuration</p>
        </div>
        <button onClick={save} disabled={saving || loading} style={{
          padding: "10px 24px",
          background: saving ? "rgba(56,189,248,0.06)" : "linear-gradient(135deg, #38bdf8, #0ea5e9)",
          color: saving ? "rgba(56,189,248,0.3)" : "#000",
          border: "none", borderRadius: "10px",
          fontWeight: 700, fontSize: "13px",
          cursor: saving ? "not-allowed" : "pointer",
          fontFamily: FONT, letterSpacing: "0.03em",
          boxShadow: saving ? "none" : "0 4px 16px rgba(56,189,248,0.25)",
          transition: "all 0.2s",
          display: "flex", alignItems: "center", gap: "6px",
        }}>
          {saving ? (
            <><div style={{ width: "12px", height: "12px", border: "2px solid rgba(56,189,248,0.3)", borderTopColor: "#38bdf8", borderRadius: "50%", animation: "spin 0.7s linear infinite" }}/>Saving...</>
          ) : "Save Changes"}
        </button>
      </div>

      {/* Branding pointer */}
      <div style={{
        display: "flex", alignItems: "center", justifyContent: "space-between",
        padding: "14px 18px", marginBottom: "20px",
        background: "rgba(56,189,248,0.04)",
        border: "1px solid rgba(56,189,248,0.1)",
        borderRadius: "10px",
      }}>
        <span style={{ fontSize: "12px", color: "rgba(122,143,166,0.7)", fontFamily: MONO }}>
          Company branding, logo, and colors have moved to White Label Settings
        </span>
        <Link to="/whitelabel" style={{
          fontSize: "12px", color: "#38bdf8", fontFamily: MONO,
          textDecoration: "none", whiteSpace: "nowrap",
        }}>Go there →</Link>
      </div>

      {/* Alerting */}
      <Section title="Alert Channels">
        <SettingRow label="Slack Webhook" desc={status.slack_configured ? "Configured" : "Not configured"}>
          <div style={{ display: "flex", gap: "8px", alignItems: "center" }}>
            <input value={form.slack_webhook} onChange={e => setForm(p => ({ ...p, slack_webhook: e.target.value }))}
              placeholder="https://hooks.slack.com/..."
              style={{ ...inputStyle, width: "260px" }}
            />
            <TestButton onClick={() => runTest("slack")} disabled={testing === "slack" || !form.slack_webhook} />
          </div>
        </SettingRow>
        <SettingRow label="Teams Webhook" desc={status.teams_configured ? "Configured" : "Not configured"}>
          <div style={{ display: "flex", gap: "8px", alignItems: "center" }}>
            <input value={form.teams_webhook} onChange={e => setForm(p => ({ ...p, teams_webhook: e.target.value }))}
              placeholder="https://outlook.office.com/webhook/..."
              style={{ ...inputStyle, width: "260px" }}
            />
            <TestButton onClick={() => runTest("teams")} disabled={testing === "teams" || !form.teams_webhook} />
          </div>
        </SettingRow>
        <SettingRow label="Alert Email" desc="Address that receives critical alert emails">
          <input value={form.alert_email} onChange={e => setForm(p => ({ ...p, alert_email: e.target.value }))}
            placeholder="ops@yourcompany.com"
            style={{ ...inputStyle, width: "260px" }}
          />
        </SettingRow>
      </Section>

      {/* SMTP */}
      <Section title="SMTP Configuration">
        <SettingRow label="SMTP Host" desc={status.smtp_configured ? "Configured" : "Not configured"}>
          <input value={form.smtp_host} onChange={e => setForm(p => ({ ...p, smtp_host: e.target.value }))}
            placeholder="smtp.gmail.com" style={{ ...inputStyle, width: "220px" }} />
        </SettingRow>
        <SettingRow label="SMTP Port">
          <input type="number" value={form.smtp_port} onChange={e => setForm(p => ({ ...p, smtp_port: parseInt(e.target.value) || 587 }))}
            style={{ ...inputStyle, width: "100px" }} />
        </SettingRow>
        <SettingRow label="SMTP Username">
          <input value={form.smtp_user} onChange={e => setForm(p => ({ ...p, smtp_user: e.target.value }))}
            style={{ ...inputStyle, width: "220px" }} />
        </SettingRow>
        <SettingRow label="SMTP Password" desc="Leave blank to keep the current password">
          <div style={{ display: "flex", gap: "8px", alignItems: "center" }}>
            <input type="password" value={form.smtp_pass} onChange={e => setForm(p => ({ ...p, smtp_pass: e.target.value }))}
              placeholder="••••••••" style={{ ...inputStyle, width: "220px" }} />
            <TestButton onClick={() => runTest("email")} disabled={testing === "email" || !status.smtp_configured} />
          </div>
        </SettingRow>
      </Section>

      <style>{`
        @keyframes spin { to { transform: rotate(360deg); } }
        @import url('https://fonts.googleapis.com/css2?family=Syne:wght@700;800&family=JetBrains+Mono:wght@400;500&family=Cabinet+Grotesk:wght@400;500;600;700&display=swap');
      `}</style>
    </div>
  );
}
