import Sparkline from "./Sparkline";

export default function KpiCard({ label, value, trendLabel, trendDirection, accent = "var(--cyan)", sparklineData }) {
  const dirColor = trendDirection === "up" ? "var(--rose)" : trendDirection === "down" ? "var(--emerald)" : "var(--text-muted)";
  const dirSymbol = trendDirection === "up" ? "▲" : trendDirection === "down" ? "▼" : "–";
  return (
    <div className="card" style={{ padding: "16px 18px" }}>
      <div style={{
        fontFamily: "var(--font-mono)", fontSize: 10, color: "var(--text-muted)",
        letterSpacing: "0.12em", textTransform: "uppercase", marginBottom: 10,
      }}>{label}</div>
      <div style={{ display: "flex", alignItems: "flex-end", justifyContent: "space-between", gap: 8 }}>
        <div style={{ fontFamily: "var(--font-display)", fontSize: 28, fontWeight: 800, color: accent, lineHeight: 1 }}>
          {value}
        </div>
        {sparklineData && <Sparkline data={sparklineData} color={accent} width={56} height={22} />}
      </div>
      {trendLabel && (
        <div style={{
          marginTop: 8, fontSize: 11, color: dirColor,
          fontFamily: "var(--font-mono)", display: "flex", alignItems: "center", gap: 4,
        }}>
          <span>{dirSymbol}</span> {trendLabel}
        </div>
      )}
    </div>
  );
}
