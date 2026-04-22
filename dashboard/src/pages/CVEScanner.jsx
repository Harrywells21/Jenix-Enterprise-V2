import { useState, useEffect } from "react";
import api, { getMachines } from "../api";

const MONO = "'JetBrains Mono', monospace";
const FONT = "'Cabinet Grotesk', sans-serif";
const DISP = "'Syne', sans-serif";

const SEV = {
  CRITICAL: { bg: "rgba(244,63,94,0.08)",   border: "rgba(244,63,94,0.25)",   text: "#f43f5e", glow: "rgba(244,63,94,0.3)" },
  HIGH:     { bg: "rgba(249,115,22,0.08)",   border: "rgba(249,115,22,0.25)",  text: "#f97316", glow: "rgba(249,115,22,0.3)" },
  MEDIUM:   { bg: "rgba(245,158,11,0.08)",   border: "rgba(245,158,11,0.2)",   text: "#f59e0b", glow: "none" },
  LOW:      { bg: "rgba(16,185,129,0.06)",   border: "rgba(16,185,129,0.15)",  text: "#10b981", glow: "none" },
  UNKNOWN:  { bg: "rgba(122,143,166,0.06)",  border: "rgba(122,143,166,0.12)", text: "#7a8fa6", glow: "none" },
};

function SevBadge({ level }) {
  const c = SEV[level] || SEV.UNKNOWN;
  return (
    <span style={{
      padding: "2px 8px", borderRadius: "5px",
      background: c.bg, border: `1px solid ${c.border}`,
      color: c.text, fontSize: "9px", fontWeight: 700,
      fontFamily: MONO, letterSpacing: "0.1em",
    }}>{level}</span>
  );
}

function ScanningAnimation() {
  return (
    <div style={{ textAlign: "center", padding: "60px 20px" }}>
      <div style={{
        width: "60px", height: "60px", margin: "0 auto 20px",
        position: "relative",
      }}>
        <div style={{
          position: "absolute", inset: 0, borderRadius: "50%",
          border: "2px solid rgba(56,189,248,0.1)",
        }}/>
        <div style={{
          position: "absolute", inset: 0, borderRadius: "50%",
          border: "2px solid transparent",
          borderTopColor: "#38bdf8",
          animation: "spin 0.8s linear infinite",
        }}/>
        <div style={{
          position: "absolute", inset: "8px", borderRadius: "50%",
          border: "2px solid transparent",
          borderTopColor: "rgba(56,189,248,0.4)",
          animation: "spin 1.2s linear infinite reverse",
        }}/>
      </div>
      <div style={{ fontFamily: DISP, fontSize: "16px", fontWeight: 700, color: "#38bdf8", marginBottom: "6px" }}>
        Scanning Packages
      </div>
      <div style={{ fontSize: "12px", color: "rgba(122,143,166,0.5)", fontFamily: MONO }}>
        Checking against OSV.dev vulnerability database...
      </div>
      <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>
    </div>
  );
}

