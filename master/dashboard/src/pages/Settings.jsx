import { useEffect, useState, useCallback } from "react";
import { Plus, Trash2, Save, RotateCcw, Database, Upload, Building2, Bell, Send, CheckCircle2 } from "lucide-react";
import { LoadingState, ErrorState, EmptyState } from "../components/States";
import { useToast } from "../components/Toast";
import {
  getAggregate,
  getWhitelabel, updateWhitelabel, resetWhitelabel,
  getBackups, createBackup, restoreBackup, backupAllFloors,
  getSites, createSite, deleteSite,
  getNotifications, updateNotifications, testNotification,
} from "../api";

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

function FloorSelect({ floors, value, onChange }) {
  return (
    <select value={value} onChange={(e) => onChange(e.target.value)} style={{ ...inputStyle, minWidth: 200 }}>
      <option value="">Select a floor…</option>
      {floors.map((f) => (
        <option key={f.idx} value={f.idx}>{f.name}</option>
      ))}
    </select>
  );
}

export default function Settings() {
  const [floors, setFloors] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const showToast = useToast();

  const load = useCallback(async () => {
    try {
      const aggRes = await getAggregate();
      setFloors((aggRes.data.floors || []).map((f, idx) => ({ idx, name: f.name })));
      setError(null);
    } catch (e) {
      setError(e.response?.data?.detail || "Failed to load floor list");
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
        <h1 style={{ fontFamily: "var(--font-display)", fontSize: 22, fontWeight: 800, marginBottom: 4 }}>Settings</h1>
        <p style={{ fontSize: 13, color: "var(--text-secondary)" }}>
          Branding, backups, and site management across the real fleet.
        </p>
      </div>

      <WhitelabelSection showToast={showToast} />
      <NotificationsSection showToast={showToast} />
      <BackupSection floors={floors} showToast={showToast} />
      <SitesSection floors={floors} showToast={showToast} />
    </div>
  );
}

// ============================================================
// Whitelabel — master-authoritative, save pushes to both floors
// ============================================================
function WhitelabelSection({ showToast }) {
  const [config, setConfig] = useState(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    try {
      const res = await getWhitelabel();
      setConfig(res.data);
    } catch (e) {
      showToast(e.response?.data?.detail || "Failed to load whitelabel config", "error");
    } finally {
      setLoading(false);
    }
  }, [showToast]);

  useEffect(() => { load(); }, [load]);

  const field = (key) => (e) => {
    const val = e.target.type === "checkbox" ? e.target.checked : e.target.value;
    setConfig((prev) => ({ ...prev, [key]: val }));
  };

  const save = async (e) => {
    e.preventDefault();
    setBusy(true);
    try {
      const res = await updateWhitelabel(config);
      showToast("Whitelabel saved to both floors", "success");
      if (res.data?.results) {
        const failed = res.data.results.filter((r) => !r.ok);
        if (failed.length) showToast(`Warning: failed on ${failed.map((f) => f.floor_name).join(", ")}`, "error");
      }
    } catch (err) {
      const detail = err.response?.data?.detail;
      if (detail?.results) {
        const failed = detail.results.filter((r) => !r.ok);
        showToast(`Partial failure: ${failed.map((f) => `${f.floor_name} (${f.error})`).join("; ")}`, "error");
      } else {
        showToast(detail || "Failed to save whitelabel config", "error");
      }
    } finally {
      setBusy(false);
    }
  };

  const reset = async () => {
    setBusy(true);
    try {
      await resetWhitelabel();
      showToast("Whitelabel reset on both floors", "success");
      load();
    } catch (e) {
      showToast(e.response?.data?.detail || "Failed to reset whitelabel", "error");
    } finally {
      setBusy(false);
    }
  };

  if (loading || !config) return <SectionCard title="Whitelabel"><LoadingState rows={2} /></SectionCard>;

  const textField = (key, label, type = "text") => (
    <label style={{ display: "flex", flexDirection: "column", gap: 4, fontSize: 12, color: "var(--text-muted)" }}>
      {label}
      <input type={type} value={config[key] ?? ""} onChange={field(key)} style={inputStyle} />
    </label>
  );

  return (
    <SectionCard
      title="Whitelabel"
      action={<GhostButton icon={RotateCcw} accent="var(--rose)" onClick={reset} disabled={busy}>Reset to Default</GhostButton>}
    >
      <form onSubmit={save} style={{ display: "flex", flexDirection: "column", gap: 14 }}>
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(200px, 1fr))", gap: 12 }}>
          {textField("company_name", "Company Name")}
          {textField("logo_text", "Logo Text")}
          {textField("logo_subtext", "Logo Subtext")}
          {textField("dashboard_title", "Dashboard Title")}
          {textField("support_email", "Support Email")}
          {textField("support_url", "Support URL")}
          {textField("favicon_emoji", "Favicon Emoji")}
          {textField("primary_color", "Primary Color", "color")}
          {textField("accent_color", "Accent Color", "color")}
          {textField("sidebar_bg", "Sidebar Background", "color")}
          {textField("main_bg", "Main Background", "color")}
          {textField("card_bg", "Card Background", "color")}
        </div>
        <label style={{ display: "flex", alignItems: "center", gap: 8, fontSize: 12.5 }}>
          <input type="checkbox" checked={!!config.powered_by} onChange={field("powered_by")} />
          Show "Powered by JENIX" footer
        </label>
        <div>
          <GhostButton icon={Save} accent="var(--emerald)" disabled={busy}>{busy ? "Saving…" : "Save to Both Floors"}</GhostButton>
        </div>
      </form>
    </SectionCard>
  );
}

