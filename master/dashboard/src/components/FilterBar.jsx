import { Search, RefreshCw } from "lucide-react";

// Matches the real 2-tier severity (Alert.level) and the real status
// workflow values (Alert.status) exactly — no fabricated options.
const SEVERITIES = ["ALL", "CRITICAL", "WARNING"];
const STATUSES = ["ALL", "open", "investigating", "acknowledged", "resolved", "snoozed"];
const STATUS_LABELS = { open: "Open", investigating: "Investigating", acknowledged: "Acknowledged", resolved: "Resolved", snoozed: "Snoozed" };

export default function FilterBar({
  search, onSearch, severity, onSeverity, status, onStatus,
  onRefresh, liveMode, onToggleLive,
}) {
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap", marginBottom: 14 }}>
      <div style={{
        display: "flex", alignItems: "center", gap: 8,
        background: "var(--bg-input)", border: "1px solid var(--border-default)",
        borderRadius: "var(--radius-sm)", padding: "7px 10px", flex: "1 1 220px", minWidth: 180,
      }}>
        <Search size={14} color="var(--text-muted)" />
        <input
          value={search}
          onChange={(e) => onSearch(e.target.value)}
          placeholder="Search signals, hosts, sources…"
          style={{ background: "none", border: "none", color: "var(--text-primary)", fontSize: 12.5, width: "100%", outline: "none" }}
        />
      </div>

      <select value={severity} onChange={(e) => onSeverity(e.target.value)} style={selectStyle}>
        {SEVERITIES.map((s) => <option key={s} value={s}>{s === "ALL" ? "All severities" : s}</option>)}
      </select>

      <select value={status} onChange={(e) => onStatus(e.target.value)} style={selectStyle}>
        {STATUSES.map((s) => <option key={s} value={s}>{s === "ALL" ? "All statuses" : STATUS_LABELS[s]}</option>)}
      </select>

      <button onClick={onRefresh} style={{ ...iconBtnStyle }}>
        <RefreshCw size={13} /> Refresh
      </button>

      <button onClick={onToggleLive} style={{
        ...iconBtnStyle,
        borderColor: liveMode ? "var(--emerald)" : "var(--border-default)",
        color: liveMode ? "var(--emerald)" : "var(--text-secondary)",
      }}>
        <span style={{
          width: 6, height: 6, borderRadius: "50%",
          background: liveMode ? "var(--emerald)" : "var(--text-muted)",
          boxShadow: liveMode ? "0 0 6px var(--emerald)" : "none",
          animation: liveMode ? "pulseDot 1.6s infinite" : "none",
        }} />
        {liveMode ? "Live" : "Paused"}
      </button>
    </div>
  );
}

const selectStyle = {
  background: "var(--bg-input)", border: "1px solid var(--border-default)",
  borderRadius: "var(--radius-sm)", color: "var(--text-secondary)",
  fontSize: 12.5, padding: "7px 10px",
};

const iconBtnStyle = {
  display: "flex", alignItems: "center", gap: 6,
  background: "var(--bg-input)", border: "1px solid var(--border-default)",
  borderRadius: "var(--radius-sm)", color: "var(--text-secondary)",
  fontSize: 12.5, padding: "7px 12px",
};
