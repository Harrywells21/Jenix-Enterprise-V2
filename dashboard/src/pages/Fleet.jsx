import { useState, useEffect, useRef } from "react";
import { useNavigate } from "react-router-dom";
import { getFleetOverview, getAllAlerts, markAllRead, fleetCommand, getSavings } from "../api";

/* ── Stat Card ── */
function StatCard({ label, value, sub, accent, icon, delay = 0 }) {
  const [visible, setVisible] = useState(false);
  useEffect(() => { setTimeout(() => setVisible(true), delay); }, [delay]);

  return (
    <div style={{
      background: "#0c1220",
      border: "1px solid rgba(255,255,255,0.06)",
      borderRadius: "14px",
      padding: "22px",
      position: "relative",
      overflow: "hidden",
      opacity: visible ? 1 : 0,
      transform: visible ? "translateY(0)" : "translateY(16px)",
      transition: "opacity 0.5s cubic-bezier(0.16,1,0.3,1), transform 0.5s cubic-bezier(0.16,1,0.3,1), border-color 0.2s",
      cursor: "default",
    }}
    onMouseOver={e => {
      e.currentTarget.style.borderColor = `${accent}30`;
      e.currentTarget.style.boxShadow = `0 0 30px ${accent}10`;
    }}
    onMouseOut={e => {
      e.currentTarget.style.borderColor = "rgba(255,255,255,0.06)";
      e.currentTarget.style.boxShadow = "none";
    }}>
      {/* Top accent bar */}
      <div style={{
        position: "absolute", top: 0, left: "20%", right: "20%", height: "1px",
        background: `linear-gradient(90deg, transparent, ${accent}60, transparent)`,
      }}/>
      {/* Icon bg */}
      <div style={{
        position: "absolute", top: "16px", right: "16px",
        width: "36px", height: "36px",
        background: `${accent}12`,
        borderRadius: "10px",
        display: "flex", alignItems: "center", justifyContent: "center",
        fontSize: "16px",
      }}>{icon}</div>

      <div style={{
        fontFamily: "'JetBrains Mono', monospace",
        fontSize: "9px", fontWeight: 500,
        color: "rgba(122,143,166,0.6)",
        letterSpacing: "0.2em", textTransform: "uppercase",
        marginBottom: "10px",
      }}>{label}</div>

      <div style={{
        fontFamily: "'Syne', sans-serif",
        fontSize: "36px", fontWeight: 800,
        color: accent, lineHeight: 1,
        letterSpacing: "-0.02em",
      }}>{value}</div>

      {sub && (
        <div style={{
          marginTop: "8px", fontSize: "12px",
          color: "rgba(122,143,166,0.6)",
          fontFamily: "'JetBrains Mono', monospace",
        }}>{sub}</div>
      )}
    </div>
  );
}

/* ── Alert Item ── */
function AlertItem({ alert, onDismiss }) {
  const sev = alert.severity || "info";
  const colors = {
    critical: { bg: "rgba(244,63,94,0.08)", border: "rgba(244,63,94,0.25)", text: "#f43f5e", dot: "#f43f5e" },
    warning:  { bg: "rgba(245,158,11,0.08)", border: "rgba(245,158,11,0.2)",  text: "#f59e0b", dot: "#f59e0b" },
    info:     { bg: "rgba(56,189,248,0.06)", border: "rgba(56,189,248,0.15)", text: "#38bdf8", dot: "#38bdf8" },
  };
  const c = colors[sev] || colors.info;

  return (
    <div style={{
      display: "flex", alignItems: "flex-start", gap: "12px",
      padding: "14px 16px",
      background: c.bg, border: `1px solid ${c.border}`,
      borderRadius: "10px", marginBottom: "8px",
      transition: "opacity 0.2s",
    }}>
      <div style={{
        width: "7px", height: "7px", borderRadius: "50%",
        background: c.dot, flexShrink: 0, marginTop: "5px",
        boxShadow: sev === "critical" ? `0 0 8px ${c.dot}` : "none",
      }}/>
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{ fontSize: "13px", color: "#e8f0fe", fontWeight: 500, marginBottom: "3px" }}>
          {alert.message}
        </div>
        <div style={{
          fontSize: "11px", color: "rgba(122,143,166,0.6)",
          fontFamily: "'JetBrains Mono', monospace",
          display: "flex", gap: "10px",
        }}>
          <span style={{ color: c.text, textTransform: "uppercase", letterSpacing: "0.06em" }}>{sev}</span>
          <span>·</span>
          <span>{alert.machine_hostname || "fleet"}</span>
          <span>·</span>
          <span>{new Date(alert.created_at || Date.now()).toLocaleTimeString()}</span>
        </div>
      </div>
      {onDismiss && (
        <button onClick={() => onDismiss(alert.id)} style={{
          background: "none", border: "none",
          color: "rgba(122,143,166,0.4)", cursor: "pointer",
          fontSize: "16px", padding: "0", lineHeight: 1,
          flexShrink: 0,
        }}>×</button>
      )}
    </div>
  );
}

