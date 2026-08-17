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

# ---- dashboard/src/api/index.js ----
api_replacements = [
    (
'''export const sendCommand      = (id, type, params = {}) => api.post(`/api/machines/${id}/command`, { type, params });
export const getCommandStatus = (id, cid)   => api.get(`/api/machines/${id}/command/${cid}`);
export const getSnapshots     = (id)        => api.get(`/api/machines/${id}/snapshots`);''',
'''export const sendCommand      = (id, type, params = {}, passphrase = null) =>
  api.post(`/api/machines/${id}/command`, { type, params, passphrase });
export const getCommandStatus = (id, cid)   => api.get(`/api/machines/${id}/command/${cid}`);
export const getSnapshots     = (id)        => api.get(`/api/machines/${id}/snapshots`);
export const setNodePassphrase   = (id, passphrase) => api.post(`/api/machines/${id}/passphrase`, { passphrase });
export const clearNodePassphrase = (id)             => api.delete(`/api/machines/${id}/passphrase`);
export const getPassphraseStatus = (id)             => api.get(`/api/machines/${id}/passphrase-status`);''',
        "sendCommand accepts passphrase + new passphrase API functions"
    ),
]
patch("dashboard/src/api/index.js", api_replacements)

# ---- dashboard/src/pages/Machine.jsx ----
machine_replacements = [
    (
'''import { getMachine, sendCommand, getLogs, connectDashboardWS, getMachineScore, getSnapshots } from "../api";''',
'''import { getMachine, sendCommand, getLogs, connectDashboardWS, getMachineScore, getSnapshots, setNodePassphrase, clearNodePassphrase, getPassphraseStatus } from "../api";''',
        "import passphrase API functions"
    ),
    (
'''  const [snapshots,  setSnapshots]  = useState([]);
  const [restoringId,setRestoringId]= useState(null);''',
'''  const [snapshots,  setSnapshots]  = useState([]);
  const [restoringId,setRestoringId]= useState(null);
  const [passphraseSet, setPassphraseSet] = useState(false);
  const [pendingAction, setPendingAction] = useState(null); // { cmd, params, label }
  const [modalPassphrase, setModalPassphrase] = useState("");
  const [modalError, setModalError] = useState("");
  const [showSetPassModal, setShowSetPassModal] = useState(false);
  const [newPassphrase, setNewPassphrase] = useState("");''',
        "add passphrase-related state"
    ),
    (
'''      getSnapshots(id).catch(() => ({ data: [] })),
    ])
      .then(([mRes, logRes, scoreRes, snapRes]) => {''',
'''      getSnapshots(id).catch(() => ({ data: [] })),
      getPassphraseStatus(id).catch(() => ({ data: { is_set: false } })),
    ])
      .then(([mRes, logRes, scoreRes, snapRes, passRes]) => {''',
        "fetch passphrase status on load"
    ),
    (
'''        setSnapshots(Array.isArray(snapRes.data) ? snapRes.data : []);
        setLoading(false);
      })
      .catch(() => setLoading(false));''',
'''        setSnapshots(Array.isArray(snapRes.data) ? snapRes.data : []);
        setPassphraseSet(!!passRes.data?.is_set);
        setLoading(false);
      })
      .catch(() => setLoading(false));''',
        "store passphrase status"
    ),
    (
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
'''  const GATED_COMMANDS = ["boost", "clean", "fix", "rollback"];

  const handleCommand = async (cmd, params = {}) => {
    if (cmdStatus === "running") return;
    const label = params.snapshot_id ? `ROLLBACK (restore point ${params.snapshot_id.slice(0, 8)})` : cmd.toUpperCase();
    if (GATED_COMMANDS.includes(cmd) && passphraseSet) {
      setModalError("");
      setModalPassphrase("");
      setPendingAction({ cmd, params, label });
      return;
    }
    await dispatchCommand(cmd, params, label, null);
  };

  const dispatchCommand = async (cmd, params, label, passphrase) => {
    try {
      setCmdStatus("running");
      if (params.snapshot_id) setRestoringId(params.snapshot_id);
      setTerminal(`> Executing ${cmd} on ${machine?.hostname}...\\n`);
      await sendCommand(id, cmd, params, passphrase);
      showToast(`${cmd} command dispatched`, "success");
    } catch (e) {
      setTerminal(`Error: ${e.response?.data?.detail || e.message}\\n`);
      setCmdStatus("failed");
      setRestoringId(null);
      showToast(e.response?.data?.detail || e.message, "error");
    }
  };

  const confirmPendingAction = async () => {
    if (!modalPassphrase) { setModalError("Enter the node passphrase"); return; }
    const { cmd, params, label } = pendingAction;
    setPendingAction(null);
    await dispatchCommand(cmd, params, label, modalPassphrase);
  };

  const handleSetPassphrase = async () => {
    if (newPassphrase.length < 8) { showToast("Passphrase must be at least 8 characters", "error"); return; }
    try {
      await setNodePassphrase(id, newPassphrase);
      setPassphraseSet(true);
      setShowSetPassModal(false);
      setNewPassphrase("");
      showToast("Node passphrase set", "success");
    } catch (e) {
      showToast(e.response?.data?.detail || e.message, "error");
    }
  };

  const handleClearPassphrase = async () => {
    if (!window.confirm(`Remove the action passphrase for ${machine?.hostname}? Boost/Clean/Auto-Fix/Rollback will no longer require it.`)) return;
    try {
      await clearNodePassphrase(id);
      setPassphraseSet(false);
      showToast("Node passphrase removed", "success");
    } catch (e) {
      showToast(e.response?.data?.detail || e.message, "error");
    }
  };''',
        "replace window.confirm flow with passphrase modal flow"
    ),
    (
'''              <div style={{ fontSize: "11px", color: "rgba(122,143,166,0.5)", fontFamily: MONO, letterSpacing: "0.16em", textTransform: "uppercase" }}>
                Remote Execution
              </div>
              <div style={{
                fontSize: "10px", fontFamily: MONO, letterSpacing: "0.08em",
                color: cmdStatus === "running" ? "#f59e0b" : cmdStatus === "done" ? "#10b981" : cmdStatus === "failed" ? "#f43f5e" : "rgba(122,143,166,0.3)",
                display: "flex", alignItems: "center", gap: "5px",
              }}>''',
'''              <div style={{ fontSize: "11px", color: "rgba(122,143,166,0.5)", fontFamily: MONO, letterSpacing: "0.16em", textTransform: "uppercase" }}>
                Remote Execution
              </div>
              <div style={{ display: "flex", alignItems: "center", gap: "12px" }}>
              <button onClick={() => passphraseSet ? handleClearPassphrase() : setShowSetPassModal(true)} style={{
                background: "none", border: "none", cursor: "pointer",
                fontSize: "10px", fontFamily: MONO, letterSpacing: "0.06em",
                color: passphraseSet ? "#10b981" : "rgba(122,143,166,0.4)",
                display: "flex", alignItems: "center", gap: "5px", padding: "0",
              }}>
                {passphraseSet ? "\\ud83d\\udd12 PASSPHRASE SET (click to remove)" : "\\ud83d\\udd13 Set node passphrase"}
              </button>
              <div style={{
                fontSize: "10px", fontFamily: MONO, letterSpacing: "0.08em",
                color: cmdStatus === "running" ? "#f59e0b" : cmdStatus === "done" ? "#10b981" : cmdStatus === "failed" ? "#f43f5e" : "rgba(122,143,166,0.3)",
                display: "flex", alignItems: "center", gap: "5px",
              }}>''',
        "add set/clear passphrase control to Remote Execution header"
    ),
    (
'''            {terminal || (
              <span style={{ color: "rgba(16,185,129,0.4)" }}>
                \\u25ca Ready. Select a command above to execute remotely.
              </span>
            )}
          </div>
        </div>
      )}''',
'''            {terminal || (
              <span style={{ color: "rgba(16,185,129,0.4)" }}>
                \\u25ca Ready. Select a command above to execute remotely.
              </span>
            )}
          </div>
        </div>
      )}

      {/* Passphrase confirm modal (gated commands) */}
      {pendingAction && (
        <div style={{
          position: "fixed", inset: 0, background: "rgba(0,0,0,0.6)",
          display: "flex", alignItems: "center", justifyContent: "center", zIndex: 10000,
        }} onClick={() => setPendingAction(null)}>
          <div onClick={e => e.stopPropagation()} style={{
            background: "#0c1220", border: "1px solid rgba(244,63,94,0.3)",
            borderRadius: "14px", padding: "24px", width: "360px",
            fontFamily: FONT,
          }}>
            <div style={{ fontSize: "13px", fontWeight: 700, color: "#e8f0fe", marginBottom: "8px" }}>
              Confirm: {pendingAction.label}
            </div>
            <div style={{ fontSize: "12px", color: "rgba(122,143,166,0.6)", marginBottom: "14px" }}>
              This node requires its action passphrase to run {pendingAction.cmd}.
            </div>
            <input
              type="password"
              autoFocus
              value={modalPassphrase}
              onChange={e => { setModalPassphrase(e.target.value); setModalError(""); }}
              onKeyDown={e => e.key === "Enter" && confirmPendingAction()}
              placeholder="Node passphrase"
              style={{
                width: "100%", padding: "10px 12px", boxSizing: "border-box",
                background: "#040810", border: `1px solid ${modalError ? "#f43f5e" : "rgba(255,255,255,0.1)"}`,
                borderRadius: "8px", color: "#e8f0fe", fontFamily: MONO, fontSize: "13px",
                marginBottom: "6px",
              }}
            />
            {modalError && <div style={{ fontSize: "11px", color: "#f43f5e", marginBottom: "10px" }}>{modalError}</div>}
            <div style={{ display: "flex", gap: "8px", marginTop: "14px" }}>
              <button onClick={() => setPendingAction(null)} style={{
                flex: 1, padding: "9px", background: "transparent",
                border: "1px solid rgba(255,255,255,0.1)", borderRadius: "8px",
                color: "rgba(122,143,166,0.7)", fontSize: "12px", cursor: "pointer", fontFamily: FONT,
              }}>Cancel</button>
              <button onClick={confirmPendingAction} style={{
                flex: 1, padding: "9px", background: "rgba(244,63,94,0.12)",
                border: "1px solid rgba(244,63,94,0.4)", borderRadius: "8px",
                color: "#f43f5e", fontSize: "12px", fontWeight: 600, cursor: "pointer", fontFamily: FONT,
              }}>Confirm</button>
            </div>
          </div>
        </div>
      )}

      {/* Set node passphrase modal */}
      {showSetPassModal && (
        <div style={{
          position: "fixed", inset: 0, background: "rgba(0,0,0,0.6)",
          display: "flex", alignItems: "center", justifyContent: "center", zIndex: 10000,
        }} onClick={() => setShowSetPassModal(false)}>
          <div onClick={e => e.stopPropagation()} style={{
            background: "#0c1220", border: "1px solid rgba(56,189,248,0.3)",
            borderRadius: "14px", padding: "24px", width: "360px",
            fontFamily: FONT,
          }}>
            <div style={{ fontSize: "13px", fontWeight: 700, color: "#e8f0fe", marginBottom: "8px" }}>
              Set Node Action Passphrase
            </div>
            <div style={{ fontSize: "12px", color: "rgba(122,143,166,0.6)", marginBottom: "14px" }}>
              Required going forward to run Boost, Clean, Auto-Fix, or Rollback on {machine?.hostname}. Minimum 8 characters.
            </div>
            <input
              type="password"
              autoFocus
              value={newPassphrase}
              onChange={e => setNewPassphrase(e.target.value)}
              onKeyDown={e => e.key === "Enter" && handleSetPassphrase()}
              placeholder="New passphrase"
              style={{
                width: "100%", padding: "10px 12px", boxSizing: "border-box",
                background: "#040810", border: "1px solid rgba(255,255,255,0.1)",
                borderRadius: "8px", color: "#e8f0fe", fontFamily: MONO, fontSize: "13px",
              }}
            />
            <div style={{ display: "flex", gap: "8px", marginTop: "14px" }}>
              <button onClick={() => setShowSetPassModal(false)} style={{
                flex: 1, padding: "9px", background: "transparent",
                border: "1px solid rgba(255,255,255,0.1)", borderRadius: "8px",
                color: "rgba(122,143,166,0.7)", fontSize: "12px", cursor: "pointer", fontFamily: FONT,
              }}>Cancel</button>
              <button onClick={handleSetPassphrase} style={{
                flex: 1, padding: "9px", background: "rgba(56,189,248,0.12)",
                border: "1px solid rgba(56,189,248,0.4)", borderRadius: "8px",
                color: "#38bdf8", fontSize: "12px", fontWeight: 600, cursor: "pointer", fontFamily: FONT,
              }}>Set Passphrase</button>
            </div>
          </div>
        </div>
      )}''',
        "add passphrase confirm modal and set-passphrase modal"
    ),
]
patch("dashboard/src/pages/Machine.jsx", machine_replacements)

print("ALL FRONTEND PATCHES APPLIED")
