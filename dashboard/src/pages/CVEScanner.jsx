import { useState, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import api, { getMachines } from "../api";

const SEVERITY_COLOR = {
  CRITICAL: "#f44336",
  HIGH:     "#ff6b35",
  MEDIUM:   "#ffb300",
  LOW:      "#4caf50",
  UNKNOWN:  "#666",
};

function SeverityBadge({ level }) {
  return (
    <span style={{
      padding:"2px 8px", borderRadius:"4px",
      fontSize:"10px", fontWeight:700,
      background: SEVERITY_COLOR[level] + "22",
      color:      SEVERITY_COLOR[level],
      border:    `1px solid ${SEVERITY_COLOR[level]}44`
    }}>
      {level}
    </span>
  );
}

export default function CVEScanner() {
  const [machines,  setMachines]  = useState([]);
  const [selected,  setSelected]  = useState("");
  const [scanning,  setScanning]  = useState(false);
  const [results,   setResults]   = useState(null);
  const [summary,   setSummary]   = useState(null);
  const [toast,     setToast]     = useState("");
  const [polling,   setPolling]   = useState(false);

  const showToast = (msg) => {
    setToast(msg); setTimeout(() => setToast(""), 4000);
  };

  useEffect(() => {
    getMachines().then(r => {
      setMachines(r.data);
      if (r.data.length > 0) setSelected(String(r.data[0].id));
    });
    api.get("/cve/summary").then(r => setSummary(r.data))
       .catch(() => {});
  }, []);

  const startScan = async () => {
    if (!selected) return showToast("Select a machine first");
    setScanning(true);
    setResults(null);
    try {
      await api.post(`/cve/scan/${selected}`);
      showToast("🔍 CVE scan started — checking packages...");
      // Poll for results every 3 seconds
      setPolling(true);
      const interval = setInterval(async () => {
        try {
          const r = await api.get(`/cve/results/${selected}`);
          if (r.data.scanned) {
            setResults(r.data);
            setScanning(false);
            setPolling(false);
            clearInterval(interval);
            // Refresh summary
            const s = await api.get("/cve/summary");
            setSummary(s.data);
          }
        } catch {}
      }, 3000);
      // Timeout after 2 minutes
      setTimeout(() => {
        clearInterval(interval);
        setScanning(false);
        setPolling(false);
      }, 120_000);
    } catch (e) {
      showToast(`❌ ${e.response?.data?.detail || e.message}`);
      setScanning(false);
    }
  };

  const riskColor = results
    ? SEVERITY_COLOR[results.risk_level] || "#666"
    : "#666";

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

      {/* Header */}
      <div style={{ marginBottom:"24px" }}>
        <h1 style={{ color:"#e0e0e0", fontSize:"22px",
                     fontWeight:700, marginBottom:"4px" }}>
          CVE Threat Intelligence
        </h1>
        <div style={{ color:"#666", fontSize:"13px" }}>
          Scan installed packages against known vulnerabilities
          via OSV.dev database
        </div>
      </div>

      {/* Summary cards */}
      {summary && summary.machines_scanned > 0 && (
        <div style={{ display:"grid",
                      gridTemplateColumns:"repeat(3,1fr)",
                      gap:"12px", marginBottom:"20px" }}>
          {[
            { label:"Machines Scanned",
              value: summary.machines_scanned,
              color:"#00bcd4", icon:"🔍" },
            { label:"Critical CVEs",
              value: summary.total_critical,
              color: summary.total_critical > 0 ? "#f44336" : "#4caf50",
              icon:"🚨" },
            { label:"High CVEs",
              value: summary.total_high,
              color: summary.total_high > 0 ? "#ff6b35" : "#4caf50",
              icon:"⚠️" },
          ].map(({ label, value, color, icon }) => (
            <div key={label} style={{
              background:"#13131f", border:"1px solid #2a2a3e",
              borderRadius:"10px", padding:"16px"
            }}>
              <div style={{ display:"flex", justifyContent:"space-between",
                            alignItems:"center", marginBottom:"8px" }}>
                <span style={{ color:"#666", fontSize:"11px",
                               fontWeight:600 }}>
                  {label}
                </span>
                <span>{icon}</span>
              </div>
              <div style={{ color, fontSize:"28px", fontWeight:800 }}>
                {value}
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Scanner control */}
      <div style={{
        background:"#13131f", border:"1px solid #2a2a3e",
        borderRadius:"12px", padding:"20px", marginBottom:"20px"
      }}>
        <div style={{ color:"#aaa", fontSize:"12px",
                      fontWeight:600, marginBottom:"12px" }}>
          RUN CVE SCAN
        </div>
        <div style={{ display:"flex", gap:"12px",
                      alignItems:"center" }}>
          <select value={selected}
            onChange={e => setSelected(e.target.value)}
            style={{
              padding:"8px 14px", background:"#1a1a2e",
              border:"1px solid #2a2a3e", borderRadius:"8px",
              color:"#e0e0e0", fontSize:"13px", outline:"none"
            }}>
            {machines.map(m => (
              <option key={m.id} value={m.id}>
                {m.hostname} ({m.ip})
              </option>
            ))}
          </select>
          <button onClick={startScan} disabled={scanning}
            style={{
              padding:"8px 24px",
              background: scanning ? "#1a1a2e" : "#f44336",
              color: scanning ? "#666" : "#fff",
              border:"none", borderRadius:"8px",
              fontWeight:700, fontSize:"13px",
              cursor: scanning ? "not-allowed" : "pointer"
            }}>
            {scanning ? "🔍 Scanning..." : "🔍 Start CVE Scan"}
          </button>
          {scanning && (
            <div style={{ color:"#666", fontSize:"12px" }}>
              Checking packages against OSV.dev database...
            </div>
          )}
        </div>
      </div>

      {/* Results */}
      {results && (
        <>
          {/* Risk summary */}
          <div style={{
            background: results.risk_level === "LOW"
              ? "#0a1a0a" : "#1a0a0a",
            border:`1px solid ${riskColor}`,
            borderRadius:"12px", padding:"20px",
            marginBottom:"20px",
            display:"flex", justifyContent:"space-between",
            alignItems:"center"
          }}>
            <div>
              <div style={{ color:riskColor, fontSize:"18px",
                            fontWeight:800, marginBottom:"4px" }}>
                Risk Level: {results.risk_level}
              </div>
              <div style={{ color:"#aaa", fontSize:"13px" }}>
                {results.packages_scanned} packages scanned ·
                {results.vulnerable_packages} vulnerable ·
                {results.total_vulns} total CVEs found
              </div>
              <div style={{ color:"#444", fontSize:"11px",
                            marginTop:"4px" }}>
                Scanned: {results.scanned_at?.slice(0,16).replace("T"," ")} UTC
              </div>
            </div>
            <div style={{ textAlign:"right" }}>
              <div style={{ display:"flex", gap:"8px",
                            justifyContent:"flex-end" }}>
                {[
                  { level:"CRITICAL", count:results.critical },
                  { level:"HIGH",     count:results.high     },
                ].map(({ level, count }) => (
                  <div key={level} style={{
                    background:"#0d0d1a",
                    border:`1px solid ${SEVERITY_COLOR[level]}44`,
                    borderRadius:"8px", padding:"8px 16px",
                    textAlign:"center"
                  }}>
                    <div style={{ color:SEVERITY_COLOR[level],
                                  fontSize:"20px", fontWeight:800 }}>
                      {count}
                    </div>
                    <div style={{ color:"#666", fontSize:"10px" }}>
                      {level}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </div>

          {/* Vulnerable packages */}
          {results.results.length === 0 ? (
            <div style={{
              background:"#0a1a0a", border:"1px solid #4caf50",
              borderRadius:"12px", padding:"40px",
              textAlign:"center"
            }}>
              <div style={{ fontSize:"40px", marginBottom:"12px" }}>
                ✅
              </div>
              <div style={{ color:"#4caf50", fontSize:"16px",
                            fontWeight:700 }}>
                No vulnerabilities found
              </div>
              <div style={{ color:"#666", fontSize:"13px",
                            marginTop:"4px" }}>
                All scanned packages are clean
              </div>
            </div>
          ) : (
            <div style={{
              background:"#13131f", border:"1px solid #2a2a3e",
              borderRadius:"12px", overflow:"hidden"
            }}>
              <div style={{ padding:"16px 20px",
                            borderBottom:"1px solid #2a2a3e" }}>
                <span style={{ color:"#aaa", fontSize:"12px",
                               fontWeight:600 }}>
                  VULNERABLE PACKAGES ({results.results.length})
                </span>
              </div>
              {results.results.map((pkg, i) => (
                <div key={i} style={{
                  padding:"16px 20px",
                  borderBottom: i < results.results.length-1
                    ? "1px solid #1a1a2e" : "none"
                }}>
                  <div style={{ display:"flex",
                                justifyContent:"space-between",
                                alignItems:"center",
                                marginBottom:"8px" }}>
                    <div>
                      <span style={{ color:"#e0e0e0", fontWeight:700,
                                     fontSize:"14px" }}>
                        {pkg.package}
                      </span>
                      <span style={{ color:"#666", fontSize:"12px",
                                     marginLeft:"8px" }}>
                        v{pkg.version}
                      </span>
                    </div>
                    <div style={{ display:"flex", gap:"8px",
                                  alignItems:"center" }}>
                      <SeverityBadge level={pkg.highest} />
                      <span style={{ color:"#666", fontSize:"12px" }}>
                        {pkg.count} CVE{pkg.count>1?"s":""}
                      </span>
                    </div>
                  </div>
                  {/* CVE list */}
                  <div style={{ display:"flex",
                                flexDirection:"column", gap:"6px" }}>
                    {pkg.vulns.map((v, j) => (
                      <div key={j} style={{
                        background:"#0d0d1a",
                        border:"1px solid #1a1a2e",
                        borderRadius:"6px",
                        padding:"8px 12px",
                        display:"flex",
                        justifyContent:"space-between",
                        alignItems:"center"
                      }}>
                        <div style={{ flex:1, minWidth:0 }}>
                          <a href={v.url} target="_blank"
                             rel="noreferrer"
                             style={{ color:"#00bcd4",
                                      fontSize:"12px",
                                      fontWeight:600,
                                      textDecoration:"none" }}>
                            {v.id}
                          </a>
                          <span style={{ color:"#aaa",
                                         fontSize:"11px",
                                         marginLeft:"8px" }}>
                            {v.summary}
                          </span>
                        </div>
                        <SeverityBadge level={v.severity} />
                      </div>
                    ))}
                  </div>
                </div>
              ))}
            </div>
          )}
        </>
      )}
    </div>
  );
}