/* ── Command Button ── */
function CmdButton({ icon, label, desc, onClick, accent = "#38bdf8" }) {
  const [hov, setHov] = useState(false);
  const [active, setActive] = useState(false);

  return (
    <button
      onClick={() => { setActive(true); onClick(); setTimeout(() => setActive(false), 1500); }}
      onMouseEnter={() => setHov(true)}
      onMouseLeave={() => setHov(false)}
      style={{
        background: hov ? `${accent}10` : "rgba(255,255,255,0.02)",
        border: `1px solid ${hov ? accent + "40" : "rgba(255,255,255,0.06)"}`,
        borderRadius: "12px", padding: "18px 16px",
        cursor: "pointer", textAlign: "left",
        transition: "all 0.2s cubic-bezier(0.16,1,0.3,1)",
        transform: hov ? "translateY(-2px)" : "translateY(0)",
        boxShadow: hov ? `0 8px 24px ${accent}15` : "none",
      }}
    >
      <div style={{ fontSize: "22px", marginBottom: "8px" }}>{active ? "⟳" : icon}</div>
      <div style={{
        fontSize: "13px", fontWeight: 700, color: hov ? accent : "#e8f0fe",
        marginBottom: "4px", fontFamily: "'Syne', sans-serif",
        transition: "color 0.2s",
      }}>{active ? "Executing..." : label}</div>
      <div style={{
        fontSize: "11px", color: "rgba(122,143,166,0.5)",
        fontFamily: "'JetBrains Mono', monospace",
        lineHeight: 1.4,
      }}>{desc}</div>
    </button>
  );
}

