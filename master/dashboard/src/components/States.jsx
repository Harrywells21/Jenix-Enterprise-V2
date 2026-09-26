export function EmptyState({ icon = "✓", title = "All clear", subtitle = "" }) {
  return (
    <div style={{ textAlign: "center", padding: "56px 20px", color: "var(--text-muted)" }}>
      <div style={{ fontSize: 26, marginBottom: 10, color: "var(--text-secondary)" }}>{icon}</div>
      <div style={{ fontSize: 14, fontWeight: 600, color: "var(--text-secondary)", marginBottom: 4 }}>{title}</div>
      {subtitle && <div style={{ fontSize: 12, fontFamily: "var(--font-mono)" }}>{subtitle}</div>}
    </div>
  );
}

export function LoadingState({ rows = 5 }) {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 8, padding: "4px 0" }}>
      {Array.from({ length: rows }).map((_, i) => (
        <div key={i} style={{
          height: 44, borderRadius: "var(--radius-sm)",
          background: "linear-gradient(90deg, var(--bg-elevated) 25%, var(--bg-card-hover) 50%, var(--bg-elevated) 75%)",
          backgroundSize: "200% 100%",
          animation: "shimmer 1.4s ease-in-out infinite",
        }} />
      ))}
    </div>
  );
}

export function ErrorState({ message = "Something went wrong." }) {
  return (
    <div style={{ textAlign: "center", padding: "56px 20px", color: "var(--rose)" }}>
      <div style={{ fontSize: 22, marginBottom: 8 }}>⚠</div>
      <div style={{ fontSize: 13, fontFamily: "var(--font-mono)" }}>{message}</div>
    </div>
  );
}
