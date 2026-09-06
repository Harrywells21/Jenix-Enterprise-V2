#!/bin/bash
set -e
TS=$(date +%Y%m%d_%H%M%S)
DASH=~/Desktop/jenix/dashboard
SRC="$DASH/src"
SERVER_DIR=~/Desktop/jenix/server

echo "=================================================================="
echo "PART A — BACKUPS"
echo "=================================================================="
cp "$SRC/api/index.js"            "$SRC/api/index.js.bak_sites_${TS}"
cp "$SRC/pages/Fleet.jsx"         "$SRC/pages/Fleet.jsx.bak_sites_${TS}"
cp "$SRC/components/Sidebar.jsx"  "$SRC/components/Sidebar.jsx.bak_sites_${TS}"
cp "$SRC/App.jsx"                 "$SRC/App.jsx.bak_sites_${TS}"
echo "Backed up 4 files with suffix _sites_${TS}"

echo ""
echo "=================================================================="
echo "PART B — PATCH api/index.js (getInstallCommand/approveMachine gain site_id, new Sites exports)"
echo "=================================================================="
python3 - << 'PYEOF'
path = "/home/aadi/Desktop/jenix/dashboard/src/api/index.js"
src = open(path).read()

anchor1 = '''// Pending enrollment
export const getPendingMachines = ()   => api.get("/api/machines/pending");
export const getInstallCommand  = ()   => api.get("/api/machines/install-command");
export const approveMachine     = (id) => api.post(`/api/machines/${id}/approve`);
export const rejectMachine      = (id) => api.post(`/api/machines/${id}/reject`);'''
assert src.count(anchor1) == 1, f"anchor1 matched {src.count(anchor1)} times"
new1 = '''// Pending enrollment
export const getPendingMachines = ()   => api.get("/api/machines/pending");
export const getInstallCommand  = (site_id) => api.get("/api/machines/install-command", site_id ? { params: { site_id } } : undefined);
export const approveMachine     = (id, site_id) => api.post(`/api/machines/${id}/approve`, site_id ? { site_id } : {});
export const rejectMachine      = (id) => api.post(`/api/machines/${id}/reject`);

// Sites
export const getSites   = ()     => api.get("/api/sites");
export const createSite = (name) => api.post("/api/sites", { name });
export const deleteSite = (id)   => api.delete(`/api/sites/${id}`);'''
src = src.replace(anchor1, new1, 1)

open(path, "w").write(src)
print("api/index.js patched: 1/1 anchor matched exactly once")
PYEOF

echo "--- re-verify ---"
grep -c "export const getSites" "$SRC/api/index.js"
grep -c "getInstallCommand  = (site_id)" "$SRC/api/index.js"
grep -c "approveMachine     = (id, site_id)" "$SRC/api/index.js"

echo ""
echo "=================================================================="
echo "PART C — CREATE pages/Sites.jsx (new file)"
echo "=================================================================="
cat > "$SRC/pages/Sites.jsx" << 'SITESJSXEOF'
import { useState, useEffect } from "react";
import { getSites, createSite, deleteSite } from "../api";

