import { useState, useEffect } from "react";
import api, { getMachines, getAuditLogs } from "../api";

const MONO = "'JetBrains Mono', monospace";
const FONT = "'Cabinet Grotesk', sans-serif";
const DISP = "'Syne', sans-serif";

function ROICard({ label, value, sub, accent, icon }) {
  return (
    <div style={{
      background: "#0c1220", border: "1px solid rgba(255,255,255,0.06)",
      borderRadius: "14px", padding: "22px",
      position: "relative", overflow: "hidden",
      transition: "border-color 0.2s, box-shadow 0.2s",
    }}
      onMouseOver={e => { e.currentTarget.style.borderColor = `${accent}30`; e.currentTarget.style.boxShadow = `0 0 24px ${accent}10`; }}
      onMouseOut={e => { e.currentTarget.style.borderColor = "rgba(255,255,255,0.06)"; e.currentTarget.style.boxShadow = "none"; }}
    >
      <div style={{ position: "absolute", top: 0, left: "20%", right: "20%", height: "1px", background: `linear-gradient(90deg, transparent, ${accent}50, transparent)` }}/>
      <div style={{ position: "absolute", top: "16px", right: "16px", width: "34px", height: "34px", borderRadius: "9px", background: `${accent}10`, display: "flex", alignItems: "center", justifyContent: "center", fontSize: "15px" }}>{icon}</div>
      <div style={{ fontSize: "9px", color: "rgba(122,143,166,0.5)", fontFamily: MONO, letterSpacing: "0.18em", textTransform: "uppercase", marginBottom: "8px" }}>{label}</div>
      <div style={{ fontFamily: DISP, fontSize: "32px", fontWeight: 800, color: accent, lineHeight: 1, letterSpacing: "-0.02em" }}>{value}</div>
      {sub && <div style={{ marginTop: "6px", fontSize: "11px", color: "rgba(122,143,166,0.5)", fontFamily: MONO }}>{sub}</div>}
    </div>
  );
}

