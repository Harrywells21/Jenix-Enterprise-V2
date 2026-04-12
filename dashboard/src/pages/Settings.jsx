import { useState, useEffect } from "react";
import api from "../api";

export default function Settings() {
  const [license,   setLicense]   = useState(null);
  const [genForm,   setGenForm]   = useState({ company_name:"", max_nodes:-1 });
  const [genKey,    setGenKey]    = useState("");
  const [actKey,    setActKey]    = useState("");
  const [schedules, setSchedules] = useState([]);
  const [machines,  setMachines]  = useState([]);
  const [schForm,   setSchForm]   = useState({
    machine_id:"", scan_type:"security", frequency:"daily", hour:2
  });
  const [toast, setToast] = useState("");

  const showToast = (msg) => { setToast(msg); setTimeout(() => setToast(""), 4000); };

  useEffect(() => {
    api.get("/license").then(r => setLicense(r.data)).catch(() => {});
    api.get("/schedules").then(r => setSchedules(r.data)).catch(() => {});
    api.get("/machines").then(r => setMachines(r.data)).catch(() => {});
  }, []);

  const generateKey = async () => {
    try {
      const r = await api.post("/license/generate", genForm);
      setGenKey(r.data.key);
      showToast("✅ License key generated");
    } catch (e) { showToast(`❌ ${e.response?.data?.detail}`); }
  };

  const activateKey = async () => {
    try {
      await api.post("/license/activate", { key: actKey });
      const r = await api.get("/license");
      setLicense(r.data);
      showToast("✅ License activated");
    } catch (e) { showToast(`❌ ${e.response?.data?.detail}`); }
  };

  const createSchedule = async () => {
    try {
      await api.post("/schedules", {
        ...schForm,
        machine_id: parseInt(schForm.machine_id),
        hour:       parseInt(schForm.hour)
      });
      const r = await api.get("/schedules");
      setSchedules(r.data);
      showToast("✅ Schedule created");
    } catch (e) { showToast(`❌ ${e.response?.data?.detail}`); }
  };

  const deleteSchedule = async (id) => {
    await api.delete(`/schedules/${id}`);
    setSchedules(prev => prev.filter(s => s.id !== id));
    showToast("Schedule deleted");
  };

  const box = {
    background:"#13131f", border:"1px solid #2a2a3e",
    borderRadius:"10px", padding:"20px", marginBottom:"20px"
  };
  const label = { color:"#aaa", fontSize:"12px",
                  fontWeight:600, marginBottom:"12px", display:"block" };
  const input = {
    padding:"8px 12px", background:"#1a1a2e",
    border:"1px solid #2a2a3e", borderRadius:"8px",
    color:"#e0e0e0", fontSize:"13px", outline:"none"
  };
  const btn = (color="#00bcd4") => ({
    padding:"8px 18px", background: color==="red" ? "#1a1a2e" : "#00bcd4",
    color: color==="red" ? "#f44336" : "#000",
    border: color==="red" ? "1px solid #f44336" : "none",
    borderRadius:"8px", fontWeight:700,
    fontSize:"13px", cursor:"pointer"
  });

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

      <h1 style={{ color:"#e0e0e0", fontSize:"22px",
                   fontWeight:700, marginBottom:"24px" }}>
        Settings
      </h1>

      {/* License Status */}
      <div style={box}>
        <span style={label}>LICENSE STATUS</span>
        {license?.activated ? (
          <div>
            <div style={{ color:"#4caf50", fontWeight:700,
                          fontSize:"15px", marginBottom:"8px" }}>
              ✅ Licensed
            </div>
            <div style={{ color:"#aaa", fontSize:"13px", lineHeight:"1.8" }}>
              <div>Company: <b style={{color:"#e0e0e0"}}>{license.company_name}</b></div>
              <div>Nodes: <b style={{color:"#e0e0e0"}}>
                {license.max_nodes === -1 ? "Unlimited" : license.max_nodes}
              </b></div>
              <div>Type: <b style={{color:"#00bcd4"}}>Perpetual</b></div>
              <div>Activated: <b style={{color:"#e0e0e0"}}>
                {license.activated_at?.slice(0,10)}
              </b></div>
            </div>
          </div>
        ) : (
          <div style={{ color:"#f44336", fontSize:"13px" }}>
            No license activated. Activate one below.
          </div>
        )}
      </div>

      {/* Generate License */}
      <div style={box}>
        <span style={label}>GENERATE LICENSE KEY (Admin)</span>
        <div style={{ display:"flex", gap:"10px", flexWrap:"wrap",
                      marginBottom:"12px" }}>
          <input placeholder="Company name" style={input}
            value={genForm.company_name}
            onChange={e => setGenForm(p => ({...p, company_name:e.target.value}))}
          />
          <select style={input} value={genForm.max_nodes}
            onChange={e => setGenForm(p => ({...p, max_nodes:parseInt(e.target.value)}))}>
            <option value={-1}>Unlimited nodes</option>
            <option value={10}>10 nodes</option>
            <option value={50}>50 nodes</option>
            <option value={100}>100 nodes</option>
          </select>
          <button style={btn()} onClick={generateKey}>Generate</button>
        </div>
        {genKey && (
          <div style={{
            background:"#0d0d1a", border:"1px solid #2a2a3e",
            borderRadius:"8px", padding:"12px",
            fontFamily:"monospace", fontSize:"11px",
            color:"#00bcd4", wordBreak:"break-all"
          }}>
            {genKey}
          </div>
        )}
      </div>

      {/* Activate License */}
      <div style={box}>
        <span style={label}>ACTIVATE LICENSE</span>
        <div style={{ display:"flex", gap:"10px" }}>
          <input placeholder="Paste license key here..."
            style={{...input, flex:1}} value={actKey}
            onChange={e => setActKey(e.target.value)}
          />
          <button style={btn()} onClick={activateKey}>Activate</button>
        </div>
      </div>

      {/* Scheduled Scans */}
      <div style={box}>
        <span style={label}>SCHEDULED SCANS</span>
        <div style={{ display:"flex", gap:"10px", flexWrap:"wrap",
                      marginBottom:"16px" }}>
          <select style={input} value={schForm.machine_id}
            onChange={e => setSchForm(p => ({...p, machine_id:e.target.value}))}>
            <option value="">Select machine...</option>
            {machines.map(m => (
              <option key={m.id} value={m.id}>{m.hostname}</option>
            ))}
          </select>
          <select style={input} value={schForm.scan_type}
            onChange={e => setSchForm(p => ({...p, scan_type:e.target.value}))}>
            <option value="security">Security</option>
            <option value="scan">Health</option>
            <option value="clean">Clean</option>
          </select>
          <select style={input} value={schForm.frequency}
            onChange={e => setSchForm(p => ({...p, frequency:e.target.value}))}>
            <option value="daily">Daily</option>
            <option value="weekly">Weekly</option>
          </select>
          <select style={input} value={schForm.hour}
            onChange={e => setSchForm(p => ({...p, hour:e.target.value}))}>
            {[...Array(24)].map((_,i) => (
              <option key={i} value={i}>{String(i).padStart(2,"0")}:00</option>
            ))}
          </select>
          <button style={btn()} onClick={createSchedule}>Add Schedule</button>
        </div>

        {schedules.length === 0 ? (
          <div style={{ color:"#666", fontSize:"13px" }}>
            No schedules configured.
          </div>
        ) : (
          <table style={{ width:"100%", borderCollapse:"collapse",
                          fontSize:"13px" }}>
            <thead>
              <tr style={{ color:"#666" }}>
                {["Machine","Type","Frequency","Hour","Action"].map(h => (
                  <th key={h} style={{ textAlign:"left", padding:"8px",
                                       borderBottom:"1px solid #2a2a3e" }}>
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {schedules.map(s => {
                const m = machines.find(x => x.id === s.machine_id);
                return (
                  <tr key={s.id} style={{ borderBottom:"1px solid #1a1a2e" }}>
                    <td style={{ padding:"8px", color:"#e0e0e0" }}>
                      {m?.hostname || s.machine_id}
                    </td>
                    <td style={{ padding:"8px", color:"#00bcd4",
                                 textTransform:"capitalize" }}>
                      {s.scan_type}
                    </td>
                    <td style={{ padding:"8px", color:"#aaa",
                                 textTransform:"capitalize" }}>
                      {s.frequency}
                    </td>
                    <td style={{ padding:"8px", color:"#aaa" }}>
                      {String(s.hour).padStart(2,"0")}:00
                    </td>
                    <td style={{ padding:"8px" }}>
                      <button style={btn("red")}
                        onClick={() => deleteSchedule(s.id)}>
                        Delete
                      </button>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
