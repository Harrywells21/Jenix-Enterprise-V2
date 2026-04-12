import { useState, useEffect, useRef } from "react";
import { useNavigate } from "react-router-dom";
import { getMachines, sendCommand, connectDashboardWS } from "../api";

function StatBar({ value, color }) {
  return (
    <div style={{ background:"#0d0d1a", borderRadius:"4px",
                  height:"6px", overflow:"hidden", marginTop:"4px" }}>
      <div style={{
        width:`${Math.min(value,100)}%`, height:"100%",
        background: value>85 ? "#f44336" : value>65 ? "#ffb300" : color,
        borderRadius:"4px", transition:"width 0.5s"
      }}/>
    </div>
  );
}

function MachineCard({ machine, liveMetrics, onCommand }) {
  const navigate  = useNavigate();
  const m         = liveMetrics[machine.id] || {};
  const cpu       = m.cpu  ?? 0;
  const ram       = m.ram  ?? 0;
  const disk      = m.disk ?? 0;
  const isOnline  = machine.status === "online";

  return (
    <div onClick={() => navigate(`/machines/${machine.id}`)}
      style={{
        background:"#13131f",
        border:`1px solid ${isOnline ? "#2a2a3e" : "#3a1a1a"}`,
        borderRadius:"12px", padding:"20px",
        cursor:"pointer", transition:"border 0.2s"
      }}>
      <div style={{ display:"flex", justifyContent:"space-between",
                    alignItems:"flex-start", marginBottom:"16px" }}>
        <div>
          <div style={{ color:"#e0e0e0", fontWeight:700, fontSize:"15px" }}>
            {machine.hostname}
          </div>
          <div style={{ color:"#666", fontSize:"12px", marginTop:"2px" }}>
            {machine.ip} · {machine.os_name}
          </div>
        </div>
        <span style={{
          padding:"3px 10px", borderRadius:"20px", fontSize:"11px", fontWeight:600,
          background: isOnline ? "#0a2a0a" : "#2a0a0a",
          color:      isOnline ? "#4caf50" : "#f44336",
          border:    `1px solid ${isOnline ? "#4caf50" : "#f44336"}`
        }}>
          {isOnline ? "● Online" : "● Offline"}
        </span>
      </div>

      {isOnline && (
        <div style={{ marginBottom:"16px" }}>
          {[
            { label:"CPU",  value:cpu,  color:"#00bcd4" },
            { label:"RAM",  value:ram,  color:"#ffb300" },
            { label:"Disk", value:disk, color:"#4caf50" },
          ].map(({ label, value, color }) => (
            <div key={label} style={{ marginBottom:"8px" }}>
              <div style={{ display:"flex", justifyContent:"space-between" }}>
                <span style={{ color:"#aaa", fontSize:"11px" }}>{label}</span>
                <span style={{ color, fontSize:"11px", fontWeight:600 }}>
                  {value.toFixed(1)}%
                </span>
              </div>
              <StatBar value={value} color={color} />
            </div>
          ))}
        </div>
      )}

      {isOnline && (
        <div style={{ display:"flex", gap:"6px" }}
             onClick={e => e.stopPropagation()}>
          {["scan","boost","clean"].map(cmd => (
            <button key={cmd} onClick={() => onCommand(machine.id, cmd)}
              style={{
                flex:1, padding:"6px 4px",
                background:"#1a1a2e", color:"#00bcd4",
                border:"1px solid #2a2a3e", borderRadius:"6px",
                fontSize:"11px", cursor:"pointer",
                textTransform:"capitalize"
              }}>
              {cmd}
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
  const [toast,       setToast]       = useState("");
  const wsRef = useRef(null);

  useEffect(() => {
    getMachines().then(r => setMachines(r.data)).catch(console.error);
    const interval = setInterval(() => {
      getMachines().then(r => setMachines(r.data)).catch(console.error);
    }, 10_000);

    wsRef.current = connectDashboardWS((msg) => {
      if (msg.type === "metrics") {
        setLiveMetrics(prev => ({
          ...prev,
          [msg.machine_id]: {
            cpu:msg.cpu, ram:msg.ram,
            disk:msg.disk, net_mb:msg.net_mb
          }
        }));
      }
      if (msg.type === "status") {
        setMachines(prev => prev.map(m =>
          m.id === msg.machine_id ? { ...m, status:msg.status } : m
        ));
      }
    });

    return () => { clearInterval(interval); wsRef.current?.close(); };
  }, []);

  const handleCommand = async (machineId, cmd) => {
    try {
      await sendCommand(machineId, cmd);
      setToast(`✅ ${cmd} sent`);
      setTimeout(() => setToast(""), 3000);
    } catch (e) {
      setToast(`❌ Failed: ${e.response?.data?.detail || e.message}`);
      setTimeout(() => setToast(""), 4000);
    }
  };

  const filtered = machines
    .filter(m => m.hostname.toLowerCase().includes(search.toLowerCase()))
    .sort((a, b) => (b.status === "online") - (a.status === "online"));

  const online  = machines.filter(m => m.status === "online").length;
  const offline = machines.length - online;

  return (
    <div>
      {toast && (
        <div style={{
          position:"fixed", top:"20px", right:"20px",
          background:"#1a1a2e", border:"1px solid #2a2a3e",
          borderRadius:"8px", padding:"12px 20px",
          color:"#e0e0e0", fontSize:"13px", zIndex:1000
        }}>{toast}</div>
      )}

      <div style={{ marginBottom:"24px" }}>
        <h1 style={{ color:"#e0e0e0", fontSize:"22px",
                     fontWeight:700, marginBottom:"4px" }}>
          System Overview
        </h1>
        <div style={{ color:"#666", fontSize:"13px" }}>
          {machines.length} machines ·
          <span style={{ color:"#4caf50" }}> {online} online</span> ·
          <span style={{ color:"#f44336" }}> {offline} offline</span>
        </div>
      </div>

      <input placeholder="Search by hostname..."
        value={search} onChange={e => setSearch(e.target.value)}
        style={{
          width:"300px", padding:"8px 14px", marginBottom:"20px",
          background:"#13131f", border:"1px solid #2a2a3e",
          borderRadius:"8px", color:"#e0e0e0",
          fontSize:"13px", outline:"none"
        }}
      />

      {filtered.length === 0 ? (
        <div style={{ textAlign:"center", color:"#666",
                      marginTop:"60px", fontSize:"15px" }}>
          No machines connected yet.<br/>
          <span style={{ fontSize:"12px", color:"#444" }}>
            Run the JENIX agent on a machine to get started.
          </span>
        </div>
      ) : (
        <div style={{
          display:"grid",
          gridTemplateColumns:"repeat(auto-fill, minmax(280px, 1fr))",
          gap:"16px"
        }}>
          {filtered.map(m => (
            <MachineCard key={m.id} machine={m}
              liveMetrics={liveMetrics}
              onCommand={handleCommand} />
          ))}
        </div>
      )}
    </div>
  );
}
