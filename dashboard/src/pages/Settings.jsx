import { useState, useEffect } from "react";
import api from "../api";
import { useBrand } from "../context/BrandContext";

const MONO = "'JetBrains Mono', monospace";
const FONT = "'Cabinet Grotesk', sans-serif";
const DISP = "'Syne', sans-serif";

function Toggle({ checked, onChange }) {
  return (
    <div onClick={() => onChange(!checked)} style={{
      width: "40px", height: "22px", borderRadius: "11px",
      background: checked ? "#38bdf8" : "rgba(255,255,255,0.06)",
      border: `1px solid ${checked ? "#38bdf8" : "rgba(255,255,255,0.08)"}`,
      cursor: "pointer", position: "relative",
      transition: "all 0.25s cubic-bezier(0.16,1,0.3,1)",
      flexShrink: 0,
    }}>
      <div style={{
        position: "absolute", top: "2px",
        left: checked ? "20px" : "2px",
        width: "16px", height: "16px", borderRadius: "50%",
        background: checked ? "#000" : "rgba(122,143,166,0.4)",
        transition: "left 0.25s cubic-bezier(0.16,1,0.3,1)",
        boxShadow: "0 1px 4px rgba(0,0,0,0.3)",
      }}/>
    </div>
  );
}

function SettingRow({ label, desc, children, danger = false }) {
  return (
    <div style={{
      display: "flex", alignItems: "center", justifyContent: "space-between",
      gap: "16px", padding: "16px 0",
      borderBottom: "1px solid rgba(255,255,255,0.04)",
    }}>
      <div style={{ flex: 1 }}>
        <div style={{ fontSize: "13px", fontWeight: 600, color: danger ? "#f43f5e" : "#e8f0fe", marginBottom: "2px" }}>{label}</div>
        {desc && <div style={{ fontSize: "12px", color: "rgba(122,143,166,0.5)" }}>{desc}</div>}
      </div>
      <div style={{ flexShrink: 0 }}>{children}</div>
    </div>
  );
}

function Section({ title, children }) {
  return (
    <div style={{ background: "#0c1220", border: "1px solid rgba(255,255,255,0.06)", borderRadius: "14px", padding: "20px 24px", marginBottom: "16px" }}>
      <div style={{ fontSize: "11px", color: "rgba(122,143,166,0.4)", fontFamily: MONO, letterSpacing: "0.16em", textTransform: "uppercase", marginBottom: "4px" }}>{title}</div>
      <div style={{ borderTop: "1px solid rgba(255,255,255,0.04)", marginTop: "12px" }}>
        {children}
      </div>
    </div>
  );
}

const ACCENT_COLORS = [
  { name: "Cyan",    value: "#38bdf8" },
  { name: "Emerald", value: "#10b981" },
  { name: "Violet",  value: "#8b5cf6" },
  { name: "Rose",    value: "#f43f5e" },
  { name: "Amber",   value: "#f59e0b" },
  { name: "Indigo",  value: "#6366f1" },
];

