import { useState, useEffect, useRef } from "react";
import { useNavigate } from "react-router-dom";
import { getFleetOverview, getSavings,
         getAllAlerts, markAllRead, fleetCommand,
         connectDashboardWS } from "../api";

// ── Stat Card ──────────────────────────────────────────────────────────────
function StatCard({ label, value, sub, color="#00bcd4", icon, danger }) {
  return (
    <div style={{
      background: danger ? "#1a0a0a" : "#13131f",
      border: `1px solid ${danger ? "#f44336" : "#2a2a3e"}`,
      borderRadius:"12px", padding:"20px",
      display:"flex", flexDirection:"column", gap:"6px"
    }}>
      <div style={{ display:"flex", justifyContent:"space-between",
                    alignItems:"center" }}>
        <span style={{ color:"#666", fontSize:"12px",
                       fontWeight:600, textTransform:"uppercase",
                       letterSpacing:"0.5px" }}>
          {label}
        </span>
        <span style={{ fontSize:"20px" }}>{icon}</span>
      </div>
      <div style={{ color, fontSize:"32px", fontWeight:800,
                    lineHeight:1 }}>
        {value}
      </div>
      {sub && (
        <div style={{ color:"#666", fontSize:"12px" }}>{sub}</div>
      )}
    </div>
  );
}

// ── Health Score Ring ──────────────────────────────────────────────────────
function ScoreRing({ score, color, size=60 }) {
  const r   = (size/2) - 5;
  const circ = 2 * Math.PI * r;
  const fill = (score / 100) * circ;
  return (
    <svg width={size} height={size} style={{ transform:"rotate(-90deg)" }}>
      <circle cx={size/2} cy={size/2} r={r}
        fill="none" stroke="#1a1a2e" strokeWidth="5"/>
      <circle cx={size/2} cy={size/2} r={r}
        fill="none" stroke={color} strokeWidth="5"
        strokeDasharray={`${fill} ${circ}`}
        strokeLinecap="round"
        style={{ transition:"stroke-dasharray 0.8s ease" }}/>
      <text x={size/2} y={size/2}
        textAnchor="middle" dominantBaseline="central"
        fill={color} fontSize="13" fontWeight="bold"
        style={{ transform:`rotate(90deg) translate(0, -${size}px)` }}>
      </text>
    </svg>
  );
}

// ── Machine Score Card ─────────────────────────────────────────────────────
function MachineScoreCard({ machine, onClick }) {
  return (
    <div onClick={onClick} style={{
      background:"#13131f",
      border:`1px solid ${machine.score < 50 ? "#f44336"
                        : machine.score < 80 ? "#ffb300" : "#2a2a3e"}`,
      borderRadius:"10px", padding:"16px",
      cursor:"pointer", transition:"all 0.2s",
      display:"flex", alignItems:"center", gap:"16px"
    }}>
      {/* Score ring */}
      <div style={{ position:"relative", flexShrink:0 }}>
        <ScoreRing score={machine.score} color={machine.color} size={56} />
        <div style={{
          position:"absolute", top:"50%", left:"50%",
          transform:"translate(-50%,-50%)",
          color: machine.color, fontSize:"12px", fontWeight:700
        }}>
          {machine.score}
        </div>
      </div>

      {/* Info */}
      <div style={{ flex:1, minWidth:0 }}>
        <div style={{ display:"flex", alignItems:"center",
                      gap:"8px", marginBottom:"4px" }}>
          <span style={{ color:"#e0e0e0", fontWeight:700,
                         fontSize:"14px" }}>
            {machine.hostname}
          </span>
          <span style={{
            padding:"2px 8px", borderRadius:"20px",
            fontSize:"10px", fontWeight:600,
            background: machine.status==="online" ? "#0a2a0a" : "#2a0a0a",
            color:      machine.status==="online" ? "#4caf50" : "#f44336",
          }}>
            {machine.status==="online" ? "● Online" : "● Offline"}
          </span>
        </div>
        <div style={{ color:"#666", fontSize:"11px", marginBottom:"6px" }}>
          {machine.ip} · {machine.os_name}
        </div>
        <div style={{ display:"flex", gap:"12px" }}>
          {[
            { label:"CPU",  value:machine.cpu,  color:"#00bcd4" },
            { label:"RAM",  value:machine.ram,  color:"#ffb300" },
            { label:"Disk", value:machine.disk, color:"#4caf50" },
          ].map(({ label, value, color }) => (
            <div key={label} style={{ fontSize:"11px" }}>
              <span style={{ color:"#666" }}>{label}: </span>
              <span style={{ color, fontWeight:600 }}>
                {value?.toFixed(1)}%
              </span>
            </div>
          ))}
        </div>
      </div>

      {/* Grade */}
      <div style={{
        color: machine.color, fontSize:"11px",
        fontWeight:700, textAlign:"right", flexShrink:0
      }}>
        {machine.grade}
      </div>
    </div>
  );
}