export default function Sites() {
  const [sites, setSites]   = useState([]);
  const [name, setName]     = useState("");
  const [toast, setToast]   = useState(null);

  const load = () => getSites().then(r => setSites(r.data || [])).catch(() => {});
  useEffect(() => { load(); }, []);

  const showToast = (msg, type) => {
    setToast({ msg, type });
    setTimeout(() => setToast(null), 3000);
  };

  const handleCreate = async (e) => {
    e.preventDefault();
    if (!name.trim()) return;
    try {
      await createSite(name.trim());
      setName("");
      showToast("Site created", "success");
      load();
    } catch (err) {
      showToast(err.response?.data?.detail || err.message, "error");
    }
  };

  const handleDelete = async (id, siteName) => {
    try {
      await deleteSite(id);
      showToast(`${siteName} deleted`, "success");
      load();
    } catch (err) {
      showToast(err.response?.data?.detail || err.message, "error");
    }
  };

  return (
    <div style={{ fontFamily: "'Cabinet Grotesk', sans-serif", color: "#e8f0fe" }}>
      <div style={{
        fontSize: "22px", fontWeight: 800, fontFamily: "'Syne', sans-serif",
        marginBottom: "6px",
      }}>Sites</div>
      <div style={{
        fontSize: "13px", color: "rgba(122,143,166,0.7)", marginBottom: "24px",
      }}>Group machines by client site or physical location.</div>

      <form onSubmit={handleCreate} style={{ display: "flex", gap: "10px", marginBottom: "24px" }}>
        <input
          value={name}
          onChange={e => setName(e.target.value)}
          placeholder="New site name"
          style={{
            flex: 1, maxWidth: "320px", padding: "10px 14px",
            background: "#0c1220", border: "1px solid rgba(255,255,255,0.08)",
            borderRadius: "8px", color: "#e8f0fe", fontSize: "13px",
            fontFamily: "'Cabinet Grotesk', sans-serif",
          }}
        />
        <button
          type="submit"
          style={{
            padding: "10px 18px", background: "rgba(56,189,248,0.12)",
            border: "1px solid rgba(56,189,248,0.3)", borderRadius: "8px",
            color: "#38bdf8", fontSize: "13px", fontWeight: 600, cursor: "pointer",
            fontFamily: "'Cabinet Grotesk', sans-serif",
          }}
        >+ Create Site</button>
      </form>

      {toast && (
        <div style={{
          padding: "10px 14px", marginBottom: "18px", borderRadius: "8px",
          background: toast.type === "error" ? "rgba(244,63,94,0.1)" : "rgba(16,185,129,0.1)",
          border: `1px solid ${toast.type === "error" ? "rgba(244,63,94,0.3)" : "rgba(16,185,129,0.3)"}`,
          color: toast.type === "error" ? "#f43f5e" : "#10b981",
          fontSize: "12px",
        }}>{toast.msg}</div>
      )}

      <div style={{ display: "flex", flexDirection: "column", gap: "8px" }}>
        {sites.length === 0 && (
          <div style={{ fontSize: "13px", color: "rgba(122,143,166,0.5)" }}>No sites yet.</div>
        )}
        {sites.map(s => (
          <div key={s.id} style={{
            display: "flex", alignItems: "center", justifyContent: "space-between",
            padding: "12px 16px", background: "#0c1220",
            border: "1px solid rgba(255,255,255,0.06)", borderRadius: "10px",
          }}>
            <div>
              <span style={{ fontWeight: 600, fontSize: "14px" }}>{s.name}</span>
              <span style={{
                marginLeft: "12px", fontSize: "11px", color: "rgba(122,143,166,0.6)",
                fontFamily: "'JetBrains Mono', monospace",
              }}>{s.machine_count} machine{s.machine_count !== 1 ? "s" : ""}</span>
            </div>
            <button
              onClick={() => handleDelete(s.id, s.name)}
              style={{
                padding: "6px 14px", background: "rgba(244,63,94,0.1)",
                border: "1px solid rgba(244,63,94,0.3)", borderRadius: "6px",
                color: "#f43f5e", fontSize: "12px", fontWeight: 600, cursor: "pointer",
                fontFamily: "'Cabinet Grotesk', sans-serif",
              }}
            >Delete</button>
          </div>
        ))}
      </div>
    </div>
  );
}
SITESJSXEOF
echo "Created pages/Sites.jsx"

echo ""
echo "=================================================================="
echo "PART D — PATCH Fleet.jsx (import, state, sites fetch, handleApprove, install-command dropdown, pending-row dropdown)"
echo "=================================================================="
python3 - << 'PYEOF'
path = "/home/aadi/Desktop/jenix/dashboard/src/pages/Fleet.jsx"
src = open(path).read()

# 1. import getSites
anchor1 = 'import { getFleetOverview, getAllAlerts, markAllRead, fleetCommand, getSavings, getPendingMachines, getInstallCommand, approveMachine, rejectMachine } from "../api";'
assert src.count(anchor1) == 1, f"anchor1 matched {src.count(anchor1)} times"
new1 = 'import { getFleetOverview, getAllAlerts, markAllRead, fleetCommand, getSavings, getPendingMachines, getInstallCommand, approveMachine, rejectMachine, getSites } from "../api";'
src = src.replace(anchor1, new1, 1)

# 2. add state after installCmd state
anchor2 = '  const [installCmd,  setInstallCmd]  = useState(null);'
assert src.count(anchor2) == 1, f"anchor2 matched {src.count(anchor2)} times"
new2 = anchor2 + '''
  const [sites,        setSites]        = useState([]);
  const [installSiteId, setInstallSiteId] = useState("");
  const [pendingSiteSelections, setPendingSiteSelections] = useState({});'''
