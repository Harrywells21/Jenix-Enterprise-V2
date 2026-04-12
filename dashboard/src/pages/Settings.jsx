import { useState, useEffect } from "react";
import api from "../api";

const input = {
  padding:"8px 12px", background:"#1a1a2e",
  border:"1px solid #2a2a3e", borderRadius:"8px",
  color:"#e0e0e0", fontSize:"13px",
  outline:"none", width:"100%"
};
const box = {
  background:"#13131f", border:"1px solid #2a2a3e",
  borderRadius:"10px", padding:"20px", marginBottom:"20px"
};
const label = {
  color:"#aaa", fontSize:"12px", fontWeight:600,
  marginBottom:"12px", display:"block"
};

export default function Settings() {
  const [license,   setLicense]   = useState(null);
  const [genForm,   setGenForm]   = useState({ company_name:"", max_nodes:-1 });
  const [genKey,    setGenKey]    = useState("");
  const [actKey,    setActKey]    = useState("");
  const [schedules, setSchedules] = useState([]);
  const [machines,  setMachines]  = useState([]);
  const [schForm,   setSchForm]   = useState({
    machine_id:"", scan_type:"security",
    frequency:"daily", hour:2
  });
  const [notify,    setNotify]    = useState({
    slack_webhook:"", teams_webhook:"",
    alert_email:"", smtp_host:"",
    smtp_port:587, smtp_user:"", smtp_pass:""
  });
  const [notifyStatus, setNotifyStatus] = useState(null);
  const [toast, setToast] = useState("");

  const showToast = (msg) => {
    setToast(msg); setTimeout(() => setToast(""), 4000);
  };

  useEffect(() => {
    api.get("/license").then(r    => setLicense(r.data)).catch(()=>{});
    api.get("/schedules").then(r  => setSchedules(r.data)).catch(()=>{});
    api.get("/machines").then(r   => setMachines(r.data)).catch(()=>{});
    api.get("/settings/notifications").then(r => {
      setNotify(r.data);
      setNotifyStatus(r.data);
    }).catch(()=>{});
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
      setLicense(r.data); setActKey("");
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

  const saveNotify = async () => {
    try {
      await api.post("/settings/notifications", notify);
      const r = await api.get("/settings/notifications");
      setNotifyStatus(r.data);
      showToast("✅ Notification settings saved");
    } catch (e) { showToast(`❌ ${e.response?.data?.detail}`); }
  };

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
          <div style={{
            display:"grid", gridTemplateColumns:"repeat(4,1fr)",
            gap:"16px"
          }}>
            {[
              { l:"Company",   v:license.company_name },
              { l:"Max Nodes", v:license.max_nodes===-1
                                 ? "Unlimited" : license.max_nodes },
              { l:"Type",      v:"Perpetual" },
              { l:"Activated", v:license.activated_at?.slice(0,10) },
            ].map(({ l, v }) => (
              <div key={l}>
                <div style={{ color:"#666", fontSize:"11px",
                              marginBottom:"4px" }}>{l}</div>
                <div style={{ color:"#00bcd4", fontWeight:700,
                              fontSize:"14px" }}>{v}</div>
              </div>
            ))}
          </div>
        ) : (
          <div style={{ color:"#f44336", fontSize:"13px" }}>
            No license activated.
          </div>
        )}
      </div>

      {/* Generate License */}
      <div style={box}>
        <span style={label}>GENERATE LICENSE KEY</span>
        <div style={{ display:"flex", gap:"10px",
                      flexWrap:"wrap", marginBottom:"12px" }}>
          <input placeholder="Company name"
            style={{...input, width:"auto"}}
            value={genForm.company_name}
            onChange={e => setGenForm(p=>({...p,company_name:e.target.value}))}
          />
          <select style={{...input, width:"auto"}}
            value={genForm.max_nodes}
            onChange={e => setGenForm(p=>({...p,max_nodes:parseInt(e.target.value)}))}>
            <option value={-1}>Unlimited nodes</option>
            <option value={10}>10 nodes</option>
            <option value={50}>50 nodes</option>
            <option value={100}>100 nodes</option>
          </select>
          <button onClick={generateKey} style={{
            padding:"8px 18px", background:"#00bcd4",
            color:"#000", border:"none", borderRadius:"8px",
            fontWeight:700, fontSize:"13px", cursor:"pointer"
          }}>Generate</button>
        </div>
        {genKey && (
          <div style={{
            background:"#0d0d1a", border:"1px solid #2a2a3e",
            borderRadius:"8px", padding:"12px",
            fontFamily:"monospace", fontSize:"11px",
            color:"#00bcd4", wordBreak:"break-all",
            cursor:"pointer"
          }} onClick={() => {
            navigator.clipboard.writeText(genKey);
            showToast("✅ Key copied to clipboard");
          }}>
            {genKey}
            <span style={{ color:"#444", marginLeft:"8px",
                           fontSize:"10px" }}>
              (click to copy)
            </span>
          </div>
        )}
      </div>

      {/* Activate License */}
      <div style={box}>
        <span style={label}>ACTIVATE LICENSE</span>
        <div style={{ display:"flex", gap:"10px" }}>
          <input placeholder="Paste license key here..."
            style={input} value={actKey}
            onChange={e => setActKey(e.target.value)}
          />
          <button onClick={activateKey} style={{
            padding:"8px 18px", background:"#00bcd4",
            color:"#000", border:"none", borderRadius:"8px",
            fontWeight:700, fontSize:"13px",
            cursor:"pointer", whiteSpace:"nowrap"
          }}>Activate</button>
        </div>
      </div>

      {/* Notifications */}
      <div style={box}>
        <span style={label}>
          NOTIFICATIONS
          <span style={{ marginLeft:"8px", fontWeight:400 }}>
            {notifyStatus?.slack_configured && (
              <span style={{ color:"#4caf50", marginRight:"8px" }}>
                ● Slack
              </span>
            )}
            {notifyStatus?.teams_configured && (
              <span style={{ color:"#4caf50", marginRight:"8px" }}>
                ● Teams
              </span>
            )}
            {notifyStatus?.smtp_configured && (
              <span style={{ color:"#4caf50" }}>● Email</span>
            )}
          </span>
        </span>

        <div style={{ display:"grid",
                      gridTemplateColumns:"1fr 1fr",
                      gap:"12px" }}>
          <div>
            <div style={{ color:"#666", fontSize:"11px",
                          marginBottom:"4px" }}>
              Slack Webhook URL
            </div>
            <input style={input}
              placeholder="https://hooks.slack.com/..."
              value={notify.slack_webhook}
              onChange={e => setNotify(p=>({...p,slack_webhook:e.target.value}))}
            />
          </div>
          <div>
            <div style={{ color:"#666", fontSize:"11px",
                          marginBottom:"4px" }}>
              Teams Webhook URL
            </div>
            <input style={input}
              placeholder="https://outlook.office.com/webhook/..."
              value={notify.teams_webhook}
              onChange={e => setNotify(p=>({...p,teams_webhook:e.target.value}))}
            />
          </div>
          <div>
            <div style={{ color:"#666", fontSize:"11px",
                          marginBottom:"4px" }}>
              Alert Email
            </div>
            <input style={input} type="email"
              placeholder="alerts@yourcompany.com"
              value={notify.alert_email}
              onChange={e => setNotify(p=>({...p,alert_email:e.target.value}))}
            />
          </div>
          <div>
            <div style={{ color:"#666", fontSize:"11px",
                          marginBottom:"4px" }}>
              SMTP Host
            </div>
            <input style={input}
              placeholder="smtp.gmail.com"
              value={notify.smtp_host}
              onChange={e => setNotify(p=>({...p,smtp_host:e.target.value}))}
            />
          </div>
          <div>
            <div style={{ color:"#666", fontSize:"11px",
                          marginBottom:"4px" }}>
              SMTP User
            </div>
            <input style={input} type="email"
              placeholder="your@email.com"
              value={notify.smtp_user}
              onChange={e => setNotify(p=>({...p,smtp_user:e.target.value}))}
            />
          </div>
          <div>
            <div style={{ color:"#666", fontSize:"11px",
                          marginBottom:"4px" }}>
              SMTP Password
            </div>
            <input style={input} type="password"
              placeholder="App password"
              value={notify.smtp_pass}
              onChange={e => setNotify(p=>({...p,smtp_pass:e.target.value}))}
            />
          </div>
        </div>
        <button onClick={saveNotify} style={{
          marginTop:"16px", padding:"8px 24px",
          background:"#00bcd4", color:"#000",
          border:"none", borderRadius:"8px",
          fontWeight:700, fontSize:"13px", cursor:"pointer"
        }}>
          Save Notification Settings
        </button>
      </div>

      {/* Scheduled Scans */}
      <div style={box}>
        <span style={label}>SCHEDULED SCANS</span>
        <div style={{ display:"flex", gap:"10px",
                      flexWrap:"wrap", marginBottom:"16px" }}>
          <select style={{...input, width:"auto"}}
            value={schForm.machine_id}
            onChange={e => setSchForm(p=>({...p,machine_id:e.target.value}))}>
            <option value="">Select machine...</option>
            {machines.map(m => (
              <option key={m.id} value={m.id}>{m.hostname}</option>
            ))}
          </select>
          <select style={{...input, width:"auto"}}
            value={schForm.scan_type}
            onChange={e => setSchForm(p=>({...p,scan_type:e.target.value}))}>
            <option value="security">Security</option>
            <option value="scan">Health</option>
            <option value="clean">Clean</option>
          </select>
          <select style={{...input, width:"auto"}}
            value={schForm.frequency}
            onChange={e => setSchForm(p=>({...p,frequency:e.target.value}))}>
            <option value="daily">Daily</option>
            <option value="weekly">Weekly</option>
          </select>
          <select style={{...input, width:"auto"}}
            value={schForm.hour}
            onChange={e => setSchForm(p=>({...p,hour:e.target.value}))}>
            {[...Array(24)].map((_,i)=>(
              <option key={i} value={i}>
                {String(i).padStart(2,"0")}:00
              </option>
            ))}
          </select>
          <button onClick={createSchedule} style={{
            padding:"8px 18px", background:"#00bcd4",
            color:"#000", border:"none", borderRadius:"8px",
            fontWeight:700, fontSize:"13px", cursor:"pointer"
          }}>Add</button>
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
                {["Machine","Type","Frequency","Time","Action"].map(h=>(
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
                  <tr key={s.id}
                    style={{ borderBottom:"1px solid #1a1a2e" }}>
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
                      <button onClick={() => deleteSchedule(s.id)}
                        style={{
                          padding:"3px 10px", background:"#1a1a2e",
                          color:"#f44336", border:"1px solid #f44336",
                          borderRadius:"6px", fontSize:"11px",
                          cursor:"pointer"
                        }}>
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
