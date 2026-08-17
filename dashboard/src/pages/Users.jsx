import { useState, useEffect } from "react";
import { getUsers, createUser } from "../api";
import { useAuth } from "../context/AuthContext";

const MONO = "'JetBrains Mono', monospace";
const FONT = "'Cabinet Grotesk', sans-serif";
const DISP = "'Syne', sans-serif";

const ROLES = ["admin", "operator", "viewer"];
const ROLE_COLORS = {
  admin:    { bg: "rgba(244,63,94,0.08)",  border: "rgba(244,63,94,0.2)",  text: "#f43f5e" },
  operator: { bg: "rgba(56,189,248,0.08)", border: "rgba(56,189,248,0.2)", text: "#38bdf8" },
  viewer:   { bg: "rgba(122,143,166,0.08)", border: "rgba(122,143,166,0.15)", text: "#7a8fa6" },
};

function Avatar({ name, size = 36 }) {
  const letter = name?.[0]?.toUpperCase() || "?";
  const colors = ["#38bdf8", "#10b981", "#8b5cf6", "#f59e0b", "#f43f5e"];
  const color = colors[letter.charCodeAt(0) % colors.length];
  return (
    <div style={{
      width: size, height: size, borderRadius: "10px",
      background: `${color}18`, border: `1px solid ${color}30`,
      display: "flex", alignItems: "center", justifyContent: "center",
      fontFamily: DISP, fontSize: size * 0.38, fontWeight: 800,
      color, flexShrink: 0,
    }}>{letter}</div>
  );
}

function RoleBadge({ role }) {
  const c = ROLE_COLORS[role] || ROLE_COLORS.viewer;
  return (
    <span style={{
      padding: "2px 9px", borderRadius: "5px",
      background: c.bg, border: `1px solid ${c.border}`,
      color: c.text, fontSize: "10px", fontWeight: 700,
      fontFamily: MONO, letterSpacing: "0.08em",
      textTransform: "uppercase",
    }}>{role}</span>
  );
}

