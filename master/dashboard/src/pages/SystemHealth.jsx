import { useEffect, useState, useCallback } from "react";
import KpiCard from "../components/KpiCard";
import { LoadingState, ErrorState, EmptyState } from "../components/States";
import { getFleetOverview } from "../api";

function ScoreBadge({ grade, color }) {
  return (
    <span style={{
      display: "inline-flex", alignItems: "center", gap: 5,
      fontSize: 11, fontFamily: "var(--font-mono)", fontWeight: 600,
      color, background: `${color}22`, border: `1px solid ${color}55`,
      padding: "2px 8px", borderRadius: 999,
    }}>
      {grade}
    </span>
  );
}

function MetricBar({ label, value }) {
  const v = value ?? 0;
  const color = v >= 90 ? "var(--rose)" : v >= 75 ? "var(--amber)" : "var(--emerald)";
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 8, minWidth: 110 }}>
      <span style={{ fontSize: 10, fontFamily: "var(--font-mono)", color: "var(--text-muted)", width: 28 }}>{label}</span>
      <div style={{ flex: 1, height: 5, borderRadius: 3, background: "var(--bg-elevated)", overflow: "hidden" }}>
        <div style={{ width: `${Math.min(v, 100)}%`, height: "100%", background: color }} />
      </div>
      <span style={{ fontSize: 10, fontFamily: "var(--font-mono)", color: "var(--text-secondary)", width: 34, textAlign: "right" }}>
        {v.toFixed(0)}%
      </span>
    </div>
  );
}

export default function SystemHealth() {
  const [overview, setOverview] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [expanded, setExpanded] = useState(null);

  const load = useCallback(async () => {
    try {
      const res = await getFleetOverview();
      setOverview(res.data);
      setError(null);
    } catch (e) {
      setError(e.response?.data?.detail || "Failed to load fleet health data");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
    const iv = setInterval(load, 15000);
    return () => clearInterval(iv);
  }, [load]);

  if (loading) return <div style={{ padding: "22px 26px" }}><LoadingState rows={6} /></div>;
  if (error) return <div style={{ padding: "22px 26px" }}><ErrorState message={error} /></div>;

  const scores = overview?.machine_scores || [];
  const critical = scores.filter((m) => m.grade === "Critical").length;
  const needsAttention = scores.filter((m) => m.grade === "Needs Attention").length;
  const avgScore = scores.length ? Math.round(scores.reduce((a, m) => a + m.score, 0) / scores.length) : 0;

  return (
    <div style={{ padding: "22px 26px", overflowY: "auto", height: "100%" }}>
      <div style={{ marginBottom: 20 }}>
        <h1 style={{ fontFamily: "var(--font-display)", fontSize: 22, fontWeight: 800, marginBottom: 4 }}>System Health</h1>
        <p style={{ fontSize: 13, color: "var(--text-secondary)" }}>
          Per-machine health scores across {scores.length} machines, worst-first.
        </p>
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(150px, 1fr))", gap: 12, marginBottom: 22 }}>
        <KpiCard label="Avg Health Score" value={avgScore} accent="var(--cyan)" />
        <KpiCard label="Critical" value={critical} accent="var(--rose)" />
        <KpiCard label="Needs Attention" value={needsAttention} accent="var(--amber)" />
        <KpiCard label="Healthy" value={scores.length - critical - needsAttention} accent="var(--emerald)" />
      </div>

      <div className="card" style={{ padding: 18 }}>
        <h2 style={{ fontFamily: "var(--font-display)", fontSize: 15, fontWeight: 700, marginBottom: 12 }}>
          Machine Scores
        </h2>
        {scores.length === 0 ? (
          <EmptyState title="No machines reporting" />
        ) : (
          <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
            {scores.map((m) => {
              const key = `${m.floor_idx}-${m.id}`;
              const isOpen = expanded === key;
              return (
                <div key={key} style={{
                  border: "1px solid var(--border-subtle)", borderRadius: "var(--radius-sm)",
                  padding: "10px 14px", background: "var(--bg-elevated)",
                }}>
                  <div
                    onClick={() => setExpanded(isOpen ? null : key)}
                    style={{ display: "flex", alignItems: "center", gap: 16, cursor: "pointer" }}
                  >
                    <div style={{ width: 34, textAlign: "center", fontFamily: "var(--font-mono)", fontSize: 15, fontWeight: 700, color: m.color }}>
                      {m.score}
                    </div>
                    <div style={{ flex: 1, minWidth: 0 }}>
                      <div style={{ fontSize: 13, fontWeight: 600 }}>{m.hostname}</div>
                      <div style={{ fontSize: 11, color: "var(--text-muted)", fontFamily: "var(--font-mono)" }}>
                        {m.ip} · {m.floor_name} · {m.status}
                      </div>
                    </div>
                    <MetricBar label="CPU" value={m.cpu} />
                    <MetricBar label="RAM" value={m.ram} />
                    <MetricBar label="DISK" value={m.disk} />
                    <ScoreBadge grade={m.grade} color={m.color} />
                  </div>
                  {isOpen && (
                    <div style={{ marginTop: 10, paddingTop: 10, borderTop: "1px solid var(--border-subtle)", display: "flex", flexDirection: "column", gap: 4 }}>
                      {m.breakdown.map((b, i) => (
                        <div key={i} style={{ display: "flex", justifyContent: "space-between", fontSize: 12 }}>
                          <span style={{ color: "var(--text-secondary)" }}>{b.factor} — {b.detail}</span>
                          <span style={{ fontFamily: "var(--font-mono)", color: b.impact < 0 ? "var(--rose)" : "var(--emerald)" }}>
                            {b.impact > 0 ? "+" : ""}{b.impact}
                          </span>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}
