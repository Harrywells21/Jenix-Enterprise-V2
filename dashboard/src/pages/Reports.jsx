import { useState, useEffect } from "react";
import { getMachines, generateReport,
         getReports, deleteReport, downloadReport } from "../api";

export default function Reports() {
  const [machines, setMachines] = useState([]);
  const [reports,  setReports]  = useState([]);
  const [selected, setSelected] = useState("");
  const [loading,  setLoading]  = useState(false);
  const [toast,    setToast]    = useState("");

  const showToast = (msg) => {
    setToast(msg); setTimeout(() => setToast(""), 4000);
  };

  // Build a quick lookup: machine_id → hostname
  const machineMap = Object.fromEntries(
    machines.map(m => [m.id, m.hostname])
  );

  useEffect(() => {
    getMachines().then(r => setMachines(r.data));
    getReports().then(r  => setReports(r.data));
  }, []);

  const generate = async () => {
    if (!selected) return showToast("Select a machine first");
    setLoading(true);
    try {
      await generateReport(selected);
      const r = await getReports();
      setReports(r.data);
      showToast("✅ Report generated successfully");
    } catch (e) {
      showToast(`❌ ${e.response?.data?.detail || e.message}`);
    } finally {
      setLoading(false);
    }
  };

  const handleDelete = async (id) => {
    if (!window.confirm("Delete this report?")) return;
    await deleteReport(id);
    setReports(prev => prev.filter(r => r.id !== id));
    showToast("Report deleted");
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
        Compliance Reports
      </h1>

      {/* Generate */}
      <div style={{
        background:"#13131f", border:"1px solid #2a2a3e",
        borderRadius:"10px", padding:"20px", marginBottom:"24px"
      }}>
        <div style={{ color:"#aaa", fontSize:"12px",
                      fontWeight:600, marginBottom:"12px" }}>
          GENERATE NEW REPORT
        </div>
        <div style={{ display:"flex", gap:"12px", alignItems:"center" }}>
          <select value={selected}
            onChange={e => setSelected(e.target.value)}
            style={{
              padding:"8px 14px", background:"#1a1a2e",
              border:"1px solid #2a2a3e", borderRadius:"8px",
              color:"#e0e0e0", fontSize:"13px", outline:"none"
            }}>
            <option value="">Select machine...</option>
            {machines.map(m => (
              <option key={m.id} value={m.id}>
                {m.hostname} ({m.ip})
              </option>
            ))}
          </select>
          <button onClick={generate} disabled={loading} style={{
            padding:"8px 20px",
            background: loading ? "#1a1a2e" : "#00bcd4",
            color:      loading ? "#666"    : "#000",
            border:"none", borderRadius:"8px",
            fontWeight:700, fontSize:"13px",
            cursor: loading ? "not-allowed" : "pointer"
          }}>
            {loading ? "Generating..." : "Generate PDF Report"}
          </button>
        </div>
      </div>

      {/* List */}
      <div style={{
        background:"#13131f", border:"1px solid #2a2a3e",
        borderRadius:"10px", padding:"20px"
      }}>
        <div style={{ color:"#aaa", fontSize:"12px",
                      fontWeight:600, marginBottom:"12px" }}>
          GENERATED REPORTS ({reports.length})
        </div>
        {reports.length === 0 ? (
          <div style={{ color:"#666", fontSize:"13px",
                        padding:"20px 0" }}>
            No reports yet. Generate one above.
          </div>
        ) : (
          <table style={{ width:"100%", borderCollapse:"collapse",
                          fontSize:"13px" }}>
            <thead>
              <tr style={{ color:"#666" }}>
                {["Machine","Filename","Size","Generated","Actions"].map(h => (
                  <th key={h} style={{ textAlign:"left", padding:"8px",
                                       borderBottom:"1px solid #2a2a3e" }}>
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {reports.map(r => (
                <tr key={r.id}
                  style={{ borderBottom:"1px solid #1a1a2e" }}>
                  {/* ✅ Fixed: show hostname not machine_id */}
                  <td style={{ padding:"8px", color:"#00bcd4",
                               fontWeight:600 }}>
                    {machineMap[r.machine_id] || `Machine ${r.machine_id}`}
                  </td>
                  <td style={{ padding:"8px", color:"#e0e0e0",
                               fontSize:"11px", maxWidth:"200px",
                               overflow:"hidden", textOverflow:"ellipsis",
                               whiteSpace:"nowrap" }}>
                    {r.filename}
                  </td>
                  <td style={{ padding:"8px", color:"#666" }}>
                    {r.size_kb} KB
                  </td>
                  <td style={{ padding:"8px", color:"#666" }}>
                    {r.created_at?.slice(0,16).replace("T"," ")}
                  </td>
                  <td style={{ padding:"8px" }}>
                    <div style={{ display:"flex", gap:"8px" }}>
                      <a href={downloadReport(r.id)}
                         target="_blank" rel="noreferrer"
                         style={{
                           padding:"4px 12px",
                           background:"#1a1a2e", color:"#00bcd4",
                           border:"1px solid #00bcd4",
                           borderRadius:"6px", fontSize:"12px",
                           textDecoration:"none"
                         }}>
                        ⬇ Download
                      </a>
                      <button onClick={() => handleDelete(r.id)}
                        style={{
                          padding:"4px 12px", background:"#1a1a2e",
                          color:"#f44336", border:"1px solid #f44336",
                          borderRadius:"6px", fontSize:"12px",
                          cursor:"pointer"
                        }}>
                        Delete
                      </button>
                    </div>
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