src = src.replace(anchor2, new2, 1)

# 3. fetch sites alongside pending fetch
anchor3 = '      getPendingMachines().then(r => setPending(r.data || [])).catch(() => {});'
assert src.count(anchor3) == 1, f"anchor3 matched {src.count(anchor3)} times"
new3 = anchor3 + '\n      getSites().then(r => setSites(r.data || [])).catch(() => {});'
src = src.replace(anchor3, new3, 1)

# 4. handleApprove passes site_id
anchor4 = '''  const handleApprove = async (id, hostname) => {
    try {
      await approveMachine(id);
      setPending(p => p.filter(m => m.id !== id));
      showToast(`${hostname} approved`, "success");
    } catch (e) {
      showToast(e.response?.data?.detail || e.message, "error");
    }
  };'''
assert src.count(anchor4) == 1, f"anchor4 matched {src.count(anchor4)} times"
new4 = '''  const handleApprove = async (id, hostname) => {
    try {
      await approveMachine(id, pendingSiteSelections[id] || undefined);
      setPending(p => p.filter(m => m.id !== id));
      showToast(`${hostname} approved`, "success");
    } catch (e) {
      showToast(e.response?.data?.detail || e.message, "error");
    }
  };'''
src = src.replace(anchor4, new4, 1)

# 5. handleShowInstall + new fetchInstallCommand helper
anchor5 = '''  const handleShowInstall = async () => {
    if (showInstall) { setShowInstall(false); return; }
    try {
      const r = await getInstallCommand();
      setInstallCmd(r.data);
      setShowInstall(true);
    } catch (e) {
      showToast(e.response?.data?.detail || e.message, "error");
    }
  };'''
assert src.count(anchor5) == 1, f"anchor5 matched {src.count(anchor5)} times"
new5 = '''  const fetchInstallCommand = async (siteId) => {
    try {
      const r = await getInstallCommand(siteId || undefined);
      setInstallCmd(r.data);
    } catch (e) {
      showToast(e.response?.data?.detail || e.message, "error");
    }
  };

  const handleShowInstall = async () => {
    if (showInstall) { setShowInstall(false); return; }
    await fetchInstallCommand(installSiteId);
    setShowInstall(true);
  };'''
src = src.replace(anchor5, new5, 1)

# 6. install command panel: add site dropdown before the code box
anchor6 = '''          }}>Run this on the target machine</div>
          <div style={{
            display: "flex", alignItems: "center", gap: "10px",
            background: "#060812", border: "1px solid rgba(255,255,255,0.08)",'''
assert src.count(anchor6) == 1, f"anchor6 matched {src.count(anchor6)} times"
new6 = '''          }}>Run this on the target machine</div>
          <select
            value={installSiteId}
            onChange={e => { const v = e.target.value; setInstallSiteId(v); fetchInstallCommand(v); }}
            style={{
              padding: "6px 10px", marginBottom: "10px",
              background: "#0c1220", border: "1px solid rgba(255,255,255,0.1)",
              borderRadius: "6px", color: "#e8f0fe", fontSize: "12px",
              fontFamily: "'Cabinet Grotesk', sans-serif",
            }}
          >
            <option value="">No site</option>
            {sites.map(s => (
              <option key={s.id} value={s.id}>{s.name}</option>
            ))}
          </select>
          <div style={{
            display: "flex", alignItems: "center", gap: "10px",
            background: "#060812", border: "1px solid rgba(255,255,255,0.08)",'''
src = src.replace(anchor6, new6, 1)

# 7. pending row: add site dropdown before Approve button
anchor7 = '''                <div style={{ display: "flex", gap: "8px" }}>
                  <button
                    onClick={() => handleApprove(m.id, m.hostname)}'''
assert src.count(anchor7) == 1, f"anchor7 matched {src.count(anchor7)} times"
new7 = '''                <div style={{ display: "flex", gap: "8px", alignItems: "center" }}>
                  <select
                    value={pendingSiteSelections[m.id] || ""}
                    onChange={e => setPendingSiteSelections(p => ({ ...p, [m.id]: e.target.value }))}
                    style={{
                      padding: "5px 8px", background: "#0c1220",
                      border: "1px solid rgba(255,255,255,0.1)",
                      borderRadius: "6px", color: "#e8f0fe",
                      fontSize: "11px", fontFamily: "'Cabinet Grotesk', sans-serif",
                    }}
                  >
                    <option value="">No site</option>
                    {sites.map(s => (
                      <option key={s.id} value={s.id}>{s.name}</option>
                    ))}
                  </select>
                  <button
                    onClick={() => handleApprove(m.id, m.hostname)}'''
