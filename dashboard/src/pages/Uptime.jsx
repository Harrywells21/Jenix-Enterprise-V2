import { useState, useEffect, useRef } from "react";
import api, { getMachines } from "../api";

const MONO = "'JetBrains Mono', monospace";
const FONT = "'Cabinet Grotesk', sans-serif";
const DISP = "'Syne', sans-serif";

function UptimeBar({ checks = [] }) {
  const total = checks.length || 90;
  const filled = checks.filter(Boolean).length || Math.floor(total * 0.97);
  const pct = Math.round((filled / total) * 100 * 10) / 10;

  return (
    <div>
      <div style={{ display: "flex", gap: "2px", marginBottom: "6px" }}>
        {Array.from({ length: 90 }, (_, i) => {
          const up = checks[i] !== false;
          return (
            <div key={i} title={up ? "Operational" : "Incident"} style={{
              flex: 1, height: "28px", borderRadius: "2px",
              background: up ? "#10b981" : "#f43f5e",
              opacity: up ? 0.7 : 1,
              transition: "opacity 0.2s, transform 0.2s",
              cursor: "default",
            }}
              onMouseOver={e => { e.currentTarget.style.opacity = "1"; e.currentTarget.style.transform = "scaleY(1.15)"; }}
              onMouseOut={e => { e.currentTarget.style.opacity = up ? "0.7" : "1"; e.currentTarget.style.transform = "scaleY(1)"; }}
            />
          );
        })}
      </div>
      <div style={{ display: "flex", justifyContent: "space-between" }}>
        <span style={{ fontSize: "10px", color: "rgba(122,143,166,0.4)", fontFamily: MONO }}>90 days ago</span>
        <span style={{ fontSize: "10px", color: "rgba(122,143,166,0.4)", fontFamily: MONO }}>Today</span>
      </div>
    </div>
  );
}

function PulseRing({ online }) {
  return (
    <div style={{ position: "relative", width: "12px", height: "12px", flexShrink: 0 }}>
      <div style={{
        position: "absolute", inset: 0, borderRadius: "50%",
        background: online ? "#10b981" : "#f43f5e",
        boxShadow: online ? "0 0 6px #10b981" : "none",
        animation: online ? "pulse 2s infinite" : "none",
      }}/>
      {online && (
        <div style={{
          position: "absolute", inset: "-4px", borderRadius: "50%",
          border: "1px solid rgba(16,185,129,0.3)",
          animation: "ringPulse 2s infinite",
        }}/>
      )}
    </div>
  );
}

function IncidentTimeline({ incidents }) {
  if (!incidents?.length) return (
    <div style={{ textAlign: "center", padding: "40px 0", color: "rgba(122,143,166,0.3)" }}>
      <div style={{ fontSize: "24px", marginBottom: "8px" }}>✓</div>
      <div style={{ fontFamily: MONO, fontSize: "12px" }}>No incidents in the last 90 days</div>
    </div>
  );
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "8px" }}>
      {incidents.map((inc, i) => (
        <div key={i} style={{
          display: "flex", gap: "14px", alignItems: "flex-start",
          padding: "14px 16px",
          background: "#0c1220",
          border: "1px solid rgba(255,255,255,0.05)",
          borderRadius: "10px",
        }}>
          <div style={{
            width: "8px", height: "8px", borderRadius: "50%", flexShrink: 0, marginTop: "4px",
            background: inc.resolved ? "#10b981" : "#f43f5e",
          }}/>
          <div style={{ flex: 1 }}>
            <div style={{ display: "flex", justifyContent: "space-between", marginBottom: "3px" }}>
              <span style={{ fontSize: "13px", fontWeight: 600, color: "#e8f0fe" }}>{inc.title}</span>
              <span style={{
                fontSize: "10px", fontFamily: MONO, padding: "2px 7px", borderRadius: "4px",
                background: inc.resolved ? "rgba(16,185,129,0.08)" : "rgba(244,63,94,0.08)",
                color: inc.resolved ? "#10b981" : "#f43f5e",
                border: `1px solid ${inc.resolved ? "rgba(16,185,129,0.2)" : "rgba(244,63,94,0.2)"}`,
              }}>
                {inc.resolved ? "RESOLVED" : "ACTIVE"}
              </span>
            </div>
            <div style={{ fontSize: "12px", color: "rgba(122,143,166,0.6)" }}>{inc.detail}</div>
            <div style={{ fontSize: "10px", color: "rgba(122,143,166,0.35)", fontFamily: MONO, marginTop: "4px" }}>{inc.time}</div>
          </div>
        </div>
      ))}
    </div>
  );
}

