import { useState, useEffect } from "react";
import { getMachines } from "../api";
import api from "../api";

function UptimeBar({ daily }) {
  return (
    <div style={{ display:"flex", gap:"2px", alignItems:"center" }}>
      {daily.slice().reverse().map((d, i) => (
        <div key={i} title={`${d.date}: ${d.status}`}
          style={{
            width:"10px", height:"28px", borderRadius:"2px",
            background:
              d.status === "up"      ? "#4caf50" :
              d.status === "down"    ? "#f44336" : "#2a2a3e",
            cursor:"pointer",
            transition:"opacity 0.2s",
            flexShrink:0
          }}
        />
      ))}
    </div>
  );
}

function SLABadge({ met, pct }) {
  return (
    <span style={{
      padding:"3px 10px", borderRadius:"20px",
      fontSize:"11px", fontWeight:700,
      background: met ? "#0a2a0a" : "#2a0a0a",
      color:      met ? "#4caf50" : "#f44336",
      border:    `1px solid ${met ? "#4caf50" : "#f44336"}`
    }}>
      {pct}% {met ? "✓ SLA Met" : "✗ SLA Breach"}
    </span>
  );
}

export default function Uptime() {
  const [summary,  setSummary]  = useState(null);
  const [selected, setSelected] = useState(null);
  const [detail,   setDetail]   = useState(null);
  const [loading,  setLoading]  = useState(false);

  useEffect(() => {
    api.get("/uptime/fleet/summary")
       .then(r => setSummary(r.data))
       .catch(console.error);
  }, []);

  const loadDetail = async (machineId) => {
    setSelected(machineId);
    setLoading(true);
    try {
      const r = await api.get(`/uptime/${machineId}?days=30`);
      setDetail(r.data);
    } catch (e) {
      console.error(e);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div>
      <div style={{ marginBottom:"24px" }}>
        <h1 style={{ color:"#e0e0e0", fontSize:"22px",
                     fontWeight:700, marginBottom:"4px" }}>
          Uptime Monitor
        </h1>
        <div style={{ color:"#666", fontSize:"13px" }}>
          30-day uptime tracking and SLA compliance reporting
        </div>
      </div>

      {/* Fleet summary */}
      {summary && (
        <div style={{
          background:"#13131f", border:"1px solid #2a2a3e",
          borderRadius:"12px", padding:"20px",
          marginBottom:"20px"
        }}>
          <div style={{ display:"flex", justifyContent:"space-between",
                        alignItems:"center", marginBottom:"16px" }}>
            <div style={{ color:"#aaa", fontSize:"12px",
                          fontWeight:600 }}>
              FLEET UPTIME SUMMARY — LAST 30 DAYS
            </div>
            <div style={{
              color: summary.fleet_uptime_pct >= 99
                ? "#4caf50" : "#f44336",
              fontSize:"24px", fontWeight:800
            }}>
              {summary.fleet_uptime_pct}%
              <span style={{ color:"#666", fontSize:"12px",
                             fontWeight:400, marginLeft:"6px" }}>
                fleet avg
              </span>
            </div>
          </div>

          {/* Machine rows */}
          <div style={{ display:"flex", flexDirection:"column",
                        gap:"8px" }}>
            {summary.machines.map(m => (
              <div key={m.machine_id}
                onClick={() => loadDetail(m.machine_id)}
                style={{
                  display:"flex", alignItems:"center",
                  gap:"16px", padding:"12px 16px",
                  background: selected===m.machine_id
                    ? "#0a1628" : "#0d0d1a",
                  borderRadius:"8px", cursor:"pointer",
                  border:`1px solid ${selected===m.machine_id
                    ? "#00bcd4" : "#1a1a2e"}`,
                  transition:"all 0.15s"
                }}>
                <div style={{ width:"120px", flexShrink:0 }}>
                  <div style={{ color:"#e0e0e0", fontSize:"13px",
                                fontWeight:600 }}>
                    {m.hostname}
                  </div>
                  <div style={{ color:"#666", fontSize:"11px" }}>
                    {m.incidents} incident{m.incidents!==1?"s":""}
                  </div>
                </div>
                <div style={{ flex:1 }}>
                  <SLABadge met={m.sla_met} pct={m.uptime_pct} />
                </div>
                <div style={{
                  padding:"3px 10px", borderRadius:"20px",
                  fontSize:"11px", fontWeight:600,
                  background: m.status==="online"
                    ? "#0a2a0a" : "#2a0a0a",
                  color: m.status==="online"
                    ? "#4caf50" : "#f44336",
                }}>
                  {m.status==="online" ? "● Online" : "● Offline"}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Machine detail */}
      {loading && (
        <div style={{ color:"#666", textAlign:"center",
                      padding:"40px" }}>
          Loading uptime data...
        </div>
      )}

      {detail && !loading && (
        <div style={{
          background:"#13131f", border:"1px solid #2a2a3e",
          borderRadius:"12px", padding:"20px"
        }}>
          <div style={{ display:"flex", justifyContent:"space-between",
                        alignItems:"flex-start",
                        marginBottom:"20px" }}>
            <div>
              <h2 style={{ color:"#e0e0e0", fontSize:"18px",
                           fontWeight:700, marginBottom:"4px" }}>
                {detail.hostname}
              </h2>
              <div style={{ color:"#666", fontSize:"12px" }}>
                Last 30 days · {detail.incidents} incidents ·
                {detail.downtime_minutes} min downtime
              </div>
            </div>
            <SLABadge met={detail.sla_met}
                      pct={detail.uptime_pct} />
          </div>

          {/* Stats row */}
          <div style={{ display:"grid",
                        gridTemplateColumns:"repeat(4,1fr)",
                        gap:"12px", marginBottom:"20px" }}>
            {[
              { label:"Uptime",    value:`${detail.uptime_pct}%`,
                color: detail.uptime_pct>=99 ? "#4caf50" : "#f44336" },
              { label:"Incidents", value:detail.incidents,
                color: detail.incidents===0 ? "#4caf50" : "#f44336" },
              { label:"Downtime",
                value:`${detail.downtime_minutes}m`,
                color:"#ffb300" },
              { label:"SLA Target", value:`${detail.sla_target}%`,
                color:"#00bcd4" },
            ].map(({ label, value, color }) => (
              <div key={label} style={{
                background:"#0d0d1a",
                border:"1px solid #1a1a2e",
                borderRadius:"8px", padding:"14px"
              }}>
                <div style={{ color:"#666", fontSize:"11px",
                              marginBottom:"4px" }}>
                  {label}
                </div>
                <div style={{ color, fontSize:"20px",
                              fontWeight:800 }}>
                  {value}
                </div>
              </div>
            ))}
          </div>

          {/* Daily uptime bar */}
          <div style={{ marginBottom:"8px" }}>
            <div style={{ color:"#aaa", fontSize:"11px",
                          fontWeight:600, marginBottom:"8px" }}>
              DAILY STATUS — LAST 30 DAYS
              <span style={{ color:"#444", marginLeft:"8px",
                             fontWeight:400 }}>
                (left = today)
              </span>
            </div>
            <UptimeBar daily={detail.daily} />
            <div style={{ display:"flex", gap:"16px",
                          marginTop:"8px" }}>
              {[
                { color:"#4caf50", label:"Operational" },
                { color:"#f44336", label:"Incident"    },
                { color:"#2a2a3e", label:"No data"     },
              ].map(({ color, label }) => (
                <div key={label} style={{ display:"flex",
                                          alignItems:"center",
                                          gap:"6px" }}>
                  <div style={{ width:"10px", height:"10px",
                                background:color,
                                borderRadius:"2px" }}/>
                  <span style={{ color:"#666", fontSize:"11px" }}>
                    {label}
                  </span>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
