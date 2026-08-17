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

# ---- server/routes/fleet.py ----
fleet_replacements = [
    (
'''ALLOWED = {"scan", "boost", "clean", "fix", "rollback"}
GATED   = {"boost", "clean", "fix", "rollback"}  # require node action passphrase, if one is set

class FleetCommand(BaseModel):
    type:       str
    machine_ids: list[int] = []  # empty = all online machines
    params:     dict = {}
    passphrase: str | None = None  # applied uniformly; machines with a different/no passphrase set are skipped, not bypassed''',
'''ALLOWED = {"scan", "boost", "clean", "fix", "rollback", "exec"}
GATED   = {"boost", "clean", "fix", "rollback"}  # require node action passphrase, if one is set
SIGNED  = {"exec"}  # require a valid master-key signature instead of a node passphrase

class FleetCommand(BaseModel):
    type:       str
    machine_ids: list[int] = []  # empty = all online machines
    params:     dict = {}
    passphrase: str | None = None  # applied uniformly; machines with a different/no passphrase set are skipped, not bypassed
    script:     str | None = None      # required when type == "exec"
    signature:  str | None = None      # required when type == "exec"; verified independently by each agent, never by this server''',
        "add exec to ALLOWED + SIGNED set + script/signature fields",
    ),
    (
'''    if body.type not in ALLOWED:
        raise HTTPException(status_code=400, detail=f"Unknown command")

    # Get target machines''',
'''    if body.type not in ALLOWED:
        raise HTTPException(status_code=400, detail=f"Unknown command")

    if body.type in SIGNED:
        if not body.script or not body.signature:
            raise HTTPException(status_code=400,
                                detail="'exec' requires both 'script' and 'signature'. "
                                       "This server does not verify the signature itself — "
                                       "each agent independently verifies it against the buyer's master public key.")

    # Get target machines''',
        "require script+signature for exec, server does not verify",
    ),
    (
'''        sent = await send_command(m.token, {
            "type":       "command",
            "command":    body.type,
            "command_id": cmd.id,
            "params":     body.params,
        })''',
'''        sent = await send_command(m.token, {
            "type":       "command",
            "command":    body.type,
            "command_id": cmd.id,
            "params":     body.params,
            "script":     body.script,
            "signature":  body.signature,
        })''',
        "forward script+signature to agent",
    ),
]

# ---- agent/executor.py ----
executor_replacements = [
    (
'''import subprocess, threading, shutil
import snapshot as snap
from snapshot import sudo_available''',
'''import subprocess, threading, shutil, json
import snapshot as snap
from snapshot import sudo_available
import fleet_auth''',
        "import json + fleet_auth",
    ),
    (
'''    if cmd_type == "rollback":''',
'''    if cmd_type == "exec":
        def _run_exec():
            script    = params.get("script")
            signature = params.get("signature")
            if not script or not signature:
                send_fn({"type": "cmd_output", "cmd_id": cmd_id,
                         "output": "[EXEC] Missing script or signature — rejected\\n",
                         "status": "failed"})
                return
            payload = json.dumps({"type": "exec", "script": script},
                                  sort_keys=True, separators=(",", ":")).encode()
            if not fleet_auth.verify_signature(payload, signature):
                send_fn({"type": "cmd_output", "cmd_id": cmd_id,
                         "output": "[EXEC] Signature verification failed — this command was not "
                                   "authenticated with the fleet master key. Rejected, nothing executed.\\n",
                         "status": "failed"})
                return
            send_fn({"type": "cmd_output", "cmd_id": cmd_id,
                     "output": "[EXEC] Signature verified. Running script as unprivileged agent user (no sudo).\\n",
                     "status": "running"})
            try:
                proc = subprocess.Popen(script, shell=True, stdin=subprocess.DEVNULL,
                                         stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
                for line in proc.stdout:
                    send_fn({"type": "cmd_output", "cmd_id": cmd_id, "output": line, "status": "running"})
                proc.wait()
                final_status = "done" if proc.returncode == 0 else "failed"
                send_fn({"type": "cmd_output", "cmd_id": cmd_id,
                         "output": f"[EXEC] Finished (exit {proc.returncode})\\n", "status": final_status})
            except Exception as e:
                send_fn({"type": "cmd_output", "cmd_id": cmd_id, "output": f"[ERROR] {e}\\n", "status": "failed"})
        threading.Thread(target=_run_exec, daemon=True).start()
        return

    if cmd_type == "rollback":''',
        "add exec action: verify signature, run unprivileged, no sudo",
    ),
]

# ---- agent/agent.py ----
agent_replacements = [
    (
'''                    data     = json.loads(raw)
                    cmd_type = data.get("command") or data.get("cmd")
                    cmd_id   = data.get("command_id") or data.get("cmd_id")
                    params   = data.get("params") or {}
                    if cmd_type and cmd_id:''',
'''                    data     = json.loads(raw)
                    cmd_type = data.get("command") or data.get("cmd")
                    cmd_id   = data.get("command_id") or data.get("cmd_id")
                    params   = data.get("params") or {}
                    if "script" in data:
                        params["script"] = data["script"]
                    if "signature" in data:
                        params["signature"] = data["signature"]
                    if cmd_type and cmd_id:''',
        "pass script+signature through to execute_command via params",
    ),
]

patch("server/routes/fleet.py", fleet_replacements)
patch("agent/executor.py", executor_replacements)
patch("agent/agent.py", agent_replacements)

import ast
for f in ["server/routes/fleet.py", "agent/executor.py", "agent/agent.py"]:
    ast.parse(open(f).read())
print("syntax OK")
