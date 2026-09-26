// Only 2 real severity levels exist in the actual Alert model (level:
// "critical" | "warning"). No HIGH/MEDIUM/LOW/INFO tiers are fabricated —
// this reflects exactly what the backend reports, nothing more.
const SEVERITY_MAP = {
  CRITICAL: { color: "var(--sev-critical)", dim: "var(--sev-critical-dim)", label: "Critical" },
  WARNING:  { color: "var(--sev-medium)",   dim: "var(--sev-medium-dim)",   label: "Warning" },
};

export function SeverityBadge({ severity, compact = false }) {
  const s = SEVERITY_MAP[severity] || SEVERITY_MAP.WARNING;
  return (
    <span style={{
      display: "inline-flex", alignItems: "center", gap: 6,
      padding: compact ? "2px 8px" : "3px 10px",
      borderRadius: 999,
      background: s.dim,
      border: `1px solid ${s.color}33`,
      color: s.color,
      fontFamily: "var(--font-mono)",
      fontSize: compact ? 10 : 11,
      fontWeight: 600,
      letterSpacing: "0.06em",
      textTransform: "uppercase",
      whiteSpace: "nowrap",
    }}>
      <span style={{
        width: 5, height: 5, borderRadius: "50%", background: s.color,
        boxShadow: severity === "CRITICAL" ? `0 0 6px ${s.color}` : "none",
      }} />
      {s.label}
    </span>
  );
}

const STATUS_MAP = {
  Open:          { color: "var(--rose)" },
  Investigating: { color: "var(--amber)" },
  Acknowledged:  { color: "var(--cyan)" },
  Resolved:      { color: "var(--emerald)" },
  Snoozed:       { color: "var(--slate)" },
};

export function StatusBadge({ status }) {
  const s = STATUS_MAP[status] || STATUS_MAP.Open;
  return (
    <span style={{
      display: "inline-flex", alignItems: "center", gap: 6,
      fontSize: 12, color: "var(--text-secondary)", fontWeight: 500,
    }}>
      <span style={{ width: 6, height: 6, borderRadius: "50%", background: s.color }} />
      {status}
    </span>
  );
}