src = src.replace(anchor7, new7, 1)

open(path, "w").write(src)
print("Fleet.jsx patched: all 7 anchors matched exactly once")
PYEOF

echo "--- re-verify ---"
grep -c "getSites" "$SRC/pages/Fleet.jsx"
grep -c "pendingSiteSelections" "$SRC/pages/Fleet.jsx"
grep -c "fetchInstallCommand" "$SRC/pages/Fleet.jsx"
grep -c "installSiteId" "$SRC/pages/Fleet.jsx"

echo ""
echo "=================================================================="
echo "PART E — PATCH Sidebar.jsx (add Sites nav item to Operations group)"
echo "=================================================================="
python3 - << 'PYEOF'
path = "/home/aadi/Desktop/jenix/dashboard/src/components/Sidebar.jsx"
src = open(path).read()

anchor = '''      { path: "/",        label: "Fleet Command",  icon: "◈", badge: null },
      { path: "/overview",label: "All Machines",   icon: "⬡", badge: null },
      { path: "/uptime",  label: "Uptime Monitor", icon: "◎", badge: null },
    ]
  },'''
assert src.count(anchor) == 1, f"anchor matched {src.count(anchor)} times"
new = '''      { path: "/",        label: "Fleet Command",  icon: "◈", badge: null },
      { path: "/overview",label: "All Machines",   icon: "⬡", badge: null },
      { path: "/uptime",  label: "Uptime Monitor", icon: "◎", badge: null },
      { path: "/sites",   label: "Sites",          icon: "▣", badge: null },
    ]
  },'''
src = src.replace(anchor, new, 1)

open(path, "w").write(src)
print("Sidebar.jsx patched: 1/1 anchor matched exactly once")
PYEOF

echo "--- re-verify ---"
grep -c 'path: "/sites"' "$SRC/components/Sidebar.jsx"

echo ""
echo "=================================================================="
echo "PART F — PATCH App.jsx (import + route)"
echo "=================================================================="
python3 - << 'PYEOF'
path = "/home/aadi/Desktop/jenix/dashboard/src/App.jsx"
src = open(path).read()

anchor1 = 'import Uptime     from "./pages/Uptime";'
assert src.count(anchor1) == 1, f"anchor1 matched {src.count(anchor1)} times"
src = src.replace(anchor1, anchor1 + '\nimport Sites      from "./pages/Sites";', 1)

anchor2 = '''            <Route path="/uptime" element={
              <Protected><Layout><Uptime /></Layout></Protected>
            }/>'''
assert src.count(anchor2) == 1, f"anchor2 matched {src.count(anchor2)} times"
new2 = anchor2 + '''
            <Route path="/sites" element={
              <Protected><Layout><Sites /></Layout></Protected>
            }/>'''
src = src.replace(anchor2, new2, 1)

open(path, "w").write(src)
print("App.jsx patched: 2/2 anchors matched exactly once")
PYEOF

echo "--- re-verify ---"
grep -c 'import Sites' "$SRC/App.jsx"
grep -c '"/sites"' "$SRC/App.jsx"

echo ""
echo "=================================================================="
echo "PART G — BUILD (real react-scripts build, will show real errors if any anchor produced broken JSX)"
echo "=================================================================="
cd "$DASH"
npm run build 2>&1 | tail -60

echo ""
echo "=================================================================="
echo "PART H — DEPLOY build output to server/static (real swap, backed up first)"
echo "=================================================================="
if [ -d "$SERVER_DIR/static" ]; then
    cp -r "$SERVER_DIR/static" "$SERVER_DIR/static.bak_sites_${TS}"
    echo "Backed up old static/ to static.bak_sites_${TS}"
fi
rm -rf "$SERVER_DIR/static"/*
cp -r "$DASH/build"/* "$SERVER_DIR/static"/
echo "Deployed new build into server/static/"

echo ""
echo "--- verify: real curl of /dashboard/sites returns 200 (SPA fallback should serve index.html) ---"
curl -s -m 5 -o /dev/null -w "GET /sites http_code: %{http_code}\n" http://localhost:8000/sites
curl -s -m 5 -o /dev/null -w "GET /health http_code: %{http_code}\n" http://localhost:8000/health
