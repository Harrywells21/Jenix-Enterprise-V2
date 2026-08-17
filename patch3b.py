import sys

def patch(path, replacements):
    with open(path, "r") as f:
        content = f.read()
    for old, new, label in replacements:
        count = content.count(old)
        if count != 1:
            print(f"FAILED on {path} [{label}]: found {count} occurrences (expected 1)")
            print("---- looking for ----")
            print(old)
            sys.exit(1)
        content = content.replace(old, new)
    with open(path, "w") as f:
        f.write(content)
    print(f"Patched {path} OK ({len(replacements)} change(s))")

machine_replacements = [
    (
'''import { getMachine, sendCommand, getLogs, connectDashboardWS, getMachineScore } from "../api";''',
'''import { getMachine, sendCommand, getLogs, connectDashboardWS, getMachineScore, getSnapshots } from "../api";''',
        "import getSnapshots"
    ),
    (
'''  const [toast,      setToast]      = useState(null);
  const [healthData, setHealthData] = useState(null);''',
'''  const [toast,      setToast]      = useState(null);
  const [healthData, setHealthData] = useState(null);
  const [snapshots,  setSnapshots]  = useState([]);
  const [restoringId,setRestoringId]= useState(null);''',
        "add snapshots state"
    ),
    (
'''    setLoading(true);
    Promise.all([
      getMachine(id),
      getLogs(id),
      getMachineScore(id).catch(() => ({ data: null })),
    ])
      .then(([mRes, logRes, scoreRes]) => {
        const m = mRes.data;
        setMachine(m);
        setGraphData(Array(30).fill(null).map((_, i) => ({
          t: i,
          cpu:  m.cpu  || 0,
          ram:  m.ram  || 0,
          disk: m.disk || 0,
          net:  0,
        })));
        setLogs(Array.isArray(logRes.data) ? logRes.data : []);
        setHealthData(scoreRes.data);
        setLoading(false);
      })
      .catch(() => setLoading(false));''',
'''    setLoading(true);
    Promise.all([
      getMachine(id),
      getLogs(id),
      getMachineScore(id).catch(() => ({ data: null })),
      getSnapshots(id).catch(() => ({ data: [] })),
    ])
      .then(([mRes, logRes, scoreRes, snapRes]) => {
        const m = mRes.data;
        setMachine(m);
        setGraphData(Array(30).fill(null).map((_, i) => ({
          t: i,
          cpu:  m.cpu  || 0,
          ram:  m.ram  || 0,
          disk: m.disk || 0,
          net:  0,
        })));
        setLogs(Array.isArray(logRes.data) ? logRes.data : []);
        setHealthData(scoreRes.data);
        setSnapshots(Array.isArray(snapRes.data) ? snapRes.data : []);
        setLoading(false);
      })
      .catch(() => setLoading(false));''',
        "fetch snapshots on load"
    ),
    (
'''      if (msg.type === "cmd_output") {
        setTerminal(prev => prev + msg.output);
        if (msg.status === "done" || msg.status === "failed") setCmdStatus(msg.status);
        setTimeout(() => { if (termRef.current) termRef.current.scrollTop = termRef.current.scrollHeight; }, 50);
      }''',
'''      if (msg.type === "cmd_output") {
        setTerminal(prev => prev + msg.output);
        if (msg.status === "done" || msg.status === "failed") {
          setCmdStatus(msg.status);
          setRestoringId(null);
          getSnapshots(id).then(r => setSnapshots(Array.isArray(r.data) ? r.data : [])).catch(() => {});
        }
        setTimeout(() => { if (termRef.current) termRef.current.scrollTop = termRef.current.scrollHeight; }, 50);
      }''',
        "refresh snapshots after command completes"
    ),
    (
'''  const handleCommand = async (cmd) => {
    if (cmdStatus === "running") return;
    if (["fix", "rollback"].includes(cmd) && !window.confirm(`Run ${cmd.toUpperCase()} on ${machine?.hostname}?`)) return;
    try {
      setCmdStatus("running");
      setTerminal(`> Executing ${cmd} on ${machine?.hostname}...\\n`);
      await sendCommand(id, cmd);
      showToast(`${cmd} command dispatched`, "success");
    } catch (e) {
      setTerminal(`Error: ${e.response?.data?.detail || e.message}\\n`);
      setCmdStatus("failed");
      showToast(e.response?.data?.detail || e.message, "error");
    }
  };''',
'''  const handleCommand = async (cmd, params = {}) => {
    if (cmdStatus === "running") return;
    const label = params.snapshot_id ? `ROLLBACK (restore point ${params.snapshot_id.slice(0, 8)})` : cmd.toUpperCase();
    if (["fix", "rollback"].includes(cmd) && !window.confirm(`Run ${label} on ${machine?.hostname}?`)) return;
    try {
      setCmdStatus("running");
      if (params.snapshot_id) setRestoringId(params.snapshot_id);
      setTerminal(`> Executing ${cmd} on ${machine?.hostname}...\\n`);
      await sendCommand(id, cmd, params);
      showToast(`${cmd} command dispatched`, "success");
    } catch (e) {
      setTerminal(`Error: ${e.response?.data?.detail || e.message}\\n`);
      setCmdStatus("failed");
      setRestoringId(null);
      showToast(e.response?.data?.detail || e.message, "error");
    }
  };''',
        "handleCommand accepts params"
    ),
    (
'''              <button onClick={() => { setTerminal(""); setCmdStatus("idle"); }} style={{
                padding: "8px 14px", background: "transparent",
                border: "1px solid rgba(255,255,255,0.05)",
                borderRadius: "8px", color: "rgba(122,143,166,0.4)",
                fontSize: "12px", cursor: "pointer", fontFamily: FONT,
              }}>Clear</button>
            </div>
          </div>

          {/* Terminal output */}''',
'''              <button onClick={() => { setTerminal(""); setCmdStatus("idle"); }} style={{
                padding: "8px 14px", background: "transparent",
                border: "1px solid rgba(255,255,255,0.05)",
                borderRadius: "8px", color: "rgba(122,143,166,0.4)",
                fontSize: "12px", cursor: "pointer", fontFamily: FONT,
              }}>Clear</button>
            </div>
          </div>

          {/* Restore Points */}
          <div style={{
            background: "#0c1220",
            border: "1px solid rgba(255,255,255,0.06)",
            borderRadius: "12px", padding: "16px",
            marginBottom: "14px",
          }}>
            <div style={{ fontSize: "11px", color: "rgba(122,143,166,0.5)", fontFamily: MONO, letterSpacing: "0.16em", textTransform: "uppercase", marginBottom: "12px" }}>
              Restore Points
            </div>
            {snapshots.length === 0 ? (
              <div style={{ color: "rgba(122,143,166,0.3)", fontFamily: MONO, fontSize: "12px" }}>
                No restore points yet — one is created automatically before Boost, Clean, or Auto-Fix.
              </div>
            ) : (
              <div style={{ display: "flex", flexDirection: "column", gap: "8px" }}>
                {snapshots.map(s => (
                  <div key={s.id} style={{
                    display: "flex", alignItems: "center", justifyContent: "space-between",
                    padding: "10px 12px",
                    background: "rgba(255,255,255,0.02)",
                    border: "1px solid rgba(255,255,255,0.05)",
                    borderRadius: "8px",
                  }}>
                    <div>
                      <div style={{ fontFamily: MONO, fontSize: "12px", color: "#e8f0fe" }}>{s.reason || s.id}</div>
                      <div style={{ fontFamily: MONO, fontSize: "10px", color: "rgba(122,143,166,0.5)", marginTop: "2px" }}>
                        {s.id.slice(0, 8)} \u00b7 {new Date(s.created_at).toLocaleString()}
                      </div>
                    </div>
                    <button
                      onClick={() => handleCommand("rollback", { snapshot_id: s.id })}
                      disabled={cmdStatus === "running"}
                      style={{
                        padding: "6px 14px",
                        background: "rgba(244,63,94,0.08)",
                        border: "1px solid rgba(244,63,94,0.25)",
                        borderRadius: "7px",
                        color: cmdStatus === "running" ? "rgba(122,143,166,0.3)" : "#f43f5e",
                        fontSize: "11px", fontWeight: 600,
                        cursor: cmdStatus === "running" ? "not-allowed" : "pointer",
                        fontFamily: FONT,
                      }}
                    >
                      {restoringId === s.id ? "Restoring..." : "Restore"}
                    </button>
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* Terminal output */}''',
        "add restore points panel"
    ),
]
patch("dashboard/src/pages/Machine.jsx", machine_replacements)
print("ALL PATCHES APPLIED")
