import { useEffect, useMemo, useState, useCallback } from "react";
import KpiCard from "../components/KpiCard";
import FilterBar from "../components/FilterBar";
import MonitoringTable from "../components/MonitoringTable";
import DetailPanel from "../components/DetailPanel";
import { LoadingState, ErrorState } from "../components/States";
import { useToast } from "../components/Toast";
import { getFleetOverview, getAllAlerts } from "../api";

// Maps the real Alert API response into the shape the UI components expect.
// Only real fields — no fabricated metric/trend/description.
function mapAlertToSignal(a) {
  return {
    id: a.id,
    machine_id: a.machine_id,
    floor_idx: a.floor_idx,
    floor_name: a.floor_name,
    severity: a.level === "critical" ? "CRITICAL" : "WARNING",
    title: a.message,
    type: a.type,
    hostname: a.hostname,
    timestamp: new Date(a.timestamp).getTime(),
    updated_at: a.updated_at ? new Date(a.updated_at).getTime() : null,
    status: a.status || "open",
    is_read: a.is_read,
    assigned_to: a.assigned_to,
  };
}

const STATUS_DISPLAY = {
  open: "Open", investigating: "Investigating", acknowledged: "Acknowledged",
  resolved: "Resolved", snoozed: "Snoozed",
};

export default function Dashboard() {
  const [overview, setOverview] = useState(null);
  const [signals, setSignals] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [search, setSearch] = useState("");
  const [severity, setSeverity] = useState("ALL");
  const [status, setStatus] = useState("ALL");
  const [selected, setSelected] = useState(null);
  const [live, setLive] = useState(true);
  const showToast = useToast();

  const load = useCallback(async () => {
    try {
      const [overviewRes, alertsRes] = await Promise.all([getFleetOverview(), getAllAlerts()]);
      setOverview(overviewRes.data);
      setSignals(alertsRes.data.map(mapAlertToSignal));
      setError(null);
    } catch (e) {
      setError(e.response?.data?.detail || "Failed to load fleet data");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
    if (!live) return;
    const iv = setInterval(load, 15000);
    return () => clearInterval(iv);
  }, [load, live]);

  const filtered = useMemo(() => {
    return signals
      .filter((s) => severity === "ALL" || s.severity === severity)
      .filter((s) => status === "ALL" || s.status === status)
      .filter((s) => {
        if (!search.trim()) return true;
        const q = search.toLowerCase();
        return s.title.toLowerCase().includes(q) || s.hostname.toLowerCase().includes(q) || s.type.toLowerCase().includes(q);
      })
      .sort((a, b) => b.timestamp - a.timestamp);
  }, [signals, search, severity, status]);

  const criticalCount = signals.filter((s) => s.severity === "CRITICAL").length;
  const openCount = signals.filter((s) => s.status === "open").length;

  // Signal display status needs friendly capitalization; StatusBadge expects
  // e.g. "Investigating" not "investigating" — small adapter here.
  const displaySignals = filtered.map((s) => ({ ...s, status: STATUS_DISPLAY[s.status] || s.status }));

  const handleStatusChange = (id, newStatus) => {
    setSignals((prev) => prev.map((s) => (s.id === id ? { ...s, status: newStatus } : s)));
    setSelected((prev) => (prev && prev.id === id ? { ...prev, status: newStatus } : prev));
  };
  const handleAssigned = (id, userId) => {
    setSignals((prev) => prev.map((s) => (s.id === id ? { ...s, assigned_to: "You" } : s)));
    setSelected((prev) => (prev && prev.id === id ? { ...prev, assigned_to: "You" } : prev));
  };

  const handleRefresh = () => { load(); showToast("Signals refreshed", "info"); };

  if (loading) {
    return <div style={{ padding: "22px 26px" }}><LoadingState rows={6} /></div>;
  }
  if (error) {
    return <div style={{ padding: "22px 26px" }}><ErrorState message={error} /></div>;
  }

  return (
    <div style={{ display: "flex", height: "100%" }}>
      <div style={{ flex: 1, minWidth: 0, padding: "22px 26px", overflowY: "auto" }}>
        <div style={{ marginBottom: 20 }}>
          <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 4 }}>
            <h1 style={{ fontFamily: "var(--font-display)", fontSize: 22, fontWeight: 800 }}>
              Operations Overview
            </h1>
            <span style={{
              display: "inline-flex", alignItems: "center", gap: 5,
              fontSize: 11, fontFamily: "var(--font-mono)", color: "var(--emerald)",
              background: "var(--emerald-dim)", border: "1px solid var(--emerald)44",
              padding: "2px 8px", borderRadius: 999,
            }}>
              <span style={{ width: 5, height: 5, borderRadius: "50%", background: "var(--emerald)" }} />
              Operational
            </span>
          </div>
          <p style={{ fontSize: 13, color: "var(--text-secondary)" }}>
            Real-time signals across {overview?.total ?? 0} machines — {criticalCount} critical, {openCount} open.
          </p>
        </div>

        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(150px, 1fr))", gap: 12, marginBottom: 22 }}>
          <KpiCard label="Active Signals" value={signals.filter(s => s.status !== "resolved").length} accent="var(--cyan)" />
          <KpiCard label="Critical" value={criticalCount} accent="var(--rose)" />
          <KpiCard label="Machines Monitored" value={overview?.total ?? "—"} trendLabel={`${overview?.online ?? 0} online`} trendDirection="flat" accent="var(--violet)" />
          <KpiCard label="Automated Fixes" value={overview?.commands_24h ?? "—"} trendLabel="last 24h" trendDirection="flat" accent="var(--emerald)" />
          <KpiCard label="Fleet CPU" value={overview?.avg_cpu != null ? `${overview.avg_cpu.toFixed(1)}%` : "—"} accent="var(--amber)" />
          <KpiCard label="Fleet Disk" value={overview?.avg_disk != null ? `${overview.avg_disk.toFixed(1)}%` : "—"} accent="var(--emerald)" />
        </div>

        <div className="card" style={{ padding: 18 }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 4 }}>
            <h2 style={{ fontFamily: "var(--font-display)", fontSize: 15, fontWeight: 700 }}>Signals</h2>
            <span style={{ fontSize: 11, color: "var(--text-muted)", fontFamily: "var(--font-mono)" }}>
              {filtered.length} of {signals.length}
            </span>
          </div>
          <FilterBar
            search={search} onSearch={setSearch}
            severity={severity} onSeverity={setSeverity}
            status={status} onStatus={setStatus}
            onRefresh={handleRefresh}
            liveMode={live} onToggleLive={() => setLive((v) => !v)}
          />
          <MonitoringTable signals={displaySignals} selectedId={selected?.id} onSelect={setSelected} />
        </div>
      </div>

      {selected && (
        <DetailPanel
          signal={selected}
          onClose={() => setSelected(null)}
          onStatusChange={handleStatusChange}
          onAssigned={handleAssigned}
        />
      )}
    </div>
  );
}