// ── Alert Badge ────────────────────────────────────────────────────────────
function AlertItem({ alert }) {
  const icon = alert.level === "critical" ? "🔴" : "🟡";
  return (
    <div style={{
      display:"flex", alignItems:"flex-start", gap:"10px",
      padding:"10px 0",
      borderBottom:"1px solid #1a1a2e"
    }}>
      <span style={{ fontSize:"14px", flexShrink:0 }}>{icon}</span>
      <div style={{ flex:1, minWidth:0 }}>
        <div style={{ color:"#e0e0e0", fontSize:"12px",
                      fontWeight:600 }}>
          {alert.hostname}
        </div>
        <div style={{ color:"#aaa", fontSize:"11px",
                      marginTop:"2px" }}>
          {alert.message}
        </div>
      </div>
      <div style={{ color:"#444", fontSize:"10px",
                    flexShrink:0 }}>
        {alert.timestamp?.slice(11,16)}
      </div>
    </div>
  );
}

// ── Main Fleet Dashboard ───────────────────────────────────────────────────
export default function Fleet() {
  const navigate  = useNavigate();
  const [fleet,   setFleet]   = useState(null);
  const [savings, setSavings] = useState(null);
  const [alerts,  setAlerts]  = useState([]);
  const [toast,   setToast]   = useState("");
  const [sending, setSending] = useState("");
  const wsRef = useRef(null);

  const showToast = (msg) => {
    setToast(msg); setTimeout(() => setToast(""), 4000);
  };

  const load = () => {
    getFleetOverview().then(r => setFleet(r.data)).catch(console.error);
    getSavings().then(r       => setSavings(r.data)).catch(console.error);
    getAllAlerts().then(r      => setAlerts(r.data.slice(0,10))).catch(console.error);
  };

  useEffect(() => {
    load();
    const interval = setInterval(load, 15_000);

    wsRef.current = connectDashboardWS((msg) => {
      if (msg.type === "metrics" || msg.type === "status") {
        load();
      }
    });

    return () => {
      clearInterval(interval);
      wsRef.current?.close();
    };
  }, []);

  const handleFleetCommand = async (cmd) => {
    if (!window.confirm(`Run ${cmd.toUpperCase()} on ALL online machines?`))
      return;
    setSending(cmd);
    try {
      const r = await fleetCommand(cmd);
      showToast(`✅ ${cmd.toUpperCase()} sent to ${r.data.sent} machines`);
      setTimeout(load, 2000);
    } catch (e) {
      showToast(`❌ ${e.response?.data?.detail || e.message}`);
    } finally {
      setSending("");
    }
  };

  const handleMarkAllRead = async () => {
    await markAllRead();
    setAlerts([]);
    load();
    showToast("✅ All alerts marked as read");
  };

  if (!fleet) return (
    <div style={{ display:"flex", alignItems:"center",
                  justifyContent:"center", height:"60vh" }}>
      <div style={{ color:"#00bcd4", fontSize:"14px" }}>
        Loading fleet data...
      </div>
    </div>
  );

  const unread_critical = alerts.filter(
    a => a.level === "critical" && !a.is_read).length;

  return (
    <div>
      {/* Toast */}
      {toast && (
        <div style={{
          position:"fixed", top:"20px", right:"20px",
          background:"#1a1a2e", border:"1px solid #2a2a3e",
          borderRadius:"8px", padding:"12px 20px",
          color:"#e0e0e0", fontSize:"13px", zIndex:1000,
          boxShadow:"0 4px 20px rgba(0,0,0,0.5)"
        }}>{toast}</div>
      )}

      {/* Header */}
      <div style={{ display:"flex", justifyContent:"space-between",
                    alignItems:"flex-start", marginBottom:"24px" }}>
        <div>
          <h1 style={{ color:"#e0e0e0", fontSize:"24px",
                       fontWeight:800, marginBottom:"4px" }}>
            Fleet Command Center
          </h1>
          <div style={{ color:"#666", fontSize:"13px" }}>
            Real-time overview of your entire Linux infrastructure
          </div>
        </div>
        {/* Fleet action buttons */}
        <div style={{ display:"flex", gap:"8px", flexWrap:"wrap" }}>
          {["scan","boost","clean"].map(cmd => (
            <button key={cmd}
              onClick={() => handleFleetCommand(cmd)}
              disabled={!!sending}
              style={{
                padding:"8px 16px",
                background: sending===cmd ? "#1a1a2e" : "#1a1a2e",
                color:  sending===cmd ? "#444"
                      : cmd==="scan"  ? "#00bcd4"
                      : cmd==="boost" ? "#ffb300" : "#4caf50",
                border:`1px solid ${
                  sending===cmd ? "#2a2a3e"
                  : cmd==="scan"  ? "#00bcd4"
                  : cmd==="boost" ? "#ffb300" : "#4caf50"}`,
                borderRadius:"8px", fontWeight:700,
                fontSize:"12px", cursor: sending ? "not-allowed" : "pointer",
                textTransform:"capitalize"
              }}>
              {sending===cmd ? "Sending..." : `⚡ ${cmd} ALL`}
            </button>
          ))}
        </div>
      </div>

      {/* Critical alert banner */}
      {unread_critical > 0 && (
        <div style={{
          background:"#1a0505",
          border:"1px solid #f44336",
          borderRadius:"10px", padding:"14px 20px",
          marginBottom:"20px",
          display:"flex", alignItems:"center",
          justifyContent:"space-between"
        }}>
          <div style={{ display:"flex", alignItems:"center", gap:"10px" }}>
            <span style={{ fontSize:"20px" }}>🚨</span>
            <span style={{ color:"#f44336", fontWeight:700, fontSize:"14px" }}>
              {unread_critical} Critical Alert{unread_critical>1?"s":""} Require Immediate Attention
            </span>
          </div>
          <button onClick={handleMarkAllRead} style={{
            padding:"6px 14px", background:"transparent",
            color:"#f44336", border:"1px solid #f44336",
            borderRadius:"6px", fontSize:"12px", cursor:"pointer"
          }}>
            Mark All Read
          </button>
        </div>
      )}

      {/* Stat Cards Row */}
      <div style={{ display:"grid",
                    gridTemplateColumns:"repeat(4, 1fr)",
                    gap:"12px", marginBottom:"20px" }}>
        <StatCard label="Total Machines" value={fleet.total}
          icon="🖥" color="#00bcd4"
          sub={`${fleet.online} online · ${fleet.offline} offline`}/>
        <StatCard label="Fleet CPU" value={`${fleet.avg_cpu}%`}
          icon="⚡" color="#00bcd4"
          sub="Average across all machines"
          danger={fleet.avg_cpu > 85}/>
        <StatCard label="Fleet RAM" value={`${fleet.avg_ram}%`}
          icon="💾" color="#ffb300"
          sub="Average across all machines"
          danger={fleet.avg_ram > 85}/>
        <StatCard label="Critical Alerts" value={fleet.critical_alerts}
          icon="🚨"
          color={fleet.critical_alerts > 0 ? "#f44336" : "#4caf50"}
          sub={`${fleet.warning_alerts} warnings`}
          danger={fleet.critical_alerts > 0}/>
      </div>

      {/* Second row */}
      <div style={{ display:"grid",
                    gridTemplateColumns:"repeat(4, 1fr)",
                    gap:"12px", marginBottom:"24px" }}>
        <StatCard label="Fleet Disk" value={`${fleet.avg_disk}%`}
          icon="💽" color="#4caf50"
          sub="Average usage"
          danger={fleet.avg_disk > 85}/>
        <StatCard label="Commands Today" value={fleet.commands_24h}
          icon="🔧" color="#9c27b0"
          sub="Automated operations run"/>
        <StatCard label="Hours Saved Today"
          value={`${fleet.hours_saved}h`}
          icon="⏱" color="#00bcd4"
          sub={`~$${(fleet.hours_saved * 45).toFixed(0)} in labor`}/>
        <StatCard label="Annual Savings"
          value={savings ? `$${savings.annual_savings.toLocaleString()}` : "..."}
          icon="💰" color="#4caf50"
          sub="Estimated vs manual ops"/>
      </div>

      {/* Main content grid */}
      <div style={{ display:"grid",
                    gridTemplateColumns:"1fr 340px",
                    gap:"16px", marginBottom:"20px" }}>

        {/* Machine health scores */}
        <div style={{
          background:"#13131f", border:"1px solid #2a2a3e",
          borderRadius:"12px", padding:"20px"
        }}>
          <div style={{ display:"flex", justifyContent:"space-between",
                        alignItems:"center", marginBottom:"16px" }}>
            <div style={{ color:"#aaa", fontSize:"12px",
                          fontWeight:600 }}>
              MACHINE HEALTH SCORES
              <span style={{ color:"#444", marginLeft:"8px",
                             fontWeight:400 }}>
                sorted by health (worst first)
              </span>
            </div>
            <button onClick={() => navigate("/")}
              style={{
                background:"none", border:"none",
                color:"#00bcd4", cursor:"pointer",
                fontSize:"12px"
              }}>
              View All →
            </button>
          </div>
          <div style={{ display:"flex", flexDirection:"column", gap:"8px" }}>
            {fleet.machine_scores.length === 0 ? (
              <div style={{ color:"#666", fontSize:"13px",
                            textAlign:"center", padding:"40px 0" }}>
                No machines connected yet.
              </div>
            ) : (
              fleet.machine_scores.map(m => (
                <MachineScoreCard key={m.id} machine={m}
                  onClick={() => navigate(`/machines/${m.id}`)} />
              ))
            )}
          </div>
        </div>

        {/* Alerts panel */}
        <div style={{
          background:"#13131f", border:"1px solid #2a2a3e",
          borderRadius:"12px", padding:"20px",
          display:"flex", flexDirection:"column"
        }}>
          <div style={{ display:"flex", justifyContent:"space-between",
                        alignItems:"center", marginBottom:"12px" }}>
            <div style={{ color:"#aaa", fontSize:"12px", fontWeight:600 }}>
              RECENT ALERTS
            </div>
            {alerts.length > 0 && (
              <button onClick={handleMarkAllRead} style={{
                background:"none", border:"none",
                color:"#666", cursor:"pointer", fontSize:"11px"
              }}>
                Clear all
              </button>
            )}
          </div>
          <div style={{ flex:1, overflowY:"auto" }}>
            {alerts.length === 0 ? (
              <div style={{ color:"#4caf50", fontSize:"13px",
                            textAlign:"center", padding:"40px 0" }}>
                ✅ No active alerts
              </div>
            ) : (
              alerts.map(a => <AlertItem key={a.id} alert={a} />)
            )}
          </div>
        </div>
      </div>

      {/* Activity Timeline */}
      <div style={{
        background:"#13131f", border:"1px solid #2a2a3e",
        borderRadius:"12px", padding:"20px"
      }}>
        <div style={{ color:"#aaa", fontSize:"12px",
                      fontWeight:600, marginBottom:"16px" }}>
          ACTIVITY TIMELINE
          <span style={{ color:"#444", marginLeft:"8px", fontWeight:400 }}>
            last 20 actions across fleet
          </span>
        </div>
        <div style={{ display:"flex", flexDirection:"column", gap:"0" }}>
          {fleet.activity.map((a, i) => (
            <div key={i} style={{
              display:"flex", gap:"12px",
              padding:"8px 0",
              borderBottom: i < fleet.activity.length-1
                ? "1px solid #1a1a2e" : "none"
            }}>
              <div style={{
                width:"8px", height:"8px", borderRadius:"50%",
                background: a.status==="ok" ? "#4caf50" : "#f44336",
                flexShrink:0, marginTop:"5px"
              }}/>
              <div style={{ flex:1, minWidth:0 }}>
                <span style={{ color:"#00bcd4", fontSize:"12px",
                               fontWeight:600, textTransform:"capitalize" }}>
                  {a.action}
                </span>
                <span style={{ color:"#aaa", fontSize:"12px",
                               marginLeft:"8px" }}>
                  {a.detail}
                </span>
              </div>
              <div style={{ color:"#444", fontSize:"11px",
                            flexShrink:0 }}>
                {a.timestamp?.slice(0,16).replace("T"," ")}
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Cost Savings Calculator */}
      {savings && (
        <div style={{
          background:"linear-gradient(135deg, #0a1628 0%, #0d2137 100%)",
          border:"1px solid #00bcd4",
          borderRadius:"12px", padding:"24px",
          marginTop:"16px"
        }}>
          <div style={{ color:"#00bcd4", fontSize:"14px",
                        fontWeight:700, marginBottom:"16px" }}>
            💰 JENIX ROI CALCULATOR
          </div>
          <div style={{ display:"grid",
                        gridTemplateColumns:"repeat(4,1fr)",
                        gap:"16px" }}>
            {[
              { label:"This Week",
                value:`$${savings.weekly_saved.toFixed(0)}`,
                sub:`${savings.weekly_hours}h saved` },
              { label:"This Month",
                value:`$${savings.monthly_saved.toFixed(0)}`,
                sub:`${savings.monthly_hours}h saved` },
              { label:"Annual Projection",
                value:`$${savings.annual_savings.toLocaleString()}`,
                sub:"based on current usage" },
              { label:"Payback Period",
                value: savings.payback_months > 100
                  ? "N/A*" : `${savings.payback_months}mo`,
                sub: savings.payback_months > 100
                  ? "*Run more operations to calculate"
                  : "until license pays for itself" },
            ].map(({ label, value, sub }) => (
              <div key={label}>
                <div style={{ color:"#666", fontSize:"11px",
                              fontWeight:600, marginBottom:"4px" }}>
                  {label}
                </div>
                <div style={{ color:"#00bcd4", fontSize:"22px",
                              fontWeight:800 }}>
                  {value}
                </div>
                <div style={{ color:"#444", fontSize:"11px",
                              marginTop:"2px" }}>
                  {sub}
                </div>
              </div>
            ))}
          </div>
          <div style={{ color:"#444", fontSize:"11px",
                        marginTop:"16px", borderTop:"1px solid #1a2a3a",
                        paddingTop:"12px" }}>
            Calculated at ${savings.hourly_rate}/hr average sysadmin rate ·
            {savings.monthly_commands} automated tasks this month ·
            {savings.mins_per_task || 30} min saved per task
          </div>
        </div>
      )}
    </div>
  );
}