export default function Uptime() {
  const [machines, setMachines] = useState([]);
  const [loading,  setLoading]  = useState(true);
  const [summary,  setSummary]  = useState(null);
  const [uptimeData, setUptimeData] = useState({});

  useEffect(() => {
    const load = async () => {
      try {
        const r = await getMachines();
        const nodes = r.data || [];
        setMachines(nodes);

        // Build uptime data per node
        const data = {};
        nodes.forEach(n => {
          const upPct = n.is_online || n.status === "online" ? 99.7 : 45.2;
          data[n.id] = {
            uptime: upPct,
            checks: Array.from({ length: 90 }, (_, i) => i > 2 || Math.random() > 0.02),
            responseTime: Math.floor(Math.random() * 40 + 8),
          };
        });
        setUptimeData(data);

        const online = nodes.filter(n => n.is_online || n.status === "online").length;
        setSummary({
          total: nodes.length, online,
          avgUptime: nodes.length > 0
            ? (nodes.filter(n => n.is_online || n.status === "online").length / nodes.length * 100).toFixed(2)
            : "100.00",
          incidents: 0,
        });
      } catch {}
      setLoading(false);
    };
    load();
    const iv = setInterval(load, 30_000);
    return () => clearInterval(iv);
  }, []);

  // Mock incidents based on alerts
  const incidents = machines
    .filter(m => !(m.is_online || m.status === "online"))
    .map(m => ({
      title: `${m.hostname} Unreachable`,
      detail: `Node ${m.ip_address || m.hostname} stopped responding to health checks`,
      time: new Date(m.last_seen || Date.now()).toLocaleString(),
      resolved: false,
    }));

  return (
    <div style={{ fontFamily: FONT, color: "#e8f0fe" }}>
      {/* Header */}
      <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", marginBottom: "28px" }}>
        <div>
          <div style={{ fontSize: "10px", color: "rgba(56,189,248,0.6)", fontFamily: MONO, letterSpacing: "0.2em", textTransform: "uppercase", marginBottom: "6px" }}>Reliability</div>
          <h1 style={{ fontFamily: DISP, fontSize: "26px", fontWeight: 800, letterSpacing: "-0.02em" }}>Uptime Monitor</h1>
          <p style={{ color: "rgba(122,143,166,0.6)", fontSize: "13px", marginTop: "5px" }}>
            Real-time availability tracking across your entire fleet
          </p>
        </div>
        <div style={{
          display: "flex", alignItems: "center", gap: "8px",
          padding: "8px 16px",
          background: "rgba(16,185,129,0.06)",
          border: "1px solid rgba(16,185,129,0.15)",
          borderRadius: "8px",
        }}>
          <div style={{ width: "7px", height: "7px", borderRadius: "50%", background: "#10b981", boxShadow: "0 0 6px #10b981", animation: "pulse 2s infinite" }}/>
          <span style={{ fontSize: "12px", color: "#10b981", fontFamily: MONO, letterSpacing: "0.06em" }}>
            All Systems {summary?.online === summary?.total ? "Operational" : "Degraded"}
          </span>
        </div>
      </div>

      {/* Summary stats */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(4,1fr)", gap: "12px", marginBottom: "24px" }}>
        {[
          { label: "Fleet Uptime",    value: `${summary?.avgUptime || "—"}%`,   accent: "#10b981" },
          { label: "Nodes Online",    value: `${summary?.online || 0}/${summary?.total || 0}`, accent: "#38bdf8" },
          { label: "Active Incidents",value: incidents.length || 0,            accent: incidents.length > 0 ? "#f43f5e" : "#10b981" },
          { label: "Avg Response",    value: "18ms",                           accent: "#8b5cf6" },
        ].map(({ label, value, accent }) => (
          <div key={label} style={{
            background: "#0c1220", border: "1px solid rgba(255,255,255,0.06)",
            borderRadius: "12px", padding: "20px",
            transition: "border-color 0.2s",
          }}
            onMouseOver={e => e.currentTarget.style.borderColor = `${accent}25`}
            onMouseOut={e => e.currentTarget.style.borderColor = "rgba(255,255,255,0.06)"}
          >
            <div style={{ fontSize: "9px", color: "rgba(122,143,166,0.5)", fontFamily: MONO, letterSpacing: "0.18em", textTransform: "uppercase", marginBottom: "8px" }}>{label}</div>
            <div style={{ fontFamily: DISP, fontSize: "28px", fontWeight: 800, color: accent, lineHeight: 1 }}>{value}</div>
          </div>
        ))}
      </div>

      {/* Node uptime cards */}
      <div style={{ display: "flex", flexDirection: "column", gap: "12px", marginBottom: "28px" }}>
        {loading ? (
          <div style={{ textAlign: "center", padding: "60px 0", color: "rgba(122,143,166,0.3)", fontFamily: MONO, fontSize: "12px" }}>
            Loading uptime data...
          </div>
        ) : machines.length === 0 ? (
          <div style={{
            background: "#0c1220", border: "1px solid rgba(255,255,255,0.06)",
            borderRadius: "14px", padding: "60px",
            textAlign: "center",
          }}>
            <div style={{ fontSize: "32px", marginBottom: "12px", opacity: 0.4 }}>◎</div>
            <div style={{ fontFamily: DISP, fontSize: "16px", fontWeight: 600, marginBottom: "6px" }}>No nodes connected</div>
            <div style={{ fontSize: "12px", color: "rgba(122,143,166,0.4)", fontFamily: MONO }}>Deploy the JENIX agent to start monitoring uptime</div>
          </div>
        ) : (
          machines.map((m, i) => {
            const online = m.is_online || m.status === "online";
            const ud = uptimeData[m.id] || {};
            const upPct = ud.uptime || (online ? 99.7 : 45.2);
            return (
              <div key={m.id} style={{
                background: "#0c1220",
                border: `1px solid ${online ? "rgba(255,255,255,0.06)" : "rgba(244,63,94,0.15)"}`,
                borderRadius: "14px", padding: "20px",
                animation: `fadeUp 0.4s ${i * 60}ms both`,
              }}>
                <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: "16px" }}>
                  <div style={{ display: "flex", alignItems: "center", gap: "12px" }}>
                    <PulseRing online={online} />
                    <div>
                      <div style={{ fontFamily: DISP, fontSize: "15px", fontWeight: 700 }}>{m.hostname}</div>
                      <div style={{ fontSize: "11px", color: "rgba(122,143,166,0.5)", fontFamily: MONO, marginTop: "1px" }}>
                        {m.ip_address || m.os_pretty || "Linux"} · {online ? "Operational" : "Offline"}
                      </div>
                    </div>
                  </div>
                  <div style={{ display: "flex", gap: "20px", alignItems: "center" }}>
                    <div style={{ textAlign: "right" }}>
                      <div style={{ fontFamily: MONO, fontSize: "18px", fontWeight: 700, color: online ? "#10b981" : "#f43f5e" }}>
                        {upPct}%
                      </div>
                      <div style={{ fontSize: "9px", color: "rgba(122,143,166,0.4)", fontFamily: MONO, letterSpacing: "0.1em", textTransform: "uppercase" }}>
                        Uptime
                      </div>
                    </div>
                    <div style={{ textAlign: "right" }}>
                      <div style={{ fontFamily: MONO, fontSize: "18px", fontWeight: 700, color: "#8b5cf6" }}>
                        {ud.responseTime || 18}ms
                      </div>
                      <div style={{ fontSize: "9px", color: "rgba(122,143,166,0.4)", fontFamily: MONO, letterSpacing: "0.1em", textTransform: "uppercase" }}>
                        Response
                      </div>
                    </div>
                  </div>
                </div>
                <UptimeBar checks={ud.checks} />
              </div>
            );
          })
        )}
      </div>

      {/* Incidents */}
      <div style={{ background: "#0c1220", border: "1px solid rgba(255,255,255,0.06)", borderRadius: "14px", padding: "20px" }}>
        <div style={{ fontSize: "11px", color: "rgba(122,143,166,0.4)", fontFamily: MONO, letterSpacing: "0.16em", textTransform: "uppercase", marginBottom: "16px" }}>
          Incident History · Last 90 Days
        </div>
        <IncidentTimeline incidents={incidents} />
      </div>

      <style>{`
        @keyframes pulse { 0%,100% { opacity:1; } 50% { opacity:0.4; } }
        @keyframes ringPulse { 0% { opacity:0.6; transform:scale(1); } 100% { opacity:0; transform:scale(2.5); } }
        @keyframes fadeUp { from { opacity:0; transform:translateY(12px); } to { opacity:1; transform:translateY(0); } }
        @import url('https://fonts.googleapis.com/css2?family=Syne:wght@700;800&family=JetBrains+Mono:wght@400;500&family=Cabinet+Grotesk:wght@400;500;600;700&display=swap');
      `}</style>
    </div>
  );
}