export default function Users() {
  const { user: currentUser } = useAuth();
  const [users,   setUsers]   = useState([]);
  const [loading, setLoading] = useState(true);
  const [showForm, setShowForm] = useState(false);
  const [toast,   setToast]   = useState(null);
  const [form, setForm] = useState({ name: "", email: "", password: "", role: "viewer" });
  const [saving, setSaving] = useState(false);

  const showToast = (msg, type = "success") => {
    setToast({ msg, type });
    setTimeout(() => setToast(null), 3000);
  };

  useEffect(() => {
    loadUsers();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const loadUsers = () => {
    setLoading(true);
    getUsers()
      .then(r => {
        const data = r.data;
        // API returns single user (me), wrap in array
        setUsers(Array.isArray(data) ? data : [data]);
      })
      .catch(() => {
        // Fallback: show current user
        if (currentUser) setUsers([{ ...currentUser, is_active: true, created_at: new Date().toISOString() }]);
      })
      .finally(() => setLoading(false));
  };

  const handleCreate = async () => {
    if (!form.name || !form.email || !form.password) return showToast("All fields required", "error");
    setSaving(true);
    try {
      await createUser({ username: form.email, name: form.name, password: form.password, role: form.role });
      showToast("User created successfully");
      setShowForm(false);
      setForm({ name: "", email: "", password: "", role: "viewer" });
      loadUsers();
    } catch (e) {
      showToast(e.response?.data?.detail || "Failed to create user", "error");
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
    <div style={{ fontFamily: FONT, color: "#e8f0fe" }}>
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
          <div style={{ fontSize: "10px", color: "rgba(56,189,248,0.6)", fontFamily: MONO, letterSpacing: "0.2em", textTransform: "uppercase", marginBottom: "6px" }}>Administration</div>
          <h1 style={{ fontFamily: DISP, fontSize: "26px", fontWeight: 800, letterSpacing: "-0.02em" }}>User Management</h1>
          <p style={{ color: "rgba(122,143,166,0.6)", fontSize: "13px", marginTop: "5px" }}>
            Manage access control and permissions
          </p>
        </div>
        <button onClick={() => setShowForm(!showForm)} style={{
          padding: "10px 20px",
          background: showForm ? "rgba(255,255,255,0.04)" : "linear-gradient(135deg, #38bdf8, #0ea5e9)",
          color: showForm ? "rgba(122,143,166,0.6)" : "#000",
          border: showForm ? "1px solid rgba(255,255,255,0.08)" : "none",
          borderRadius: "10px", fontWeight: 700, fontSize: "13px",
          cursor: "pointer", fontFamily: FONT, letterSpacing: "0.03em",
          transition: "all 0.2s",
        }}>
          {showForm ? "Cancel" : "+ Invite User"}
        </button>
      </div>

      {/* Role legend */}
      <div style={{ display: "flex", gap: "8px", marginBottom: "20px", flexWrap: "wrap" }}>
        {ROLES.map(role => {
          const c = ROLE_COLORS[role];
          return (
            <div key={role} style={{
              display: "flex", alignItems: "center", gap: "8px",
              padding: "6px 14px",
              background: c.bg, border: `1px solid ${c.border}`,
              borderRadius: "20px",
            }}>
              <span style={{ fontSize: "11px", fontWeight: 700, color: c.text, fontFamily: MONO, textTransform: "uppercase", letterSpacing: "0.08em" }}>{role}</span>
              <span style={{ fontSize: "11px", color: "rgba(122,143,166,0.5)" }}>·</span>
              <span style={{ fontSize: "11px", color: "rgba(122,143,166,0.5)" }}>
                {role === "admin" ? "Full access" : role === "operator" ? "Run commands" : "Read only"}
              </span>
            </div>
          );
        })}
      </div>

      {/* Create user form */}
      {showForm && (
        <div style={{
          background: "#0c1220", border: "1px solid rgba(56,189,248,0.15)",
          borderRadius: "14px", padding: "24px",
          marginBottom: "20px",
          animation: "fadeUp 0.3s cubic-bezier(0.16,1,0.3,1) both",
        }}>
          <div style={{ fontSize: "13px", fontWeight: 700, color: "#e8f0fe", marginBottom: "18px", fontFamily: DISP }}>
            Invite New User
          </div>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "12px", marginBottom: "12px" }}>
            <div>
              <label style={{ fontSize: "10px", color: "rgba(122,143,166,0.5)", fontFamily: MONO, letterSpacing: "0.14em", textTransform: "uppercase", display: "block", marginBottom: "6px" }}>Full Name</label>
              <input placeholder="John Smith" value={form.name} onChange={e => setForm(p => ({ ...p, name: e.target.value }))}
                style={inputStyle}
                onFocus={e => e.target.style.borderColor = "rgba(56,189,248,0.4)"}
                onBlur={e => e.target.style.borderColor = "rgba(255,255,255,0.07)"}
              />
            </div>
            <div>
              <label style={{ fontSize: "10px", color: "rgba(122,143,166,0.5)", fontFamily: MONO, letterSpacing: "0.14em", textTransform: "uppercase", display: "block", marginBottom: "6px" }}>Email / Username</label>
              <input placeholder="john@company.com" value={form.email} onChange={e => setForm(p => ({ ...p, email: e.target.value }))}
                style={inputStyle}
                onFocus={e => e.target.style.borderColor = "rgba(56,189,248,0.4)"}
                onBlur={e => e.target.style.borderColor = "rgba(255,255,255,0.07)"}
              />
            </div>
            <div>
              <label style={{ fontSize: "10px", color: "rgba(122,143,166,0.5)", fontFamily: MONO, letterSpacing: "0.14em", textTransform: "uppercase", display: "block", marginBottom: "6px" }}>Password</label>
              <input type="password" placeholder="••••••••" value={form.password} onChange={e => setForm(p => ({ ...p, password: e.target.value }))}
                style={inputStyle}
                onFocus={e => e.target.style.borderColor = "rgba(56,189,248,0.4)"}
                onBlur={e => e.target.style.borderColor = "rgba(255,255,255,0.07)"}
              />
            </div>
            <div>
              <label style={{ fontSize: "10px", color: "rgba(122,143,166,0.5)", fontFamily: MONO, letterSpacing: "0.14em", textTransform: "uppercase", display: "block", marginBottom: "6px" }}>Role</label>
              <select value={form.role} onChange={e => setForm(p => ({ ...p, role: e.target.value }))}
                style={{ ...inputStyle, background: "#080d1a" }}>
                {ROLES.map(r => <option key={r} value={r} style={{ background: "#080d1a" }}>{r}</option>)}
              </select>
            </div>
          </div>
          <button onClick={handleCreate} disabled={saving} style={{
            padding: "10px 24px",
            background: saving ? "rgba(56,189,248,0.06)" : "linear-gradient(135deg, #38bdf8, #0ea5e9)",
            color: saving ? "rgba(56,189,248,0.3)" : "#000",
            border: "none", borderRadius: "9px",
            fontWeight: 700, fontSize: "13px",
            cursor: saving ? "not-allowed" : "pointer", fontFamily: FONT,
            display: "flex", alignItems: "center", gap: "6px",
          }}>
            {saving ? <><div style={{ width: "12px", height: "12px", border: "2px solid rgba(56,189,248,0.3)", borderTopColor: "#38bdf8", borderRadius: "50%", animation: "spin 0.7s linear infinite" }}/>Creating...</> : "Create User"}
          </button>
        </div>
      )}

      {/* Users list */}
      <div style={{ background: "#0c1220", border: "1px solid rgba(255,255,255,0.06)", borderRadius: "14px", overflow: "hidden" }}>
        <div style={{ padding: "16px 20px", borderBottom: "1px solid rgba(255,255,255,0.05)", display: "flex", justifyContent: "space-between", alignItems: "center" }}>
          <span style={{ fontSize: "11px", color: "rgba(122,143,166,0.4)", fontFamily: MONO, letterSpacing: "0.16em", textTransform: "uppercase" }}>
            Users · {users.length}
          </span>
        </div>

        {loading ? (
          <div style={{ padding: "48px", textAlign: "center", color: "rgba(122,143,166,0.3)", fontFamily: MONO, fontSize: "12px" }}>Loading users...</div>
        ) : (
          users.map((u, i) => (
            <div key={u.id || i} style={{
              display: "flex", alignItems: "center", gap: "14px",
              padding: "16px 20px",
              borderBottom: i < users.length - 1 ? "1px solid rgba(255,255,255,0.04)" : "none",
              transition: "background 0.15s",
              animation: `fadeUp 0.3s ${i * 50}ms both`,
            }}
              onMouseOver={e => e.currentTarget.style.background = "rgba(255,255,255,0.01)"}
              onMouseOut={e => e.currentTarget.style.background = "transparent"}
            >
              <Avatar name={u.name || u.username} />
              <div style={{ flex: 1, minWidth: 0 }}>
                <div style={{ display: "flex", alignItems: "center", gap: "8px", marginBottom: "2px" }}>
                  <span style={{ fontSize: "14px", fontWeight: 600, color: "#e8f0fe" }}>{u.name || u.username}</span>
                  {(u.username === currentUser?.name || u.id === currentUser?.id) && (
                    <span style={{ fontSize: "9px", fontFamily: MONO, color: "#38bdf8", background: "rgba(56,189,248,0.08)", border: "1px solid rgba(56,189,248,0.2)", borderRadius: "4px", padding: "1px 6px", letterSpacing: "0.08em" }}>YOU</span>
                  )}
                </div>
                <div style={{ fontSize: "12px", color: "rgba(122,143,166,0.5)", fontFamily: MONO }}>
                  {u.email || u.username}
                </div>
              </div>

              <div style={{ display: "flex", alignItems: "center", gap: "12px" }}>
                <RoleBadge role={u.role || "admin"} />
                <div style={{
                  display: "flex", alignItems: "center", gap: "5px",
                  padding: "3px 9px", borderRadius: "5px",
                  background: u.is_active !== false ? "rgba(16,185,129,0.06)" : "rgba(244,63,94,0.06)",
                  border: `1px solid ${u.is_active !== false ? "rgba(16,185,129,0.15)" : "rgba(244,63,94,0.15)"}`,
                }}>
                  <div style={{ width: "5px", height: "5px", borderRadius: "50%", background: u.is_active !== false ? "#10b981" : "#f43f5e" }}/>
                  <span style={{ fontSize: "10px", fontFamily: MONO, color: u.is_active !== false ? "#10b981" : "#f43f5e" }}>
                    {u.is_active !== false ? "Active" : "Inactive"}
                  </span>
                </div>
                <span style={{ fontSize: "10px", color: "rgba(61,80,104,0.5)", fontFamily: MONO }}>
                  {u.created_at ? new Date(u.created_at).toLocaleDateString() : "—"}
                </span>
              </div>
            </div>
          ))
        )}
      </div>

      <style>{`
        @keyframes spin { to { transform: rotate(360deg); } }
        @keyframes fadeUp { from { opacity:0; transform:translateY(10px); } to { opacity:1; transform:translateY(0); } }
        @import url('https://fonts.googleapis.com/css2?family=Syne:wght@700;800&family=JetBrains+Mono:wght@400;500&family=Cabinet+Grotesk:wght@400;500;600;700&display=swap');
        select option { background: #080d1a; }
      `}</style>
    </div>
  );
}
