import { SeverityBadge, StatusBadge } from "./Badges";
import { EmptyState } from "./States";

function timeAgo(ts) {
  const mins = Math.round((Date.now() - ts) / 60000);
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.round(mins / 60);
  if (hrs < 24) return `${hrs}h ago`;
  return `${Math.round(hrs / 24)}d ago`;
}

// No Trend column here — the real Alert model has no historical time-series
// data, so a sparkline would have to be fabricated. Removed rather than faked.
export default function MonitoringTable({ signals, selectedId, onSelect }) {
  if (signals.length === 0) {
    return <EmptyState icon="✓" title="No signals match your filters" subtitle="Try widening the search or clearing filters" />;
  }

  return (
    <div style={{ overflowX: "auto" }}>
      <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13 }}>
        <thead>
          <tr style={{ borderBottom: "1px solid var(--border-default)" }}>
            {["Severity", "Signal", "Type", "Host", "Floor", "Status", "Age"].map((h) => (
              <th key={h} style={{
                textAlign: "left", padding: "8px 12px",
                fontFamily: "var(--font-mono)", fontSize: 10, fontWeight: 500,
                color: "var(--text-muted)", letterSpacing: "0.08em", textTransform: "uppercase",
                whiteSpace: "nowrap",
              }}>{h}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {signals.map((s) => {
            const active = s.id === selectedId;
            return (
              <tr
                key={s.id}
                onClick={() => onSelect(s)}
                tabIndex={0}
                onKeyDown={(e) => { if (e.key === "Enter") onSelect(s); }}
                style={{
                  borderBottom: "1px solid var(--border-subtle)",
                  cursor: "pointer",
                  background: active ? "var(--bg-card-hover)" : "transparent",
                  transition: "background 0.12s",
                }}
                onMouseEnter={(e) => { if (!active) e.currentTarget.style.background = "var(--bg-elevated)"; }}
                onMouseLeave={(e) => { if (!active) e.currentTarget.style.background = "transparent"; }}
              >
                <td style={{ padding: "10px 12px" }}><SeverityBadge severity={s.severity} compact /></td>
                <td style={{ padding: "10px 12px", maxWidth: 320 }}>
                  <div style={{ color: "var(--text-primary)", fontWeight: 500, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                    {s.title}
                  </div>
                </td>
                <td style={{ padding: "10px 12px", color: "var(--text-secondary)", fontFamily: "var(--font-mono)", fontSize: 12, whiteSpace: "nowrap" }}>
                  {s.type}
                </td>
                <td style={{ padding: "10px 12px", fontFamily: "var(--font-mono)", fontSize: 12, color: "var(--text-secondary)", whiteSpace: "nowrap" }}>
                  {s.hostname}
                </td>
                <td style={{ padding: "10px 12px", color: "var(--text-muted)", fontSize: 12, whiteSpace: "nowrap" }}>
                  {s.floor_name}
                </td>
                <td style={{ padding: "10px 12px", whiteSpace: "nowrap" }}><StatusBadge status={s.status} /></td>
                <td style={{ padding: "10px 12px", fontFamily: "var(--font-mono)", fontSize: 11, color: "var(--text-muted)", whiteSpace: "nowrap" }}>
                  {timeAgo(s.timestamp)}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