// ============================================================
// Notifications — master-authoritative, save pushes to both floors
// ============================================================
function NotificationsSection({ showToast }) {
  const [config, setConfig] = useState(null);
  const [smtpPass, setSmtpPass] = useState("");
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [testBusy, setTestBusy] = useState(null);

  const load = useCallback(async () => {
    try {
      const res = await getNotifications();
      setConfig(res.data);
      setSmtpPass("");
    } catch (e) {
      showToast(e.response?.data?.detail || "Failed to load notification config", "error");
    } finally {
      setLoading(false);
    }
  }, [showToast]);

  useEffect(() => { load(); }, [load]);

  const field = (key) => (e) => setConfig((prev) => ({ ...prev, [key]: e.target.value }));

  const save = async (e) => {
    e.preventDefault();
    setBusy(true);
    try {
      const { smtp_configured, slack_configured, teams_configured, ...editable } = config;
      const body = { ...editable };
      if (smtpPass) body.smtp_pass = smtpPass;
      const res = await updateNotifications(body);
      showToast("Notification settings saved to both floors", "success");
      if (res.data?.results) {
        const failed = res.data.results.filter((r) => !r.ok);
        if (failed.length) showToast(`Warning: failed on ${failed.map((f) => f.floor_name).join(", ")}`, "error");
      }
      load();
    } catch (err) {
      const detail = err.response?.data?.detail;
      if (detail?.results) {
        const failed = detail.results.filter((r) => !r.ok);
        showToast(`Partial failure: ${failed.map((f) => `${f.floor_name} (${f.error})`).join("; ")}`, "error");
      } else {
        showToast(detail || "Failed to save notification settings", "error");
      }
    } finally {
      setBusy(false);
    }
  };

  const runTest = async (type) => {
    setTestBusy(type);
    try {
      await testNotification(type);
      showToast(`Test ${type} notification sent`, "success");
    } catch (e) {
      showToast(e.response?.data?.detail || `Test ${type} notification failed`, "error");
    } finally {
      setTestBusy(null);
    }
  };

  if (loading || !config) return <SectionCard title="Notifications"><LoadingState rows={2} /></SectionCard>;

  const textField = (key, label, type = "text") => (
    <label style={{ display: "flex", flexDirection: "column", gap: 4, fontSize: 12, color: "var(--text-muted)" }}>
      {label}
      <input type={type} value={config[key] ?? ""} onChange={field(key)} style={inputStyle} />
    </label>
  );

  const configBadge = (ok) => (
    <span style={{ display: "inline-flex", alignItems: "center", gap: 4, fontSize: 11, color: ok ? "var(--emerald)" : "var(--text-muted)" }}>
      {ok && <CheckCircle2 size={12} />} {ok ? "Configured" : "Not configured"}
    </span>
  );

  return (
    <SectionCard title="Notifications">
      <form onSubmit={save} style={{ display: "flex", flexDirection: "column", gap: 18 }}>
        <div>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 8 }}>
            <span style={{ fontSize: 12.5, fontWeight: 600 }}>Slack</span>
            {configBadge(config.slack_configured)}
          </div>
          <div style={{ display: "flex", gap: 10, alignItems: "flex-end" }}>
            <div style={{ flex: 1 }}>{textField("slack_webhook", "Webhook URL")}</div>
            <GhostButton icon={Send} onClick={() => runTest("slack")} disabled={testBusy === "slack"}>{testBusy === "slack" ? "Sending…" : "Test"}</GhostButton>
          </div>
        </div>

        <div>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 8 }}>
            <span style={{ fontSize: 12.5, fontWeight: 600 }}>Teams</span>
            {configBadge(config.teams_configured)}
          </div>
          <div style={{ display: "flex", gap: 10, alignItems: "flex-end" }}>
            <div style={{ flex: 1 }}>{textField("teams_webhook", "Webhook URL")}</div>
            <GhostButton icon={Send} onClick={() => runTest("teams")} disabled={testBusy === "teams"}>{testBusy === "teams" ? "Sending…" : "Test"}</GhostButton>
          </div>
        </div>

        <div>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 8 }}>
            <span style={{ fontSize: 12.5, fontWeight: 600 }}>Email / SMTP</span>
            {configBadge(config.smtp_configured)}
          </div>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(200px, 1fr))", gap: 12, marginBottom: 10 }}>
            {textField("alert_email", "Alert Email")}
            {textField("smtp_host", "SMTP Host")}
            {textField("smtp_port", "SMTP Port")}
            {textField("smtp_user", "SMTP User")}
            <label style={{ display: "flex", flexDirection: "column", gap: 4, fontSize: 12, color: "var(--text-muted)" }}>
              SMTP Password
              <input type="password" value={smtpPass} onChange={(e) => setSmtpPass(e.target.value)} placeholder={config.smtp_configured ? "Leave blank to keep existing" : ""} style={inputStyle} />
            </label>
          </div>
          <GhostButton icon={Send} onClick={() => runTest("email")} disabled={testBusy === "email"}>{testBusy === "email" ? "Sending…" : "Test Email"}</GhostButton>
        </div>

        <div>
          <GhostButton icon={Bell} accent="var(--emerald)" disabled={busy}>{busy ? "Saving…" : "Save to Both Floors"}</GhostButton>
        </div>
      </form>
    </SectionCard>
  );
}

