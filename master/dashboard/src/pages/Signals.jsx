import { useEffect, useState, useCallback } from "react";
import { LoadingState, ErrorState, EmptyState } from "../components/States";
import { getFleetOverview } from "../api";

const ACTION_COLOR = {
  node_approved: "var(--emerald)",
  registered: "var(--amber)",
  node_redirect_pending: "var(--cyan)",
  cve_scan: "var(--violet)",
};

function actionColor(action) {
  return ACTION_COLOR[action] || "var(--text-secondary)";
}

function timeAgo(iso) {
  const diffMs = Date.now() - new Date(iso).getTime();
  const mins = Math.floor(diffMs / 60000);
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `${hrs}h ago`;
  return `${Math.floor(hrs / 24)}d ago`;
}

export default function Signals() {
  const [activity, setActivity] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  const load = useCallback(async () => {
    try {
      const res = await getFleetOverview();
      setActivity(res.data.activity || []);
      setError(null);
    } catch (e) {
      setError(e.response?.data?.detail || "Failed to load signal activity");
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

  return (
    <div style={{ padding: "22px 26px", overflowY: "auto", height: "100%" }}>
      <div style={{ marginBottom: 20 }}>
        <h1 style={{ fontFamily: "var(--font-display)", fontSize: 22, fontWeight: 800, marginBottom: 4 }}>Signals</h1>
        <p style={{ fontSize: 13, color: "var(--text-secondary)" }}>
          Live event stream across the fleet — enrollments, redirects, scans, and fleet commands.
        </p>
      </div>

      <div className="card" style={{ padding: 18 }}>
        {activity.length === 0 ? (
          <EmptyState title="No recent activity" />
        ) : (
          <div style={{ display: "flex", flexDirection: "column" }}>
            {activity.map((a, i) => (
              <div key={i} style={{
                display: "flex", alignItems: "flex-start", gap: 12,
                padding: "10px 4px", borderTop: i > 0 ? "1px solid var(--border-subtle)" : "none",
              }}>
                <span style={{
                  width: 7, height: 7, borderRadius: "50%", marginTop: 5,
                  background: actionColor(a.action), flexShrink: 0,
                }} />
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ fontSize: 13 }}>{a.detail}</div>
                  <div style={{ fontSize: 11, color: "var(--text-muted)", fontFamily: "var(--font-mono)", marginTop: 2 }}>
                    {a.action} · {a.floor_name} · {timeAgo(a.timestamp)}
                  </div>
                </div>
                <span style={{
                  fontSize: 10, fontFamily: "var(--font-mono)", color: "var(--text-muted)",
                  whiteSpace: "nowrap",
                }}>
                  {a.status}
                </span>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
