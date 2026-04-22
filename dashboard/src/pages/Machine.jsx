import { useState, useEffect, useRef } from "react";
import { useParams, useNavigate } from "react-router-dom";
import {
  LineChart, Line, XAxis, YAxis, Tooltip,
  ResponsiveContainer, CartesianGrid, AreaChart, Area
} from "recharts";
import { getMachine, sendCommand, getLogs, connectDashboardWS } from "../api";

const FONT = "'Cabinet Grotesk', sans-serif";
const MONO = "'JetBrains Mono', monospace";
const DISP = "'Syne', sans-serif";

function MetricChart({ data, dataKey, color, label, unit = "%" }) {
  const vals = data.map(d => d[dataKey] || 0);
  const last = vals[vals.length - 1] ?? 0;
  const peak = Math.max(...vals, 1);
  const danger = last > 85;
  const warn   = last > 65;
  const c = danger ? "#f43f5e" : warn ? "#f59e0b" : color;

  return (
    <div style={{
      background: "#0c1220",
      border: `1px solid ${danger ? "rgba(244,63,94,0.2)" : "rgba(255,255,255,0.06)"}`,
      borderRadius: "12px", padding: "16px",
      transition: "border-color 0.3s",
    }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: "12px" }}>
        <div>
          <div style={{
            fontSize: "9px", color: "rgba(122,143,166,0.5)",
            fontFamily: MONO, letterSpacing: "0.18em",
            textTransform: "uppercase", marginBottom: "4px",
          }}>{label}</div>
          <div style={{
            fontFamily: DISP, fontSize: "28px", fontWeight: 800,
            color: c, lineHeight: 1, letterSpacing: "-0.02em",
          }}>{last.toFixed(1)}{unit}</div>
        </div>
        <div style={{
          padding: "4px 10px",
          background: danger ? "rgba(244,63,94,0.08)" : warn ? "rgba(245,158,11,0.08)" : "rgba(16,185,129,0.08)",
          border: `1px solid ${danger ? "rgba(244,63,94,0.2)" : warn ? "rgba(245,158,11,0.2)" : "rgba(16,185,129,0.2)"}`,
          borderRadius: "20px",
          fontSize: "10px", fontFamily: MONO,
          color: danger ? "#f43f5e" : warn ? "#f59e0b" : "#10b981",
          letterSpacing: "0.06em",
        }}>
          {danger ? "CRITICAL" : warn ? "WARNING" : "NORMAL"}
        </div>
      </div>
      <ResponsiveContainer width="100%" height={80}>
        <AreaChart data={data} margin={{ top: 0, right: 0, left: 0, bottom: 0 }}>
          <defs>
            <linearGradient id={`grad-${dataKey}`} x1="0" y1="0" x2="0" y2="1">
              <stop offset="5%"  stopColor={c} stopOpacity={0.15}/>
              <stop offset="95%" stopColor={c} stopOpacity={0}/>
            </linearGradient>
          </defs>
          <YAxis domain={[0, unit === "%" ? 100 : Math.ceil(peak * 1.3)]} hide />
          <Tooltip
            contentStyle={{
              background: "#0c1220", border: "1px solid rgba(255,255,255,0.08)",
              borderRadius: "8px", fontSize: "11px",
              fontFamily: MONO, color: "#e8f0fe",
            }}
            formatter={v => [`${v.toFixed(2)}${unit}`, label]}
            labelFormatter={() => ""}
          />
          <Area type="monotone" dataKey={dataKey}
            stroke={c} strokeWidth={1.5}
            fill={`url(#grad-${dataKey})`}
            dot={false} isAnimationActive={false}
          />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  );
}

function StatPill({ label, value, accent }) {
  return (
    <div style={{
      padding: "12px 16px",
      background: "#0c1220",
      border: "1px solid rgba(255,255,255,0.06)",
      borderRadius: "10px", flex: 1,
    }}>
      <div style={{ fontSize: "9px", color: "rgba(122,143,166,0.5)", fontFamily: MONO, letterSpacing: "0.16em", textTransform: "uppercase", marginBottom: "5px" }}>{label}</div>
      <div style={{ fontFamily: DISP, fontSize: "20px", fontWeight: 800, color: accent }}>{value}</div>
    </div>
  );
}