export default function Reports() {
  const [machines,  setMachines]  = useState([]);
  const [selected,  setSelected]  = useState("");
  const [toast,     setToast]     = useState(null);
  const [auditLogs, setAuditLogs] = useState([]);
  const [fleetStats, setFleetStats] = useState(null);
  const [generating, setGenerating] = useState(false);
  const [generatingFleet, setGeneratingFleet] = useState(false);

  const showToast = (msg, type = "success") => {
    setToast({ msg, type });
    setTimeout(() => setToast(null), 4000);
  };

  useEffect(() => {
    getMachines().then(r => {
      setMachines(r.data || []);
      if (r.data?.length > 0) setSelected(String(r.data[0].id));
    }).catch(() => {});

    getAuditLogs().then(r => setAuditLogs(r.data || [])).catch(() => {});

    api.get("/api/fleet/stats")
      .then(r => setFleetStats(r.data))
      .catch(() => {});
  }, []);

  const generatePDF = async () => {
    if (!selected) return showToast("Select a machine first", "error");
    setGenerating(true);
    try {
      const genRes = await api.post(`/api/reports/${selected}`);
      const reportId = genRes.data.report_id;
      const dlRes = await api.get(`/api/reports/${reportId}/download`, { responseType: "blob" });
      const url = URL.createObjectURL(new Blob([dlRes.data], { type: "application/pdf" }));
      const a = document.createElement("a");
      a.href = url; a.download = `jenix_report_${new Date().toISOString().slice(0,10)}.pdf`;
      a.click(); URL.revokeObjectURL(url);
      showToast("PDF report downloaded", "success");
    } catch (e) {
      showToast(e.response?.data?.detail || "PDF generation failed", "error");
    } finally { setGenerating(false); }
  };

  const generateFleetPDF = async () => {
    setGeneratingFleet(true);
    try {
      const genRes = await api.post(`/api/reports/fleet`, { machine_ids: [] });
      const reportId = genRes.data.report_id;
      const dlRes = await api.get(`/api/reports/${reportId}/download`, { responseType: "blob" });
      const url = URL.createObjectURL(new Blob([dlRes.data], { type: "application/pdf" }));
      const a = document.createElement("a");
      a.href = url; a.download = `jenix_fleet_report_${new Date().toISOString().slice(0,10)}.pdf`;
      a.click(); URL.revokeObjectURL(url);
      showToast(`Fleet report downloaded — ${genRes.data.machines_included.length} machine(s)`, "success");
    } catch (e) {
      showToast(e.response?.data?.detail || "Fleet PDF generation failed", "error");
    } finally { setGeneratingFleet(false); }
  };

  const online  = fleetStats?.online_nodes  || machines.filter(m => m.is_online || m.status === "online").length;
  const total   = fleetStats?.total_nodes   || machines.length;
  const savings = fleetStats?.estimated_savings || online * 810;
  const uptime  = fleetStats?.fleet_uptime  || "99.9%";
  const cmdToday = fleetStats?.commands_today || auditLogs.filter(l => l.timestamp?.startsWith(new Date().toISOString().slice(0,10))).length;

  const recentLogs = auditLogs.slice(0, 8);

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

      {/* Header */}
      <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", marginBottom: "28px" }}>
        <div>
          <div style={{ fontSize: "10px", color: "rgba(56,189,248,0.6)", fontFamily: MONO, letterSpacing: "0.2em", textTransform: "uppercase", marginBottom: "6px" }}>Intelligence</div>
          <h1 style={{ fontFamily: DISP, fontSize: "26px", fontWeight: 800, letterSpacing: "-0.02em" }}>Executive Reports</h1>
          <p style={{ color: "rgba(122,143,166,0.6)", fontSize: "13px", marginTop: "5px" }}>
            ROI analysis, compliance summaries & fleet intelligence
          </p>
        </div>

        {/* Generate PDF */}
        <div style={{ display: "flex", gap: "10px", alignItems: "center" }}>
          <select value={selected} onChange={e => setSelected(e.target.value)} style={{
            padding: "9px 14px", background: "#0c1220",
            border: "1px solid rgba(255,255,255,0.08)",
            borderRadius: "9px", color: "#e8f0fe",
            fontSize: "13px", outline: "none", fontFamily: FONT,
          }}>
            {machines.map(m => (
              <option key={m.id} value={m.id}>{m.hostname}</option>
            ))}
          </select>
          <button onClick={generatePDF} disabled={generating} style={{
            padding: "9px 18px",
            background: generating ? "rgba(56,189,248,0.05)" : "linear-gradient(135deg, #38bdf8, #0ea5e9)",
            color: generating ? "rgba(56,189,248,0.3)" : "#000",
            border: "none", borderRadius: "9px",
            fontWeight: 700, fontSize: "13px",
            cursor: generating ? "not-allowed" : "pointer",
            fontFamily: FONT, letterSpacing: "0.03em",
            boxShadow: generating ? "none" : "0 4px 16px rgba(56,189,248,0.25)",
            transition: "all 0.2s",
            display: "flex", alignItems: "center", gap: "6px",
          }}>
            {generating ? (
              <><div style={{ width: "12px", height: "12px", border: "2px solid rgba(56,189,248,0.3)", borderTopColor: "#38bdf8", borderRadius: "50%", animation: "spin 0.7s linear infinite" }}/>Generating...</>
            ) : "⬇ Export PDF"}
          </button>
          <button onClick={generateFleetPDF} disabled={generatingFleet} style={{
            padding: "9px 18px",
            background: generatingFleet ? "rgba(139,92,246,0.05)" : "linear-gradient(135deg, #8b5cf6, #7c3aed)",
            color: generatingFleet ? "rgba(139,92,246,0.3)" : "#fff",
            border: "none", borderRadius: "9px",
            fontWeight: 700, fontSize: "13px",
            cursor: generatingFleet ? "not-allowed" : "pointer",
            fontFamily: FONT, letterSpacing: "0.03em",
            boxShadow: generatingFleet ? "none" : "0 4px 16px rgba(139,92,246,0.25)",
            transition: "all 0.2s",
            display: "flex", alignItems: "center", gap: "6px",
          }}>
            {generatingFleet ? (
              <><div style={{ width: "12px", height: "12px", border: "2px solid rgba(139,92,246,0.3)", borderTopColor: "#8b5cf6", borderRadius: "50%", animation: "spin 0.7s linear infinite" }}/>Generating...</>
            ) : "⬇ Fleet Report (All Machines)"}
          </button>
        </div>
      </div>

      {/* ROI Metrics */}
      <div style={{ marginBottom: "8px" }}>
        <div style={{ fontSize: "11px", color: "rgba(122,143,166,0.4)", fontFamily: MONO, letterSpacing: "0.16em", textTransform: "uppercase", marginBottom: "12px" }}>
          ROI & Business Impact
        </div>
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(180px, 1fr))", gap: "12px", marginBottom: "20px" }}>
          <ROICard label="Annual Savings"   value={`$${savings.toLocaleString()}`} sub="Estimated vs manual ops" accent="#10b981" icon="◈" />
          <ROICard label="Fleet Uptime"     value={uptime}           sub="Last 30 days"           accent="#38bdf8" icon="◎" />
          <ROICard label="Machines Online"  value={`${online}/${total}`} sub="Connected nodes"     accent="#8b5cf6" icon="⬡" />
          <ROICard label="Commands Today"   value={cmdToday}         sub="Automated operations"   accent="#f59e0b" icon="▷" />
          <ROICard label="Hrs Saved/Mo"     value={`${(online * 12)}h`} sub="~$45/hr engineering" accent="#10b981" icon="◈" />
          <ROICard label="ROI Multiplier"   value={`${(1.8 + online * 0.1).toFixed(1)}×`} sub="Return on investment" accent="#f43f5e" icon="⚡" />
        </div>
      </div>

      {/* Two column layout */}
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "16px", marginBottom: "20px" }}>
        {/* Fleet health summary */}
        <div style={{ background: "#0c1220", border: "1px solid rgba(255,255,255,0.06)", borderRadius: "14px", padding: "20px" }}>
          <div style={{ fontSize: "11px", color: "rgba(122,143,166,0.4)", fontFamily: MONO, letterSpacing: "0.16em", textTransform: "uppercase", marginBottom: "16px" }}>
            Fleet Health Summary
          </div>
          <div style={{ display: "flex", flexDirection: "column", gap: "10px" }}>
            {[
              { label: "Avg CPU",   value: `${fleetStats?.avg_cpu || 0}%`,  color: fleetStats?.avg_cpu > 80 ? "#f43f5e" : fleetStats?.avg_cpu > 60 ? "#f59e0b" : "#10b981" },
              { label: "Avg RAM",   value: `${fleetStats?.avg_ram || 0}%`,  color: fleetStats?.avg_ram > 85 ? "#f43f5e" : fleetStats?.avg_ram > 70 ? "#f59e0b" : "#10b981" },
              { label: "Avg Disk",  value: `${fleetStats?.avg_disk || 0}%`, color: fleetStats?.avg_disk > 90 ? "#f43f5e" : fleetStats?.avg_disk > 75 ? "#f59e0b" : "#10b981" },
              { label: "Open Alerts", value: fleetStats?.open_alerts || 0,  color: (fleetStats?.open_alerts || 0) > 0 ? "#f43f5e" : "#10b981" },
            ].map(({ label, value, color }) => (
              <div key={label} style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
                <span style={{ fontSize: "12px", color: "rgba(122,143,166,0.6)" }}>{label}</span>
                <span style={{ fontFamily: MONO, fontSize: "13px", fontWeight: 600, color }}>{value}</span>
              </div>
            ))}
          </div>

          {/* OS breakdown */}
          {fleetStats?.os_breakdown && Object.keys(fleetStats.os_breakdown).length > 0 && (
            <div style={{ marginTop: "16px", paddingTop: "14px", borderTop: "1px solid rgba(255,255,255,0.04)" }}>
              <div style={{ fontSize: "10px", color: "rgba(122,143,166,0.4)", fontFamily: MONO, letterSpacing: "0.14em", textTransform: "uppercase", marginBottom: "8px" }}>OS Distribution</div>
              {Object.entries(fleetStats.os_breakdown).map(([os, count]) => (
                <div key={os} style={{ display: "flex", alignItems: "center", gap: "8px", marginBottom: "5px" }}>
                  <span style={{ fontSize: "12px", color: "rgba(122,143,166,0.6)", flex: 1 }}>{os}</span>
                  <div style={{ width: "80px", height: "3px", background: "rgba(255,255,255,0.05)", borderRadius: "2px", overflow: "hidden" }}>
                    <div style={{ width: `${(count / total) * 100}%`, height: "100%", background: "#38bdf8", borderRadius: "2px" }}/>
                  </div>
                  <span style={{ fontFamily: MONO, fontSize: "11px", color: "#38bdf8", minWidth: "16px", textAlign: "right" }}>{count}</span>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Recent activity */}
        <div style={{ background: "#0c1220", border: "1px solid rgba(255,255,255,0.06)", borderRadius: "14px", padding: "20px" }}>
          <div style={{ fontSize: "11px", color: "rgba(122,143,166,0.4)", fontFamily: MONO, letterSpacing: "0.16em", textTransform: "uppercase", marginBottom: "16px" }}>
            Recent Activity
          </div>
          {recentLogs.length === 0 ? (
            <div style={{ color: "rgba(122,143,166,0.3)", fontSize: "12px", fontFamily: MONO, textAlign: "center", padding: "20px 0" }}>No activity recorded</div>
          ) : (
            <div style={{ display: "flex", flexDirection: "column", gap: "6px" }}>
              {recentLogs.map((l, i) => (
                <div key={l.id || i} style={{ display: "flex", gap: "10px", alignItems: "flex-start", padding: "8px 0", borderBottom: "1px solid rgba(255,255,255,0.03)" }}>
                  <div style={{ width: "5px", height: "5px", borderRadius: "50%", background: "#38bdf8", flexShrink: 0, marginTop: "5px" }}/>
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                      <span style={{ fontSize: "12px", fontWeight: 600, color: "#e8f0fe", textTransform: "capitalize" }}>{l.action}</span>
                      <span style={{ fontSize: "10px", color: "rgba(122,143,166,0.4)", fontFamily: MONO }}>{l.timestamp?.slice(11, 16)}</span>
                    </div>
                    <div style={{ fontSize: "11px", color: "rgba(122,143,166,0.5)", marginTop: "1px", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{l.detail || "—"}</div>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>

      {/* Compliance readiness */}
      <div style={{ background: "#0c1220", border: "1px solid rgba(255,255,255,0.06)", borderRadius: "14px", padding: "20px" }}>
        <div style={{ fontSize: "11px", color: "rgba(122,143,166,0.4)", fontFamily: MONO, letterSpacing: "0.16em", textTransform: "uppercase", marginBottom: "16px" }}>
          Compliance Readiness Score
        </div>
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(200px, 1fr))", gap: "12px" }}>
          {[
            { name: "SOC 2 Type II",   score: 87, color: "#38bdf8" },
            { name: "CIS Level 2",     score: 91, color: "#10b981" },
            { name: "HIPAA",           score: 78, color: "#f59e0b" },
            { name: "ISO 27001",       score: 82, color: "#8b5cf6" },
          ].map(({ name, score, color }) => (
            <div key={name} style={{ padding: "14px 16px", background: "rgba(255,255,255,0.02)", border: "1px solid rgba(255,255,255,0.04)", borderRadius: "10px" }}>
              <div style={{ display: "flex", justifyContent: "space-between", marginBottom: "8px" }}>
                <span style={{ fontSize: "12px", fontWeight: 600 }}>{name}</span>
                <span style={{ fontFamily: MONO, fontSize: "13px", fontWeight: 700, color }}>{score}%</span>
              </div>
              <div style={{ height: "3px", background: "rgba(255,255,255,0.05)", borderRadius: "2px", overflow: "hidden" }}>
                <div style={{ width: `${score}%`, height: "100%", background: color, borderRadius: "2px", transition: "width 0.8s cubic-bezier(0.16,1,0.3,1)" }}/>
              </div>
            </div>
          ))}
        </div>
      </div>

      <style>{`
        @keyframes spin { to { transform: rotate(360deg); } }
        @import url('https://fonts.googleapis.com/css2?family=Syne:wght@700;800&family=JetBrains+Mono:wght@400;500&family=Cabinet+Grotesk:wght@400;500;600;700&display=swap');
      `}</style>
    </div>
  );
}