// ============================================================
// Backup — aggregate + per-floor action, matches Schedules/Presets
// ============================================================
function BackupSection({ floors, showToast }) {
  const [backups, setBackups] = useState([]);
  const [loading, setLoading] = useState(true);
  const [floorKey, setFloorKey] = useState("");
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    try {
      const res = await getBackups();
      setBackups(res.data || []);
    } catch (e) {
      showToast(e.response?.data?.detail || "Failed to load backups", "error");
    } finally {
      setLoading(false);
    }
  }, [showToast]);

  useEffect(() => { load(); }, [load]);

  const onCreateOne = async () => {
    if (!floorKey) { showToast("Select a floor first", "error"); return; }
    setBusy(true);
    try {
      await createBackup(Number(floorKey));
      showToast("Backup created", "success");
      load();
    } catch (e) {
      showToast(e.response?.data?.detail || "Failed to create backup", "error");
    } finally {
      setBusy(false);
    }
  };

  const onBackupAll = async () => {
    setBusy(true);
    try {
      const res = await backupAllFloors();
      const failed = (res.data.results || []).filter((r) => !r.ok);
      if (failed.length) {
        showToast(`Backed up ${res.data.results.length - failed.length}/${res.data.results.length} floors — failed: ${failed.map((f) => f.floor_name).join(", ")}`, "error");
      } else {
        showToast(`Backed up all ${res.data.results.length} floors`, "success");
      }
      load();
    } catch (e) {
      showToast(e.response?.data?.detail || "Failed to back up floors", "error");
    } finally {
      setBusy(false);
    }
  };

  const onRestore = async (b) => {
    if (!window.confirm(`Restore ${b.floor_name} to ${b.filename}? This overwrites that floor's current database. A safety backup of the current state is taken automatically first.`)) return;
    try {
      await restoreBackup(b.floor_idx, b.filename);
      showToast(`${b.floor_name} restored from ${b.filename}`, "success");
      load();
    } catch (e) {
      showToast(e.response?.data?.detail || "Failed to restore backup", "error");
    }
  };

  return (
    <SectionCard
      title="Backup"
      action={<GhostButton icon={Database} accent="var(--emerald)" onClick={onBackupAll} disabled={busy}>{busy ? "Working…" : "Backup All Floors"}</GhostButton>}
    >
      <div style={{ display: "flex", gap: 10, alignItems: "center", marginBottom: 16 }}>
        <FloorSelect floors={floors} value={floorKey} onChange={setFloorKey} />
        <GhostButton icon={Plus} onClick={onCreateOne} disabled={busy}>Backup This Floor</GhostButton>
      </div>

      {loading ? <LoadingState rows={3} /> : backups.length === 0 ? (
        <EmptyState icon="💾" title="No backups yet" subtitle="Create one above" />
      ) : (
        <div style={{ overflowX: "auto" }}>
          <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13 }}>
            <thead>
              <tr style={{ borderBottom: "1px solid var(--border-default)" }}>
                {["Filename", "Floor", "Size", "Created", ""].map((h) => (
                  <th key={h} style={{ textAlign: "left", padding: "8px 12px", fontFamily: "var(--font-mono)", fontSize: 10, color: "var(--text-muted)", letterSpacing: "0.08em", textTransform: "uppercase" }}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {backups.map((b) => (
                <tr key={`${b.floor_idx}-${b.filename}`} style={{ borderBottom: "1px solid var(--border-subtle)" }}>
                  <td style={{ padding: "10px 12px", fontFamily: "var(--font-mono)", fontSize: 12 }}>{b.filename}</td>
                  <td style={{ padding: "10px 12px", color: "var(--text-muted)" }}>{b.floor_name}</td>
                  <td style={{ padding: "10px 12px" }}>{b.size_kb.toLocaleString()} KB</td>
                  <td style={{ padding: "10px 12px", fontFamily: "var(--font-mono)", fontSize: 12 }}>{new Date(b.created).toLocaleString()}</td>
                  <td style={{ padding: "10px 12px", textAlign: "right" }}>
                    <GhostButton icon={Upload} onClick={() => onRestore(b)}>Restore</GhostButton>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </SectionCard>
  );
}

// ============================================================
// Sites — real consolidated list, actions floor-scoped
// ============================================================
function SitesSection({ floors, showToast }) {
  const [sites, setSites] = useState([]);
  const [loading, setLoading] = useState(true);
  const [showForm, setShowForm] = useState(false);
  const [floorKey, setFloorKey] = useState("");
  const [name, setName] = useState("");
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    try {
      const res = await getSites();
      setSites(res.data || []);
    } catch (e) {
      showToast(e.response?.data?.detail || "Failed to load sites", "error");
    } finally {
      setLoading(false);
    }
  }, [showToast]);

  useEffect(() => { load(); }, [load]);

  const submit = async (e) => {
    e.preventDefault();
    if (!floorKey) { showToast("Select a floor first", "error"); return; }
    setBusy(true);
    try {
      await createSite(Number(floorKey), name);
      showToast("Site created", "success");
      setShowForm(false);
      setName("");
      load();
    } catch (e) {
      showToast(e.response?.data?.detail || "Failed to create site", "error");
    } finally {
      setBusy(false);
    }
  };

  const onDelete = async (s) => {
    if (!window.confirm(`Delete site "${s.name}"? Its ${s.machine_count} machine(s) will be unassigned, not deleted.`)) return;
    try {
      await deleteSite(s.floor_idx, s.id);
      setSites((prev) => prev.filter((x) => !(x.id === s.id && x.floor_idx === s.floor_idx)));
      showToast("Site deleted", "success");
    } catch (e) {
      showToast(e.response?.data?.detail || "Failed to delete site", "error");
    }
  };

  return (
    <SectionCard
      title="Sites"
      action={<GhostButton icon={showForm ? Trash2 : Plus} onClick={() => setShowForm((v) => !v)}>{showForm ? "Cancel" : "New Site"}</GhostButton>}
    >
      {showForm && (
        <form onSubmit={submit} style={{ display: "flex", gap: 10, alignItems: "center", marginBottom: 16, padding: 12, background: "var(--bg-elevated)", borderRadius: "var(--radius-md)" }}>
          <FloorSelect floors={floors} value={floorKey} onChange={setFloorKey} />
          <input placeholder="Site name" value={name} onChange={(e) => setName(e.target.value)} style={{ ...inputStyle, flex: 1 }} required />
          <GhostButton icon={Plus} accent="var(--emerald)" disabled={busy}>{busy ? "Creating…" : "Create"}</GhostButton>
        </form>
      )}

      {loading ? <LoadingState rows={2} /> : sites.length === 0 ? (
        <EmptyState icon={<Building2 size={28} />} title="No sites yet" subtitle="Create one above to group machines" />
      ) : (
        <div style={{ overflowX: "auto" }}>
          <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13 }}>
            <thead>
              <tr style={{ borderBottom: "1px solid var(--border-default)" }}>
                {["Name", "Floor", "Machines", ""].map((h) => (
                  <th key={h} style={{ textAlign: "left", padding: "8px 12px", fontFamily: "var(--font-mono)", fontSize: 10, color: "var(--text-muted)", letterSpacing: "0.08em", textTransform: "uppercase" }}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {sites.map((s) => (
                <tr key={`${s.floor_idx}-${s.id}`} style={{ borderBottom: "1px solid var(--border-subtle)" }}>
                  <td style={{ padding: "10px 12px", fontWeight: 600 }}>{s.name}</td>
                  <td style={{ padding: "10px 12px", color: "var(--text-muted)" }}>{s.floor_name}</td>
                  <td style={{ padding: "10px 12px", fontFamily: "var(--font-mono)" }}>{s.machine_count}</td>
                  <td style={{ padding: "10px 12px", textAlign: "right" }}>
                    <GhostButton icon={Trash2} accent="var(--rose)" onClick={() => onDelete(s)}>Delete</GhostButton>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </SectionCard>
  );
}
