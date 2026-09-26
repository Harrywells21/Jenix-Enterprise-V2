import { LineChart, Line, ResponsiveContainer } from "recharts";

export default function Sparkline({ data, color = "var(--cyan)", width = 72, height = 24 }) {
  if (!data || data.length === 0) return null;
  // Resolve CSS var to a real color string for recharts (SVG stroke doesn't
  // reliably accept var() in some browsers' inline-SVG contexts)
  const resolved = color.startsWith("var(")
    ? getComputedStyle(document.documentElement).getPropertyValue(color.slice(4, -1)).trim() || "#38bdf8"
    : color;
  return (
    <div style={{ width, height }}>
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={data}>
          <Line type="monotone" dataKey="v" stroke={resolved} strokeWidth={1.5} dot={false} isAnimationActive={false} />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