export default function Fleet() {
  const [overview,  setOverview]  = useState(null);
  const [alerts,    setAlerts]    = useState([]);
  const [savings,   setSavings]   = useState(null);
  const [toast,     setToast]     = useState(null);
  const [cmdOutput, setCmdOutput] = useState([]);
  const [tab,       setTab]       = useState("alerts");
  const navigate = useNavigate();

  const showToast = (msg, type = "success") => {
    setToast({ msg, type });
    setTimeout(() => setToast(null), 3500);
  };

  useEffect(() => {
    const load = () => {
      getFleetOverview().then(r => setOverview(r.data)).catch(() => {});
      getAllAlerts().then(r => setAlerts(r.data?.alerts || r.data || [])).catch(() => {});
      getSavings().then(r => setSavings(r.data)).catch(() => {});
    };
    load();
    const iv = setInterval(load, 15_000);
    return () => clearInterval(iv);
  }, []);

  const handleCommand = async (type) => {
    try {
      const r = await fleetCommand(type, []);
      const line = `[${new Date().toLocaleTimeString()}] ${type.toUpperCase()} dispatched → ${r.data?.dispatched || 0} nodes`;
      setCmdOutput(p => [line, ...p.slice(0, 19)]);
      showToast(`${type} command sent to all online nodes`, "success");
    } catch (e) {
      showToast(e.response?.data?.detail || e.message, "error");
    }
  };

  const stats = [
    {
      label: "Total Machines",
      value: overview?.total_machines ?? "—",
      sub: `${overview?.online_machines ?? 0} online · ${(overview?.total_machines ?? 0) - (overview?.online_machines ?? 0)} offline`,
      accent: "#38bdf8", icon: "⬡", delay: 0,
    },
    {
      label: "Fleet CPU",
      value: overview?.avg_cpu != null ? `${overview.avg_cpu.toFixed(1)}%` : "—",
      sub: "Average across all machines",
      accent: overview?.avg_cpu > 80 ? "#f43f5e" : overview?.avg_cpu > 60 ? "#f59e0b" : "#10b981",
      icon: "⚡", delay: 80,
    },
    {
      label: "Fleet RAM",
      value: overview?.avg_ram != null ? `${overview.avg_ram.toFixed(1)}%` : "—",
      sub: "Average across all machines",
      accent: overview?.avg_ram > 85 ? "#f43f5e" : overview?.avg_ram > 70 ? "#f59e0b" : "#10b981",
      icon: "◫", delay: 160,
    },
    {
      label: "Critical Alerts",
      value: alerts.filter(a => a.severity === "critical").length || "—",
      sub: `${alerts.length} total · ${alerts.filter(a => a.severity === "warning").length} warnings`,
      accent: alerts.filter(a => a.severity === "critical").length > 0 ? "#f43f5e" : "#10b981",
      icon: "⚠", delay: 240,
    },
    {
      label: "Commands Today",
      value: overview?.commands_today ?? "—",
      sub: "Automated operations run",
      accent: "#8b5cf6", icon: "▷", delay: 320,
    },
    {
      label: "Annual Savings",
      value: savings?.estimated_savings
        ? `$${(savings.estimated_savings / 1000).toFixed(0)}k`
        : overview?.estimated_savings
          ? `$${Math.round(overview.estimated_savings).toLocaleString()}`
          : "—",
      sub: "~$45/hr in manual labor",
      accent: "#10b981", icon: "◈", delay: 400,
    },
  ];

  const critical = alerts.filter(a => a.severity === "critical");

  return (
    <div style={{
      fontFamily: "'Cabinet Grotesk', sans-serif",
      color: "#e8f0fe",
      minHeight: "100%",
    }}>
      {/* Toast */}
      {toast && (
        <div style={{
          position: "fixed", top: "24px", right: "24px", zIndex: 9999,
          padding: "12px 18px",
          background: toast.type === "error" ? "rgba(244,63,94,0.12)" : "rgba(16,185,129,0.12)",
          border: `1px solid ${toast.type === "error" ? "rgba(244,63,94,0.3)" : "rgba(16,185,129,0.3)"}`,
          borderRadius: "10px", color: toast.type === "error" ? "#f43f5e" : "#10b981",
          fontSize: "13px",
          boxShadow: "0 8px 32px rgba(0,0,0,0.4)",
          animation: "fadeIn 0.3s ease",
          display: "flex", alignItems: "center", gap: "8px",
          fontFamily: "'JetBrains Mono', monospace",
        }}>
          {toast.type === "error" ? "✗" : "✓"} {toast.msg}
        </div>
      )}

      {/* Page Header */}
      <div style={{ marginBottom: "28px", display: "flex", alignItems: "flex-start", justifyContent: "space-between" }}>
        <div>
          <div style={{
            fontFamily: "'JetBrains Mono', monospace",
            fontSize: "10px", color: "rgba(56,189,248,0.6)",
            letterSpacing: "0.2em", textTransform: "uppercase",
            marginBottom: "6px",
          }}>
            Operations Center
          </div>
          <h1 style={{
            fontFamily: "'Syne', sans-serif",
            fontSize: "28px", fontWeight: 800,
            color: "#e8f0fe", letterSpacing: "-0.02em",
            lineHeight: 1,
          }}>
            Fleet Command Center
          </h1>
          <p style={{
            color: "rgba(122,143,166,0.7)", fontSize: "14px", marginTop: "6px",
          }}>
            Real-time overview of your entire Linux infrastructure
          </p>
        </div>

        <div style={{ display: "flex", gap: "8px", alignItems: "center" }}>
          <button
            onClick={() => handleCommand("scan")}
            style={{
              padding: "9px 16px",
              background: "rgba(56,189,248,0.08)",
              border: "1px solid rgba(56,189,248,0.2)",
              borderRadius: "8px", color: "#38bdf8",
              fontSize: "12px", fontWeight: 600,
              cursor: "pointer", fontFamily: "'Cabinet Grotesk', sans-serif",
              letterSpacing: "0.04em", transition: "all 0.2s",
            }}
            onMouseOver={e => { e.currentTarget.style.background = "rgba(56,189,248,0.15)"; }}
            onMouseOut={e => { e.currentTarget.style.background = "rgba(56,189,248,0.08)"; }}
          >⚡ Scan ALL</button>
          <button
            onClick={() => handleCommand("boost")}
            style={{
              padding: "9px 16px",
              background: "rgba(16,185,129,0.08)",
              border: "1px solid rgba(16,185,129,0.2)",
              borderRadius: "8px", color: "#10b981",
              fontSize: "12px", fontWeight: 600,
              cursor: "pointer", fontFamily: "'Cabinet Grotesk', sans-serif",
              letterSpacing: "0.04em", transition: "all 0.2s",
            }}
            onMouseOver={e => { e.currentTarget.style.background = "rgba(16,185,129,0.15)"; }}
            onMouseOut={e => { e.currentTarget.style.background = "rgba(16,185,129,0.08)"; }}
          >⚡ Boost ALL</button>
          <button
            onClick={() => handleCommand("clean")}
            style={{
              padding: "9px 16px",
              background: "rgba(245,158,11,0.08)",
              border: "1px solid rgba(245,158,11,0.2)",
              borderRadius: "8px", color: "#f59e0b",
              fontSize: "12px", fontWeight: 600,
              cursor: "pointer", fontFamily: "'Cabinet Grotesk', sans-serif",
              letterSpacing: "0.04em", transition: "all 0.2s",
            }}
            onMouseOver={e => { e.currentTarget.style.background = "rgba(245,158,11,0.15)"; }}
            onMouseOut={e => { e.currentTarget.style.background = "rgba(245,158,11,0.08)"; }}
          >⚡ Clean ALL</button>
        </div>
      </div>

      {/* Critical Alert Banner */}
      {critical.length > 0 && (
        <div style={{
          display: "flex", alignItems: "center", justifyContent: "space-between",
          padding: "14px 18px", marginBottom: "24px",
          background: "rgba(244,63,94,0.07)",
          border: "1px solid rgba(244,63,94,0.25)",
          borderRadius: "12px",
          animation: "fadeIn 0.4s ease",
        }}>
          <div style={{ display: "flex", alignItems: "center", gap: "12px" }}>
            <div style={{
              width: "8px", height: "8px", borderRadius: "50%",
              background: "#f43f5e", boxShadow: "0 0 10px #f43f5e",
              animation: "pulse 1.5s infinite",
            }}/>
            <span style={{
              color: "#f43f5e", fontWeight: 700, fontSize: "14px",
              fontFamily: "'Syne', sans-serif",
            }}>
              {critical.length} Critical Alert{critical.length > 1 ? "s" : ""} Require Immediate Attention
            </span>
          </div>
          <button
            onClick={() => markAllRead().then(() => setAlerts([]))}
            style={{
              padding: "6px 14px",
              background: "rgba(244,63,94,0.12)",
              border: "1px solid rgba(244,63,94,0.3)",
              borderRadius: "6px", color: "#f43f5e",
              fontSize: "12px", cursor: "pointer",
              fontFamily: "'Cabinet Grotesk', sans-serif",
            }}
          >Mark All Read</button>
        </div>
      )}

      {/* Stats Grid */}
      <div style={{
        display: "grid",
        gridTemplateColumns: "repeat(auto-fill, minmax(200px, 1fr))",
        gap: "14px",
        marginBottom: "28px",
      }}>
        {stats.map((s) => (
          <StatCard key={s.label} {...s} />
        ))}
      </div>

      {/* Main Content Grid */}
      <div style={{
        display: "grid",
        gridTemplateColumns: "1fr 380px",
        gap: "20px",
        marginBottom: "24px",
      }}>
        {/* Left — Tabs panel */}
        <div style={{
          background: "#0c1220",
          border: "1px solid rgba(255,255,255,0.06)",
          borderRadius: "14px",
          overflow: "hidden",
        }}>
          {/* Tab bar */}
          <div style={{
            display: "flex",
            borderBottom: "1px solid rgba(255,255,255,0.06)",
            padding: "0 4px",
          }}>
            {["alerts", "command-log"].map(t => (
              <button key={t}
                onClick={() => setTab(t)}
                style={{
                  padding: "14px 20px", border: "none",
                  background: "none", cursor: "pointer",
                  fontSize: "12px", fontWeight: tab === t ? 700 : 400,
                  color: tab === t ? "#38bdf8" : "rgba(122,143,166,0.5)",
                  borderBottom: `2px solid ${tab === t ? "#38bdf8" : "transparent"}`,
                  marginBottom: "-1px",
                  fontFamily: "'Cabinet Grotesk', sans-serif",
                  letterSpacing: "0.04em",
                  transition: "all 0.2s",
                  textTransform: "capitalize",
                }}>
                {t === "alerts" ? `Alerts ${alerts.length > 0 ? `(${alerts.length})` : ""}` : "Command Log"}
              </button>
            ))}
          </div>

          <div style={{ padding: "16px", maxHeight: "360px", overflowY: "auto" }}>
            {tab === "alerts" && (
              alerts.length === 0 ? (
                <div style={{
                  textAlign: "center", padding: "48px 0",
                  color: "rgba(122,143,166,0.4)",
                }}>
                  <div style={{ fontSize: "28px", marginBottom: "8px" }}>✓</div>
                  <div style={{ fontSize: "14px", fontWeight: 500, marginBottom: "4px" }}>All Systems Clear</div>
                  <div style={{ fontSize: "12px", fontFamily: "'JetBrains Mono', monospace" }}>No active alerts</div>
                </div>
              ) : (
                alerts.map(a => <AlertItem key={a.id || a.message} alert={a} />)
              )
            )}
            {tab === "command-log" && (
              cmdOutput.length === 0 ? (
                <div style={{
                  textAlign: "center", padding: "48px 0",
                  color: "rgba(122,143,166,0.4)",
                  fontFamily: "'JetBrains Mono', monospace", fontSize: "12px",
                }}>
                  No commands executed yet
                </div>
              ) : (
                <div style={{ fontFamily: "'JetBrains Mono', monospace", fontSize: "12px" }}>
                  {cmdOutput.map((line, i) => (
                    <div key={i} style={{
                      padding: "8px 0",
                      borderBottom: "1px solid rgba(255,255,255,0.04)",
                      color: "rgba(56,189,248,0.8)",
                    }}>
                      <span style={{ color: "rgba(122,143,166,0.4)", marginRight: "8px" }}>›</span>
                      {line}
                    </div>
                  ))}
                </div>
              )
            )}
          </div>
        </div>

        {/* Right — Quick Commands */}
        <div style={{
          background: "#0c1220",
          border: "1px solid rgba(255,255,255,0.06)",
          borderRadius: "14px",
          padding: "20px",
        }}>
          <div style={{
            fontFamily: "'Syne', sans-serif",
            fontSize: "14px", fontWeight: 700,
            color: "#e8f0fe", marginBottom: "4px",
          }}>Quick Commands</div>
          <div style={{
            fontSize: "11px", color: "rgba(122,143,166,0.5)",
            fontFamily: "'JetBrains Mono', monospace",
            marginBottom: "16px",
          }}>Execute across all online nodes</div>

          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "10px" }}>
            {[
              { icon: "🛡", label: "CVE Scan",    desc: "Full vulnerability audit",   type: "scan",    accent: "#38bdf8" },
              { icon: "⚡", label: "Boost",       desc: "Optimize performance",       type: "boost",   accent: "#10b981" },
              { icon: "🧹", label: "Clean",       desc: "Remove junk & temp files",   type: "clean",   accent: "#f59e0b" },
              { icon: "📊", label: "Health",      desc: "System health report",       type: "report",  accent: "#8b5cf6" },
              { icon: "🔄", label: "Restart Svc", desc: "Reload all services",        type: "restart", accent: "#f43f5e" },
              { icon: "📋", label: "Collect Logs",desc: "Gather system logs",         type: "logs",    accent: "#38bdf8" },
            ].map(cmd => (
              <CmdButton key={cmd.type} {...cmd} onClick={() => handleCommand(cmd.type)} />
            ))}
          </div>
        </div>
      </div>

      {/* Fleet Status Bar */}
      <div style={{
        background: "#0c1220",
        border: "1px solid rgba(255,255,255,0.06)",
        borderRadius: "14px",
        padding: "16px 20px",
        display: "flex", alignItems: "center",
        justifyContent: "space-between",
        flexWrap: "wrap", gap: "12px",
      }}>
        {[
          { label: "Fleet Disk",   value: overview?.avg_disk ? `${overview.avg_disk.toFixed(1)}%` : "—", accent: "#8b5cf6" },
          { label: "Hours Saved",  value: overview?.hours_saved ? `${overview.hours_saved}h` : "—",      accent: "#10b981" },
          { label: "Online",       value: `${overview?.online_machines ?? 0}/${overview?.total_machines ?? 0}`, accent: "#38bdf8" },
          { label: "Uptime",       value: overview?.fleet_uptime || "99.9%", accent: "#10b981" },
        ].map(({ label, value, accent }) => (
          <div key={label} style={{ display: "flex", alignItems: "center", gap: "12px" }}>
            <div>
              <div style={{
                fontSize: "10px", color: "rgba(122,143,166,0.5)",
                fontFamily: "'JetBrains Mono', monospace",
                letterSpacing: "0.12em", textTransform: "uppercase",
              }}>{label}</div>
              <div style={{
                fontFamily: "'Syne', sans-serif",
                fontSize: "20px", fontWeight: 800, color: accent,
              }}>{value}</div>
            </div>
            <div style={{ width: "1px", height: "36px", background: "rgba(255,255,255,0.05)" }}/>
          </div>
        ))}

        <button
          onClick={() => navigate("/overview")}
          style={{
            padding: "9px 18px",
            background: "rgba(56,189,248,0.08)",
            border: "1px solid rgba(56,189,248,0.2)",
            borderRadius: "8px", color: "#38bdf8",
            fontSize: "13px", fontWeight: 600,
            cursor: "pointer",
            fontFamily: "'Cabinet Grotesk', sans-serif",
            letterSpacing: "0.03em",
            transition: "all 0.2s",
          }}
          onMouseOver={e => { e.currentTarget.style.background = "rgba(56,189,248,0.14)"; }}
          onMouseOut={e => { e.currentTarget.style.background = "rgba(56,189,248,0.08)"; }}
        >
          View All Machines →
        </button>
      </div>

      <style>{`
        @keyframes fadeIn { from { opacity: 0; } to { opacity: 1; } }
        @keyframes pulse { 0%, 100% { opacity: 1; } 50% { opacity: 0.4; } }
        @import url('https://fonts.googleapis.com/css2?family=Syne:wght@700;800&family=JetBrains+Mono:wght@400;500&family=Cabinet+Grotesk:wght@400;500;600;700&display=swap');
      `}</style>
    </div>
  );
}
