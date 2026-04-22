import { Link, useLocation } from "react-router-dom";
import { useAuth } from "../context/AuthContext";
import { useBrand } from "../context/BrandContext";
import { useState } from "react";

const NAV_GROUPS = [
  {
    label: "Operations",
    items: [
      { path: "/",        label: "Fleet Command",  icon: "◈", badge: null },
      { path: "/overview",label: "All Machines",   icon: "⬡", badge: null },
      { path: "/uptime",  label: "Uptime Monitor", icon: "◎", badge: null },
    ]
  },
  {
    label: "Security",
    items: [
      { path: "/cve",     label: "CVE Scanner",    icon: "⬡", badge: "NEW" },
      { path: "/reports", label: "Reports",        icon: "▦",  badge: null },
      { path: "/audit",   label: "Audit Log",      icon: "◱",  badge: null },
    ]
  },
  {
    label: "Admin",
    adminOnly: true,
    items: [
      { path: "/users",      label: "Users",       icon: "◎", badge: null },
      { path: "/settings",   label: "Settings",    icon: "◈", badge: null },
      { path: "/whitelabel", label: "Branding",    icon: "◇", badge: null },
      { path: "/demo",       label: "Demo Script", icon: "▷", badge: null },
    ]
  },
];

export default function Sidebar() {
  const { pathname }     = useLocation();
  const { user, logout } = useAuth();
  const { brand }        = useBrand();
  const [hoveredPath, setHoveredPath] = useState(null);
  const role = user?.role || "viewer";
  const accent = brand?.primary_color || "#38bdf8";

  return (
    <aside style={{
      width: "240px", minWidth: "240px",
      height: "100vh",
      background: "#080d1a",
      borderRight: "1px solid rgba(255,255,255,0.05)",
      display: "flex", flexDirection: "column",
      fontFamily: "'Cabinet Grotesk', sans-serif",
      position: "relative",
      overflow: "hidden",
    }}>
      {/* Subtle vertical gradient line */}
      <div style={{
        position: "absolute", top: 0, right: 0, width: "1px", height: "100%",
        background: "linear-gradient(180deg, transparent, rgba(56,189,248,0.2) 30%, rgba(56,189,248,0.2) 70%, transparent)",
        pointerEvents: "none",
      }}/>

      {/* Logo */}
      <div style={{
        padding: "24px 20px 20px",
        borderBottom: "1px solid rgba(255,255,255,0.04)",
      }}>
        <div style={{ display: "flex", alignItems: "center", gap: "10px" }}>
          <div style={{
            width: "32px", height: "32px",
            background: `linear-gradient(135deg, ${accent}, #8b5cf6)`,
            clipPath: "polygon(50% 0%, 100% 25%, 100% 75%, 50% 100%, 0% 75%, 0% 25%)",
            display: "flex", alignItems: "center", justifyContent: "center",
            flexShrink: 0,
          }}>
            <span style={{ color: "#000", fontSize: "11px", fontWeight: 800, fontFamily: "'Syne', sans-serif" }}>J</span>
          </div>
          <div>
            <div style={{
              fontFamily: "'Syne', sans-serif",
              fontSize: "16px", fontWeight: 800,
              letterSpacing: "0.1em",
              background: `linear-gradient(135deg, ${accent} 0%, #e8f0fe 60%)`,
              WebkitBackgroundClip: "text",
              WebkitTextFillColor: "transparent",
            }}>
              {brand?.logo_text || "JENIX"}
            </div>
            <div style={{
              fontSize: "9px", color: "rgba(61,80,104,0.8)",
              letterSpacing: "0.15em", fontFamily: "'JetBrains Mono', monospace",
              textTransform: "uppercase", marginTop: "1px",
            }}>
              {brand?.logo_subtext || "Enterprise v2.0"}
            </div>
          </div>
        </div>

        {/* Live indicator */}
        <div style={{
          display: "flex", alignItems: "center", gap: "6px",
          marginTop: "14px", padding: "6px 10px",
          background: "rgba(16,185,129,0.06)",
          border: "1px solid rgba(16,185,129,0.15)",
          borderRadius: "6px",
        }}>
          <div style={{
            width: "6px", height: "6px", borderRadius: "50%",
            background: "#10b981",
            boxShadow: "0 0 6px #10b981",
            animation: "pulse 2s infinite",
          }}/>
          <span style={{
            fontSize: "10px", color: "rgba(16,185,129,0.8)",
            fontFamily: "'JetBrains Mono', monospace",
            letterSpacing: "0.08em",
          }}>SYSTEM LIVE</span>
        </div>
      </div>

      {/* Navigation */}
      <nav style={{ flex: 1, padding: "12px 0", overflowY: "auto" }}>
        {NAV_GROUPS.map(group => {
          if (group.adminOnly && role !== "admin") return null;
          return (
            <div key={group.label} style={{ marginBottom: "4px" }}>
              <div style={{
                padding: "8px 20px 4px",
                fontSize: "9px", fontWeight: 700,
                color: "rgba(61,80,104,0.6)",
                letterSpacing: "0.2em", textTransform: "uppercase",
                fontFamily: "'JetBrains Mono', monospace",
              }}>
                {group.label}
              </div>
              {group.items.map(({ path, label, icon, badge }) => {
                const active  = pathname === path;
                const hovered = hoveredPath === path;
                return (
                  <Link
                    key={path}
                    to={path}
                    onMouseEnter={() => setHoveredPath(path)}
                    onMouseLeave={() => setHoveredPath(null)}
                    style={{
                      display: "flex", alignItems: "center", gap: "10px",
                      padding: "9px 20px",
                      textDecoration: "none",
                      color: active ? accent : hovered ? "#e8f0fe" : "#4a6080",
                      background: active
                        ? `linear-gradient(90deg, rgba(56,189,248,0.1), transparent)`
                        : hovered ? "rgba(255,255,255,0.02)" : "transparent",
                      borderLeft: active
                        ? `2px solid ${accent}`
                        : "2px solid transparent",
                      fontSize: "13px",
                      fontWeight: active ? 600 : 400,
                      transition: "all 0.15s",
                      position: "relative",
                    }}
                  >
                    <span style={{
                      fontSize: "12px", width: "16px",
                      textAlign: "center", flexShrink: 0,
                      opacity: active ? 1 : 0.6,
                    }}>{icon}</span>
                    <span style={{ flex: 1 }}>{label}</span>
                    {badge && (
                      <span style={{
                        fontSize: "8px", padding: "2px 5px",
                        background: "rgba(56,189,248,0.15)",
                        border: "1px solid rgba(56,189,248,0.3)",
                        borderRadius: "4px", color: accent,
                        fontFamily: "'JetBrains Mono', monospace",
                        letterSpacing: "0.06em",
                      }}>{badge}</span>
                    )}
                    {active && (
                      <div style={{
                        position: "absolute", right: "12px",
                        width: "4px", height: "4px",
                        borderRadius: "50%", background: accent,
                        boxShadow: `0 0 6px ${accent}`,
                      }}/>
                    )}
                  </Link>
                );
              })}
            </div>
          );
        })}
      </nav>

      {/* User section */}
      <div style={{
        borderTop: "1px solid rgba(255,255,255,0.04)",
        padding: "16px 20px",
      }}>
        <div style={{
          display: "flex", alignItems: "center", gap: "10px",
          marginBottom: "12px",
        }}>
          <div style={{
            width: "34px", height: "34px", borderRadius: "10px",
            background: `linear-gradient(135deg, rgba(56,189,248,0.2), rgba(139,92,246,0.2))`,
            border: `1px solid ${accent}30`,
            display: "flex", alignItems: "center", justifyContent: "center",
            color: accent, fontSize: "13px", fontWeight: 700,
            fontFamily: "'Syne', sans-serif",
            flexShrink: 0,
          }}>
            {user?.name?.[0]?.toUpperCase() || "A"}
          </div>
          <div style={{ minWidth: 0 }}>
            <div style={{
              color: "#e8f0fe", fontSize: "13px", fontWeight: 600,
              overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap",
            }}>
              {user?.name || "Admin"}
            </div>
            <div style={{
              fontSize: "10px", color: "rgba(61,80,104,0.8)",
              textTransform: "capitalize",
              fontFamily: "'JetBrains Mono', monospace",
            }}>
              {user?.role || "admin"} · authenticated
            </div>
          </div>
        </div>

        <button
          onClick={logout}
          style={{
            width: "100%", padding: "8px",
            background: "transparent",
            color: "rgba(61,80,104,0.8)",
            border: "1px solid rgba(255,255,255,0.05)",
            borderRadius: "8px",
            cursor: "pointer", fontSize: "12px",
            fontFamily: "'Cabinet Grotesk', sans-serif",
            fontWeight: 500, letterSpacing: "0.03em",
            transition: "all 0.15s",
          }}
          onMouseOver={e => {
            e.currentTarget.style.color = "#f43f5e";
            e.currentTarget.style.borderColor = "rgba(244,63,94,0.3)";
            e.currentTarget.style.background = "rgba(244,63,94,0.05)";
          }}
          onMouseOut={e => {
            e.currentTarget.style.color = "rgba(61,80,104,0.8)";
            e.currentTarget.style.borderColor = "rgba(255,255,255,0.05)";
            e.currentTarget.style.background = "transparent";
          }}
        >
          Sign Out
        </button>
      </div>

      <style>{`
        @keyframes pulse {
          0%, 100% { opacity: 1; }
          50% { opacity: 0.4; }
        }
        @import url('https://fonts.googleapis.com/css2?family=Syne:wght@700;800&family=JetBrains+Mono:wght@400;600&family=Cabinet+Grotesk:wght@400;500;600;700&display=swap');
      `}</style>
    </aside>
  );
}