export default function Machine() {
  const { id }   = useParams();
  const navigate = useNavigate();

  const [machine,   setMachine]   = useState(null);
  const [graphData, setGraphData] = useState([]);
  const [logs,      setLogs]      = useState([]);
  const [terminal,  setTerminal]  = useState("");
  const [cmdStatus, setCmdStatus] = useState("idle");
  const [loading,   setLoading]   = useState(true);
  const [activeTab, setActiveTab] = useState("metrics");
  const [toast,     setToast]     = useState(null);

  const termRef = useRef(null);
  const wsRef   = useRef(null);

  const showToast = (msg, type = "success") => {
    setToast({ msg, type });
    setTimeout(() => setToast(null), 3000);
  };

  useEffect(() => {
    setLoading(true);
    Promise.all([getMachine(id), getLogs(id)])
      .then(([mRes, logRes]) => {
        const m = mRes.data;
        setMachine(m);
        setGraphData(Array(30).fill(null).map((_, i) => ({
          t: i,
          cpu:  m.cpu  || 0,
          ram:  m.ram  || 0,
          disk: m.disk || 0,
          net:  0,
        })));
        setLogs(Array.isArray(logRes.data) ? logRes.data : []);
        setLoading(false);
      })
      .catch(() => setLoading(false));

    wsRef.current = connectDashboardWS(msg => {
      if (msg.type === "metrics_update" && String(msg.node_id) === String(id)) {
        const d = msg.data || {};
        setGraphData(prev => [...prev, {
          t:    prev.length,
          cpu:  d.cpu?.cpu_percent    || 0,
          ram:  d.memory?.ram_percent || 0,
          disk: d.disks?.[0]?.percent || 0,
          net:  0,
        }].slice(-60));
      }
      if (msg.type === "cmd_output") {
        setTerminal(prev => prev + msg.output);
        if (msg.status === "done" || msg.status === "failed") setCmdStatus(msg.status);
        setTimeout(() => { if (termRef.current) termRef.current.scrollTop = termRef.current.scrollHeight; }, 50);
      }
    });

    return () => wsRef.current?.close();
  }, [id]);

  const handleCommand = async (cmd) => {
    if (cmdStatus === "running") return;
    if (["fix", "rollback"].includes(cmd) && !window.confirm(`Run ${cmd.toUpperCase()} on ${machine?.hostname}?`)) return;
    try {
      setCmdStatus("running");
      setTerminal(`> Executing ${cmd} on ${machine?.hostname}...\n`);
      await sendCommand(id, cmd);
      showToast(`${cmd} command dispatched`, "success");
    } catch (e) {
      setTerminal(`Error: ${e.response?.data?.detail || e.message}\n`);
      setCmdStatus("failed");
      showToast(e.response?.data?.detail || e.message, "error");
    }
  };

  if (loading) return (
    <div style={{ fontFamily: FONT, color: "#e8f0fe" }}>
      <div style={{ display: "flex", alignItems: "center", gap: "12px", padding: "40px 0", color: "rgba(122,143,166,0.4)" }}>
        <div style={{ width: "16px", height: "16px", border: "2px solid rgba(56,189,248,0.3)", borderTopColor: "#38bdf8", borderRadius: "50%", animation: "spin 0.7s linear infinite" }}/>
        Loading machine data...
      </div>
      <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>
    </div>
  );

  if (!machine) return (
    <div style={{ fontFamily: FONT, color: "#f43f5e", padding: "40px 0" }}>Machine not found</div>
  );

  const health = machine.health_score || 0;
  const healthColor = health > 70 ? "#10b981" : health > 40 ? "#f59e0b" : "#f43f5e";
  const online = machine.is_online;

  const cmds = [
    { id: "scan",     label: "CVE Scan",   accent: "#38bdf8" },
    { id: "boost",    label: "Boost",      accent: "#10b981" },
    { id: "clean",    label: "Clean",      accent: "#f59e0b" },
    { id: "fix",      label: "Auto-Fix",   accent: "#8b5cf6" },
    { id: "rollback", label: "Rollback",   accent: "#f43f5e" },
  ];

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

      {/* Back */}
      <button onClick={() => navigate("/overview")} style={{
        background: "none", border: "none",
        color: "rgba(56,189,248,0.6)", cursor: "pointer",
        fontSize: "12px", fontFamily: MONO, padding: "0",
        marginBottom: "20px", letterSpacing: "0.08em",
        display: "flex", alignItems: "center", gap: "6px",
        transition: "color 0.2s",
      }}
        onMouseOver={e => e.currentTarget.style.color = "#38bdf8"}
        onMouseOut={e => e.currentTarget.style.color = "rgba(56,189,248,0.6)"}
      >
        ← ALL MACHINES
      </button>

      {/* Header */}
      <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", marginBottom: "24px" }}>
        <div style={{ display: "flex", alignItems: "center", gap: "14px" }}>
          <div style={{
            width: "48px", height: "48px", borderRadius: "13px",
            background: online ? "rgba(56,189,248,0.08)" : "rgba(244,63,94,0.08)",
            border: `1px solid ${online ? "rgba(56,189,248,0.2)" : "rgba(244,63,94,0.2)"}`,
            display: "flex", alignItems: "center", justifyContent: "center",
            fontSize: "22px",
          }}>🐧</div>
          <div>
            <h1 style={{ fontFamily: DISP, fontSize: "24px", fontWeight: 800, letterSpacing: "-0.02em" }}>
              {machine.hostname}
            </h1>
            <div style={{ fontSize: "12px", color: "rgba(122,143,166,0.6)", fontFamily: MONO, marginTop: "2px" }}>
              {machine.os_pretty || machine.os_type} · {machine.ip_address || "IP not set"}
            </div>
          </div>
        </div>

        <div style={{ display: "flex", gap: "10px", alignItems: "center" }}>
          <div style={{
            display: "flex", alignItems: "center", gap: "6px",
            padding: "6px 12px",
            background: online ? "rgba(16,185,129,0.08)" : "rgba(244,63,94,0.08)",
            border: `1px solid ${online ? "rgba(16,185,129,0.25)" : "rgba(244,63,94,0.25)"}`,
            borderRadius: "20px",
          }}>
            <div style={{
              width: "6px", height: "6px", borderRadius: "50%",
              background: online ? "#10b981" : "#f43f5e",
              boxShadow: online ? "0 0 6px #10b981" : "none",
              animation: online ? "pulse 2s infinite" : "none",
            }}/>
            <span style={{ fontSize: "11px", fontWeight: 600, fontFamily: MONO, color: online ? "#10b981" : "#f43f5e" }}>
              {online ? "ONLINE" : "OFFLINE"}
            </span>
          </div>
          <div style={{
            padding: "6px 14px",
            background: `${healthColor}10`,
            border: `1px solid ${healthColor}30`,
            borderRadius: "20px",
            fontSize: "11px", fontFamily: MONO, color: healthColor,
          }}>
            Health {health}%
          </div>
        </div>
      </div>

      {/* Quick Stats */}
      <div style={{ display: "flex", gap: "10px", marginBottom: "20px" }}>
        <StatPill label="CPU"  value={`${(machine.cpu  || 0).toFixed(1)}%`} accent={machine.cpu  > 85 ? "#f43f5e" : machine.cpu  > 65 ? "#f59e0b" : "#38bdf8"} />
        <StatPill label="RAM"  value={`${(machine.ram  || 0).toFixed(1)}%`} accent={machine.ram  > 85 ? "#f43f5e" : machine.ram  > 65 ? "#f59e0b" : "#8b5cf6"} />
        <StatPill label="Disk" value={`${(machine.disk || 0).toFixed(1)}%`} accent={machine.disk > 90 ? "#f43f5e" : machine.disk > 75 ? "#f59e0b" : "#10b981"} />
        <StatPill label="Last Seen" value={machine.last_seen ? new Date(machine.last_seen).toLocaleTimeString() : "—"} accent="#38bdf8" />
      </div>

      {/* Tabs */}
      <div style={{
        display: "flex", gap: "2px",
        background: "rgba(255,255,255,0.02)",
        border: "1px solid rgba(255,255,255,0.05)",
        borderRadius: "10px", padding: "4px",
        marginBottom: "20px", width: "fit-content",
      }}>
        {["metrics", "terminal", "audit"].map(tab => (
          <button key={tab} onClick={() => setActiveTab(tab)} style={{
            padding: "7px 18px", border: "none", borderRadius: "7px",
            background: activeTab === tab ? "#0c1220" : "transparent",
            color: activeTab === tab ? "#38bdf8" : "rgba(122,143,166,0.5)",
            fontSize: "12px", fontWeight: activeTab === tab ? 600 : 400,
            cursor: "pointer", fontFamily: FONT,
            boxShadow: activeTab === tab ? "0 2px 8px rgba(0,0,0,0.3)" : "none",
            transition: "all 0.15s", textTransform: "capitalize",
            letterSpacing: "0.03em",
          }}>{tab}</button>
        ))}
      </div>

      {/* Tab: Metrics */}
      {activeTab === "metrics" && (
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "12px" }}>
          <MetricChart data={graphData} dataKey="cpu"  color="#38bdf8" label="CPU Usage"    unit="%" />
          <MetricChart data={graphData} dataKey="ram"  color="#8b5cf6" label="Memory Usage" unit="%" />
          <MetricChart data={graphData} dataKey="disk" color="#10b981" label="Disk Usage"   unit="%" />
          <MetricChart data={graphData} dataKey="net"  color="#f59e0b" label="Net I/O"      unit=" MB/s" />
        </div>
      )}

      {/* Tab: Terminal */}
      {activeTab === "terminal" && (
        <div>
          {/* Command buttons */}
          <div style={{
            background: "#0c1220",
            border: "1px solid rgba(255,255,255,0.06)",
            borderRadius: "12px", padding: "16px",
            marginBottom: "14px",
          }}>
            <div style={{
              display: "flex", alignItems: "center",
              justifyContent: "space-between", marginBottom: "14px",
            }}>
              <div style={{ fontSize: "11px", color: "rgba(122,143,166,0.5)", fontFamily: MONO, letterSpacing: "0.16em", textTransform: "uppercase" }}>
                Remote Execution
              </div>
              <div style={{
                fontSize: "10px", fontFamily: MONO, letterSpacing: "0.08em",
                color: cmdStatus === "running" ? "#f59e0b" : cmdStatus === "done" ? "#10b981" : cmdStatus === "failed" ? "#f43f5e" : "rgba(122,143,166,0.3)",
                display: "flex", alignItems: "center", gap: "5px",
              }}>
                {cmdStatus !== "idle" && (
                  <>
                    <div style={{ width: "5px", height: "5px", borderRadius: "50%", background: "currentColor" }}/>
                    {cmdStatus.toUpperCase()}
                  </>
                )}
              </div>
            </div>
            <div style={{ display: "flex", gap: "8px", flexWrap: "wrap" }}>
              {cmds.map(({ id: cmd, label, accent }) => (
                <button key={cmd}
                  onClick={() => handleCommand(cmd)}
                  disabled={cmdStatus === "running"}
                  style={{
                    padding: "8px 16px",
                    background: `${accent}0a`,
                    border: `1px solid ${cmdStatus === "running" ? "rgba(255,255,255,0.05)" : `${accent}30`}`,
                    borderRadius: "8px",
                    color: cmdStatus === "running" ? "rgba(122,143,166,0.3)" : accent,
                    fontSize: "12px", fontWeight: 600,
                    cursor: cmdStatus === "running" ? "not-allowed" : "pointer",
                    fontFamily: FONT, letterSpacing: "0.03em",
                    transition: "all 0.15s",
                  }}
                  onMouseOver={e => { if (cmdStatus !== "running") e.currentTarget.style.background = `${accent}18`; }}
                  onMouseOut={e => { e.currentTarget.style.background = `${accent}0a`; }}
                >{label}</button>
              ))}
              <button onClick={() => { setTerminal(""); setCmdStatus("idle"); }} style={{
                padding: "8px 14px", background: "transparent",
                border: "1px solid rgba(255,255,255,0.05)",
                borderRadius: "8px", color: "rgba(122,143,166,0.4)",
                fontSize: "12px", cursor: "pointer", fontFamily: FONT,
              }}>Clear</button>
            </div>
          </div>

          {/* Terminal output */}
          <div ref={termRef} style={{
            background: "#040810",
            border: "1px solid rgba(255,255,255,0.06)",
            borderRadius: "12px", padding: "16px",
            fontFamily: MONO, fontSize: "12px",
            color: "#10b981", height: "260px",
            overflowY: "auto",
            whiteSpace: "pre-wrap", lineHeight: "1.8",
            boxShadow: "inset 0 2px 12px rgba(0,0,0,0.5)",
          }}>
            <div style={{ color: "rgba(56,189,248,0.4)", marginBottom: "6px", fontSize: "10px", letterSpacing: "0.12em" }}>
              JENIX REMOTE SHELL · {machine.hostname}
            </div>
            {terminal || (
              <span style={{ color: "rgba(16,185,129,0.4)" }}>
                ▊ Ready. Select a command above to execute remotely.
              </span>
            )}
          </div>
        </div>
      )}

      {/* Tab: Audit */}
      {activeTab === "audit" && (
        <div style={{
          background: "#0c1220",
          border: "1px solid rgba(255,255,255,0.06)",
          borderRadius: "12px", overflow: "hidden",
        }}>
          <div style={{ padding: "16px 20px", borderBottom: "1px solid rgba(255,255,255,0.05)" }}>
            <span style={{ fontSize: "11px", color: "rgba(122,143,166,0.5)", fontFamily: MONO, letterSpacing: "0.16em", textTransform: "uppercase" }}>
              Audit Log · {logs.length} entries
            </span>
          </div>
          {logs.length === 0 ? (
            <div style={{ padding: "48px", textAlign: "center", color: "rgba(122,143,166,0.3)", fontFamily: MONO, fontSize: "12px" }}>
              No actions recorded yet
            </div>
          ) : (
            <div style={{ maxHeight: "400px", overflowY: "auto" }}>
              {logs.map((l, i) => (
                <div key={l.id || i} style={{
                  display: "flex", gap: "14px", alignItems: "flex-start",
                  padding: "12px 20px",
                  borderBottom: "1px solid rgba(255,255,255,0.03)",
                  transition: "background 0.15s",
                }}
                  onMouseOver={e => e.currentTarget.style.background = "rgba(255,255,255,0.02)"}
                  onMouseOut={e => e.currentTarget.style.background = "transparent"}
                >
                  <div style={{ fontFamily: MONO, fontSize: "10px", color: "rgba(122,143,166,0.4)", whiteSpace: "nowrap", marginTop: "1px" }}>
                    {l.timestamp?.slice(11, 19) || "—"}
                  </div>
                  <div style={{
                    width: "6px", height: "6px", borderRadius: "50%", flexShrink: 0, marginTop: "4px",
                    background: l.status === "ok" ? "#10b981" : l.status === "warning" ? "#f59e0b" : l.status === "critical" ? "#f43f5e" : "#38bdf8",
                  }}/>
                  <div style={{ flex: 1 }}>
                    <span style={{ color: "#38bdf8", fontFamily: MONO, fontSize: "11px", fontWeight: 600 }}>{l.action}</span>
                    <span style={{ color: "rgba(122,143,166,0.5)", fontSize: "12px", marginLeft: "8px" }}>{l.detail}</span>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      <style>{`
        @keyframes pulse { 0%, 100% { opacity: 1; } 50% { opacity: 0.4; } }
        @keyframes spin  { to { transform: rotate(360deg); } }
        @import url('https://fonts.googleapis.com/css2?family=Syne:wght@700;800&family=JetBrains+Mono:wght@400;500&family=Cabinet+Grotesk:wght@400;500;600;700&display=swap');
      `}</style>
    </div>
  );
}
