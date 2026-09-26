import { useEffect, useState, useCallback } from "react";
import KpiCard from "../components/KpiCard";
import { LoadingState, ErrorState, EmptyState } from "../components/States";
import { getComplianceScore } from "../api";

function scoreColor(score) {
  if (score >= 80) return "var(--emerald)";
  if (score >= 50) return "var(--amber)";
  return "var(--rose)";
}

export default function Security() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  const load = useCallback(async () => {
    try {
      const res = await getComplianceScore();
      setData(res.data);
      setError(null);
    } catch (e) {
      setError(e.response?.data?.detail || "Failed to load security data");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
    const iv = setInterval(load, 30000);
    return () => clearInterval(iv);
  }, [load]);

  if (loading) return <div style={{ padding: "22px 26px" }}><LoadingState rows={6} /></div>;
  if (error) return <div style={{ padding: "22px 26px" }}><ErrorState message={error} /></div>;

  const cve = data?.cve_severity_counts || {};
  const unresolved = data?.unresolved_alerts || { critical: 0, warning: 0 };
  const color = scoreColor(data?.score ?? 0);

  return (
    <div style={{ padding: "22px 26px", overflowY: "auto", height: "100%" }}>
      <div style={{ marginBottom: 20 }}>
        <h1 style={{ fontFamily: "var(--font-display)", fontSize: 22, fontWeight: 800, marginBottom: 4 }}>Security</h1>
        <p style={{ fontSize: 13, color: "var(--text-secondary)" }}>
          Fleet-wide compliance posture — CVE exposure, unresolved alerts, scan coverage.
        </p>
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(150px, 1fr))", gap: 12, marginBottom: 22 }}>
        <KpiCard label="Compliance Score" value={data?.score ?? "—"} accent={color} />
        <KpiCard label="Critical Alerts" value={unresolved.critical} accent="var(--rose)" />
        <KpiCard label="Warnings" value={unresolved.warning} accent="var(--amber)" />
        <KpiCard label="CVE Findings" value={Object.values(cve).reduce((a, b) => a + b, 0)} accent="var(--violet)" />
      </div>

      {Object.keys(cve).length > 0 && (
        <div className="card" style={{ padding: 18, marginBottom: 18 }}>
          <h2 style={{ fontFamily: "var(--font-display)", fontSize: 15, fontWeight: 700, marginBottom: 12 }}>
            CVE Findings by Severity
          </h2>
          <div style={{ display: "flex", gap: 10, flexWrap: "wrap" }}>
            {Object.entries(cve).map(([sev, count]) => (
              <div key={sev} style={{
                padding: "8px 14px", borderRadius: "var(--radius-sm)",
                background: "var(--bg-elevated)", border: "1px solid var(--border-subtle)",
              }}>
                <div style={{ fontSize: 10, fontFamily: "var(--font-mono)", color: "var(--text-muted)" }}>{sev}</div>
                <div style={{ fontSize: 18, fontWeight: 700 }}>{count}</div>
              </div>
            ))}
          </div>
        </div>
      )}

      <div className="card" style={{ padding: 18 }}>
        <h2 style={{ fontFamily: "var(--font-display)", fontSize: 15, fontWeight: 700, marginBottom: 12 }}>
          Per-Floor Breakdown
        </h2>
        {(!data?.floors || data.floors.length === 0) ? (
          <EmptyState title="No floor data available" />
        ) : (
          <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
            {data.floors.map((f) => (
              <div key={f.floor_idx} style={{
                border: "1px solid var(--border-subtle)", borderRadius: "var(--radius-sm)", padding: 14,
                background: "var(--bg-elevated)",
              }}>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 8 }}>
                  <div style={{ fontSize: 13, fontWeight: 600 }}>{f.floor_name}</div>
                  <span style={{
                    fontSize: 11, fontFamily: "var(--font-mono)", fontWeight: 600,
                    color: f.color, background: `${f.color}22`, border: `1px solid ${f.color}55`,
                    padding: "2px 8px", borderRadius: 999,
                  }}>
                    {f.score} · {f.grade}
                  </span>
                </div>
                <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
                  {f.breakdown.map((b, i) => (
                    <div key={i} style={{ display: "flex", justifyContent: "space-between", fontSize: 12 }}>
                      <span style={{ color: "var(--text-secondary)" }}>{b.factor} — {b.detail}</span>
                      <span style={{ fontFamily: "var(--font-mono)", color: b.impact < 0 ? "var(--rose)" : "var(--emerald)" }}>
                        {b.impact > 0 ? "+" : ""}{b.impact}
                      </span>
                    </div>
                  ))}
                </div>
              </div>
            ))}
          </div>
        )}
        {data?.floor_errors && data.floor_errors.length > 0 && (
          <div style={{ marginTop: 14, paddingTop: 14, borderTop: "1px solid var(--border-subtle)" }}>
            {data.floor_errors.map((e, i) => (
              <div key={i} style={{ fontSize: 11, color: "var(--text-muted)", fontFamily: "var(--font-mono)" }}>
                {e.name}: not included ({e.error.split("\n")[0]})
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
