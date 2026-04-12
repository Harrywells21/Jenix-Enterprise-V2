import { useState, useEffect, useRef } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { LineChart, Line, XAxis, YAxis, Tooltip,
         ResponsiveContainer, CartesianGrid } from "recharts";
import { getMachine, getMetrics, sendCommand,
         getLogs, connectDashboardWS } from "../api";

function Graph({ data, dataKey, color, label }) {
  return (
    <div style={{
      background:"#13131f", border:"1px solid #2a2a3e",
      borderRadius:"10px", padding:"16px"
    }}>
      <div style={{ color:"#aaa", fontSize:"12px",
                    marginBottom:"8px", fontWeight:600 }}>
        {label}
      </div>
      <ResponsiveContainer width="100%" height={120}>
        <LineChart data={data}>
          <CartesianGrid strokeDasharray="3 3" stroke="#1a1a2e" />
          <XAxis dataKey="t" hide />
          <YAxis domain={[0,100]} tick={{ fontSize:10, fill:"#666" }} />
          <Tooltip
            contentStyle={{ background:"#1a1a2e", border:"1px solid #2a2a3e",
                            borderRadius:"6px", fontSize:"12px" }}
            labelFormatter={() => ""}
          />
          <Line type="monotone" dataKey={dataKey}
            stroke={color} dot={false} strokeWidth={2} />
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
  const { id }    = useParams();
  const navigate  = useNavigate();
  const [machine,     setMachine]     = useState(null);
  const [graphData,   setGraphData]   = useState([]);
  const [logs,        setLogs]        = useState([]);
  const [terminal,    setTerminal]    = useState("");
  const [cmdStatus,   setCmdStatus]   = useState("idle");
  const termRef = useRef(null);
  const wsRef   = useRef(null);

  useEffect(() => {
    getMachine(id).then(r => setMachine(r.data)).catch(() => navigate("/"));
    getMetrics(id).then(r => {
      setGraphData(r.data.map((m, i) => ({
        t:i, cpu:m.cpu, ram:m.ram, disk:m.disk, net:m.net_mb
      })));
    });
    getLogs(id).then(r => setLogs(r.data));

    wsRef.current = connectDashboardWS((msg) => {
      if (msg.type === "metrics" && String(msg.machine_id) === String(id)) {
        setGraphData(prev => [...prev, {
          t:prev.length, cpu:msg.cpu, ram:msg.ram,
          disk:msg.disk, net:msg.net_mb
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
        !window.confirm(`Run ${cmd.toUpperCase()} on ${machine?.hostname}?`))
      return;
    try {
      setCmdStatus("running");
      setTerminal(`> Running ${cmd}...\n`);
      await sendCommand(id, cmd);
    } catch (e) {
      setTerminal(`Error: ${e.response?.data?.detail || e.message}\n`);
      setCmdStatus("failed");
    }
  };

  if (!machine) return (
    <div style={{ color:"#666", textAlign:"center", marginTop:"80px" }}>
      Loading...
    </div>
  );

  return (
    <div>
      <button onClick={() => navigate("/")} style={{
        background:"none", border:"none", color:"#00bcd4",
        cursor:"pointer", fontSize:"13px", marginBottom:"16px"
      }}>← Back to Overview</button>

      <div style={{ marginBottom:"24px" }}>
        <div style={{ display:"flex", alignItems:"center",
                      gap:"12px", marginBottom:"4px" }}>
          <h1 style={{ color:"#e0e0e0", fontSize:"22px", fontWeight:700 }}>
            {machine.hostname}
          </h1>
          <span style={{
            padding:"3px 10px", borderRadius:"20px", fontSize:"11px",
            background: machine.status==="online" ? "#0a2a0a" : "#2a0a0a",
            color:      machine.status==="online" ? "#4caf50" : "#f44336",
            border:    `1px solid ${machine.status==="online" ? "#4caf50" : "#f44336"}`
          }}>
            {machine.status==="online" ? "● Online" : "● Offline"}
          </span>
        </div>
        <div style={{ color:"#666", fontSize:"13px" }}>
          {machine.ip} · {machine.os_name}
        </div>
      </div>

      {/* Graphs */}
      <div style={{ display:"grid", gridTemplateColumns:"1fr 1fr",
                    gap:"12px", marginBottom:"20px" }}>
        <Graph data={graphData} dataKey="cpu"  color="#00bcd4" label="CPU %"     />
        <Graph data={graphData} dataKey="ram"  color="#ffb300" label="RAM %"     />
        <Graph data={graphData} dataKey="disk" color="#4caf50" label="Disk %"    />
        <Graph data={graphData} dataKey="net"  color="#9c27b0" label="Net MB/s"  />
      </div>

      {/* Commands */}
      <div style={{
        background:"#13131f", border:"1px solid #2a2a3e",
        borderRadius:"10px", padding:"20px", marginBottom:"16px"
      }}>
        <div style={{ color:"#aaa", fontSize:"12px",
                      fontWeight:600, marginBottom:"12px" }}>
          COMMANDS
          <span style={{ marginLeft:"10px", fontSize:"11px",
            color: cmdStatus==="running" ? "#ffb300"
                 : cmdStatus==="done"    ? "#4caf50"
                 : cmdStatus==="failed"  ? "#f44336" : "#666"
          }}>
            {cmdStatus.toUpperCase()}
          </span>
        </div>
        <div style={{ display:"flex", gap:"8px", flexWrap:"wrap" }}>
          {["scan","boost","clean","fix","rollback"].map(cmd => (
            <button key={cmd} onClick={() => handleCommand(cmd)}
              disabled={cmdStatus==="running"}
              style={{
                padding:"8px 20px", background:"#1a1a2e",
                color:  cmdStatus==="running" ? "#444" : CMD_COLORS[cmd],
                border:`1px solid ${cmdStatus==="running" ? "#2a2a3e" : CMD_COLORS[cmd]}`,
                borderRadius:"8px", fontWeight:600, fontSize:"13px",
                textTransform:"capitalize",
                cursor: cmdStatus==="running" ? "not-allowed" : "pointer"
              }}>
              {cmd}
            </button>
          ))}
          <button onClick={() => { setTerminal(""); setCmdStatus("idle"); }}
            style={{
              padding:"8px 16px", background:"transparent",
              color:"#666", border:"1px solid #2a2a3e",
              borderRadius:"8px", cursor:"pointer", fontSize:"13px"
            }}>
            Clear
          </button>
        </div>
      </div>

      {/* Terminal */}
      <div ref={termRef} style={{
        background:"#080810", border:"1px solid #2a2a3e",
        borderRadius:"10px", padding:"16px",
        fontFamily:"monospace", fontSize:"12px",
        color:"#00ff88", height:"200px",
        overflowY:"auto", marginBottom:"20px",
        whiteSpace:"pre-wrap", lineHeight:"1.6"
      }}>
        {terminal || "No output yet. Run a command above."}
      </div>

      {/* Audit Log */}
      <div style={{
        background:"#13131f", border:"1px solid #2a2a3e",
        borderRadius:"10px", padding:"20px"
      }}>
        <div style={{ color:"#aaa", fontSize:"12px",
                      fontWeight:600, marginBottom:"12px" }}>
          AUDIT LOG
        </div>
        <table style={{ width:"100%", borderCollapse:"collapse", fontSize:"12px" }}>
          <thead>
            <tr style={{ color:"#666" }}>
              {["Timestamp","Action","Detail","Status"].map(h => (
                <th key={h} style={{ textAlign:"left", padding:"6px 8px",
                                     borderBottom:"1px solid #2a2a3e" }}>
                  {h}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {logs.map(l => (
              <tr key={l.id} style={{ borderBottom:"1px solid #1a1a2e" }}>
                <td style={{ padding:"6px 8px", color:"#666" }}>
                  {l.timestamp?.slice(0,16)}
                </td>
                <td style={{ padding:"6px 8px", color:"#00bcd4",
                             textTransform:"capitalize" }}>
                  {l.action}
                </td>
                <td style={{ padding:"6px 8px", color:"#aaa" }}>{l.detail}</td>
                <td style={{ padding:"6px 8px",
                  color: l.status==="ok" ? "#4caf50" : "#f44336" }}>
                  {l.status}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
