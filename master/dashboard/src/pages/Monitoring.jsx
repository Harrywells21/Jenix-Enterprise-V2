import { useEffect, useState, useCallback, useMemo } from "react";
import KpiCard from "../components/KpiCard";
import { LoadingState, ErrorState, EmptyState } from "../components/States";
import { getFleetOverview, getAggregate } from "../api";

function timeAgo(iso) {
  if (!iso) return "never";
  const diffMs = Date.now() - new Date(iso).getTime();
  const mins = Math.floor(diffMs / 60000);
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `${hrs}h ago`;
  return `${Math.floor(hrs / 24)}d ago`;
}

export default function Monitoring() {
  const [overview, setOverview] = useState(null);
  const [aggregate, setAggregate] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [search, setSearch] = useState("");

  const load = useCallback(async () => {
    try {
      const [overviewRes, aggRes] = await Promise.all([getFleetOverview(), getAggregate()]);
      setOverview(overviewRes.data);
      setAggregate(aggRes.data);
      setError(null);
    } catch (e) {
      setError(e.response?.data?.detail || "Failed to load monitoring data");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
    const iv = setInterval(load, 15000);
    return () => clearInterval(iv);
  }, [load]);

  const machines = useMemo(() => {
    if (!overview || !aggregate) return [];
    const detailsByKey = {};
    for (const floor of aggregate.floors) {
      for (const m of floor.machines) {
        detailsByKey[`${floor.idx}-${m.id}`] = m;
      }
    }
    return overview.machine_scores
      .map((s) => ({ ...s, ...(detailsByKey[`${s.floor_idx}-${s.id}`] || {}) }))
      .filter((m) => {
        if (!search.trim()) return true;
        const q = search.toLowerCase();
        return m.hostname.toLowerCase().includes(q) || (m.ip || "").toLowerCase().includes(q) || (m.os_name || "").toLowerCase().includes(q);
      });
  }, [overview, aggregate, search]);

  if (loading) return <div style={{ padding: "22px 26px" }}><LoadingState rows={6} /></div>;
  if (error) return <div style={{ padding: "22px 26px" }}><ErrorState message={error} /></div>;

  const online = machines.filter((m) => m.status === "online").length;

  return (
    <div style={{ padding: "22px 26px", overflowY: "auto", height: "100%" }}>
      <div style={{ marginBottom: 20 }}>
        <h1 style={{ fontFamily: "var(--font-display)", fontSize: 22, fontWeight: 800, marginBottom: 4 }}>Monitoring</h1>
        <p style={{ fontSize: 13, color: "var(--text-secondary)" }}>
          Live per-machine resource usage and connectivity across all floors.
        </p>
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(150px, 1fr))", gap: 12, marginBottom: 22 }}>
        <KpiCard label="Machines" value={machines.length} accent="var(--cyan)" />
        <KpiCard label="Online" value={online} accent="var(--emerald)" />
        <KpiCard label="Offline" value={machines.length - online} accent="var(--rose)" />
        <KpiCard label="Avg CPU" value={overview?.avg_cpu != null ? `${overview.avg_cpu.toFixed(1)}%` : "—"} accent="var(--amber)" />
      </div>

      <div className="card" style={{ padding: 18 }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 12 }}>
          <h2 style={{ fontFamily: "var(--font-display)", fontSize: 15, fontWeight: 700 }}>Machines</h2>
          <input
            value={search} onChange={(e) => setSearch(e.target.value)}
            placeholder="Search hostname, IP, OS..."
            style={{
              background: "var(--bg-elevated)", border: "1px solid var(--border-default)",
              borderRadius: "var(--radius-sm)", padding: "6px 10px", fontSize: 12,
              color: "var(--text-primary)", width: 220,
            }}
          />
        </div>
        {machines.length === 0 ? (
          <EmptyState title="No machines found" />
        ) : (
          <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 12 }}>
            <thead>
              <tr style={{ textAlign: "left", color: "var(--text-muted)", fontFamily: "var(--font-mono)", fontSize: 10 }}>
                <th style={{ padding: "6px 8px" }}>HOST</th>
                <th style={{ padding: "6px 8px" }}>IP</th>
                <th style={{ padding: "6px 8px" }}>OS</th>
                <th style={{ padding: "6px 8px" }}>STATUS</th>
                <th style={{ padding: "6px 8px" }}>CPU</th>
                <th style={{ padding: "6px 8px" }}>RAM</th>
                <th style={{ padding: "6px 8px" }}>DISK</th>
                <th style={{ padding: "6px 8px" }}>LAST SEEN</th>
                <th style={{ padding: "6px 8px" }}>FLOOR</th>
              </tr>
            </thead>
            <tbody>
              {machines.map((m) => (
                <tr key={`${m.floor_idx}-${m.id}`} style={{ borderTop: "1px solid var(--border-subtle)" }}>
                  <td style={{ padding: "8px" }}>{m.hostname}</td>
                  <td style={{ padding: "8px", fontFamily: "var(--font-mono)", color: "var(--text-secondary)" }}>{m.ip}</td>
                  <td style={{ padding: "8px", color: "var(--text-secondary)" }}>{m.os_name}</td>
                  <td style={{ padding: "8px" }}>
                    <span style={{
                      color: m.status === "online" ? "var(--emerald)" : "var(--text-muted)",
                      fontFamily: "var(--font-mono)", fontSize: 11,
                    }}>{m.status}</span>
                  </td>
                  <td style={{ padding: "8px", fontFamily: "var(--font-mono)" }}>{m.cpu?.toFixed(0)}%</td>
                  <td style={{ padding: "8px", fontFamily: "var(--font-mono)" }}>{m.ram?.toFixed(0)}%</td>
                  <td style={{ padding: "8px", fontFamily: "var(--font-mono)" }}>{m.disk?.toFixed(0)}%</td>
                  <td style={{ padding: "8px", color: "var(--text-muted)" }}>{timeAgo(m.last_seen)}</td>
                  <td style={{ padding: "8px", color: "var(--text-muted)" }}>{m.floor_name}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