export default function CVEScanner() {
  const [machines, setMachines] = useState([]);
  const [selected, setSelected] = useState("");
  const [scanning, setScanning] = useState(false);
  const [results,  setResults]  = useState(null);
  const [summary,  setSummary]  = useState(null);
  const [toast,    setToast]    = useState(null);
  const [sevFilter, setSevFilter] = useState("ALL");

  const showToast = (msg, type = "success") => {
    setToast({ msg, type });
    setTimeout(() => setToast(null), 4000);
  };

  useEffect(() => {
    getMachines().then(r => {
      setMachines(r.data || []);
      if (r.data?.length > 0) setSelected(String(r.data[0].id));
    }).catch(() => {});
    api.get("/api/nodes").then(r => {
      const nodes = r.data || [];
      if (nodes.length > 0) {
        api.get(`/api/nodes/${nodes[0].id}/scan/latest`)
          .then(s => setSummary(s.data))
          .catch(() => {});
      }
    }).catch(() => {});
  }, []);

  const startScan = async () => {
    if (!selected) return showToast("Select a machine first", "error");
    setScanning(true); setResults(null);
    try {
      await api.post(`/api/nodes/${selected}/scan`);
      showToast("CVE scan initiated — checking packages...", "success");
      const interval = setInterval(async () => {
        try {
          const r = await api.get(`/api/nodes/${selected}/scan/latest`);
          if (r.data && !r.data.message) {
            setResults(r.data); setScanning(false);
            clearInterval(interval);
            showToast(`Scan complete — ${r.data.findings?.length || 0} CVEs found`, r.data.critical_cve > 0 ? "error" : "success");
          }
        } catch {}
      }, 3000);
      setTimeout(() => { clearInterval(interval); setScanning(false); }, 120_000);
    } catch (e) {
      showToast(e.response?.data?.detail || e.message, "error");
      setScanning(false);
    }
  };

  const findings = results?.findings || [];
  const filtered = sevFilter === "ALL" ? findings : findings.filter(f => f.severity?.toUpperCase() === sevFilter);

  const sevCounts = findings.reduce((acc, f) => {
    const s = f.severity?.toUpperCase() || "UNKNOWN";
    acc[s] = (acc[s] || 0) + 1;
    return acc;
  }, {});

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
      <div style={{ marginBottom: "24px" }}>
        <div style={{ fontSize: "10px", color: "rgba(56,189,248,0.6)", fontFamily: MONO, letterSpacing: "0.2em", textTransform: "uppercase", marginBottom: "6px" }}>Security</div>
        <h1 style={{ fontFamily: DISP, fontSize: "26px", fontWeight: 800, letterSpacing: "-0.02em" }}>CVE Scanner</h1>
        <p style={{ color: "rgba(122,143,166,0.6)", fontSize: "13px", marginTop: "5px" }}>
          Real-time vulnerability detection via OSV.dev database
        </p>
      </div>

      {/* Severity summary cards */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: "12px", marginBottom: "20px" }}>
        {["CRITICAL", "HIGH", "MEDIUM", "LOW"].map(sev => {
          const c = SEV[sev];
          const count = (results ? sevCounts[sev] || 0 : summary?.[`${sev.toLowerCase()}_cve`] || 0);
          return (
            <div key={sev} style={{
              background: count > 0 ? c.bg : "#0c1220",
              border: `1px solid ${count > 0 ? c.border : "rgba(255,255,255,0.06)"}`,
              borderRadius: "12px", padding: "18px",
              cursor: results ? "pointer" : "default",
              transition: "all 0.2s",
              boxShadow: count > 0 && (sev === "CRITICAL" || sev === "HIGH") ? `0 0 20px ${c.glow}` : "none",
            }}
              onClick={() => results && setSevFilter(sevFilter === sev ? "ALL" : sev)}
            >
              <div style={{ fontSize: "9px", color: count > 0 ? c.text : "rgba(122,143,166,0.4)", fontFamily: MONO, letterSpacing: "0.18em", textTransform: "uppercase", marginBottom: "8px" }}>
                {sev}
              </div>
              <div style={{ fontFamily: DISP, fontSize: "32px", fontWeight: 800, color: count > 0 ? c.text : "rgba(61,80,104,0.5)", lineHeight: 1 }}>
                {count}
              </div>
              {count > 0 && sev === "CRITICAL" && (
                <div style={{ fontSize: "10px", color: c.text, fontFamily: MONO, marginTop: "6px", opacity: 0.7 }}>Immediate action</div>
              )}
            </div>
          );
        })}
      </div>

      {/* Scanner control */}
      <div style={{
        background: "#0c1220",
        border: "1px solid rgba(255,255,255,0.06)",
        borderRadius: "14px", padding: "20px",
        marginBottom: "20px",
      }}>
        <div style={{ fontSize: "11px", color: "rgba(122,143,166,0.5)", fontFamily: MONO, letterSpacing: "0.16em", textTransform: "uppercase", marginBottom: "14px" }}>
          Run Vulnerability Scan
        </div>
        <div style={{ display: "flex", gap: "12px", alignItems: "center", flexWrap: "wrap" }}>
          <select
            value={selected} onChange={e => setSelected(e.target.value)}
            style={{
              padding: "10px 14px",
              background: "#080d1a", border: "1px solid rgba(255,255,255,0.08)",
              borderRadius: "9px", color: "#e8f0fe",
              fontSize: "13px", outline: "none", fontFamily: FONT,
              minWidth: "200px",
            }}
          >
            {machines.length === 0 && <option value="">No machines connected</option>}
            {machines.map(m => (
              <option key={m.id} value={m.id}>{m.hostname} · {m.ip || m.ip_address || "—"}</option>
            ))}
          </select>

          <button onClick={startScan} disabled={scanning || machines.length === 0}
            style={{
              padding: "10px 24px",
              background: scanning ? "rgba(244,63,94,0.06)" : "linear-gradient(135deg, #f43f5e, #e11d48)",
              color: scanning ? "rgba(244,63,94,0.4)" : "#fff",
              border: `1px solid ${scanning ? "rgba(244,63,94,0.15)" : "transparent"}`,
              borderRadius: "9px", fontWeight: 700, fontSize: "13px",
              cursor: scanning ? "not-allowed" : "pointer",
              fontFamily: FONT, letterSpacing: "0.03em",
              boxShadow: scanning ? "none" : "0 4px 16px rgba(244,63,94,0.3)",
              transition: "all 0.2s",
              display: "flex", alignItems: "center", gap: "8px",
            }}
            onMouseOver={e => { if (!scanning) e.currentTarget.style.transform = "translateY(-1px)"; }}
            onMouseOut={e => { e.currentTarget.style.transform = "translateY(0)"; }}
          >
            {scanning ? (
              <>
                <div style={{ width: "12px", height: "12px", border: "2px solid rgba(244,63,94,0.3)", borderTopColor: "#f43f5e", borderRadius: "50%", animation: "spin 0.7s linear infinite" }}/>
                Scanning...
              </>
            ) : "🛡 Start CVE Scan"}
          </button>

          {results && (
            <div style={{ fontSize: "12px", color: "rgba(122,143,166,0.5)", fontFamily: MONO }}>
              Last scan: {results.scanned_at?.slice(0, 16).replace("T", " ")} UTC
            </div>
          )}
        </div>
      </div>

      {/* Scanning animation */}
      {scanning && (
        <div style={{
          background: "#0c1220", border: "1px solid rgba(56,189,248,0.1)",
          borderRadius: "14px", marginBottom: "20px",
        }}>
          <ScanningAnimation />
        </div>
      )}

      {/* Results */}
      {results && !scanning && (
        <>
          {/* Risk banner */}
          <div style={{
            display: "flex", alignItems: "center", justifyContent: "space-between",
            padding: "16px 20px", marginBottom: "16px",
            background: results.critical_cve > 0 ? "rgba(244,63,94,0.06)" : "rgba(16,185,129,0.06)",
            border: `1px solid ${results.critical_cve > 0 ? "rgba(244,63,94,0.2)" : "rgba(16,185,129,0.2)"}`,
            borderRadius: "12px",
          }}>
            <div>
              <div style={{
                fontFamily: DISP, fontSize: "16px", fontWeight: 700,
                color: results.critical_cve > 0 ? "#f43f5e" : "#10b981",
                marginBottom: "3px",
              }}>
                {results.critical_cve > 0 ? "⚠ Critical Vulnerabilities Detected" : "✓ No Critical Vulnerabilities"}
              </div>
              <div style={{ fontSize: "12px", color: "rgba(122,143,166,0.6)", fontFamily: MONO }}>
                {findings.length} total CVEs found across all packages
              </div>
            </div>
            <div style={{ display: "flex", gap: "8px" }}>
              {sevFilter !== "ALL" && (
                <button onClick={() => setSevFilter("ALL")} style={{
                  padding: "6px 12px", background: "rgba(255,255,255,0.04)",
                  border: "1px solid rgba(255,255,255,0.08)", borderRadius: "6px",
                  color: "rgba(122,143,166,0.6)", fontSize: "11px", cursor: "pointer",
                  fontFamily: MONO,
                }}>Show All</button>
              )}
            </div>
          </div>

          {/* Severity filter tabs */}
          {findings.length > 0 && (
            <div style={{ display: "flex", gap: "6px", marginBottom: "14px", flexWrap: "wrap" }}>
              {["ALL", "CRITICAL", "HIGH", "MEDIUM", "LOW"].map(sev => {
                const count = sev === "ALL" ? findings.length : (sevCounts[sev] || 0);
                if (sev !== "ALL" && count === 0) return null;
                const c = sev === "ALL" ? { text: "#38bdf8", border: "rgba(56,189,248,0.3)", bg: "rgba(56,189,248,0.08)" } : SEV[sev];
                return (
                  <button key={sev} onClick={() => setSevFilter(sev)} style={{
                    padding: "6px 12px",
                    background: sevFilter === sev ? c.bg : "rgba(255,255,255,0.02)",
                    border: `1px solid ${sevFilter === sev ? c.border : "rgba(255,255,255,0.06)"}`,
                    borderRadius: "20px", color: sevFilter === sev ? c.text : "rgba(122,143,166,0.4)",
                    fontSize: "11px", cursor: "pointer", fontFamily: MONO,
                    display: "flex", alignItems: "center", gap: "5px",
                  }}>
                    {sev} <span style={{ opacity: 0.7 }}>{count}</span>
                  </button>
                );
              })}
            </div>
          )}

          {/* CVE list */}
          {filtered.length === 0 ? (
            <div style={{
              textAlign: "center", padding: "60px",
              background: "#0c1220", border: "1px solid rgba(16,185,129,0.15)",
              borderRadius: "14px",
            }}>
              <div style={{ fontSize: "32px", marginBottom: "12px" }}>✓</div>
              <div style={{ fontFamily: DISP, fontSize: "16px", fontWeight: 700, color: "#10b981", marginBottom: "6px" }}>
                No {sevFilter !== "ALL" ? sevFilter + " " : ""}Vulnerabilities Found
              </div>
              <div style={{ fontSize: "12px", color: "rgba(122,143,166,0.5)", fontFamily: MONO }}>
                All scanned packages are clean
              </div>
            </div>
          ) : (
            <div style={{ display: "flex", flexDirection: "column", gap: "8px" }}>
              {filtered.map((f, i) => {
                const sev = f.severity?.toUpperCase() || "UNKNOWN";
                const c = SEV[sev] || SEV.UNKNOWN;
                return (
                  <div key={f.cve_id || i} style={{
                    background: "#0c1220",
                    border: `1px solid ${sev === "CRITICAL" || sev === "HIGH" ? c.border : "rgba(255,255,255,0.06)"}`,
                    borderRadius: "12px", padding: "16px 18px",
                    transition: "all 0.15s",
                  }}
                    onMouseOver={e => { e.currentTarget.style.borderColor = c.border; e.currentTarget.style.background = "#0e1628"; }}
                    onMouseOut={e => { e.currentTarget.style.borderColor = (sev === "CRITICAL" || sev === "HIGH") ? c.border : "rgba(255,255,255,0.06)"; e.currentTarget.style.background = "#0c1220"; }}
                  >
                    <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", gap: "12px" }}>
                      <div style={{ flex: 1, minWidth: 0 }}>
                        <div style={{ display: "flex", alignItems: "center", gap: "8px", marginBottom: "6px", flexWrap: "wrap" }}>
                          <span style={{ fontFamily: MONO, fontSize: "13px", fontWeight: 700, color: c.text }}>
                            {f.cve_id || "CVE-UNKNOWN"}
                          </span>
                          <SevBadge level={sev} />
                          {f.package && (
                            <span style={{ fontSize: "11px", color: "rgba(122,143,166,0.5)", fontFamily: MONO }}>
                              {f.package}
                            </span>
                          )}
                        </div>
                        <div style={{ fontSize: "13px", color: "rgba(122,143,166,0.7)", lineHeight: 1.5 }}>
                          {f.description || "No description available"}
                        </div>
                      </div>
                      {f.cve_id && (
                        <a
                          href={`https://osv.dev/vulnerability/${f.cve_id}`}
                          target="_blank" rel="noreferrer"
                          style={{
                            padding: "5px 12px",
                            background: "rgba(255,255,255,0.03)",
                            border: "1px solid rgba(255,255,255,0.07)",
                            borderRadius: "6px", color: "rgba(56,189,248,0.6)",
                            fontSize: "11px", textDecoration: "none",
                            fontFamily: MONO, flexShrink: 0,
                            transition: "all 0.15s",
                          }}
                          onMouseOver={e => { e.currentTarget.style.color = "#38bdf8"; e.currentTarget.style.borderColor = "rgba(56,189,248,0.25)"; }}
                          onMouseOut={e => { e.currentTarget.style.color = "rgba(56,189,248,0.6)"; e.currentTarget.style.borderColor = "rgba(255,255,255,0.07)"; }}
                        >Details →</a>
                      )}
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </>
      )}

      {!results && !scanning && (
        <div style={{
          textAlign: "center", padding: "80px 20px",
          color: "rgba(122,143,166,0.3)",
        }}>
          <div style={{ fontSize: "36px", marginBottom: "14px", opacity: 0.5 }}>🛡</div>
          <div style={{ fontFamily: DISP, fontSize: "16px", fontWeight: 600, marginBottom: "6px" }}>
            Ready to Scan
          </div>
          <div style={{ fontSize: "12px", fontFamily: MONO }}>
            Select a machine and click Start CVE Scan
          </div>
        </div>
      )}

      <style>{`
        @keyframes spin { to { transform: rotate(360deg); } }
        @import url('https://fonts.googleapis.com/css2?family=Syne:wght@700;800&family=JetBrains+Mono:wght@400;500&family=Cabinet+Grotesk:wght@400;500;600;700&display=swap');
      `}</style>
    </div>
  );
}
