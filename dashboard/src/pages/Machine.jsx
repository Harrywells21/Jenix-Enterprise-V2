import { useState, useEffect, useRef } from "react";
import { useParams, useNavigate } from "react-router-dom";
import {
  LineChart, Line, XAxis, YAxis, Tooltip,
  ResponsiveContainer, CartesianGrid
} from "recharts";
import { getMachine, getMetrics, sendCommand,
         getLogs, connectDashboardWS } from "../api";
import { SkeletonGraph } from "../components/Skeleton";

// ── Graph with dynamic Y-axis ──────────────────────────────────────────────
function Graph({ data, dataKey, color, label, unit="%" }) {
  const values  = data.map(d => d[dataKey] || 0);
  const maxVal  = Math.max(...values, 1);
  const yMax    = unit === "%" ? 100 : Math.ceil(maxVal * 1.2);

  return (
    <div style={{
      background:"#13131f", border:"1px solid #2a2a3e",
      borderRadius:"10px", padding:"16px"
    }}>
      <div style={{ display:"flex", justifyContent:"space-between",
                    marginBottom:"8px" }}>
        <span style={{ color:"#aaa", fontSize:"12px", fontWeight:600 }}>
          {label}
        </span>
        <span style={{ color, fontSize:"12px", fontWeight:700 }}>
          {values[values.length-1]?.toFixed(unit==="%" ? 1 : 2)}{unit}
        </span>
      </div>
      <ResponsiveContainer width="100%" height={120}>
        <LineChart data={data}>
          <CartesianGrid strokeDasharray="3 3" stroke="#1a1a2e" />
          <XAxis dataKey="t" hide />
          <YAxis
            domain={[0, yMax]}
            tick={{ fontSize:10, fill:"#666" }}
            tickFormatter={v => unit==="%" ? `${v}%` : `${v}`}
            width={35}
          />
          <Tooltip
            contentStyle={{
              background:"#1a1a2e", border:"1px solid #2a2a3e",
              borderRadius:"6px", fontSize:"12px"
            }}
            formatter={v => [`${v.toFixed(2)}${unit}`, label]}
            labelFormatter={() => ""}
          />
          <Line type="monotone" dataKey={dataKey}
            stroke={color} dot={false} strokeWidth={2}
            isAnimationActive={false}
          />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}

const CMD_COLORS = {
  scan:"#00bcd4", boost:"#ffb300",
  clean:"#4caf50", fix:"#9c27b0", rollback:"#f44336"
};

export default function Machine() {
  const { id }   = useParams();
  const navigate = useNavigate();

  const [machine,   setMachine]   = useState(null);
  const [graphData, setGraphData] = useState([]);
  const [logs,      setLogs]      = useState([]);
  const [terminal,  setTerminal]  = useState("");
  const [cmdStatus, setCmdStatus] = useState("idle");
  const [loading,   setLoading]   = useState(true);

  const termRef = useRef(null);
  const wsRef   = useRef(null);

  useEffect(() => {
    setLoading(true);
    Promise.all([
      getMachine(id),
      getMetrics(id),
      getLogs(id),
    ]).then(([mRes, metRes, logRes]) => {
      setMachine(mRes.data);
      setGraphData(metRes.data.map((m, i) => ({
        t:i, cpu:m.cpu, ram:m.ram,
        disk:m.disk, net:m.net_mb
      })));
      setLogs(logRes.data);
      setLoading(false);
    }).catch(() => navigate("/"));

    wsRef.current = connectDashboardWS((msg) => {
      if (msg.type === "metrics" &&
          String(msg.machine_id) === String(id)) {
        setGraphData(prev => [...prev, {
          t:    prev.length,
          cpu:  msg.cpu,
          ram:  msg.ram,
          disk: msg.disk,
          net:  msg.net_mb,
        }].slice(-60));
      }
      if (msg.type === "cmd_output") {
        setTerminal(prev => prev + msg.output);
        if (msg.status === "done" || msg.status === "failed")
          setCmdStatus(msg.status);
        setTimeout(() => {
          if (termRef.current)
            termRef.current.scrollTop = termRef.current.scrollHeight;
        }, 50);
      }
    });

    return () => wsRef.current?.close();
  }, [id]);

  const handleCommand = async (cmd) => {
    if (cmdStatus === "running") return;
    if (["fix","rollback"].includes(cmd) &&
        !window.confirm(
          `Run ${cmd.toUpperCase()} on ${machine?.hostname}?`
        )) return;
    try {
      setCmdStatus("running");
      setTerminal(`> Running ${cmd}...\n`);
      await sendCommand(id, cmd);
    } catch (e) {
      setTerminal(
        `Error: ${e.response?.data?.detail || e.message}\n`
      );
      setCmdStatus("failed");
    }
  };

  // ── Loading skeleton ───────────────────────────────────────────────────
  if (loading) return (
    <div>
      <div style={{ color:"#555", fontSize:"13px",
                    marginBottom:"16px" }}>
        ← Back
      </div>
      <div style={{ marginBottom:"24px" }}>
        <div style={{
          width:"200px", height:"24px", borderRadius:"6px",
          background:"#1a1a2e", marginBottom:"8px"
        }}/>
        <div style={{
          width:"150px", height:"14px", borderRadius:"4px",
          background:"#1a1a2e"
        }}/>
      </div>
      <div style={{ display:"grid",
                    gridTemplateColumns:"1fr 1fr",
                    gap:"12px", marginBottom:"20px" }}>
        {[1,2,3,4].map(i => <SkeletonGraph key={i} />)}
      </div>
    </div>
  );

  return (
    <div>
      {/* Back */}
      <button onClick={() => navigate("/")} style={{
        background:"none", border:"none", color:"#00bcd4",
        cursor:"pointer", fontSize:"13px", marginBottom:"16px",
        display:"flex", alignItems:"center", gap:"4px"
      }}>
        ← Back to Fleet
      </button>

      {/* Header */}
      <div style={{ marginBottom:"24px" }}>
        <div style={{ display:"flex", alignItems:"center",
                      gap:"12px", marginBottom:"4px" }}>
          <h1 style={{ color:"#e0e0e0", fontSize:"22px",
                       fontWeight:700 }}>
            {machine.hostname}
          </h1>
          <span style={{
            padding:"3px 10px", borderRadius:"20px",
            fontSize:"11px", fontWeight:600,
            background: machine.status==="online"
              ? "#0a2a0a" : "#2a0a0a",
            color: machine.status==="online"
              ? "#4caf50" : "#f44336",
            border:`1px solid ${
              machine.status==="online" ? "#4caf50" : "#f44336"}`
          }}>
            {machine.status==="online" ? "● Online" : "● Offline"}
          </span>
        </div>
        <div style={{ color:"#666", fontSize:"13px" }}>
          {machine.ip} · {machine.os_name}
        </div>
      </div>

      {/* ✅ Fixed graphs — Net has dynamic Y-axis */}
      <div style={{ display:"grid",
                    gridTemplateColumns:"1fr 1fr",
                    gap:"12px", marginBottom:"20px" }}>
        <Graph data={graphData} dataKey="cpu"
               color="#00bcd4" label="CPU" unit="%" />
        <Graph data={graphData} dataKey="ram"
               color="#ffb300" label="RAM" unit="%" />
        <Graph data={graphData} dataKey="disk"
               color="#4caf50" label="Disk" unit="%" />
        <Graph data={graphData} dataKey="net"
               color="#9c27b0" label="Net I/O" unit=" MB/s" />
      </div>

      {/* Commands */}
      <div style={{
        background:"#13131f", border:"1px solid #2a2a3e",
        borderRadius:"10px", padding:"20px", marginBottom:"16px"
      }}>
        <div style={{ display:"flex", alignItems:"center",
                      gap:"10px", marginBottom:"12px" }}>
          <span style={{ color:"#aaa", fontSize:"12px",
                         fontWeight:600 }}>
            COMMANDS
          </span>
          <span style={{
            fontSize:"11px", fontWeight:600,
            color: cmdStatus==="running" ? "#ffb300"
                 : cmdStatus==="done"    ? "#4caf50"
                 : cmdStatus==="failed"  ? "#f44336" : "#444"
          }}>
            {cmdStatus !== "idle" && `● ${cmdStatus.toUpperCase()}`}
          </span>
        </div>
        <div style={{ display:"flex", gap:"8px", flexWrap:"wrap" }}>
          {["scan","boost","clean","fix","rollback"].map(cmd => (
            <button key={cmd} onClick={() => handleCommand(cmd)}
              disabled={cmdStatus==="running"}
              style={{
                padding:"8px 20px", background:"#1a1a2e",
                color:  cmdStatus==="running"
                  ? "#444" : CMD_COLORS[cmd],
                border:`1px solid ${
                  cmdStatus==="running"
                    ? "#2a2a3e" : CMD_COLORS[cmd]}`,
                borderRadius:"8px", fontWeight:600,
                fontSize:"13px", textTransform:"capitalize",
                cursor: cmdStatus==="running"
                  ? "not-allowed" : "pointer"
              }}>
              {cmd}
            </button>
          ))}
          <button onClick={() => {
            setTerminal(""); setCmdStatus("idle");
          }} style={{
            padding:"8px 16px", background:"transparent",
            color:"#555", border:"1px solid #2a2a3e",
            borderRadius:"8px", cursor:"pointer", fontSize:"13px"
          }}>
            Clear
          </button>
        </div>
      </div>

      {/* Terminal */}
      <div ref={termRef} style={{
        background:"#050510", border:"1px solid #2a2a3e",
        borderRadius:"10px", padding:"16px",
        fontFamily:"'Courier New', monospace", fontSize:"12px",
        color:"#00ff88", height:"220px",
        overflowY:"auto", marginBottom:"20px",
        whiteSpace:"pre-wrap", lineHeight:"1.7",
        boxShadow:"inset 0 2px 10px rgba(0,0,0,0.5)"
      }}>
        {terminal || "> Ready. Run a command above."}
      </div>

      {/* Audit Log */}
      <div style={{
        background:"#13131f", border:"1px solid #2a2a3e",
        borderRadius:"10px", padding:"20px"
      }}>
        <div style={{ color:"#aaa", fontSize:"12px",
                      fontWeight:600, marginBottom:"12px" }}>
          AUDIT LOG
          <span style={{ color:"#444", marginLeft:"8px",
                         fontWeight:400 }}>
            last {logs.length} entries
          </span>
        </div>
        {logs.length === 0 ? (
          <div style={{ color:"#555", fontSize:"13px" }}>
            No actions recorded yet.
          </div>
        ) : (
          <table style={{ width:"100%",
                          borderCollapse:"collapse",
                          fontSize:"12px" }}>
            <thead>
              <tr style={{ color:"#555" }}>
                {["Timestamp","Action","Detail","Status"].map(h=>(
                  <th key={h} style={{
                    textAlign:"left", padding:"6px 8px",
                    borderBottom:"1px solid #2a2a3e",
                    fontWeight:600
                  }}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {logs.map(l => (
                <tr key={l.id}
                  style={{ borderBottom:"1px solid #1a1a2e" }}>
                  <td style={{ padding:"6px 8px", color:"#555",
                               fontSize:"11px" }}>
                    {l.timestamp?.slice(0,16).replace("T"," ")}
                  </td>
                  <td style={{ padding:"6px 8px", color:"#00bcd4",
                               textTransform:"capitalize",
                               fontWeight:600 }}>
                    {l.action}
                  </td>
                  <td style={{ padding:"6px 8px", color:"#aaa",
                               maxWidth:"200px", overflow:"hidden",
                               textOverflow:"ellipsis",
                               whiteSpace:"nowrap" }}>
                    {l.detail}
                  </td>
                  <td style={{ padding:"6px 8px",
                    color: l.status==="ok"
                      ? "#4caf50" : "#f44336" }}>
                    {l.status}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