export default function Settings() {
  const { brand, setBrand } = useBrand();
  const [toast, setToast]   = useState(null);
  const [saving, setSaving] = useState(false);
  const [form, setForm] = useState({
    company_name: "JENIX Enterprise",
    logo_text: "JENIX",
    logo_subtext: "Enterprise v2.0",
    primary_color: "#38bdf8",
    alert_email: true,
    alert_slack: false,
    alert_cpu_threshold: 85,
    alert_ram_threshold: 90,
    alert_disk_threshold: 95,
    auto_remediate: false,
    scan_interval: "24h",
    data_retention: "90",
    mfa_required: false,
    session_timeout: "8h",
  });

  useEffect(() => {
    api.get("/api/brand").then(r => {
      if (r.data) setForm(p => ({ ...p, ...r.data }));
    }).catch(() => {});
  }, []);

  const showToast = (msg, type = "success") => {
    setToast({ msg, type });
    setTimeout(() => setToast(null), 3000);
  };

  const save = async () => {
    setSaving(true);
    try {
      await api.put("/api/brand", {
        company_name: form.company_name,
        logo_text: form.logo_text,
        logo_subtext: form.logo_subtext,
        primary_color: form.primary_color,
      });
      if (setBrand) setBrand({ ...brand, ...form });
      showToast("Settings saved successfully");
    } catch (e) {
      showToast(e.response?.data?.detail || "Save failed", "error");
    } finally { setSaving(false); }
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
      <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", marginBottom: "28px" }}>
        <div>
          <div style={{ fontSize: "10px", color: "rgba(56,189,248,0.6)", fontFamily: MONO, letterSpacing: "0.2em", textTransform: "uppercase", marginBottom: "6px" }}>Configuration</div>
          <h1 style={{ fontFamily: DISP, fontSize: "26px", fontWeight: 800, letterSpacing: "-0.02em" }}>Settings</h1>
          <p style={{ color: "rgba(122,143,166,0.6)", fontSize: "13px", marginTop: "5px" }}>Platform configuration and preferences</p>
        </div>
        <button onClick={save} disabled={saving} style={{
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

      {/* Branding */}
      <Section title="Branding">
        <SettingRow label="Platform Name" desc="Displayed in the sidebar and browser tab">
          <input value={form.company_name} onChange={e => setForm(p => ({ ...p, company_name: e.target.value }))}
            style={{ ...inputStyle, width: "220px" }}
            onFocus={e => e.target.style.borderColor = "rgba(56,189,248,0.4)"}
            onBlur={e => e.target.style.borderColor = "rgba(255,255,255,0.07)"}
          />
        </SettingRow>
        <SettingRow label="Logo Text" desc="Short brand identifier shown in the header">
          <input value={form.logo_text} onChange={e => setForm(p => ({ ...p, logo_text: e.target.value }))}
            style={{ ...inputStyle, width: "160px" }}
            onFocus={e => e.target.style.borderColor = "rgba(56,189,248,0.4)"}
            onBlur={e => e.target.style.borderColor = "rgba(255,255,255,0.07)"}
          />
        </SettingRow>
        <SettingRow label="Accent Color" desc="Primary brand color used throughout the interface">
          <div style={{ display: "flex", gap: "8px", alignItems: "center" }}>
            {ACCENT_COLORS.map(({ name, value }) => (
              <div key={value}
                title={name}
                onClick={() => setForm(p => ({ ...p, primary_color: value }))}
                style={{
                  width: "24px", height: "24px", borderRadius: "6px",
                  background: value, cursor: "pointer",
                  border: form.primary_color === value ? "2px solid #fff" : "2px solid transparent",
                  boxShadow: form.primary_color === value ? `0 0 10px ${value}60` : "none",
                  transition: "all 0.2s",
                  transform: form.primary_color === value ? "scale(1.15)" : "scale(1)",
                }}
              />
            ))}
            <input type="color" value={form.primary_color} onChange={e => setForm(p => ({ ...p, primary_color: e.target.value }))}
              style={{ width: "24px", height: "24px", borderRadius: "6px", border: "none", cursor: "pointer", padding: 0, background: "none" }}
            />
          </div>
        </SettingRow>
      </Section>

      {/* Alerts */}
      <Section title="Alerting">
        <SettingRow label="Email Notifications" desc="Send alerts to configured email addresses">
          <Toggle checked={form.alert_email} onChange={v => setForm(p => ({ ...p, alert_email: v }))} />
        </SettingRow>
        <SettingRow label="Slack Webhook" desc="Post alerts to a Slack channel">
          <Toggle checked={form.alert_slack} onChange={v => setForm(p => ({ ...p, alert_slack: v }))} />
        </SettingRow>
        <SettingRow label="CPU Alert Threshold" desc="Alert when CPU exceeds this percentage">
          <div style={{ display: "flex", alignItems: "center", gap: "10px" }}>
            <input type="range" min={50} max={99} value={form.alert_cpu_threshold}
              onChange={e => setForm(p => ({ ...p, alert_cpu_threshold: parseInt(e.target.value) }))}
              style={{ width: "100px", accentColor: "#38bdf8" }}
            />
            <span style={{ fontFamily: MONO, fontSize: "13px", color: "#38bdf8", minWidth: "40px" }}>{form.alert_cpu_threshold}%</span>
          </div>
        </SettingRow>
        <SettingRow label="Disk Alert Threshold" desc="Alert when disk usage exceeds this percentage">
          <div style={{ display: "flex", alignItems: "center", gap: "10px" }}>
            <input type="range" min={70} max={99} value={form.alert_disk_threshold}
              onChange={e => setForm(p => ({ ...p, alert_disk_threshold: parseInt(e.target.value) }))}
              style={{ width: "100px", accentColor: "#38bdf8" }}
            />
            <span style={{ fontFamily: MONO, fontSize: "13px", color: "#38bdf8", minWidth: "40px" }}>{form.alert_disk_threshold}%</span>
          </div>
        </SettingRow>
        <SettingRow label="Auto-Remediation" desc="Automatically run fixes when critical thresholds are exceeded">
          <Toggle checked={form.auto_remediate} onChange={v => setForm(p => ({ ...p, auto_remediate: v }))} />
        </SettingRow>
      </Section>

      {/* Security */}
      <Section title="Security">
        <SettingRow label="Require MFA" desc="Enforce two-factor authentication for all users">
          <Toggle checked={form.mfa_required} onChange={v => setForm(p => ({ ...p, mfa_required: v }))} />
        </SettingRow>
        <SettingRow label="Session Timeout" desc="Automatically log out inactive sessions">
          <select value={form.session_timeout} onChange={e => setForm(p => ({ ...p, session_timeout: e.target.value }))}
            style={{ ...inputStyle, width: "120px" }}>
            {["1h", "4h", "8h", "24h", "never"].map(v => <option key={v} value={v}>{v}</option>)}
          </select>
        </SettingRow>
        <SettingRow label="Data Retention" desc="How long to keep audit logs and metrics">
          <select value={form.data_retention} onChange={e => setForm(p => ({ ...p, data_retention: e.target.value }))}
            style={{ ...inputStyle, width: "120px" }}>
            {[["30", "30 days"], ["90", "90 days"], ["365", "1 year"], ["0", "Forever"]].map(([v, l]) => <option key={v} value={v}>{l}</option>)}
          </select>
        </SettingRow>
      </Section>

      {/* API */}
      <Section title="API Access">
        <SettingRow label="API Token" desc="Use this token to authenticate API requests">
          <div style={{ display: "flex", gap: "8px" }}>
            <input type="password" value="jnx_live_••••••••••••••••"
              readOnly
              style={{ ...inputStyle, width: "200px", fontFamily: MONO, fontSize: "12px" }}
            />
            <button style={{
              padding: "9px 14px", background: "rgba(56,189,248,0.06)",
              border: "1px solid rgba(56,189,248,0.15)", borderRadius: "9px",
              color: "#38bdf8", fontSize: "12px", cursor: "pointer", fontFamily: MONO,
              transition: "all 0.15s",
            }}
              onMouseOver={e => e.currentTarget.style.background = "rgba(56,189,248,0.12)"}
              onMouseOut={e => e.currentTarget.style.background = "rgba(56,189,248,0.06)"}
            >Regenerate</button>
          </div>
        </SettingRow>
      </Section>

      {/* Danger zone */}
      <Section title="Danger Zone">
        <SettingRow label="Reset All Alerts" desc="Clear all active alerts from the database" danger>
          <button style={{
            padding: "8px 16px", background: "rgba(244,63,94,0.06)",
            border: "1px solid rgba(244,63,94,0.2)", borderRadius: "8px",
            color: "#f43f5e", fontSize: "12px", cursor: "pointer", fontFamily: FONT,
            transition: "all 0.15s",
          }}
            onMouseOver={e => e.currentTarget.style.background = "rgba(244,63,94,0.12)"}
            onMouseOut={e => e.currentTarget.style.background = "rgba(244,63,94,0.06)"}
          >Reset Alerts</button>
        </SettingRow>
        <SettingRow label="Purge Audit Log" desc="Permanently delete all audit records" danger>
          <button style={{
            padding: "8px 16px", background: "rgba(244,63,94,0.06)",
            border: "1px solid rgba(244,63,94,0.2)", borderRadius: "8px",
            color: "#f43f5e", fontSize: "12px", cursor: "pointer", fontFamily: FONT,
            transition: "all 0.15s",
          }}
            onMouseOver={e => e.currentTarget.style.background = "rgba(244,63,94,0.12)"}
            onMouseOut={e => e.currentTarget.style.background = "rgba(244,63,94,0.06)"}
          >Purge Logs</button>
        </SettingRow>
      </Section>

      <style>{`
        @keyframes spin { to { transform: rotate(360deg); } }
        @import url('https://fonts.googleapis.com/css2?family=Syne:wght@700;800&family=JetBrains+Mono:wght@400;500&family=Cabinet+Grotesk:wght@400;500;600;700&display=swap');
        select option { background: #0c1220; }
      `}</style>
    </div>
  );
}
