import { NavLink } from "react-router-dom";
import {
  LayoutDashboard, Activity, ShieldAlert, AlertTriangle, HeartPulse,
  Zap, FileText, ScrollText, Settings, Server,
} from "lucide-react";

const NAV = [
  { to: "/",          label: "Dashboard",    icon: LayoutDashboard },
  { to: "/monitoring", label: "Monitoring",  icon: Activity },
  { to: "/security",   label: "Security",    icon: ShieldAlert },
  { to: "/signals",    label: "Signals",     icon: AlertTriangle },
  { to: "/health",     label: "System Health", icon: HeartPulse },
  { to: "/automation", label: "Automation",  icon: Zap },
  { to: "/reports",    label: "Reports",     icon: FileText },
  { to: "/audit",      label: "Audit Logs",  icon: ScrollText },
];

export default function Sidebar({ systemStatus = "operational" }) {
  return (
    <aside style={{
      width: 232, minWidth: 232, height: "100%",
      background: "var(--bg-surface)",
      borderRight: "1px solid var(--border-default)",
      display: "flex", flexDirection: "column",
      padding: "18px 12px",
    }}>
      {/* Logo */}
      <div style={{ display: "flex", alignItems: "center", gap: 10, padding: "6px 8px 22px" }}>
        <div style={{
          width: 30, height: 30, borderRadius: 8,
          background: "linear-gradient(135deg, var(--cyan), var(--violet))",
          display: "flex", alignItems: "center", justifyContent: "center",
          fontFamily: "var(--font-display)", fontWeight: 800, fontSize: 14, color: "#04101c",
        }}>J</div>
        <div>
          <div style={{ fontFamily: "var(--font-display)", fontWeight: 800, fontSize: 14, letterSpacing: "-0.01em" }}>
            JENIX
          </div>
          <div style={{ fontFamily: "var(--font-mono)", fontSize: 9, color: "var(--text-muted)", letterSpacing: "0.14em" }}>
            MASTER CONTROL
          </div>
        </div>
      </div>

      {/* Nav */}
      <nav style={{ display: "flex", flexDirection: "column", gap: 2, flex: 1 }}>
        {NAV.map(({ to, label, icon: Icon }) => (
          <NavLink key={to} to={to} end={to === "/"} style={({ isActive }) => ({
            display: "flex", alignItems: "center", gap: 10,
            padding: "9px 12px", borderRadius: "var(--radius-sm)",
            fontSize: 13, fontWeight: isActive ? 600 : 500,
            color: isActive ? "var(--text-primary)" : "var(--text-secondary)",
            background: isActive ? "var(--bg-card)" : "transparent",
            borderLeft: `2px solid ${isActive ? "var(--cyan)" : "transparent"}`,
            textDecoration: "none",
            transition: "background 0.15s, color 0.15s",
          })}>
            <Icon size={15} strokeWidth={2} />
            {label}
          </NavLink>
        ))}
      </nav>

      {/* Bottom: system status + settings */}
      <div style={{ borderTop: "1px solid var(--border-subtle)", paddingTop: 12, display: "flex", flexDirection: "column", gap: 10 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 8, padding: "0 12px" }}>
          <span style={{
            width: 7, height: 7, borderRadius: "50%", background: "var(--emerald)",
            boxShadow: "0 0 6px var(--emerald)", animation: "pulseDot 2s infinite",
          }} />
          <span style={{ fontSize: 11, fontFamily: "var(--font-mono)", color: "var(--text-secondary)" }}>
            All systems {systemStatus}
          </span>
        </div>
        <NavLink to="/floors" style={({ isActive }) => ({
          display: "flex", alignItems: "center", gap: 10, padding: "9px 12px",
          borderRadius: "var(--radius-sm)", fontSize: 13, fontWeight: isActive ? 600 : 500,
          color: isActive ? "var(--text-primary)" : "var(--text-secondary)",
          background: isActive ? "var(--bg-card)" : "transparent", textDecoration: "none",
        })}>
          <Server size={15} /> Floors
        </NavLink>
        <NavLink to="/settings" style={({ isActive }) => ({
          display: "flex", alignItems: "center", gap: 10, padding: "9px 12px",
          borderRadius: "var(--radius-sm)", fontSize: 13, fontWeight: isActive ? 600 : 500,
          color: isActive ? "var(--text-primary)" : "var(--text-secondary)",
          background: isActive ? "var(--bg-card)" : "transparent", textDecoration: "none",
        })}>
          <Settings size={15} /> Settings
        </NavLink>
        <div style={{ display: "flex", alignItems: "center", gap: 8, padding: "8px 12px 0" }}>
          <div style={{
            width: 26, height: 26, borderRadius: "50%", background: "var(--bg-elevated)",
            display: "flex", alignItems: "center", justifyContent: "center",
            fontSize: 11, fontWeight: 700, color: "var(--text-secondary)",
          }}>A</div>
          <div style={{ fontSize: 12, color: "var(--text-secondary)" }}>admin@jenix.io</div>
        </div>
      </div>
    </aside>
  );
}
