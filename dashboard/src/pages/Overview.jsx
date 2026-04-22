import { useState, useEffect, useRef } from "react";
import { useNavigate } from "react-router-dom";
import { getMachines, sendCommand, connectDashboardWS } from "../api";

function MiniBar({ value, accent }) {
  const pct = Math.min(value, 100);
  const color = pct > 85 ? "#f43f5e" : pct > 65 ? "#f59e0b" : accent;
  return (
    <div style={{
      height: "3px", background: "rgba(255,255,255,0.05)",
      borderRadius: "2px", overflow: "hidden", marginTop: "3px",
    }}>
      <div style={{
        width: `${pct}%`, height: "100%",
        background: color, borderRadius: "2px",
        transition: "width 0.6s cubic-bezier(0.16,1,0.3,1)",
        boxShadow: pct > 85 ? `0 0 6px ${color}` : "none",
      }}/>
    </div>
  );
}

function MachineCard({ machine, liveMetrics, onCommand, style = {} }) {
  const navigate = useNavigate();
  const [hov, setHov] = useState(false);
  const [cmdLoading, setCmdLoading] = useState(null);
  const m = liveMetrics[machine.id] || {};
  const cpu  = m.cpu  ?? machine.last_cpu  ?? 0;
  const ram  = m.ram  ?? machine.last_ram  ?? 0;
  const disk = m.disk ?? machine.last_disk ?? 0;
  const online = machine.status === "online";

  const osIcon = machine.os_name?.toLowerCase().includes("ubuntu") ? "🐧"
    : machine.os_name?.toLowerCase().includes("debian") ? "🐧"
    : machine.os_name?.toLowerCase().includes("centos") ? "🔴"
    : machine.os_name?.toLowerCase().includes("windows") ? "🪟"
    : machine.os_name?.toLowerCase().includes("mac") ? "🍎" : "🖥";

  const health = online ? Math.round(100 - (cpu * 0.4 + ram * 0.3 + disk * 0.3)) : 0;
  const healthColor = health > 70 ? "#10b981" : health > 40 ? "#f59e0b" : "#f43f5e";

  return (
    <div
      onClick={() => navigate(`/machines/${machine.id}`)}
      onMouseEnter={() => setHov(true)}
      onMouseLeave={() => setHov(false)}
      style={{
        background: "#0c1220",
        border: `1px solid ${hov ? (online ? "rgba(56,189,248,0.25)" : "rgba(244,63,94,0.2)") : "rgba(255,255,255,0.06)"}`,
        borderRadius: "14px", padding: "20px",
        cursor: "pointer",
        transition: "all 0.2s cubic-bezier(0.16,1,0.3,1)",
        transform: hov ? "translateY(-2px)" : "translateY(0)",
        boxShadow: hov ? "0 8px 32px rgba(0,0,0,0.4)" : "none",
        position: "relative", overflow: "hidden",
        ...style,
      }}
    >
      {/* Top highlight */}
      {hov && (
        <div style={{
          position: "absolute", top: 0, left: "20%", right: "20%", height: "1px",
          background: `linear-gradient(90deg, transparent, rgba(56,189,248,0.5), transparent)`,
        }}/>
      )}

      {/* Header */}
      <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", marginBottom: "14px" }}>
        <div style={{ display: "flex", alignItems: "center", gap: "10px" }}>
          <div style={{
            width: "38px", height: "38px", borderRadius: "10px",
            background: online ? "rgba(56,189,248,0.08)" : "rgba(244,63,94,0.08)",
            border: `1px solid ${online ? "rgba(56,189,248,0.15)" : "rgba(244,63,94,0.15)"}`,
            display: "flex", alignItems: "center", justifyContent: "center",
            fontSize: "18px", flexShrink: 0,
          }}>{osIcon}</div>
          <div>
            <div style={{
              fontFamily: "'Syne', sans-serif",
              fontSize: "14px", fontWeight: 700, color: "#e8f0fe",
            }}>{machine.hostname}</div>
            <div style={{
              fontSize: "11px", color: "rgba(122,143,166,0.5)",
              fontFamily: "'JetBrains Mono', monospace",
              marginTop: "1px",
            }}>{machine.ip}</div>
          </div>
        </div>

        <div style={{ display: "flex", flexDirection: "column", alignItems: "flex-end", gap: "6px" }}>
          <div style={{
            display: "flex", alignItems: "center", gap: "5px",
            padding: "3px 9px",
            background: online ? "rgba(16,185,129,0.08)" : "rgba(244,63,94,0.08)",
            border: `1px solid ${online ? "rgba(16,185,129,0.2)" : "rgba(244,63,94,0.2)"}`,
            borderRadius: "20px",
          }}>
            <div style={{
              width: "5px", height: "5px", borderRadius: "50%",
              background: online ? "#10b981" : "#f43f5e",
              boxShadow: online ? "0 0 5px #10b981" : "none",
              animation: online ? "pulse 2s infinite" : "none",
            }}/>
            <span style={{
              fontSize: "10px", fontWeight: 600,
              color: online ? "#10b981" : "#f43f5e",
              fontFamily: "'JetBrains Mono', monospace",
              letterSpacing: "0.06em",
            }}>{online ? "ONLINE" : "OFFLINE"}</span>
          </div>

          {online && (
            <div style={{
              fontSize: "11px", fontFamily: "'JetBrains Mono', monospace",
              color: healthColor, display: "flex", alignItems: "center", gap: "4px",
            }}>
              <span style={{ fontSize: "8px" }}>◈</span>
              Health {health}%
            </div>
          )}
        </div>
      </div>

      {/* OS tag */}
      <div style={{
        display: "inline-flex", alignItems: "center", gap: "5px",
        padding: "2px 8px", borderRadius: "4px",
        background: "rgba(255,255,255,0.03)",
        border: "1px solid rgba(255,255,255,0.06)",
        fontSize: "10px", color: "rgba(122,143,166,0.5)",
        fontFamily: "'JetBrains Mono', monospace",
        marginBottom: "14px",
      }}>
        {machine.os_name || "Linux"}
      </div>

      {/* Metrics */}
      {online && (
        <div style={{ marginBottom: "16px" }}>
          {[
            { label: "CPU",  value: cpu,  accent: "#38bdf8" },
            { label: "RAM",  value: ram,  accent: "#8b5cf6" },
            { label: "Disk", value: disk, accent: "#10b981" },
          ].map(({ label, value, accent }) => (
            <div key={label} style={{ marginBottom: "8px" }}>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                <span style={{
                  fontSize: "10px", color: "rgba(122,143,166,0.5)",
                  fontFamily: "'JetBrains Mono', monospace",
                  letterSpacing: "0.1em",
                }}>{label}</span>
                <span style={{
                  fontSize: "11px", fontWeight: 600,
                  color: value > 85 ? "#f43f5e" : value > 65 ? "#f59e0b" : accent,
                  fontFamily: "'JetBrains Mono', monospace",
                }}>{value.toFixed(1)}%</span>
              </div>
              <MiniBar value={value} accent={accent} />
            </div>
          ))}
        </div>
      )}

      {/* Actions */}
      {online && (
        <div style={{ display: "flex", gap: "6px" }}
          onClick={e => e.stopPropagation()}>
          {[
            { cmd: "scan",  label: "Scan",  accent: "#38bdf8" },
            { cmd: "boost", label: "Boost", accent: "#10b981" },
            { cmd: "clean", label: "Clean", accent: "#f59e0b" },
          ].map(({ cmd, label, accent }) => (
            <button key={cmd}
              onClick={() => { setCmdLoading(cmd); onCommand(machine.id, cmd).finally(() => setCmdLoading(null)); }}
              style={{
                flex: 1, padding: "7px 4px",
                background: `${accent}0a`,
                border: `1px solid ${accent}20`,
                borderRadius: "8px",
                color: cmdLoading === cmd ? accent : "rgba(122,143,166,0.6)",
                fontSize: "11px", cursor: "pointer",
                fontFamily: "'JetBrains Mono', monospace",
                fontWeight: 500, letterSpacing: "0.06em",
                transition: "all 0.15s",
              }}
              onMouseOver={e => {
                e.currentTarget.style.background = `${accent}18`;
                e.currentTarget.style.color = accent;
              }}
              onMouseOut={e => {
                e.currentTarget.style.background = `${accent}0a`;
                e.currentTarget.style.color = "rgba(122,143,166,0.6)";
              }}
            >
              {cmdLoading === cmd ? "..." : label}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

export default function Overview() {
  const [machines,    setMachines]    = useState([]);
  const [liveMetrics, setLiveMetrics] = useState({});
  const [search,      setSearch]      = useState("");
  const [filter,      setFilter]      = useState("all");
  const [toast,       setToast]       = useState("");
  const [view,        setView]        = useState("grid");
  const wsRef = useRef(null);

  useEffect(() => {
    getMachines().then(r => setMachines(r.data)).catch(console.error);
    const iv = setInterval(() => {
      getMachines().then(r => setMachines(r.data)).catch(console.error);
    }, 10_000);
    wsRef.current = connectDashboardWS(msg => {
      if (msg.type === "metrics") {
        setLiveMetrics(p => ({ ...p, [msg.machine_id]: { cpu: msg.cpu, ram: msg.ram, disk: msg.disk } }));
      }
      if (msg.type === "status") {
        setMachines(p => p.map(m => m.id === msg.machine_id ? { ...m, status: msg.status } : m));
      }
    });
    return () => { clearInterval(iv); wsRef.current?.close(); };
  }, []);

  const handleCommand = async (id, cmd) => {
    try {
      await sendCommand(id, cmd);
      setToast(`✓ ${cmd} dispatched`);
    } catch (e) {
      setToast(`✗ ${e.response?.data?.detail || e.message}`);
    }
    setTimeout(() => setToast(""), 3000);
  };

  const online  = machines.filter(m => m.status === "online").length;
  const offline = machines.length - online;

  const filtered = machines
    .filter(m => {
      if (filter === "online")  return m.status === "online";
      if (filter === "offline") return m.status !== "online";
      return true;
    })
    .filter(m => m.hostname.toLowerCase().includes(search.toLowerCase()) ||
                 (m.ip || "").includes(search))
    .sort((a, b) => (b.status === "online") - (a.status === "online"));

  return (
    <div style={{ fontFamily: "'Cabinet Grotesk', sans-serif", color: "#e8f0fe" }}>
      {toast && (
        <div style={{
          position: "fixed", top: "24px", right: "24px", zIndex: 9999,
          padding: "12px 18px",
          background: toast.startsWith("✓") ? "rgba(16,185,129,0.12)" : "rgba(244,63,94,0.12)",
          border: `1px solid ${toast.startsWith("✓") ? "rgba(16,185,129,0.3)" : "rgba(244,63,94,0.3)"}`,
          borderRadius: "10px",
          color: toast.startsWith("✓") ? "#10b981" : "#f43f5e",
          fontSize: "13px", fontFamily: "'JetBrains Mono', monospace",
        }}>{toast}</div>
      )}

      {/* Header */}
      <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", marginBottom: "24px" }}>
        <div>
          <div style={{
            fontSize: "10px", color: "rgba(56,189,248,0.6)",
            fontFamily: "'JetBrains Mono', monospace",
            letterSpacing: "0.2em", textTransform: "uppercase", marginBottom: "6px",
          }}>Infrastructure</div>
          <h1 style={{
            fontFamily: "'Syne', sans-serif",
            fontSize: "26px", fontWeight: 800, letterSpacing: "-0.02em",
          }}>All Machines</h1>
          <p style={{ color: "rgba(122,143,166,0.6)", fontSize: "13px", marginTop: "5px" }}>
            {machines.length} total ·
            <span style={{ color: "#10b981" }}> {online} online</span> ·
            <span style={{ color: "#f43f5e" }}> {offline} offline</span>
          </p>
        </div>

        {/* Filter pills */}
        <div style={{ display: "flex", gap: "6px", alignItems: "center" }}>
          {["all", "online", "offline"].map(f => (
            <button key={f} onClick={() => setFilter(f)} style={{
              padding: "7px 14px",
              background: filter === f ? "rgba(56,189,248,0.12)" : "rgba(255,255,255,0.02)",
              border: `1px solid ${filter === f ? "rgba(56,189,248,0.3)" : "rgba(255,255,255,0.06)"}`,
              borderRadius: "20px", color: filter === f ? "#38bdf8" : "rgba(122,143,166,0.5)",
              fontSize: "12px", fontWeight: filter === f ? 600 : 400,
              cursor: "pointer", fontFamily: "'Cabinet Grotesk', sans-serif",
              textTransform: "capitalize", transition: "all 0.15s",
            }}>{f}</button>
          ))}
        </div>
      </div>

      {/* Search */}
      <div style={{ position: "relative", marginBottom: "20px", maxWidth: "360px" }}>
        <span style={{
          position: "absolute", left: "12px", top: "50%", transform: "translateY(-50%)",
          color: "rgba(122,143,166,0.4)", fontSize: "14px", pointerEvents: "none",
        }}>⌕</span>
        <input
          placeholder="Search by hostname or IP..."
          value={search} onChange={e => setSearch(e.target.value)}
          style={{
            width: "100%", padding: "10px 14px 10px 34px",
            background: "#0c1220",
            border: "1px solid rgba(255,255,255,0.06)",
            borderRadius: "10px", color: "#e8f0fe",
            fontSize: "13px", outline: "none",
            fontFamily: "'Cabinet Grotesk', sans-serif",
            transition: "border-color 0.2s",
          }}
          onFocus={e => { e.target.style.borderColor = "rgba(56,189,248,0.3)"; }}
          onBlur={e => { e.target.style.borderColor = "rgba(255,255,255,0.06)"; }}
        />
      </div>

      {/* Grid */}
      {filtered.length === 0 ? (
        <div style={{
          textAlign: "center", padding: "80px 0",
          color: "rgba(122,143,166,0.3)",
        }}>
          <div style={{ fontSize: "32px", marginBottom: "12px" }}>⬡</div>
          <div style={{ fontSize: "15px", fontWeight: 600, marginBottom: "6px" }}>No machines found</div>
          <div style={{ fontSize: "12px", fontFamily: "'JetBrains Mono', monospace" }}>
            Deploy the JENIX agent to connect machines
          </div>
        </div>
      ) : (
        <div style={{
          display: "grid",
          gridTemplateColumns: "repeat(auto-fill, minmax(300px, 1fr))",
          gap: "14px",
        }}>
          {filtered.map((m, i) => (
            <MachineCard key={m.id} machine={m}
              liveMetrics={liveMetrics}
              onCommand={handleCommand}
              style={{ animationDelay: `${i * 40}ms` }}
            />
          ))}
        </div>
      )}

      <style>{`
        @keyframes pulse { 0%, 100% { opacity: 1; } 50% { opacity: 0.4; } }
        @import url('https://fonts.googleapis.com/css2?family=Syne:wght@700;800&family=JetBrains+Mono:wght@400;500&family=Cabinet+Grotesk:wght@400;500;600;700&display=swap');
      `}</style>
    </div>
  );
}
